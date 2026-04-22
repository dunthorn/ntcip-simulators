#!/usr/bin/env python3
"""
NTCIP 1218 v01 RSU SNMP Agent
Implements the Roadside Unit MIB.

Derived from NTCIP 1218 v01. Copyright by AASHTO / ITE / NEMA. Used by permission.

Usage (from the simulation/ directory):
    python3 -m ntcip1218_agent.rsu_agent [options]

Options:
    --host HOST              Bind address (default: 0.0.0.0)
    --port PORT              UDP/TCP port (default: 1162; use 162 with sudo)
    --community STR          Read-only community  (default: public)
    --write-community STR    Read-write community (default: private)
    --asc-host HOST          ASC simulator host for SPaT bridge (default: 127.0.0.1)
    --asc-port PORT          ASC simulator SNMP port (default: 1161)
    --asc-community STR      ASC community string (default: public)
    --lat DEGREES            RSU latitude in decimal degrees (default: 32.729)
    --lon DEGREES            RSU longitude in decimal degrees (default: -97.508)
    --verbose                Debug logging

Requires only the Python standard library.  No third-party packages needed.
"""

import argparse
import logging
import signal
import sys
import time

from ntcip1218_agent.rsu_mib_data import RSUDataStore
from ntcip1218_agent.rsu_oid_tree  import RSUOIDTree
from ntcip1218_agent.spat_bridge   import SPaTBridge
from common.snmp_server   import SNMPServer
from common.standard_mibs import SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB
_HAS_SHARED = True

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
log = logging.getLogger('ntcip1218_agent')


# ---------------------------------------------------------------------------
# Combined OID tree: standard MIBs + RSU MIB
# ---------------------------------------------------------------------------

class CombinedOIDTree:
    """
    Merges the standard MIBs OID tree (from the ASC agent) with the RSU OID
    tree into a single sorted structure that the SNMPServer can query.
    """

    def __init__(self, rsu_tree, std_tree=None):
        self._rsu = rsu_tree
        self._std = std_tree

        # Merge and sort all entries
        entries = list(rsu_tree._entries)
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
# Standard MIB tree for RSU (wraps NativeOIDTree from the ASC agent)
# ---------------------------------------------------------------------------

def _build_std_tree(hostname, snmp_mib):
    """Build a minimal standard-MIB OID tree for the RSU."""
    if not _HAS_SHARED:
        return None

    from common.standard_mibs import SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB

    # Create a minimal data store wrapper
    class _StdStore:
        pass

    store         = _StdStore()
    store.system  = SystemMIB(hostname=hostname)
    store.system.sysDescr    = (
        b'NTCIP 1218 v01 Roadside Unit Simulator; Python SNMP Agent'
    )
    store.system.sysObjectID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 18)
    store.system.sysServices = 6   # physical + datalink
    store.system.sysLocation = b'Roadside / Main St & 1st Ave'

    store.interfaces = InterfacesMIB()
    store.snmp_mib   = snmp_mib
    store.ntcip1201  = NTCIP1201MIB()
    # Update 1201 module table to reflect RSU
    store.ntcip1201.module_table[2] = {
        'moduleNumber':     2,
        'moduleDeviceNode': (1, 3, 6, 1, 4, 1, 1206, 4, 2, 18),
        'moduleMake':       b'Simulator',
        'moduleModel':      b'NTCIP 1218',
        'moduleVersion':    b'01.38',
        'moduleType':       1,   # NTCIP
    }

    from ntcip1202_agent.oid_tree import NativeOIDTree
    # NativeOIDTree expects the full ASCDataStore; monkey-patch minimally
    tree = object.__new__(NativeOIDTree)
    tree.store    = store
    tree._entries = []
    tree._build_standard_mibs()
    tree._entries.sort(key=lambda e: e[0])
    return tree


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='NTCIP 1218 v01 RSU SNMP Agent')
    parser.add_argument('--host',            default='0.0.0.0')
    parser.add_argument('--port',            type=int, default=1162)
    parser.add_argument('--community',       default='public')
    parser.add_argument('--write-community', default='private', dest='write_community')
    parser.add_argument('--asc-host',        default='127.0.0.1', dest='asc_host')
    parser.add_argument('--asc-port',        type=int, default=1161, dest='asc_port')
    parser.add_argument('--asc-community',   default='public', dest='asc_community')
    parser.add_argument('--lat',             type=float, default=32.729)
    parser.add_argument('--lon',             type=float, default=-97.508)
    parser.add_argument('--verbose',         action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("NTCIP 1218 v01 RSU SNMP Agent")
    log.info(f"  Address:         {args.host}:{args.port}/udp")
    log.info(f"  Read community:  {args.community}")
    log.info(f"  Write community: {args.write_community}")
    log.info(f"  ASC endpoint:    {args.asc_host}:{args.asc_port}")
    log.info(f"  Position:        {args.lat:.6f}, {args.lon:.6f}")
    log.info(f"  OID root:        1.3.6.1.4.1.1206.4.2.18")
    log.info("=" * 60)

    # Build RSU data store and OID tree
    lat_int = int(args.lat * 1e7)
    lon_int = int(args.lon * 1e7)
    rsu_store = RSUDataStore(latitude=lat_int, longitude=lon_int)
    rsu_tree  = RSUOIDTree(rsu_store)

    # Build standard MIBs OID tree
    from common.standard_mibs import SnmpMIB
    snmp_mib = SnmpMIB()
    std_tree = _build_std_tree(None, snmp_mib)

    # Merge into combined tree
    combined = CombinedOIDTree(rsu_tree, std_tree)

    log.info(f"  Total OIDs:      {len(combined._entries)}")

    # SPaT bridge (SNMP mode — polls ASC)
    bridge = SPaTBridge(
        rsu_store,
        asc_host=args.asc_host,
        asc_port=args.asc_port,
        asc_community=args.asc_community.encode(),
        poll_interval=0.1,
    )
    bridge.start()

    # SNMP server
    server = SNMPServer(
        combined,
        host=args.host,
        port=args.port,
        ro_communities=[args.community.encode()],
        rw_communities=[args.write_community.encode()],
        snmp_mib=snmp_mib,
    )
    server.start()

    def _shutdown(signum, frame):
        log.info("Shutting down...")
        bridge.stop()
        server.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("RSU agent running. Press Ctrl+C to stop.")
    bridge.join()


if __name__ == '__main__':
    main()
