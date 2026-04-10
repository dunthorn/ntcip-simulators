"""
spat_bridge.py  —  ASC → RSU SPaT Bridge

Reads phase timing and status from the ASC simulator (via SNMP or directly
via shared memory when co-located) and synthesises a minimal SPaT payload
for the RSU's rsuMsgRepeatTable row 1.

The bridge runs as a background thread.  When the RSU and ASC simulators run
in the same process, it reads directly from an ASCDataStore reference.
When they run as separate processes, it polls the ASC via SNMP UDP.

Derived from NTCIP 1218 v01. Copyright by AASHTO / ITE / NEMA. Used by permission.
SAE J2735 SPaT message format reference (simplified / illustrative encoding).
"""

import time
import struct
import socket
import threading
import logging

log = logging.getLogger('spat_bridge')


# ---------------------------------------------------------------------------
# Minimal SPaT encoder
# ---------------------------------------------------------------------------
# We produce a simplified illustrative SPaT payload.  A full J2735 SPaT
# requires ASN.1 UPER encoding; here we build a fixed-length binary blob
# that carries the essential fields so that the rsuMsgRepeatPayload contains
# something meaningful and changes when the phase state changes.
#
# Format (36 bytes total):
#   Bytes 0-1:   SAE J2735 Message ID (big-endian): 0x0013 = SPaT (19)
#   Bytes 2-3:   Intersection ID (big-endian)
#   Bytes 4-5:   Revision counter (big-endian, increments each change)
#   Bytes 6-7:   Minute of the Year (J2735 MinuteOfTheYear, 0..527040)
#                   = (day_of_year - 1) * 1440 + hour*60 + minute
#   Bytes 8-23:  Phase movement state bytes (one byte per phase 1..16)
#                   0x01 = permissive-green
#                   0x02 = protected-green
#                   0x03 = permissive-yellow
#                   0x04 = protected-yellow
#                   0x05 = stop-and-remain (red)
#                   0x06 = unavailable
#   Bytes 24-39: Phase min-end-time (2 bytes per phase, deciseconds from now)
# ---------------------------------------------------------------------------

_SPAT_MSG_ID      = 0x0013   # SAE J2735 SPAT
_INTERSECTION_ID  = 1001     # arbitrary intersection ID


def _minute_of_year():
    t = time.gmtime()
    return ((t.tm_yday - 1) * 1440 + t.tm_hour * 60 + t.tm_min) % 527040


def encode_spat(greens_bitmap, yellows_bitmap, reds_bitmap,
                num_phases, revision, phase_remaining_ds):
    """
    Build a simplified SPaT payload bytes object.

    greens_bitmap, yellows_bitmap, reds_bitmap: integers (bit N-1 = phase N)
    num_phases: number of phases (1..16)
    revision: counter (uint16)
    phase_remaining_ds: list of remaining deciseconds per phase (index 0 = phase 1)
    """
    moy = _minute_of_year()

    phase_states = []
    for bit in range(min(num_phases, 16)):
        mask = 1 << bit
        if greens_bitmap  & mask:
            phase_states.append(0x01)   # permissive-green
        elif yellows_bitmap & mask:
            phase_states.append(0x03)   # permissive-yellow
        elif reds_bitmap    & mask:
            phase_states.append(0x05)   # stop-and-remain
        else:
            phase_states.append(0x06)   # unavailable
    # Pad to 16 bytes
    phase_states += [0x06] * (16 - len(phase_states))

    # Min-end-time: clamp to uint16
    min_end = []
    for i in range(16):
        ds = phase_remaining_ds[i] if i < len(phase_remaining_ds) else 0
        min_end.append(max(0, min(0xFFFF, int(ds))))

    header = struct.pack('>HHHH',
                         _SPAT_MSG_ID,
                         _INTERSECTION_ID,
                         revision & 0xFFFF,
                         moy & 0xFFFF)
    states  = bytes(phase_states)
    timings = struct.pack('>16H', *min_end)

    return header + states + timings   # 8 + 16 + 32 = 56 bytes


# ---------------------------------------------------------------------------
# SPaTBridge — thread that polls ASC state and updates RSU payload
# ---------------------------------------------------------------------------

