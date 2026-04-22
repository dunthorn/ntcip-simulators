#!/usr/bin/env python3
"""
NTCIP 1207 v02 RMC SNMP Agent
Implements the Ramp Meter Control MIB.

Derived from NTCIP 1207 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.

Usage (from the simulation/ directory):
    python3 -m ntcip1207_agent.rmc_agent [options]

Options:
    --host HOST              Bind address (default: 0.0.0.0)
    --port PORT              UDP/TCP port (default: 1163; use 163 with sudo)
    --community STR          Read-only community  (default: public)
    --write-community STR    Read-write community (default: private)
    --transport MODE         udp | tcp | both     (default: udp)
    --mainline-lanes N       Number of mainline detector lanes (default: 2)
    --metered-lanes N        Number of metered lanes (default: 1)
    --metering-plans N       Number of metering plans (default: 4)
    --verbose                Debug logging

Requires only the Python standard library.  No third-party packages needed.
"""

import argparse
import logging
import signal
import threading
import time

from ntcip1207_agent.rmc_mib_data import RMCDataStore
from ntcip1207_agent.rmc_oid_tree  import RMCOIDTree
from common.snmp_server   import SNMPServer
from common.standard_mibs import SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
log = logging.getLogger('ntcip1207_agent')


# ---------------------------------------------------------------------------
# Combined OID tree: standard MIBs + RMC MIB
# ---------------------------------------------------------------------------

class CombinedOIDTree:
    """
    Merges the standard MIBs OID tree with the RMC OID tree into a single
    sorted structure that the SNMPServer can query.
    """

    def __init__(self, rmc_tree, std_tree=None):
        self._rmc = rmc_tree
        self._std = std_tree

        entries = list(rmc_tree._entries)
        if std_tree is not None:
            entries += list(std_tree._entries)
        entries.sort(key=lambda e: e[0])
        self._entries = entries

    def get(self, oid):
        e = self._lookup(oid)
        if e is None:
            return None
        try:
            return e[1]()
        except Exception as ex:
            log.warning(f"GET {oid}: {ex}")
            return None

    def get_next(self, oid):
        idx = self._next_idx(oid)
        if idx is None:
            return None, None
        e = self._entries[idx]
        try:
            return e[0], e[1]()
        except Exception as ex:
            log.warning(f"GETNEXT {oid}: {ex}")
            return None, None

    def set(self, oid, value):
        e = self._lookup(oid)
        if e is None or e[2] is None:
            return False
        try:
            e[2](value)
            return True
        except Exception as ex:
            log.warning(f"SET {oid}={value}: {ex}")
            return False

    def _lookup(self, oid):
        lo, hi = 0, len(self._entries) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            e   = self._entries[mid]
            if   e[0] == oid: return e
            elif e[0] <  oid: lo = mid + 1
            else:             hi = mid - 1
        return None

    def _next_idx(self, oid):
        lo, hi = 0, len(self._entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._entries[mid][0] <= oid: lo = mid + 1
            else:                            hi = mid
        return lo if lo < len(self._entries) else None


# ---------------------------------------------------------------------------
# Standard MIB tree for RMC
# ---------------------------------------------------------------------------

def _build_std_tree(snmp_mib):
    """Build a standard MIB OID tree for the RMC agent."""
    try:
        from ntcip1202_agent.oid_tree import NativeOIDTree

        class _StdStore:
            pass

        store         = _StdStore()
        store.system  = SystemMIB(hostname=None)
        store.system.sysDescr    = (
            b'NTCIP 1207 v02 Ramp Meter Control Simulator; Python SNMP Agent'
        )
        store.system.sysObjectID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 5)
        store.system.sysServices = 6
        store.system.sysLocation = b'On-Ramp / Freeway Entrance'

        store.interfaces = InterfacesMIB()
        store.snmp_mib   = snmp_mib
        store.ntcip1201  = NTCIP1201MIB()
        store.ntcip1201.module_table[2] = {
            'moduleNumber':     2,
            'moduleDeviceNode': (1, 3, 6, 1, 4, 1, 1206, 4, 2, 5),
            'moduleMake':       b'Simulator',
            'moduleModel':      b'NTCIP 1207',
            'moduleVersion':    b'02.14',
            'moduleType':       1,   # NTCIP
        }

        tree = object.__new__(NativeOIDTree)
        tree.store    = store
        tree._entries = []
        tree._build_standard_mibs()
        tree._entries.sort(key=lambda e: e[0])
        return tree

    except Exception as ex:
        log.warning(f"Could not build standard MIB tree: {ex}")
        return None


