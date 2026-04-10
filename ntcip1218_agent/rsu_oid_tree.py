"""
rsu_oid_tree.py  —  NTCIP 1218 v01 RSU OID Tree

Maps every OID under rsu (1.3.6.1.4.1.1206.4.2.18) to a getter/setter
against the RSUDataStore.

Derived from NTCIP 1218 v01. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import time
import logging

log = logging.getLogger('ntcip1218_oid_tree')

# RSU root: devices.18 = 1.3.6.1.4.1.1206.4.2.18
_RSU = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 18)

def _oid(*tail):
    return _RSU + tuple(tail)


class RSUOIDTree:
    """
    Sorted OID table for the NTCIP 1218 RSU MIB.
    get() / get_next() / set() interface matches NativeOIDTree from the ASC agent.
    """

    def __init__(self, store):
        self.store    = store
        self._entries = []
        self._build()
        self._entries.sort(key=lambda e: e[0])
        log.info(f"RSU OID tree built: {len(self._entries)} OIDs")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal search
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def _reg(self, oid, getter, setter=None):
        self._entries.append((oid, getter, setter))

    def _ri_ro(self, oid, fn):
        self._reg(oid, lambda: int(fn()))

    def _ri_rw(self, oid, gfn, sfn):
        self._reg(oid, lambda: int(gfn()),
                  lambda v: sfn(int(v) if not isinstance(v, int) else v))

    def _ro_ro(self, oid, fn):
        self._reg(oid, lambda: bytes(fn()))

    def _ro_rw(self, oid, gfn, sfn):
        self._reg(oid, lambda: bytes(gfn()),
                  lambda v: sfn(bytes(v) if not isinstance(v, bytes) else v))

    def _counter(self, oid, fn):
        self._reg(oid, lambda: ('counter', int(fn())))

    def _gauge(self, oid, fn):
        self._reg(oid, lambda: ('gauge', int(fn())))

    def _timeticks(self, oid, fn):
        self._reg(oid, lambda: ('timeticks', int(fn())))

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self._build_radio_group()
        self._build_gnss_group()
        self._build_msg_repeat_group()
        self._build_rcv_msg_group()
        self._build_system_group()
        self._build_notification_group()
        self._build_performance_group()
        self._build_security_group()

    # ==================================================================
    # 5.2  RSU Radios  —  rsu.1
    # ==================================================================

    def _build_radio_group(self):
        s = self.store

        # rsuMaxRadios  .1.1.0
        self._ri_ro(_oid(1, 1, 0), lambda: s.max_radios)

        # rsuRadioTable  .1.2.1.<col>.<row>
        int_rw_cols = [
            (2, 'rsuRadioChanMode'),
            (3, 'rsuRadioChannel'),
            (4, 'rsuRadioTxPower'),
            (5, 'rsuRadioRxThreshold'),
            (7, 'rsuRadioPowerSave'),
        ]
        int_ro_cols = [
            (6, 'rsuRadioType'),
        ]
        oct_ro_cols = [
            (8, 'rsuRadioMacAddr'),
            (9, 'rsuRadioDesc'),
        ]

        for row in s.radio_table:
            self._ri_ro(_oid(1, 2, 1, 1, row), lambda r=row: s.radio_table[r]['rsuRadioIndex'])
            for col, key in int_rw_cols:
                self._ri_rw(_oid(1, 2, 1, col, row),
                    lambda k=key, r=row: s.radio_table[r][k],
                    lambda v, k=key, r=row: s.radio_table[r].__setitem__(k, v))
            for col, key in int_ro_cols:
                self._ri_ro(_oid(1, 2, 1, col, row),
                    lambda k=key, r=row: s.radio_table[r][k])
            for col, key in oct_ro_cols:
                self._ro_ro(_oid(1, 2, 1, col, row),
                    lambda k=key, r=row: s.radio_table[r][k])

    # ==================================================================
    # 5.3  RSU GNSS  —  rsu.2
    # ==================================================================

    def _build_gnss_group(self):
        s = self.store
        g = s.gnss_status

        self._ri_rw(_oid(2, 1, 0),
            lambda: g['rsuGnssOutputPort'],
            lambda v: g.__setitem__('rsuGnssOutputPort', v))

        self._ro_rw(_oid(2, 2, 0),
            lambda: g['rsuGnssOutputInterface'],
            lambda v: g.__setitem__('rsuGnssOutputInterface', v))

        # Status — read-only
        self._ri_ro(_oid(2, 3, 0), lambda: g['rsuGnssStatus'])

        # Position — live
        self._ri_ro(_oid(2, 4, 0), lambda: g['rsuGnssLatitude'])
        self._ri_ro(_oid(2, 5, 0), lambda: g['rsuGnssLongitude'])
        self._ri_ro(_oid(2, 6, 0), lambda: g['rsuGnssElevation'])
        self._ri_ro(_oid(2, 7, 0), lambda: g['rsuGnssSpeed'])
        self._ri_ro(_oid(2, 8, 0), lambda: g['rsuGnssHeading'])

        # Clock — read from system time live
        self._ri_ro(_oid(2, 9,  0), lambda: time.gmtime().tm_year)
        self._ri_ro(_oid(2, 10, 0), lambda: time.gmtime().tm_mon)
        self._ri_ro(_oid(2, 11, 0), lambda: time.gmtime().tm_mday)
        self._ri_ro(_oid(2, 12, 0), lambda: time.gmtime().tm_hour)
        self._ri_ro(_oid(2, 13, 0), lambda: time.gmtime().tm_min)
        self._ri_ro(_oid(2, 14, 0), lambda: time.gmtime().tm_sec)
        self._ri_ro(_oid(2, 15, 0), lambda: g['rsuGnssOffset'])

    # ==================================================================
    # 5.4  RSU Message Store-and-Repeat  —  rsu.3
    # ==================================================================

    def _build_msg_repeat_group(self):
        s = self.store

        # rsuMsgRepeatMaxEntries  .3.1.0
        self._ri_ro(_oid(3, 1, 0), lambda: s.max_msg_repeat)

        # rsuMsgRepeatTable  .3.2.1.<col>.<row>
        int_rw_cols = [
            (3, 'rsuMsgRepeatTxChannel'),
            (4, 'rsuMsgRepeatTxInterval'),
            (7, 'rsuMsgRepeatEnable'),
            (9, 'rsuMsgRepeatPriority'),
            (10,'rsuMsgRepeatOptions'),
        ]
        int_ro_cols = [
            (8, 'rsuMsgRepeatStatus'),
        ]
        oct_rw_cols = [
            (2,  'rsuMsgRepeatPsid'),
            (5,  'rsuMsgRepeatDeliveryStart'),
            (6,  'rsuMsgRepeatDeliveryStop'),
            (11, 'rsuMsgRepeatPayload'),
        ]

        for row in s.msg_repeat_table:
            self._ri_ro(_oid(3, 2, 1, 1, row),
                lambda r=row: s.msg_repeat_table[r]['rsuMsgRepeatIndex'])
            for col, key in int_rw_cols:
                self._ri_rw(_oid(3, 2, 1, col, row),
                    lambda k=key, r=row: s.msg_repeat_table[r][k],
                    lambda v, k=key, r=row: s.msg_repeat_table[r].__setitem__(k, v))
            for col, key in int_ro_cols:
                self._ri_ro(_oid(3, 2, 1, col, row),
                    lambda k=key, r=row: s.msg_repeat_table[r][k])
            for col, key in oct_rw_cols:
                self._ro_rw(_oid(3, 2, 1, col, row),
                    lambda k=key, r=row: s.msg_repeat_table[r][k],
                    lambda v, k=key, r=row: s.msg_repeat_table[r].__setitem__(k, v))

        # rsuIFMStatusTable  .3.3.1.<col>.<row>
        ifm_int_cols = [
            (1, 'rsuIFMIndex'),
            (3, 'rsuIFMDsrcMsgId'),
            (4, 'rsuIFMTxChannel'),
            (5, 'rsuIFMEnable'),
            (6, 'rsuIFMStatus'),
        ]
        ifm_oct_cols = [
            (2, 'rsuIFMPsid'),
        ]

        for row in s.ifm_status_table:
            for col, key in ifm_int_cols:
                self._ri_ro(_oid(3, 3, 1, col, row),
                    lambda k=key, r=row: s.ifm_status_table[r][k])
            for col, key in ifm_oct_cols:
                self._ro_ro(_oid(3, 3, 1, col, row),
                    lambda k=key, r=row: s.ifm_status_table[r][k])

    # ==================================================================
    # 5.5  RSU Received Message Log  —  rsu.4
    # ==================================================================

    def _build_rcv_msg_group(self):
        s = self.store

        # rsuReceivedMsgMaxEntries  .4.1.0
        self._ri_ro(_oid(4, 1, 0), lambda: s.max_rcv_msg)

        # rsuReceivedMsgTable  .4.2.1.<col>.<row>
        rcv_int_rw = [
            (3, 'rsuReceivedMsgChannel'),
            (4, 'rsuReceivedMsgInterval'),
            (5, 'rsuReceivedMsgEnable'),
            (7, 'rsuReceivedMsgOptions'),
        ]
        rcv_int_ro = [
            (1, 'rsuReceivedMsgIndex'),
            (6, 'rsuReceivedMsgStatus'),
        ]
        rcv_oct_rw = [
            (2, 'rsuReceivedMsgPsid'),
            (8, 'rsuReceivedMsgPayload'),
        ]

        for row in s.rcv_msg_table:
            for col, key in rcv_int_rw:
                self._ri_rw(_oid(4, 2, 1, col, row),
                    lambda k=key, r=row: s.rcv_msg_table[r][k],
                    lambda v, k=key, r=row: s.rcv_msg_table[r].__setitem__(k, v))
            for col, key in rcv_int_ro:
                self._ri_ro(_oid(4, 2, 1, col, row),
                    lambda k=key, r=row: s.rcv_msg_table[r][k])
            for col, key in rcv_oct_rw:
                self._ro_rw(_oid(4, 2, 1, col, row),
                    lambda k=key, r=row: s.rcv_msg_table[r][k],
                    lambda v, k=key, r=row: s.rcv_msg_table[r].__setitem__(k, v))

    # ==================================================================
    # 5.6  RSU System  —  rsu.5
    # ==================================================================

    def _build_system_group(self):
        s  = self.store
        sy = s.system
        start = self.store._start_time

        # rsuMode  .5.1.0  (read-write)
        self._ri_rw(_oid(5, 1, 0),
            lambda: sy['rsuMode'],
            lambda v: sy.__setitem__('rsuMode', v))

        # rsuModeStatus  .5.2.0  (read-only)
        self._ri_ro(_oid(5, 2, 0), lambda: sy['rsuModeStatus'])

        # rsuID  .5.3.0  (read-write octet string)
        self._ro_rw(_oid(5, 3, 0),
            lambda: sy['rsuID'],
            lambda v: sy.__setitem__('rsuID', v))

        # rsuFirmwareVersion  .5.4.0  (read-only)
        self._ro_ro(_oid(5, 4, 0), lambda: sy['rsuFirmwareVersion'])

        # rsuLocationDesc  .5.5.0  (read-write)
        self._ro_rw(_oid(5, 5, 0),
            lambda: sy['rsuLocationDesc'],
            lambda v: sy.__setitem__('rsuLocationDesc', v))

        # rsuMibVersion  .5.6.0  (read-only)
        self._ro_ro(_oid(5, 6, 0), lambda: sy['rsuMibVersion'])

        # rsuClockSource  .5.7.0  (read-write)
        self._ri_rw(_oid(5, 7, 0),
            lambda: sy['rsuClockSource'],
            lambda v: sy.__setitem__('rsuClockSource', v))

        # rsuClockSourceStatus  .5.8.0  (read-only)
        self._ri_ro(_oid(5, 8, 0), lambda: sy['rsuClockSourceStatus'])

        # rsuSysUptime  .5.9.0  — TimeTicks (live)
        self._timeticks(_oid(5, 9, 0),
            lambda: int((time.time() - start) * 100))

        # rsuClockOffset  .5.10.0
        self._ri_rw(_oid(5, 10, 0),
            lambda: sy['rsuClockOffset'],
            lambda v: sy.__setitem__('rsuClockOffset', v))

        # rsuTimestamp  .5.11.0  — live 5-byte BCD: YY MM DD HH MM
        def _live_ts():
            t = time.gmtime()
            return bytes([
                t.tm_year % 100, t.tm_mon, t.tm_mday,
                t.tm_hour, t.tm_min
            ])
        self._ro_ro(_oid(5, 11, 0), _live_ts)

        # rsuIFMRepeatEnable  .5.12.0
        self._ri_rw(_oid(5, 12, 0),
            lambda: sy['rsuIFMRepeatEnable'],
            lambda v: sy.__setitem__('rsuIFMRepeatEnable', v))

    # ==================================================================
    # 5.7  RSU Notifications  —  rsu.6
    # ==================================================================

    def _build_notification_group(self):
        s = self.store

        # rsuNotifMaxEntries  .6.1.0
        self._ri_ro(_oid(6, 1, 0), lambda: s.max_notifications)

        # rsuNotifTable  .6.2.1.<col>.<row>
        for row in s.notif_table:
            self._ri_ro(_oid(6, 2, 1, 1, row),
                lambda r=row: s.notif_table[r]['rsuNotifIndex'])
            self._ro_rw(_oid(6, 2, 1, 2, row),
                lambda r=row: s.notif_table[r]['rsuNotifDest'],
                lambda v, r=row: s.notif_table[r].__setitem__('rsuNotifDest', v))
            self._ri_rw(_oid(6, 2, 1, 3, row),
                lambda r=row: s.notif_table[r]['rsuNotifPort'],
                lambda v, r=row: s.notif_table[r].__setitem__('rsuNotifPort', v))
            self._ri_rw(_oid(6, 2, 1, 4, row),
                lambda r=row: s.notif_table[r]['rsuNotifEnable'],
                lambda v, r=row: s.notif_table[r].__setitem__('rsuNotifEnable', v))
            self._ri_ro(_oid(6, 2, 1, 5, row),
                lambda r=row: s.notif_table[r]['rsuNotifStatus'])

    # ==================================================================
    # 5.8  RSU Performance  —  rsu.7
    # ==================================================================

    def _build_performance_group(self):
        s = self.store
        p = s.perf

        counter_scalars = [
            (1, 'rsuMsgRepeatTxCount'),
            (2, 'rsuMsgRepeatTxError'),
            (3, 'rsuRcvMsgCount'),
            (4, 'rsuRcvMsgError'),
            (5, 'rsuRadioTxCount'),
            (6, 'rsuRadioRxCount'),
            (8, 'rsuGnssFixCount'),
        ]
        for sub, key in counter_scalars:
            self._counter(_oid(7, sub, 0), lambda k=key: p[k])

        # rsuGnssLockStatus  .7.7.0  — integer
        self._ri_ro(_oid(7, 7, 0), lambda: p['rsuGnssLockStatus'])

    # ==================================================================
    # 5.9  RSU Security  —  rsu.8
    # ==================================================================

    def _build_security_group(self):
        s  = self.store
        ss = s.sec_system

        # Scalars
        self._ri_ro(_oid(8, 1, 0), lambda: ss['rsuSecCredStatus'])
        self._ri_ro(_oid(8, 2, 0), lambda: ss['rsuSecCertRevocStatus'])
        self._ro_ro(_oid(8, 3, 0), lambda: ss['rsuSecCredExpiration'])
        self._ro_rw(_oid(8, 4, 0),
            lambda: ss['rsuSecCertRevocUrl'],
            lambda v: ss.__setitem__('rsuSecCertRevocUrl', v))
        self._ro_rw(_oid(8, 5, 0),
            lambda: ss['rsuSecCredDownloadUrl'],
            lambda v: ss.__setitem__('rsuSecCredDownloadUrl', v))
        self._ri_rw(_oid(8, 6, 0),
            lambda: ss['rsuSecCredDownloadEnable'],
            lambda v: ss.__setitem__('rsuSecCredDownloadEnable', v))
        self._ri_rw(_oid(8, 7, 0),
            lambda: ss['rsuSecCertRevocEnable'],
            lambda v: ss.__setitem__('rsuSecCertRevocEnable', v))

        # maxSecEnrollCerts  .8.8.0
        self._ri_ro(_oid(8, 8, 0), lambda: s.max_sec_enroll_certs)

        # rsuSecEnrollCertTable  .8.9.1.<col>.<row>
        for row in s.sec_enroll_cert_table:
            ec = s.sec_enroll_cert_table
            self._ri_ro(_oid(8, 9, 1, 1, row),
                lambda r=row: ec[r]['rsuSecEnrollCertIndex'])
            self._ri_ro(_oid(8, 9, 1, 2, row),
                lambda r=row: ec[r]['rsuSecEnrollCertStatus'])
            self._ro_ro(_oid(8, 9, 1, 3, row),
                lambda r=row: ec[r]['rsuSecEnrollCertValidRegion'])
            self._ro_ro(_oid(8, 9, 1, 4, row),
                lambda r=row: ec[r]['rsuSecEnrollCertExpiration'])
            self._ro_rw(_oid(8, 9, 1, 5, row),
                lambda r=row: ec[r]['rsuSecEnrollCertUrl'],
                lambda v, r=row: ec[r].__setitem__('rsuSecEnrollCertUrl', v))
            self._ro_ro(_oid(8, 9, 1, 6, row),
                lambda r=row: ec[r]['rsuSecEnrollCertId'])

        # maxSecAppCerts  .8.10.0
        self._ri_ro(_oid(8, 10, 0), lambda: s.max_sec_app_certs)

        # rsuSecAppCertTable  .8.11.1.<col>.<row>
        for row in s.sec_app_cert_table:
            ac = s.sec_app_cert_table
            self._ri_ro(_oid(8, 11, 1, 1, row),
                lambda r=row: ac[r]['rsuSecAppCertIndex'])
            self._ri_ro(_oid(8, 11, 1, 2, row),
                lambda r=row: ac[r]['rsuSecAppCertStatus'])
            self._ro_ro(_oid(8, 11, 1, 3, row),
                lambda r=row: ac[r]['rsuSecAppCertExpiration'])
            self._ro_ro(_oid(8, 11, 1, 4, row),
                lambda r=row: ac[r]['rsuSecAppCertId'])
            self._ri_ro(_oid(8, 11, 1, 5, row),
                lambda r=row: ac[r]['rsuSecAppCertExpirationPending'])
