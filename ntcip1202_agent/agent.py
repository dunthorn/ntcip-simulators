#!/usr/bin/env python3
"""
NTCIP 1202 v4.11b SNMP Agent
Implements the Actuated Signal Controller (ASC) MIB.

Derived from NTCIP 1202 v04. Copyright by AASHTO / ITE / NEMA. Used by permission.

Usage (from the simulation/ directory):
    python3 -m ntcip1202_agent.agent [options]

Options:
    --host HOST              Bind address (default: 0.0.0.0)
    --port PORT              UDP/TCP port (default: 1161; use 161 with sudo)
    --community STR          Read-only community  (default: public)
    --write-community STR    Read-write community (default: private)
    --phases N               Number of phases 2..255 (default: 8)
    --transport STR          Transport: udp, tcp, or both (default: udp)
    --verbose                Debug logging

Requires only the Python standard library.  No third-party packages needed.
"""

import argparse
import logging
import signal
import time
import threading

from ntcip1202_agent.mib_data import ASCDataStore
from ntcip1202_agent.oid_tree import NativeOIDTree
from common.snmp_server import SNMPServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
log = logging.getLogger('ntcip1202_agent')


# ---------------------------------------------------------------------------
# Ring Status bit definitions (MIB section 5.8.6.1)
# ---------------------------------------------------------------------------
# Bits 2-0: coded interval state
_RS_MIN_GREEN    = 0x000  # 0b000
_RS_EXTENSION    = 0x001  # 0b001
_RS_MAXIMUM      = 0x002  # 0b010
_RS_GREEN_REST   = 0x003  # 0b011
_RS_YELLOW       = 0x004  # 0b100
_RS_RED_CLEAR    = 0x005  # 0b101
_RS_RED_REST     = 0x006  # 0b110

# Upper bits
_RS_DONT_WALK    = 0x800  # bit 11
_RS_FLASH_DW     = 0x400  # bit 10
_RS_WALK         = 0x080  # bit 7
_RS_GAP_OUT      = 0x008  # bit 3  (set on gap-out termination)
_RS_MAX_OUT      = 0x010  # bit 4  (set on max-out termination)