class SPaTBridge(threading.Thread):
    """
    Polls ASC phase status and synthesises a SPaT payload for the RSU.

    Two modes:
      direct  — ASCDataStore passed directly (same process)
      snmp    — polls ASC over SNMP UDP (separate processes)
    """

    def __init__(self, rsu_store, asc_store=None,
                 asc_host='127.0.0.1', asc_port=1161,
                 asc_community=b'public',
                 poll_interval=0.1):
        super().__init__(daemon=True, name='SPaTBridge')
        self._rsu      = rsu_store
        self._asc      = asc_store          # direct reference if co-located
        self._host     = asc_host
        self._port     = asc_port
        self._comm     = asc_community
        self._interval = poll_interval
        self._stop     = threading.Event()
        self._revision = 0
        self._last_greens = -1

    def stop(self):
        self._stop.set()

    def run(self):
        log.info(f"SPaT bridge started ({'direct' if self._asc else 'SNMP'})")
        while not self._stop.is_set():
            try:
                self._update()
            except Exception as ex:
                log.warning(f"SPaT bridge error: {ex}")
            time.sleep(self._interval)

    def _update(self):
        if self._asc is not None:
            greens, yellows, reds = self._read_direct()
        else:
            greens, yellows, reds = self._read_snmp()

        n = self._rsu.max_radios   # reuse as proxy for phase count — use store
        try:
            n = len(self._rsu.msg_repeat_table) and self._rsu._num_phases
        except AttributeError:
            pass

        if greens != self._last_greens:
            self._revision = (self._revision + 1) & 0xFFFF
            self._last_greens = greens

        # Estimate remaining time per phase (simplified: use 0 for now)
        remaining = [0] * 16

        payload = encode_spat(greens, yellows, reds, 8, self._revision, remaining)

        # Write into RSU msg repeat row 1 (SPaT)
        self._rsu.msg_repeat_table[1]['rsuMsgRepeatPayload'] = payload
        self._rsu.ifm_status_table[1]['rsuIFMStatus'] = 1   # active

        # Also update RSU GNSS timestamp (keep fresh)
        t = time.gmtime()
        self._rsu.gnss_status.update({
            'rsuGnssYear':   t.tm_year,
            'rsuGnssMonth':  t.tm_mon,
            'rsuGnssDay':    t.tm_mday,
            'rsuGnssHour':   t.tm_hour,
            'rsuGnssMinute': t.tm_min,
            'rsuGnssSecond': t.tm_sec,
        })

        # Tick performance counters
        self._rsu.tick_performance()

    def _read_direct(self):
        """Read phase bitmaps directly from ASCDataStore."""
        sg = self._asc.phase_status_groups.get(1, {})
        def unpack(key):
            b = sg.get(key, b'\x00\x00')
            return int.from_bytes(b[:2], 'big')
        return (unpack('phaseStatusGroupGreens'),
                unpack('phaseStatusGroupYellows'),
                unpack('phaseStatusGroupReds'))

    def _read_snmp(self):
        """Poll ASC phase status bitmaps via SNMP GETNEXT."""
        # OIDs for phaseStatusGroup 1 greens/yellows/reds
        ASC_GREENS  = (1,3,6,1,4,1,1206,4,2,1,1,3,1,4,1)
        ASC_YELLOWS = (1,3,6,1,4,1,1206,4,2,1,1,3,1,3,1)
        ASC_REDS    = (1,3,6,1,4,1,1206,4,2,1,1,3,1,2,1)

        results = {}
        for name, oid in [('g', ASC_GREENS), ('y', ASC_YELLOWS), ('r', ASC_REDS)]:
            val = self._snmp_get(oid)
            results[name] = int.from_bytes(val[:2], 'big') if val and len(val) >= 2 else 0

        return results['g'], results['y'], results['r']

    def _snmp_get(self, oid):
        """Minimal SNMP GET for an OCTET STRING value."""
        try:
            from common.snmp_server import (
                _encode_oid, _encode_integer, _encode_octet_string,
                _tlv, _decode_tlv, _decode_oid,
                TAG_SEQUENCE, PDU_GET
            )
        except ImportError:
            return None

        vbl = _tlv(TAG_SEQUENCE, _encode_oid(oid) + _tlv(5, b''))
        pdu = _tlv(PDU_GET,
                   _encode_integer(1) + _encode_integer(0) + _encode_integer(0) +
                   _tlv(TAG_SEQUENCE, vbl))
        msg = _tlv(TAG_SEQUENCE,
                   _encode_integer(1) +
                   _encode_octet_string(self._comm) +
                   pdu)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            sock.sendto(msg, (self._host, self._port))
            resp, _ = sock.recvfrom(65535)
            # Navigate to varbind value: outer seq → pdu → vbl seq → varbind → value
            _, outer, _ = _decode_tlv(resp, 0)
            pos = 0
            _, _, pos = _decode_tlv(outer, pos)   # version
            _, _, pos = _decode_tlv(outer, pos)   # community
            _, pdu_c, pos = _decode_tlv(outer, pos)  # PDU
            pos2 = 0
            _, _, pos2 = _decode_tlv(pdu_c, pos2)   # req-id
            _, _, pos2 = _decode_tlv(pdu_c, pos2)   # err-status
            _, _, pos2 = _decode_tlv(pdu_c, pos2)   # err-index
            _, vbl_c, pos2 = _decode_tlv(pdu_c, pos2)  # vbl
            _, vb_c, _ = _decode_tlv(vbl_c, 0)         # first varbind
            pos3 = 0
            _, _, pos3 = _decode_tlv(vb_c, pos3)    # oid
            _, val_c, _ = _decode_tlv(vb_c, pos3)   # value
            return bytes(val_c)
        except Exception:
            return None
        finally:
            sock.close()