# ---------------------------------------------------------------------------
# Simulation tick thread
# ---------------------------------------------------------------------------

class SimulationThread(threading.Thread):
    """
    Background thread that advances the RMC simulation state:
      - mainline detector readings (sinusoidal flow/occ/speed variation)
      - passage detector counts
    Runs at the rmcCalculationInterval rate.
    """

    def __init__(self, store):
        super().__init__(daemon=True, name='rmc-sim')
        self._store   = store
        self._stop_ev = threading.Event()

    def run(self):
        while not self._stop_ev.wait(timeout=self._store.general['rmcCalculationInterval']):
            try:
                self._store.tick_mainline()
                self._store.tick_metered_lanes()
            except Exception as ex:
                log.warning(f"Sim tick error: {ex}")

    def stop(self):
        self._stop_ev.set()

    def join(self, timeout=None):
        self._stop_ev.wait()
        super().join(timeout=timeout)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='NTCIP 1207 v02 RMC SNMP Agent')
    parser.add_argument('--host',            default='0.0.0.0')
    parser.add_argument('--port',            type=int, default=1163)
    parser.add_argument('--community',       default='public')
    parser.add_argument('--write-community', default='private', dest='write_community')
    parser.add_argument('--transport',       default='udp',
                        choices=['udp', 'tcp', 'both'])
    parser.add_argument('--mainline-lanes',  type=int, default=2, dest='mainline_lanes',
                        help='Number of mainline detector lanes (1-8)')
    parser.add_argument('--metered-lanes',   type=int, default=1, dest='metered_lanes',
                        help='Number of metered lanes (1-8)')
    parser.add_argument('--metering-plans',  type=int, default=4, dest='metering_plans',
                        help='Number of metering plans (1-16)')
    parser.add_argument('--verbose',         action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("NTCIP 1207 v02 RMC SNMP Agent")
    log.info(f"  Address:         {args.host}:{args.port}/{args.transport}")
    log.info(f"  Read community:  {args.community}")
    log.info(f"  Write community: {args.write_community}")
    log.info(f"  Mainline lanes:  {args.mainline_lanes}")
    log.info(f"  Metered lanes:   {args.metered_lanes}")
    log.info(f"  Metering plans:  {args.metering_plans}")
    log.info(f"  OID root:        1.3.6.1.4.1.1206.4.2.5")
    log.info("=" * 60)

    # Build RMC data store and OID tree
    rmc_store = RMCDataStore(
        num_mainline_lanes=args.mainline_lanes,
        num_metered_lanes=args.metered_lanes,
        num_metering_plans=args.metering_plans,
    )
    rmc_tree = RMCOIDTree(rmc_store)

    # Build standard MIBs OID tree
    snmp_mib = SnmpMIB()
    std_tree = _build_std_tree(snmp_mib)

    # Merge into combined tree
    combined = CombinedOIDTree(rmc_tree, std_tree)
    log.info(f"  Total OIDs:      {len(combined._entries)}")

    # Start simulation thread
    sim = SimulationThread(rmc_store)
    sim.start()

    # SNMP server
    server = SNMPServer(
        combined,
        host=args.host,
        port=args.port,
        ro_communities=[args.community.encode()],
        rw_communities=[args.write_community.encode()],
        snmp_mib=snmp_mib,
        transport=args.transport,
    )
    server.start()

    def _shutdown(signum, frame):
        log.info("Shutting down...")
        sim.stop()
        server.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("RMC agent running. Press Ctrl+C to stop.")
    sim.join()


if __name__ == '__main__':
    main()
