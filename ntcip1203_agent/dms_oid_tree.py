"""
dms_oid_tree.py  —  NTCIP 1203 v03 DMS OID Tree

Maps every OID under dms (1.3.6.1.4.1.1206.4.2.3) to a getter/setter
against the DMSDataStore.

Derived from NTCIP 1203 v03. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import logging

log = logging.getLogger('ntcip1203_oid_tree')

# DMS root: devices.dms = 1.3.6.1.4.1.1206.4.2.3
_DMS = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 3)

def _oid(*tail):
    return _DMS + tuple(tail)


class DMSOIDTree:
    """
    Sorted OID table for the NTCIP 1203 v03 DMS MIB.
    get() / get_next() / set() interface matches NativeOIDTree from the ASC agent.
    """

    def __init__(self, store):
        self.store    = store
        self._entries = []
        self._build()
        self._entries.sort(key=lambda e: e[0])
        log.info(f"DMS OID tree built: {len(self._entries)} OIDs")

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

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        self._build_sign_config()
        self._build_vms_config()
        self._build_font_group()
        self._build_multi_config()
        self._build_message_group()
        self._build_sign_control()
        self._build_illumination()
        self._build_scheduling()
        self._build_sign_status()
        self._build_graphic_group()

    # ==================================================================
    # 5.2  Sign Configuration and Capability  —  dms.1
    # ==================================================================

    def _build_sign_config(self):
        s  = self.store
        sc = s.sign_config

        self._ri_ro(_oid(1, 1, 0), lambda: sc['dmsSignAccess'])
        self._ri_ro(_oid(1, 2, 0), lambda: sc['dmsSignType'])
        self._ri_ro(_oid(1, 3, 0), lambda: sc['dmsSignHeight'])
        self._ri_ro(_oid(1, 4, 0), lambda: sc['dmsSignWidth'])
        self._ri_ro(_oid(1, 5, 0), lambda: sc['dmsHorizontalBorder'])
        self._ri_ro(_oid(1, 6, 0), lambda: sc['dmsVerticalBorder'])
        self._ro_ro(_oid(1, 7, 0), lambda: sc['dmsLegend'])
        self._ri_ro(_oid(1, 8, 0), lambda: sc['dmsBeaconType'])
        self._ri_ro(_oid(1, 9, 0), lambda: sc['dmsSignTechnology'])

    # ==================================================================
    # 5.3  VMS Configuration  —  dms.2
    # ==================================================================

    def _build_vms_config(self):
        s  = self.store
        vc = s.vms_config

        self._ri_ro(_oid(2, 1, 0), lambda: vc['vmsCharacterHeightPixels'])
        self._ri_ro(_oid(2, 2, 0), lambda: vc['vmsCharacterWidthPixels'])
        self._ri_ro(_oid(2, 3, 0), lambda: vc['vmsSignHeightPixels'])
        self._ri_ro(_oid(2, 4, 0), lambda: vc['vmsSignWidthPixels'])
        self._ri_ro(_oid(2, 5, 0), lambda: vc['vmsHorizontalPitch'])
        self._ri_ro(_oid(2, 6, 0), lambda: vc['vmsVerticalPitch'])
        self._ro_ro(_oid(2, 7, 0), lambda: vc['monochromeColor'])

    # ==================================================================
    # 5.4  Font Definition Objects  —  dms.3
    # ==================================================================

    def _build_font_group(self):
        s = self.store

        self._ri_ro(_oid(3, 1, 0), lambda: s.num_fonts)

        # Font table  dms.3.2.1.<col>.<fontIndex>
        for fi, row in s.font_table.items():
            self._ri_ro(_oid(3, 2, 1, 1, fi), lambda r=row: r['fontIndex'])
            self._ri_rw(_oid(3, 2, 1, 2, fi),
                lambda r=row: r['fontNumber'],
                lambda v, r=row: r.__setitem__('fontNumber', v))
            self._ro_rw(_oid(3, 2, 1, 3, fi),
                lambda r=row: r['fontName'],
                lambda v, r=row: r.__setitem__('fontName', v))
            self._ri_ro(_oid(3, 2, 1, 4, fi), lambda r=row: r['fontHeight'])
            self._ri_rw(_oid(3, 2, 1, 5, fi),
                lambda r=row: r['fontCharSpacing'],
                lambda v, r=row: r.__setitem__('fontCharSpacing', v))
            self._ri_rw(_oid(3, 2, 1, 6, fi),
                lambda r=row: r['fontLineSpacing'],
                lambda v, r=row: r.__setitem__('fontLineSpacing', v))
            self._ri_ro(_oid(3, 2, 1, 7, fi), lambda r=row: r['fontVersionID'])
            self._ri_rw(_oid(3, 2, 1, 8, fi),
                lambda r=row: r['fontStatus'],
                lambda v, r=row: r.__setitem__('fontStatus', v))

        # Max chars per font / character table
        self._ri_ro(_oid(3, 3, 0), lambda: s.max_font_chars)

        # Character table  dms.3.4.1.<col>.<fontIndex>.<charIndex>
        for (fi, ch), row in s.char_table.items():
            self._ri_ro(_oid(3, 4, 1, 1, fi, ch), lambda r=row: r['chTableFontIndex'])
            self._ri_ro(_oid(3, 4, 1, 2, fi, ch), lambda r=row: r['chTableCharIndex'])
            self._ri_rw(_oid(3, 4, 1, 3, fi, ch),
                lambda r=row: r['chTableCharWidth'],
                lambda v, r=row: r.__setitem__('chTableCharWidth', v))
            self._ro_rw(_oid(3, 4, 1, 4, fi, ch),
                lambda r=row: r['chTableCharPattern'],
                lambda v, r=row: r.__setitem__('chTableCharPattern', v))

        # Max character size
        self._ri_ro(_oid(3, 5, 0), lambda: s.max_char_size)

    # ==================================================================
    # 5.5  MULTI Configuration Objects  —  dms.4
    # ==================================================================

    def _build_multi_config(self):
        s = self.store
        m = s.multi_cfg

        pairs_ri_rw = [
            (_oid(4, 1, 0),  'dmsDefaultBackgroundColor'),
            (_oid(4, 2, 0),  'dmsDefaultForegroundColor'),
            (_oid(4, 3, 0),  'dmsDefaultFlashOn'),
            (_oid(4, 4, 0),  'dmsDefaultFlashOnActivate'),
            (_oid(4, 5, 0),  'dmsDefaultFlashOff'),
            (_oid(4, 6, 0),  'dmsDefaultFlashOffActivate'),
            (_oid(4, 7, 0),  'dmsDefaultFont'),
            (_oid(4, 8, 0),  'dmsDefaultFontActivate'),
            (_oid(4, 9, 0),  'dmsDefaultJustificationLine'),
            (_oid(4, 10, 0), 'dmsDefaultJustificationLineActivate'),
            (_oid(4, 11, 0), 'dmsDefaultJustificationPage'),
            (_oid(4, 12, 0), 'dmsDefaultJustificationPageActivate'),
            (_oid(4, 13, 0), 'dmsDefaultPageOnTime'),
            (_oid(4, 14, 0), 'dmsDefaultPageOnTimeActivate'),
            (_oid(4, 15, 0), 'dmsDefaultPageOffTime'),
            (_oid(4, 16, 0), 'dmsDefaultPageOffTimeActivate'),
            (_oid(4, 20, 0), 'dmsDefaultCharacterSet'),
            (_oid(4, 21, 0), 'dmsColorScheme'),
            (_oid(4, 23, 0), 'dmsMaxNumberPages'),
            (_oid(4, 24, 0), 'dmsMaxMultiStringLength'),
        ]
        for oid, key in pairs_ri_rw:
            self._ri_rw(oid,
                lambda k=key: m[k],
                lambda v, k=key: m.__setitem__(k, v))

        pairs_ro_rw = [
            (_oid(4, 17, 0), 'dmsDefaultBackgroundColorRGB'),
            (_oid(4, 18, 0), 'dmsDefaultBackgroundColorRGBActivate'),
            (_oid(4, 19, 0), 'dmsDefaultForegroundColorRGB'),
            (_oid(4, 19, 1), 'dmsDefaultForegroundColorRGBActivate'),
        ]
        for oid, key in pairs_ro_rw:
            self._ro_rw(oid,
                lambda k=key: m[k],
                lambda v, k=key: m.__setitem__(k, v))

        # dmsSupportedMultiTags (read-only bitmask)
        self._ro_ro(_oid(4, 22, 0), lambda: m['dmsSupportedMultiTags'])

    # ==================================================================
    # 5.6  Message Objects  —  dms.5
    # ==================================================================

    def _build_message_group(self):
        s = self.store

        # Scalars
        self._ri_ro(_oid(5, 1, 0), lambda: s.num_permanent_messages)
        self._ri_ro(_oid(5, 2, 0), lambda: s.num_changeable_messages)
        self._ri_ro(_oid(5, 3, 0), lambda: s.max_changeable_messages)
        self._gauge( _oid(5, 4, 0), lambda: s.changeable_free_bytes)
        self._ri_ro(_oid(5, 5, 0), lambda: s.num_volatile_messages)
        self._ri_ro(_oid(5, 6, 0), lambda: s.max_volatile_messages)
        self._gauge( _oid(5, 7, 0), lambda: s.volatile_free_bytes)

        # Message table  dms.5.8.1.<col>.<memType>.<msgNum>
        # We flatten all three memory types into the same table OID branch,
        # keyed by (memType, msgNum) as the two-part row index.
        def _reg_msg_row(mem_type, msg_num, table):
            row = table[msg_num]
            # Read-only columns
            self._ri_ro(_oid(5, 8, 1, 1, mem_type, msg_num),
                lambda r=row: r['dmsMessageMemoryType'])
            self._ri_ro(_oid(5, 8, 1, 2, mem_type, msg_num),
                lambda r=row: r['dmsMessageNumber'])
            # Read-write: MULTI string
            self._ro_rw(_oid(5, 8, 1, 3, mem_type, msg_num),
                lambda r=row: r['dmsMessageMultiString'],
                lambda v, r=row, mn=msg_num, tbl=table, mt=mem_type:
                    self._write_multi(tbl, mn, v))
            # Owner
            self._ro_rw(_oid(5, 8, 1, 4, mem_type, msg_num),
                lambda r=row: r['dmsMessageOwner'],
                lambda v, r=row: r.__setitem__('dmsMessageOwner', v))
            # CRC (read-only, computed)
            self._ri_ro(_oid(5, 8, 1, 5, mem_type, msg_num),
                lambda r=row: r['dmsMessageCRC'])
            # Beacon
            self._ri_rw(_oid(5, 8, 1, 6, mem_type, msg_num),
                lambda r=row: r['dmsMessageBeacon'],
                lambda v, r=row: r.__setitem__('dmsMessageBeacon', v))
            # PixelService
            self._ri_rw(_oid(5, 8, 1, 7, mem_type, msg_num),
                lambda r=row: r['dmsMessagePixelService'],
                lambda v, r=row: r.__setitem__('dmsMessagePixelService', v))
            # RunTimePriority
            self._ri_rw(_oid(5, 8, 1, 8, mem_type, msg_num),
                lambda r=row: r['dmsMessageRunTimePriority'],
                lambda v, r=row: r.__setitem__('dmsMessageRunTimePriority', v))
            # Status
            self._ri_ro(_oid(5, 8, 1, 9, mem_type, msg_num),
                lambda r=row: r['dmsMessageStatus'])

        from ntcip1203_agent.dms_mib_data import (
            MSG_MEM_PERMANENT, MSG_MEM_CHANGEABLE, MSG_MEM_VOLATILE)

        for mn in s.permanent_msg_table:
            _reg_msg_row(MSG_MEM_PERMANENT, mn, s.permanent_msg_table)
        for mn in s.changeable_msg_table:
            _reg_msg_row(MSG_MEM_CHANGEABLE, mn, s.changeable_msg_table)
        for mn in s.volatile_msg_table:
            _reg_msg_row(MSG_MEM_VOLATILE, mn, s.volatile_msg_table)

        # Validate message error
        self._ri_ro(_oid(5, 9, 0), lambda: s.validate_msg_error)

    def _write_multi(self, table, msg_num, value):
        """Helper: write MULTI string to a message row, recompute CRC and status."""
        row = table[msg_num]
        mb  = bytes(value) if not isinstance(value, bytes) else value
        row['dmsMessageMultiString'] = mb
        row['dmsMessageCRC']         = self.store._crc16(mb)
        row['dmsMessageStatus']      = 4 if mb else 1   # valid or notUsed

    # ==================================================================
    # 5.7  Sign Control Objects  —  dms.6
    # ==================================================================

    def _build_sign_control(self):
        s = self.store
        c = s.sign_control

        self._ri_rw(_oid(6, 1, 0),
            lambda: c['dmsControlMode'],
            lambda v: c.__setitem__('dmsControlMode', v))

        self._ri_rw(_oid(6, 2, 0),
            lambda: c['dmsSoftwareReset'],
            lambda v: c.__setitem__('dmsSoftwareReset', v))

        # dmsActivateMessage — write triggers activation logic
        self._ro_rw(_oid(6, 3, 0),
            lambda: c['dmsActivateMessage'],
            lambda v: s.activate_message(bytes(v) if not isinstance(v, bytes) else v))

        self._ri_ro(_oid(6, 4, 0), lambda: c['dmsMessageTimeRemaining'])
        self._ro_ro(_oid(6, 5, 0), lambda: c['dmsMessageTableSource'])
        self._ro_rw(_oid(6, 6, 0),
            lambda: c['dmsMessageRequesterID'],
            lambda v: c.__setitem__('dmsMessageRequesterID', v))
        self._ri_ro(_oid(6, 7, 0), lambda: c['dmsMessageSourceMode'])

        self._ro_rw(_oid(6, 8, 0),
            lambda: c['dmsShortPowerLossRecoveryMessage'],
            lambda v: c.__setitem__('dmsShortPowerLossRecoveryMessage', v))
        self._ro_rw(_oid(6, 9, 0),
            lambda: c['dmsLongPowerLossRecoveryMessage'],
            lambda v: c.__setitem__('dmsLongPowerLossRecoveryMessage', v))
        self._ri_rw(_oid(6, 10, 0),
            lambda: c['dmsShortPowerLossTime'],
            lambda v: c.__setitem__('dmsShortPowerLossTime', v))
        self._ro_rw(_oid(6, 11, 0),
            lambda: c['dmsResetMessage'],
            lambda v: c.__setitem__('dmsResetMessage', v))
        self._ro_rw(_oid(6, 12, 0),
            lambda: c['dmsCommLossMessage'],
            lambda v: c.__setitem__('dmsCommLossMessage', v))
        self._ri_rw(_oid(6, 13, 0),
            lambda: c['dmsCommLossTime'],
            lambda v: c.__setitem__('dmsCommLossTime', v))
        self._ro_rw(_oid(6, 14, 0),
            lambda: c['dmsPowerLossMessage'],
            lambda v: c.__setitem__('dmsPowerLossMessage', v))
        self._ro_rw(_oid(6, 15, 0),
            lambda: c['dmsEndDurationMessage'],
            lambda v: c.__setitem__('dmsEndDurationMessage', v))
        self._ri_rw(_oid(6, 16, 0),
            lambda: c['dmsMemoryMgmt'],
            lambda v: c.__setitem__('dmsMemoryMgmt', v))
        self._ri_ro(_oid(6, 17, 0), lambda: c['dmsActivateMessageError'])
        self._ri_ro(_oid(6, 18, 0), lambda: c['dmsMultiSyntaxError'])
        self._ri_ro(_oid(6, 19, 0), lambda: c['dmsMultiSyntaxErrorPosition'])
        self._ri_ro(_oid(6, 20, 0), lambda: c['dmsOtherMultiError'])
        self._ri_rw(_oid(6, 21, 0),
            lambda: c['dmsPixelServiceDuration'],
            lambda v: c.__setitem__('dmsPixelServiceDuration', v))
        self._ri_rw(_oid(6, 22, 0),
            lambda: c['dmsPixelServiceFrequency'],
            lambda v: c.__setitem__('dmsPixelServiceFrequency', v))
        self._ri_ro(_oid(6, 23, 0), lambda: c['dmsPixelServiceTime'])
        self._ro_ro(_oid(6, 24, 0), lambda: c['dmsMessageCodeOfActivationError'])
        self._ri_ro(_oid(6, 25, 0), lambda: c['dmsActivateMessageState'])

    # ==================================================================
    # 5.8  Illumination / Brightness Objects  —  dms.7
    # ==================================================================

    def _build_illumination(self):
        s = self.store
        il = s.illum

        self._ri_rw(_oid(7, 1, 0),
            lambda: il['dmsIllumControl'],
            lambda v: il.__setitem__('dmsIllumControl', v))
        self._ri_ro(_oid(7, 2, 0), lambda: il['dmsIllumMaxPhotocellLevel'])
        self._gauge( _oid(7, 3, 0), lambda: il['dmsIllumPhotocellLevelStatus'])
        self._ri_ro(_oid(7, 4, 0), lambda: il['dmsIllumNumBrightLevels'])
        self._ri_ro(_oid(7, 5, 0), lambda: il['dmsIllumBrightLevelStatus'])
        self._ri_rw(_oid(7, 6, 0),
            lambda: il['dmsIllumManLevel'],
            lambda v: il.__setitem__('dmsIllumManLevel', v))
        self._gauge( _oid(7, 8, 0), lambda: il['dmsIllumLightOutputStatus'])
        self._ri_ro(_oid(7, 9, 0), lambda: il['dmsIllumBrightnessValuesError'])

        # Brightness values table  dms.7.7.1.<col>.<level>
        for lv, row in s.illum_brightness_table.items():
            self._ri_ro(_oid(7, 7, 1, 1, lv),
                lambda r=row: r['dmsIllumBrightnessLevel'])
            self._ri_rw(_oid(7, 7, 1, 2, lv),
                lambda r=row: r['dmsIllumPhotocellLevelRange'],
                lambda v, r=row: r.__setitem__('dmsIllumPhotocellLevelRange', v))
            self._ri_rw(_oid(7, 7, 1, 3, lv),
                lambda r=row: r['dmsIllumBrightnessOutput'],
                lambda v, r=row: r.__setitem__('dmsIllumBrightnessOutput', v))

    # ==================================================================
    # 5.9  Scheduling Action Objects  —  dms.8
    # ==================================================================

    def _build_scheduling(self):
        s = self.store

        self._ri_rw(_oid(8, 1, 0),
            lambda: s.action_num_entries,
            lambda v: setattr(s, 'action_num_entries', v))

        # Action table  dms.8.2.1.<col>.<row>
        for row in range(1, len(s.action_table) + 1):
            at = s.action_table
            self._ri_ro(_oid(8, 2, 1, 1, row),
                lambda r=row: at[r]['dmsActionIndex'])
            self._ro_rw(_oid(8, 2, 1, 2, row),
                lambda r=row: at[r]['dmsActionMsgCode'],
                lambda v, r=row: at[r].__setitem__('dmsActionMsgCode', v))
            self._ri_rw(_oid(8, 2, 1, 3, row),
                lambda r=row: at[r]['dmsActionStartMinute'],
                lambda v, r=row: at[r].__setitem__('dmsActionStartMinute', v))
            self._ri_rw(_oid(8, 2, 1, 4, row),
                lambda r=row: at[r]['dmsActionStopMinute'],
                lambda v, r=row: at[r].__setitem__('dmsActionStopMinute', v))
            self._ri_rw(_oid(8, 2, 1, 5, row),
                lambda r=row: at[r]['dmsActionDayBitmap'],
                lambda v, r=row: at[r].__setitem__('dmsActionDayBitmap', v))

    # ==================================================================
    # 5.11  Sign Status  —  dms.9
    # ==================================================================

    def _build_sign_status(self):
        s = self.store
        st = s.status

        # 5.11.1 Core status
        self._ri_ro(_oid(9, 1, 0), lambda: st['dmsSignStatus'])
        self._ri_ro(_oid(9, 2, 0), lambda: st['shortErrorStatus'])

        # 5.11.2 Error objects
        self._ri_ro(_oid(9, 3, 0),  lambda: st['dmsPixelFailureByteCount'])
        self._ri_ro(_oid(9, 4, 0),  lambda: st['dmsPixelFailureMessageCount'])
        # Pixel failure table omitted (empty in simulation)
        self._ri_ro(_oid(9, 6, 0),  lambda: st['dmsStatCurrentErrors'])
        self._ri_ro(_oid(9, 7, 0),  lambda: st['dmsStatDoorOpen'])
        self._ri_ro(_oid(9, 8, 0),  lambda: st['dmsHumidityPercent'])

        # 5.11.3 Power status
        self._ri_ro(_oid(9, 9, 0),  lambda: s.power_num_rows)
        for row, pw in s.power_table.items():
            self._ri_ro(_oid(9, 10, 1, 1, row), lambda r=pw: r['dmsPowerIndex'])
            self._ri_ro(_oid(9, 10, 1, 2, row), lambda r=pw: r['dmsPowerType'])
            self._gauge( _oid(9, 10, 1, 3, row), lambda r=pw: r['dmsPowerVoltage'])
            self._ri_ro(_oid(9, 10, 1, 4, row), lambda r=pw: r['dmsPowerStatus'])

        # 5.11.4 Temperature status
        ts = s.temp_status
        self._ri_ro(_oid(9, 11, 0), lambda: ts['dmsMinCabinetTemp'])
        self._ri_ro(_oid(9, 12, 0), lambda: ts['dmsMaxCabinetTemp'])
        self._ri_ro(_oid(9, 13, 0), lambda: ts['dmsMinAmbientTemp'])
        self._ri_ro(_oid(9, 14, 0), lambda: ts['dmsMaxAmbientTemp'])
        self._ri_ro(_oid(9, 15, 0), lambda: ts['dmsMinSignHousingTemp'])
        self._ri_ro(_oid(9, 16, 0), lambda: ts['dmsMaxSignHousingTemp'])

    # ==================================================================
    # 5.12  Graphic Definition Objects  —  dms.10
    # ==================================================================

    def _build_graphic_group(self):
        s = self.store

        self._ri_ro(_oid(10, 1, 0), lambda: s.max_graphics)
        self._ri_ro(_oid(10, 2, 0), lambda: s.num_graphics)
        self._ri_ro(_oid(10, 3, 0), lambda: s.max_graphic_size)
        self._gauge( _oid(10, 4, 0), lambda: s.available_graphic_mem)
        self._ri_ro(_oid(10, 5, 0), lambda: s.graphic_block_size)

        # Graphic table  dms.10.6.1.<col>.<graphicIndex>
        for gi, row in s.graphic_table.items():
            self._ri_ro(_oid(10, 6, 1, 1, gi), lambda r=row: r['dmsGraphicIndex'])
            self._ri_rw(_oid(10, 6, 1, 2, gi),
                lambda r=row: r['dmsGraphicNumber'],
                lambda v, r=row: r.__setitem__('dmsGraphicNumber', v))
            self._ro_rw(_oid(10, 6, 1, 3, gi),
                lambda r=row: r['dmsGraphicName'],
                lambda v, r=row: r.__setitem__('dmsGraphicName', v))
            self._ri_ro(_oid(10, 6, 1, 4, gi), lambda r=row: r['dmsGraphicHeight'])
            self._ri_ro(_oid(10, 6, 1, 5, gi), lambda r=row: r['dmsGraphicWidth'])
            self._ri_ro(_oid(10, 6, 1, 6, gi), lambda r=row: r['dmsGraphicType'])
            self._ri_ro(_oid(10, 6, 1, 7, gi), lambda r=row: r['dmsGraphicID'])
            self._ri_rw(_oid(10, 6, 1, 8, gi),
                lambda r=row: r['dmsGraphicStatus'],
                lambda v, r=row: r.__setitem__('dmsGraphicStatus', v))

        # Graphic bitmap table  dms.10.7.1.<col>.<graphicIndex>.<blockIndex>
        for (gi, bi), row in s.graphic_bitmap_table.items():
            self._ri_ro(_oid(10, 7, 1, 1, gi, bi), lambda r=row: r['dmsGraphicBitmapIndex'])
            self._ri_ro(_oid(10, 7, 1, 2, gi, bi), lambda r=row: r['dmsGraphicBlockIndex'])
            self._ro_rw(_oid(10, 7, 1, 3, gi, bi),
                lambda r=row: r['dmsGraphicBlockBitmap'],
                lambda v, r=row: r.__setitem__('dmsGraphicBlockBitmap', v))