class PhaseSimulator(threading.Thread):
    """
    Simulates a 2-ring dual-barrier NEMA TS-2 controller.

    Reads its phase ordering from the sequenceTable (sequence plan 1) so that
    what the simulator does is always consistent with what the MIB reports.

    Updates every simulation tick (default 100 ms):
      - phaseStatusGroup bitmaps (reds/yellows/greens/walks/dontwalks/phaseOns)
      - ringStatusTable  (ringOnPhase, ringStatus, ringOnPhaseDuration)
      - unitCounterActuations
    """

    _INTERVALS = ['green', 'yellow', 'red']

    def __init__(self, store: ASCDataStore):
        super().__init__(daemon=True, name='PhaseSimulator')
        self.store = store
        self._stop  = threading.Event()
        self._tick  = 0.1          # seconds per simulation step

        # Simulator internal state
        self._pair_idx      = 0    # index into the sequence of concurrent pairs
        self._interval_idx  = 0    # 0=green 1=yellow 2=red
        self._elapsed       = 0.0  # seconds elapsed in current interval
        self._phase_on_ds   = {1: 0, 2: 0}   # ringOnPhaseDuration (deciseconds)

    # ------------------------------------------------------------------
    # Thread entry
    # ------------------------------------------------------------------

    def stop(self):
        self._stop.set()

    def run(self):
        log.info("Phase simulator started")
        while not self._stop.is_set():
            self._step()
            time.sleep(self._tick)
        log.info("Phase simulator stopped")

    # ------------------------------------------------------------------
    # Sequence helpers — read from MIB tables
    # ------------------------------------------------------------------

    def _get_sequence(self):
        """
        Return the list of concurrent phase pairs from sequence plan 1.

        Each pair is a tuple (ring1_phase, ring2_phase) at the same barrier
        position.  Pairs are built by zipping ring 1 and ring 2 in order.

        E.g. ring1=[1,2,3,4], ring2=[5,6,7,8]
             → pairs = [(1,5),(2,6),(3,7),(4,8)]
        """
        st = self.store.sequence_table
        ring1 = list(st.get((1, 1), bytes()))
        ring2 = list(st.get((1, 2), bytes()))
        # Pad shorter ring with zeros (skipped phases)
        length = max(len(ring1), len(ring2))
        ring1 += [0] * (length - len(ring1))
        ring2 += [0] * (length - len(ring2))
        return list(zip(ring1, ring2))

    def _current_pair(self):
        pairs = self._get_sequence()
        if not pairs:
            return (0, 0)
        return pairs[self._pair_idx % len(pairs)]

    def _interval_duration(self, pair):
        """Return duration of current interval in seconds, from phase timing."""
        s = self.store
        # Use ring-1 phase timing as reference (fall back to ring-2 if 0)
        ref_phase = pair[0] or pair[1]
        pt = s.phase_table.get(ref_phase, {})
        interval = self._INTERVALS[self._interval_idx]
        if interval == 'green':
            return float(pt.get('phaseMaximum1', 30))
        elif interval == 'yellow':
            return pt.get('phaseYellowChange', 40) / 10.0
        else:
            return pt.get('phaseRedClear', 20) / 10.0

    # ------------------------------------------------------------------
    # Per-tick update
    # ------------------------------------------------------------------

    def _step(self):
        s    = self.store
        n    = s.num_phases
        pair = self._current_pair()
        interval = self._INTERVALS[self._interval_idx]
        self._elapsed += self._tick

        # Active phases (non-zero entries in the pair that exist on this device)
        active = [p for p in pair if 1 <= p <= n]

        # ---- Build phaseStatusGroup bitmaps ----
        reds = yellows = greens = dwlks = walks = phase_ons = 0
        for bit in range(n):
            ph   = bit + 1
            mask = 1 << bit
            if ph in active:
                phase_ons |= mask
                if interval == 'green':
                    greens |= mask
                    walks  |= mask
                elif interval == 'yellow':
                    yellows |= mask
                    dwlks   |= mask
                else:                       # red clearance
                    reds  |= mask
                    dwlks |= mask
            else:
                reds  |= mask
                dwlks |= mask

        def pack(v): return v.to_bytes(2, 'big')
        sg = s.phase_status_groups[1]
        sg['phaseStatusGroupReds']      = pack(reds)
        sg['phaseStatusGroupYellows']   = pack(yellows)
        sg['phaseStatusGroupGreens']    = pack(greens)
        sg['phaseStatusGroupDontWalks'] = pack(dwlks)
        sg['phaseStatusGroupWalks']     = pack(walks)
        sg['phaseStatusGroupPhaseOns']  = pack(phase_ons)

        # ---- Build ringStatus for each ring ----
        if interval == 'green':
            coded = _RS_MIN_GREEN
            upper = _RS_WALK
        elif interval == 'yellow':
            coded = _RS_YELLOW
            upper = _RS_DONT_WALK | _RS_FLASH_DW
        else:
            coded = _RS_RED_CLEAR
            upper = _RS_DONT_WALK

        pairs_all = self._get_sequence()
        ring_phases = {1: pair[0], 2: pair[1]}   # active phase per ring

        for ring_num in (1, 2):
            ph = ring_phases.get(ring_num, 0)
            rs = s.ring_status[ring_num]
            rs['ringOnPhase'] = ph if (1 <= ph <= n) else 0

            if rs['ringOnPhase'] > 0:
                rs['ringStatus'] = coded | upper
                # Accumulate duration in deciseconds (only during green/yellow)
                if interval in ('green', 'yellow'):
                    self._phase_on_ds[ring_num] = int(
                        self._phase_on_ds.get(ring_num, 0) + self._tick * 10
                    )
                rs['ringOnPhaseDuration'] = self._phase_on_ds[ring_num]
            else:
                rs['ringStatus']          = _RS_RED_REST | _RS_DONT_WALK
                rs['ringOnPhaseDuration'] = 0

        # ---- actuation counter ----
        s.unit_scalars['unitCounterActuations'] = (
            s.unit_scalars.get('unitCounterActuations', 0) + 1
        ) & 0xFFFFFFFF

        # ---- Advance interval / phase pair ----
        duration = self._interval_duration(pair)
        if self._elapsed >= duration:
            self._elapsed = 0.0
            prev_interval = self._interval_idx
            self._interval_idx = (self._interval_idx + 1) % 3

            if self._interval_idx == 0:
                # Finished the full green→yellow→red cycle; advance to next pair
                pairs_all = self._get_sequence()
                self._pair_idx = (self._pair_idx + 1) % max(len(pairs_all), 1)
                # Reset duration counters for the new phase
                self._phase_on_ds = {1: 0, 2: 0}
            elif prev_interval == 0:
                # Transitioning green→yellow: mark gap-out (simplification)
                for ring_num in (1, 2):
                    s.ring_status[ring_num]['ringStatus'] |= _RS_GAP_OUT


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='NTCIP 1202 v4.11b ASC SNMP Agent')
    parser.add_argument('--host',            default='0.0.0.0')
    parser.add_argument('--port',            type=int, default=1161)
    parser.add_argument('--community',       default='public')
    parser.add_argument('--write-community', default='private', dest='write_community')
    parser.add_argument('--phases',          type=int, default=8)
    parser.add_argument('--transport',       default='udp',
                        choices=['udp', 'tcp', 'both'],
                        help='Transport protocol (default: udp)')
    parser.add_argument('--verbose',         action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 60)
    log.info("NTCIP 1202 v4.11b ASC SNMP Agent")
    log.info(f"  Address:         {args.host}:{args.port}/{args.transport}")
    log.info(f"  Transport:       {args.transport}")
    log.info(f"  Read community:  {args.community}")
    log.info(f"  Write community: {args.write_community}")
    log.info(f"  Phases:          {args.phases}")
    log.info(f"  OID root:        1.3.6.1.4.1.1206.4.2.1")
    log.info("=" * 60)

    store    = ASCDataStore(num_phases=args.phases)
    oid_tree = NativeOIDTree(store)
    sim      = PhaseSimulator(store)
    sim.start()

    server = SNMPServer(
        oid_tree,
        host=args.host,
        port=args.port,
        ro_communities=[args.community.encode()],
        rw_communities=[args.write_community.encode()],
        snmp_mib=store.snmp_mib,
        transport=args.transport,
    )
    server.start()

    def _shutdown(signum, frame):
        log.info("Shutting down...")
        sim.stop()
        server.stop()

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("Agent running. Press Ctrl+C to stop.")
    sim.join()


if __name__ == '__main__':
    main()
