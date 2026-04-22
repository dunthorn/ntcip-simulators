#!/usr/bin/env python3
"""
NTCIP 1203 v02 DMS SNMP Agent
Implements the Dynamic Message Sign MIB.

Derived from NTCIP 1203 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.

Usage (from the repository root):
    python3 -m ntcip1203_agent.dms_agent [options]

Options:
    --host HOST              Bind address (default: 0.0.0.0)
    --port PORT              UDP/TCP port (default: 1164)
    --community STR          Read-only community  (default: public)
    --write-community STR    Read-write community (default: private)
    --transport MODE         udp | tcp | both     (default: udp)
    --sign-width-px N        Sign width in pixels (default: 96)
    --sign-height-px N       Sign height in pixels (default: 32)
    --changeable N           Number of changeable message slots (default: 10)
    --volatile N             Number of volatile message slots (default: 5)
    --verbose                Debug logging

Requires only the Python standard library.  No third-party packages needed.
"""

import argparse
import logging
import signal
import threading
import time

from ntcip1203_agent.dms_mib_data import DMSDataStore
from ntcip1203_agent.dms_oid_tree  import DMSOIDTree
from common.snmp_server   import SNMPServer
from common.standard_mibs import SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
log = logging.getLogger('ntcip1203_agent')


# ---------------------------------------------------------------------------
# Combined OID tree: standard MIBs + DMS MIB
# ---------------------------------------------------------------------------

class CombinedOIDTree:
    """
    Merges the standard MIBs OID tree with the DMS OID tree into a single
    sorted structure that SNMPServer can query.
    """

    def __init__(self, dms_tree, std_tree=None):
        self._dms = dms_tree
        self._std = std_tree

        entries = list(dms_tree._entries)
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
# Standard MIB tree for DMS
# ---------------------------------------------------------------------------

def _build_std_tree(snmp_mib):
    """Build a standard MIB OID tree for the DMS agent."""
    try:
        from ntcip1202_agent.oid_tree import NativeOIDTree

        class _StdStore:
            pass

        store         = _StdStore()
        store.system  = SystemMIB(hostname=None)
        store.system.sysDescr    = (
            b'NTCIP 1203 v02 Dynamic Message Sign Simulator; Python SNMP Agent'
        )
        store.system.sysObjectID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 3)
        store.system.sysServices = 6
        store.system.sysLocation = b'Freeway / I-10 Eastbound MM 42'

        store.interfaces = InterfacesMIB()
        store.snmp_mib   = snmp_mib
        store.ntcip1201  = NTCIP1201MIB()
        store.ntcip1201.module_table[2] = {
            'moduleNumber':     2,
            'moduleDeviceNode': (1, 3, 6, 1, 4, 1, 1206, 4, 2, 3),
            'moduleMake':       b'Simulator',
            'moduleModel':      b'NTCIP 1203',
            'moduleVersion':    b'02.35',
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
    Background thread that advances DMS simulation state:
      - Photocell / brightness level variation (simulated day/night cycle)
      - Cabinet and ambient temperature drift
      - Message duration expiry
    Ticks every 10 seconds.
    """

    TICK_INTERVAL = 10   # seconds

    def __init__(self, store):
        super().__init__(daemon=True, name='dms-sim')
        self._store   = store
        self._stop_ev = threading.Event()

    def run(self):
        while not self._stop_ev.wait(timeout=self.TICK_INTERVAL):
            try:
                self._store.tick_illumination()
                self._store.tick_status()
                self._store.tick_control()
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
    parser = argparse.ArgumentParser(description='NTCIP 1203 v02 DMS SNMP Agent')
    parser.add_argument('--host',             default='0.0.0.0')
    parser.add_argument('--port',             type=int, default=1164)
    parser.add_argument('--community',        default='public')
    parser.add_argument('--write-community',  default='private', dest='write_community')
    parser.add_argument('--transport',        default='udp',
                        choices=['udp', 'tcp', 'both'])
    parser.add_argument('--sign-width-px',    type=int, default=96,
                        dest='sign_width_px',
                        help='Sign width in pixels (default: 96)')
    parser.add_argument('--sign-height-px',   type=int, default=32,
                        dest='sign_height_px',
                        help='Sign height in pixels (default: 32)')
    parser.add_argument('--changeable',       type=int, default=10,
                        help='Number of changeable message slots (default: 10)')
    parser.add_argument('--volatile',         type=int, default=5,
                        help='Number of volatile message slots (default: 5)')
    parser.add_argument('--config-port',      type=int, default=0, dest='config_port',
                        help='Port for the web config UI (default: 0 = disabled)')
    parser.add_argument('--config-file',      default=None, dest='config_file',
                        help='JSON file to load/save DMS configuration (e.g. dms.json)')
    parser.add_argument('--verbose',          action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("NTCIP 1203 v02 DMS SNMP Agent")
    log.info(f"  Address:         {args.host}:{args.port}/{args.transport}")
    log.info(f"  Read community:  {args.community}")
    log.info(f"  Write community: {args.write_community}")
    log.info(f"  Sign size:       {args.sign_width_px}×{args.sign_height_px} px")
    log.info(f"  Changeable msgs: {args.changeable}")
    log.info(f"  Volatile msgs:   {args.volatile}")
    if args.config_port:
        log.info(f"  Config UI:       http://0.0.0.0:{args.config_port}/")
    if args.config_file:
        log.info(f"  Config file:     {args.config_file}")
    log.info(f"  OID root:        1.3.6.1.4.1.1206.4.2.3")
    log.info("=" * 60)

    # Build DMS data store and OID tree
    dms_store = DMSDataStore(
        sign_width_px=args.sign_width_px,
        sign_height_px=args.sign_height_px,
        num_changeable=args.changeable,
        num_volatile=args.volatile,
    )
    dms_tree = DMSOIDTree(dms_store)

    # Build standard MIBs OID tree
    snmp_mib = SnmpMIB()
    std_tree = _build_std_tree(snmp_mib)

    # Merge into combined tree
    combined = CombinedOIDTree(dms_tree, std_tree)
    log.info(f"  Total OIDs:      {len(combined._entries)}")

    # Log active message info
    log.info(f"  Active message:  (blank — awaiting activation)")

    # Load saved config at startup if specified (even without the UI)
    if args.config_file and not args.config_port:
        from ntcip1203_agent.config_server import _apply_config_dict
        import json, os
        if os.path.exists(args.config_file):
            try:
                with open(args.config_file) as f:
                    _apply_config_dict(dms_store, json.load(f))
                log.info(f"Loaded config from {args.config_file!r}")
            except Exception as ex:
                log.warning(f"Failed to load config: {ex}")

    # Start config UI if requested
    config_srv = None
    if args.config_port:
        from ntcip1203_agent.config_server import ConfigServer
        config_srv = ConfigServer(dms_store, port=args.config_port,
                                  config_file=args.config_file)
        config_srv.start()

    # Start simulation thread
    sim = SimulationThread(dms_store)
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
        if config_srv:
            config_srv.stop()
        sim.stop()
        server.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("DMS agent running. Press Ctrl+C to stop.")
    sim.join()


if __name__ == '__main__':
    main()
