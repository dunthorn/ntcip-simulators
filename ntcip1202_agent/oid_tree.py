"""
oid_tree.py — NTCIP 1202 v4 OID Tree
Maps every OID in the ASC MIB to a getter/setter against the ASCDataStore.

OID prefix:  1.3.6.1.4.1.1206.4.2.1   (devices.asc)

Derived from NTCIP 1202 v04. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import time
import logging

log = logging.getLogger('ntcip1202_oid_tree')

# Optional pysnmp support (used only by the pysnmp-based OIDTree class)
try:
    from pysnmp.proto.api import v2c as _v2c
    _HAS_PYSNMP = True
except ImportError:
    _v2c = None
    _HAS_PYSNMP = False

# Root of the ASC MIB
_ASC = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 1)

def _oid(*tail):
    return _ASC + tuple(tail)


# ---------------------------------------------------------------------------
# Helper converters: Python native → pysnmp value objects
# (only used if pysnmp is available)
# ---------------------------------------------------------------------------

def _int(v):
    return _v2c.Integer(int(v)) if _HAS_PYSNMP else int(v)

def _uint(v):
    return _v2c.Gauge32(int(v) & 0xFFFFFFFF) if _HAS_PYSNMP else int(v)

def _counter(v):
    return _v2c.Counter32(int(v) & 0xFFFFFFFF) if _HAS_PYSNMP else int(v)

def _octets(v):
    if isinstance(v, (bytes, bytearray)):
        return _v2c.OctetString(bytes(v)) if _HAS_PYSNMP else bytes(v)
    return _v2c.OctetString(v) if _HAS_PYSNMP else v

def _str(v):
    if isinstance(v, (bytes, bytearray)):
        return _v2c.OctetString(v) if _HAS_PYSNMP else v
    return _v2c.OctetString(str(v).encode()) if _HAS_PYSNMP else str(v).encode()


# ---------------------------------------------------------------------------
# OIDTree
# ---------------------------------------------------------------------------

class OIDTree:
    """
    Provides get / get_next / set for the full NTCIP 1202 OID space.

    Internally built as a sorted list of (oid_tuple, getter, setter) triples.
    """

    def __init__(self, store):
        self.store = store
        self._entries = []   # list of (oid, getter_fn, setter_fn)
        self._build()
        self._entries.sort(key=lambda e: e[0])
        log.info(f"OID tree built: {len(self._entries)} OIDs registered")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, oid):
        """Return pysnmp value for oid, or None if not found."""
        entry = self._lookup(oid)
        if entry is None:
            return None
        try:
            return entry[1]()
        except Exception as e:
            log.warning(f"GET {oid}: {e}")
            return None

    def get_next(self, oid):
        """Return (next_oid, value) or (None, None)."""
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
        """Set oid to value. Returns True on success."""
        entry = self._lookup(oid)
        if entry is None or entry[2] is None:
            return False
        try:
            entry[2](value)
            return True
        except Exception as e:
            log.warning(f"SET {oid} = {value}: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal search helpers
    # ------------------------------------------------------------------

    def _lookup(self, oid):
        lo, hi = 0, len(self._entries) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            e = self._entries[mid]
            if e[0] == oid:
                return e
            elif e[0] < oid:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def _next_idx(self, oid):
        # Find first entry whose OID is strictly greater than oid
        lo, hi = 0, len(self._entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._entries[mid][0] <= oid:
                lo = mid + 1
            else:
                hi = mid
        return lo if lo < len(self._entries) else None

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def _reg(self, oid, getter, setter=None):
        self._entries.append((oid, getter, setter))

    def _reg_int_ro(self, oid, fn):
        self._reg(oid, lambda: _int(fn()))

    def _reg_int_rw(self, oid, getter_fn, setter_fn):
        self._reg(oid, lambda: _int(getter_fn()), lambda v: setter_fn(int(v)))

    def _reg_uint_ro(self, oid, fn):
        self._reg(oid, lambda: _uint(fn()))

    def _reg_oct_ro(self, oid, fn):
        self._reg(oid, lambda: _octets(fn()))

    def _reg_oct_rw(self, oid, getter_fn, setter_fn):
        self._reg(oid, lambda: _octets(getter_fn()),
                  lambda v: setter_fn(bytes(v)))

    def _reg_str_ro(self, oid, fn):
        self._reg(oid, lambda: _str(fn()))

    # ------------------------------------------------------------------
    # Build the full OID tree
    # ------------------------------------------------------------------

    def _build(self):
        self._build_phase_group()
        self._build_detector_group()
        self._build_unit_group()
        self._build_coord_group()
        self._build_timebase_group()
        self._build_preempt_group()
        self._build_channel_group()
        self._build_overlap_group()
        self._build_ts2port1_group()
        self._build_block_group()
        self._build_io_mapping_group()
        self._build_siu_port1_group()
        self._build_rsu_interface_group()
        self._build_spat_group()
        self._build_ecla_group()
        self._build_smu_group()

    # ==================================================================
    # 5.2  Phase  (asc.1)
    # ==================================================================

    def _build_phase_group(self):
        s = self.store

        # 5.2.1 maxPhases  .1.1.0
        self._reg_int_ro(_oid(1, 1, 0), lambda: s.max_phases)

        # 5.2.2 phaseTable  .1.2.1.<col>.<row>
        for idx, phase in s.phase_table.items():
            row = idx
            cols = [
                (2,  'phaseWalk',                        True),
                (3,  'phasePedestrianClear',              True),
                (4,  'phaseMinimumGreen',                 True),
                (5,  'phasePassage',                      True),
                (6,  'phaseMaximum1',                     True),
                (7,  'phaseMaximum2',                     True),
                (8,  'phaseYellowChange',                 True),
                (9,  'phaseRedClear',                     True),
                (10, 'phaseRedRevert',                    True),
                (11, 'phaseAddedInitial',                 True),
                (12, 'phaseMaximumInitial',               True),
                (13, 'phaseTimeBeforeReduction',          True),
                (14, 'phaseCarsBeforeReduction',          True),
                (15, 'phaseTimeToReduce',                 True),
                (16, 'phaseReduceBy',                     True),
                (17, 'phaseMinimumGap',                   True),
                (18, 'phaseDynamicMaxLimit',              True),
                (19, 'phaseDynamicMaxStep',               True),
                (20, 'phaseStartup',                      True),
                (21, 'phaseOptions',                      True),
                (22, 'phaseRing',                         True),
                (24, 'phaseMaximum3',                     True),
                (25, 'phasePedClearDuringVehicleClear',   True),
                (26, 'phasePedServiceLimit',              True),
                (27, 'phaseDontWalkRevert',               True),
                (28, 'phasePedAlternateClearance',        True),
                (29, 'phasePedAlternateWalk',             True),
                (30, 'phasePedAdvanceWalkTime',           True),
                (31, 'phasePedDelayTime',                 True),
                (32, 'phaseAdvWarnGrnStartTime',          True),
                (33, 'phaseAdvWarnRedStartTime',          True),
                (34, 'phaseAltMinTimeTransition',         True),
                (35, 'phaseWalkDuringTransition',         True),
                (36, 'phasePedClearDuringTransition',     True),
            ]
            for col, key, writable in cols:
                oid = _oid(1, 2, 1, col, row)
                if key == 'phaseConcurrency':
                    if writable:
                        self._reg_oct_rw(oid,
                            lambda k=key, r=row: s.phase_table[r][k],
                            lambda v, k=key, r=row: s.phase_table[r].__setitem__(k, v))
                    else:
                        self._reg_oct_ro(oid, lambda k=key, r=row: s.phase_table[r][k])
                else:
                    if writable:
                        self._reg_int_rw(oid,
                            lambda k=key, r=row: s.phase_table[r][k],
                            lambda v, k=key, r=row: s.phase_table[r].__setitem__(k, v))
                    else:
                        self._reg_int_ro(oid, lambda k=key, r=row: s.phase_table[r][k])

        # 5.2.3 phaseStatusGroupTable  .1.3.1.<col>.<row>
        status_cols = [
            (2, 'phaseStatusGroupReds'),
            (3, 'phaseStatusGroupYellows'),
            (4, 'phaseStatusGroupGreens'),
            (5, 'phaseStatusGroupDontWalks'),
            (6, 'phaseStatusGroupPedClears'),
            (7, 'phaseStatusGroupWalks'),
            (8, 'phaseStatusGroupVehCalls'),
            (9, 'phaseStatusGroupPedCalls'),
            (10,'phaseStatusGroupPhaseOns'),
            (11,'phaseStatusGroupPhaseNexts'),
        ]
        for row, sg in s.phase_status_groups.items():
            for col, key in status_cols:
                oid = _oid(1, 3, 1, col, row)
                self._reg_oct_ro(oid, lambda k=key, r=row: s.phase_status_groups[r][k])

        # 5.2.4 phaseControlGroupTable  .1.4.1.<col>.<row>
        ctrl_cols = [
            (2, 'phaseControlGroupPhaseOmit'),
            (3, 'phaseControlGroupPedOmit'),
            (4, 'phaseControlGroupHold'),
            (5, 'phaseControlGroupForceOff'),
            (6, 'phaseControlGroupVehCall'),
            (7, 'phaseControlGroupPedCall'),
        ]
        for row, cg in s.phase_control_groups.items():
            for col, key in ctrl_cols:
                oid = _oid(1, 4, 1, col, row)
                self._reg_oct_rw(oid,
                    lambda k=key, r=row: s.phase_control_groups[r][k],
                    lambda v, k=key, r=row: s.phase_control_groups[r].__setitem__(k, v))

        # 5.2.5 Phase Set scalars
        self._reg_int_ro(_oid(1, 5, 0), lambda: s.max_phase_sets)

        # phaseSetTable  .1.6.1.<col>.<phaseRow>.<setRow>
        pset_cols = [
            (3,  'phaseSetWalk',                        True),
            (4,  'phaseSetPedestrianClear',              True),
            (5,  'phaseSetMinimumGreen',                 True),
            (6,  'phaseSetPassage',                      True),
            (7,  'phaseSetMaximum1',                     True),
            (8,  'phaseSetMaximum2',                     True),
            (9,  'phaseSetYellowChange',                 True),
            (10, 'phaseSetRedClear',                     True),
            (11, 'phaseSetRedRevert',                    True),
            (12, 'phaseSetAddedInitial',                 True),
            (13, 'phaseSetMaximumInitial',               True),
            (14, 'phaseSetTimeBeforeReduction',          True),
            (15, 'phaseSetCarsBeforeReduction',          True),
            (16, 'phaseSetTimeToReduce',                 True),
            (17, 'phaseSetReduceBy',                     True),
            (18, 'phaseSetMinimumGap',                   True),
            (19, 'phaseSetDynamicMaxLimit',              True),
            (20, 'phaseSetDynamicMaxStep',               True),
            (24, 'phaseSetMaximum3',                     True),
            (25, 'phaseSetPedClearDuringVehicleClear',   True),
            (26, 'phaseSetPedServiceLimit',              True),
            (27, 'phaseSetDontWalkRevert',               True),
            (28, 'phaseSetPedAlternateClearance',        True),
            (29, 'phaseSetPedAlternateWalk',             True),
            (30, 'phaseSetPedAdvanceWalkTime',           True),
            (31, 'phaseSetPedDelayTime',                 True),
            (32, 'phaseSetAdvWarnGrnStartTime',          True),
            (33, 'phaseSetAdvWarnRedStartTime',          True),
            (34, 'phaseSetAltMinTimeTransition',         True),
            (35, 'phaseSetWalkDuringTransition',         True),
            (36, 'phaseSetPedClearDuringTransition',     True),
        ]
        for (ph, ps), row_data in s.phase_set_table.items():
            for col, key, writable in pset_cols:
                oid = _oid(1, 6, 1, col, ph, ps)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, p=ph, pss=ps: s.phase_set_table[(p, pss)][k],
                        lambda v, k=key, p=ph, pss=ps: s.phase_set_table[(p, pss)].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, p=ph, pss=ps: s.phase_set_table[(p, pss)][k])

    # ==================================================================
    # 5.3  Detector  (asc.2)
    # ==================================================================

    def _build_detector_group(self):
        s = self.store

        # 5.3.1 maxVehicleDetectors  .2.1.0
        self._reg_int_ro(_oid(2, 1, 0), lambda: s.max_vehicle_detectors)

        # 5.3.5 maxPedestrianDetectors  .2.5.0
        self._reg_int_ro(_oid(2, 5, 0), lambda: s.max_pedestrian_detectors)

        # vehicleDetectorTable  .2.2.1.<col>.<row>
        det_cols = [
            (2,  'detectorType',           True),
            (3,  'detectorCallPhase',      True),
            (4,  'detectorSwitchPhase',    True),
            (5,  'detectorOptions',        True),
            (6,  'detectorCallDelay',      True),
            (7,  'detectorExtension',      True),
            (8,  'detectorRecallMode',     True),
            (9,  'detectorAlarmState',     False),
            (10, 'detectorAlarmThreshold', True),
            (11, 'detectorVolume',         False),
            (12, 'detectorOccupancy',      False),
            (13, 'detectorClassify',       True),
            (15, 'detectorZoneLength',     True),
            (16, 'detectorQueueLimit',     True),
            (17, 'detectorQueue',          False),
            (18, 'detectorNoActivity',     True),
            (19, 'detectorMaxPresence',    True),
            (20, 'detectorErraticCounts',  True),
        ]
        for row, det in s.detector_table.items():
            for col, key, writable in det_cols:
                oid = _oid(2, 2, 1, col, row)
                if key == 'detectorStatus':
                    self._reg_oct_ro(oid, lambda k=key, r=row: s.detector_table[r][k])
                elif writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.detector_table[r][k],
                        lambda v, k=key, r=row: s.detector_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.detector_table[r][k])

            # detectorStatus as octet string  col 14
            self._reg_oct_ro(_oid(2, 2, 1, 14, row),
                lambda r=row: s.detector_table[r]['detectorStatus'])

    # ==================================================================
    # 5.4  Unit  (asc.3)
    # ==================================================================

    def _build_unit_group(self):
        s = self.store
        u = s.unit_scalars

        int_scalars = [
            (1,  'unitStartUpFlash',       True),
            (2,  'unitAlarmState1',        False),
            (3,  'unitAlarmState2',        False),
            (4,  'unitFlash',              True),
            (5,  'unitSignalPlan',         False),
            (6,  'unitOffset',             False),
            (7,  'unitMode',               False),
            (8,  'unitControl',            True),
            (13, 'unitFaultMonitor',       False),
        ]
        for sub, key, writable in int_scalars:
            oid = _oid(3, sub, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.unit_scalars[k],
                    lambda v, k=key: s.unit_scalars.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.unit_scalars[k])

        # Octet string scalars
        self._reg_oct_ro(_oid(3, 9, 0),  lambda: s.unit_scalars['unitInputFunction'])
        self._reg_oct_ro(_oid(3, 11, 0), lambda: s.unit_scalars['unitRingControl'])

        # Counter
        self._reg(_oid(3, 10, 0),
                  lambda: _counter(s.unit_scalars.get('unitCounterActuations', 0)))

        # String scalars
        self._reg_str_ro(_oid(3, 14, 0), lambda: s.unit_scalars['unitControllerID'])
        self._reg_str_ro(_oid(3, 15, 0), lambda: s.unit_scalars['unitFirmwareVersion'])

        # maxUnitAlarms  .3.12.0
        self._reg_int_ro(_oid(3, 12, 0), lambda: s.unit_scalars['maxUnitAlarms'])

        # unitAlarmTable  .3.13.1.<col>.<row>
        alarm_cols = [
            (1, 'unitAlarmNumber',  False),
            (2, 'unitAlarmCode',    False),
            (3, 'unitAlarmTime',    False),
            (4, 'unitAlarmState',   False),
        ]
        for row, alarm in s.unit_alarm_table.items():
            for col, key, _ in alarm_cols:
                oid = _oid(3, 13, 1, col, row)
                if key == 'unitAlarmTime':
                    self._reg_oct_ro(oid, lambda k=key, r=row: s.unit_alarm_table[r][k])
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.unit_alarm_table[r][k])

    # ==================================================================
    # 5.5  Coordination  (asc.4)
    # ==================================================================

    def _build_coord_group(self):
        s = self.store

        coord_int = [
            (1, 'coordOperationalMode',  True),
            (2, 'coordPatternNumber',    False),
            (3, 'coordCycleNumber',      False),
            (4, 'coordSplitNumber',      False),
            (5, 'coordOffset',           False),
            (6, 'coordMaximumMode',      True),
            (7, 'coordYieldPhase',       True),
        ]
        for sub, key, writable in coord_int:
            oid = _oid(4, sub, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.coord_scalars[k],
                    lambda v, k=key: s.coord_scalars.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.coord_scalars[k])

        # maxCycles  .4.8.0
        self._reg_int_ro(_oid(4, 8, 0), lambda: s.max_cycles)

        # coordCycleTable  .4.9.1.<col>.<row>
        for row, cyc in s.coord_cycle_table.items():
            self._reg_int_ro(_oid(4, 9, 1, 1, row), lambda r=row: s.coord_cycle_table[r]['coordCycleNumber'])
            self._reg_int_rw(_oid(4, 9, 1, 2, row),
                lambda r=row: s.coord_cycle_table[r]['coordCycleLength'],
                lambda v, r=row: s.coord_cycle_table[r].__setitem__('coordCycleLength', v))

        # maxSplits  .4.10.0
        self._reg_int_ro(_oid(4, 10, 0), lambda: s.max_splits)

        # coordSplitTable  .4.11.1.<col>.<splitRow>.<phaseRow>
        for (sp, ph), row_data in s.coord_split_table.items():
            self._reg_int_rw(_oid(4, 11, 1, 2, sp, ph),
                lambda spx=sp, phx=ph: s.coord_split_table[(spx, phx)]['coordSplitPhase'],
                lambda v, spx=sp, phx=ph: s.coord_split_table[(spx, phx)].__setitem__('coordSplitPhase', v))

        # maxCoordPatterns  .4.12.0
        self._reg_int_ro(_oid(4, 12, 0), lambda: s.max_coord_patterns)

        # coordPatternTable  .4.13.1.<col>.<row>
        pat_cols = [
            (2, 'coordPatternCycleNum',  True),
            (3, 'coordPatternSplitNum',  True),
            (4, 'coordPatternOffsetNum', True),
            (5, 'coordPatternMode',      True),
        ]
        for row, pat in s.coord_pattern_table.items():
            self._reg_int_ro(_oid(4, 13, 1, 1, row), lambda r=row: s.coord_pattern_table[r]['coordPatternNumber'])
            for col, key, writable in pat_cols:
                oid = _oid(4, 13, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.coord_pattern_table[r][k],
                        lambda v, k=key, r=row: s.coord_pattern_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.coord_pattern_table[r][k])

    # ==================================================================
    # 5.6  Time Base  (asc.5)
    # ==================================================================

    def _build_timebase_group(self):
        s = self.store

        # timebaseAscPatternSync  .5.1.0
        self._reg_int_rw(_oid(5, 1, 0),
            lambda: s.timebase_scalars['timebaseAscPatternSync'],
            lambda v: s.timebase_scalars.__setitem__('timebaseAscPatternSync', v))

        # ASC Clock  .5.2.x
        clock_cols = [
            (1, 'ascTimeDayOfWeek'),
            (2, 'ascTimeDayOfMonth'),
            (3, 'ascTimeMonthOfYear'),
            (4, 'ascTimeYear'),
            (5, 'ascTimeHours'),
            (6, 'ascTimeMinutes'),
            (7, 'ascTimeSeconds'),
            (8, 'ascTimeSystemStart'),
        ]
        for sub, key in clock_cols:
            # Dynamic: read from system clock each time
            if key == 'ascTimeSystemStart':
                start = time.time()
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda st=start: int(time.time() - st))
            elif key == 'ascTimeYear':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_year)
            elif key == 'ascTimeMonthOfYear':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_mon)
            elif key == 'ascTimeDayOfMonth':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_mday)
            elif key == 'ascTimeDayOfWeek':
                # NTCIP: 1=Sunday ... 7=Saturday; Python: 0=Monday
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: (time.localtime().tm_wday + 1) % 7 + 1)
            elif key == 'ascTimeHours':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_hour)
            elif key == 'ascTimeMinutes':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_min)
            elif key == 'ascTimeSeconds':
                self._reg_int_ro(_oid(5, 2, sub, 0),
                    lambda: time.localtime().tm_sec)

        # maxTimeBaseSchedules  .5.3.0
        self._reg_int_ro(_oid(5, 3, 0), lambda: s.max_time_base_schedules)

        # timebaseScheduleTable  .5.4.1.<col>.<row>
        for row, sched in s.timebase_schedule_table.items():
            sched_cols = [
                (2, 'timebaseScheduleMonth', True),
                (3, 'timebaseScheduleDay',   True),
                (4, 'timebaseSchedulePlan',  True),
            ]
            for col, key, writable in sched_cols:
                oid = _oid(5, 4, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.timebase_schedule_table[r][k],
                        lambda v, k=key, r=row: s.timebase_schedule_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.timebase_schedule_table[r][k])

        # maxDayPlans  .5.5.0
        self._reg_int_ro(_oid(5, 5, 0), lambda: s.max_day_plans)

        # dayPlanTable  .5.6.1.<col>.<planRow>.<eventRow>
        for plan, events in s.day_plan_table.items():
            for event, evt in events.items():
                evt_cols = [
                    (2, 'dayPlanHour',       True),
                    (3, 'dayPlanMinute',     True),
                    (4, 'dayPlanPatternNum', True),
                ]
                for col, key, writable in evt_cols:
                    oid = _oid(5, 6, 1, col, plan, event)
                    if writable:
                        self._reg_int_rw(oid,
                            lambda k=key, p=plan, e=event: s.day_plan_table[p][e][k],
                            lambda v, k=key, p=plan, e=event: s.day_plan_table[p][e].__setitem__(k, v))
                    else:
                        self._reg_int_ro(oid, lambda k=key, p=plan, e=event: s.day_plan_table[p][e][k])

    # ==================================================================
    # 5.7  Preempt  (asc.6)
    # ==================================================================

    def _build_preempt_group(self):
        s = self.store

        # maxPreempts  .6.1.0
        self._reg_int_ro(_oid(6, 1, 0), lambda: s.max_preempts)

        # preemptTable  .6.2.1.<col>.<row>
        pre_cols = [
            (2,  'preemptState',          False),
            (3,  'preemptLinkActive',     True),
            (4,  'preemptDelay',          True),
            (5,  'preemptPhase',          True),
            (6,  'preemptMinGreen',       True),
            (7,  'preemptYellowChange',   True),
            (8,  'preemptRedClear',       True),
            (9,  'preemptTrackGreen',     True),
            (10, 'preemptDwellTime',      True),
            (11, 'preemptExitPhase',      True),
            (12, 'preemptExitMinGreen',   True),
            (13, 'preemptLinkedExit',     True),
        ]
        for row, pre in s.preempt_table.items():
            for col, key, writable in pre_cols:
                oid = _oid(6, 2, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.preempt_table[r][k],
                        lambda v, k=key, r=row: s.preempt_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.preempt_table[r][k])

    # ==================================================================
    # 5.9  Channel  (asc.8)
    # ==================================================================

    def _build_channel_group(self):
        s = self.store

        # maxChannels  .8.1.0
        self._reg_int_ro(_oid(8, 1, 0), lambda: s.max_channels)

        # channelTable  .8.2.1.<col>.<row>
        ch_cols = [
            (2, 'channelControlSource', True),
            (3, 'channelControlType',   True),
            (4, 'channelOptions',       True),
        ]
        for row, ch in s.channel_table.items():
            for col, key, writable in ch_cols:
                oid = _oid(8, 2, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.channel_table[r][k],
                        lambda v, k=key, r=row: s.channel_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.channel_table[r][k])

    # ==================================================================
    # 5.10  Overlap  (asc.9)
    # ==================================================================

    def _build_overlap_group(self):
        s = self.store

        # maxOverlaps  .9.1.0
        self._reg_int_ro(_oid(9, 1, 0), lambda: s.max_overlaps)

        # overlapTable  .9.2.1.<col>.<row>
        ov_cols = [
            (2, 'overlapType',             True),
            (3, 'overlapOptions',          True),
            (6, 'overlapYellowChange',     True),
            (7, 'overlapRedClear',         True),
            (8, 'overlapTrailGreen',       True),
        ]
        ov_oct_cols = [
            (4, 'overlapIncludedPhases'),
            (5, 'overlapModifierPhases'),
            (9, 'overlapStatus'),
        ]
        for row, ov in s.overlap_table.items():
            for col, key, writable in ov_cols:
                oid = _oid(9, 2, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.overlap_table[r][k],
                        lambda v, k=key, r=row: s.overlap_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.overlap_table[r][k])
            for col, key in ov_oct_cols:
                oid = _oid(9, 2, 1, col, row)
                self._reg_oct_rw(oid,
                    lambda k=key, r=row: s.overlap_table[r][k],
                    lambda v, k=key, r=row: s.overlap_table[r].__setitem__(k, v))

    # ==================================================================
    # 5.11  TS2 Port 1  (asc.10)
    # ==================================================================

    def _build_ts2port1_group(self):
        s = self.store

        # maxPort1Addresses  .10.1.0
        self._reg_int_ro(_oid(10, 1, 0), lambda: s.max_port1_addresses)

        ts2_cols = [
            (2, 'ts2Port1PhaseOmit', True),
            (3, 'ts2Port1PedOmit',   True),
            (4, 'ts2Port1Hold',      True),
            (5, 'ts2Port1CallVeh',   True),
            (6, 'ts2Port1CallPed',   True),
        ]
        ts2_oct_cols = [
            (7, 'ts2Port1IntervalInfo'),
        ]
        for row, ts2 in s.ts2port1_table.items():
            for col, key, writable in ts2_cols:
                oid = _oid(10, 2, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.ts2port1_table[r][k],
                        lambda v, k=key, r=row: s.ts2port1_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.ts2port1_table[r][k])
            for col, key in ts2_oct_cols:
                self._reg_oct_ro(_oid(10, 2, 1, col, row),
                    lambda k=key, r=row: s.ts2port1_table[r][k])

    # ==================================================================
    # 5.12  ASC Block  (asc.11)
    # ==================================================================

    def _build_block_group(self):
        s = self.store

        self._reg_oct_rw(_oid(11, 1, 0),
            lambda: s.asc_block['ascBlockGetControl'],
            lambda v: s.asc_block.__setitem__('ascBlockGetControl', v))

        self._reg_oct_rw(_oid(11, 2, 0),
            lambda: s.asc_block['ascBlockSetControl'],
            lambda v: s.asc_block.__setitem__('ascBlockSetControl', v))

        self._reg_oct_ro(_oid(11, 3, 0),
            lambda: s.asc_block['ascBlockData'])

    # ==================================================================
    # 5.13  I/O Mapping  (asc.13)
    # ==================================================================

    def _build_io_mapping_group(self):
        s = self.store

        # Control scalars
        io_ctrl_ints = [
            (1, 1, 'ascIOmapControlMode',    True),
            (1, 2, 'ascIOmapControlStatus',  False),
            (1, 3, 'ascIOmapControlCommand', True),
        ]
        for sub1, sub2, key, writable in io_ctrl_ints:
            oid = _oid(13, sub1, sub2, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.io_map_control[k],
                    lambda v, k=key: s.io_map_control.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.io_map_control[k])

        # maxIOInputs / maxIOOutputs  .13.2.0 / .13.3.0
        self._reg_int_ro(_oid(13, 2, 0), lambda: s.max_io_inputs)
        self._reg_int_ro(_oid(13, 3, 0), lambda: s.max_io_outputs)

        # ascIOinputMapTable  .13.4.1.<col>.<row>
        in_cols = [
            (2, 'ascIOinputFunction',   True),
            (3, 'ascIOinputState',      False),
            (4, 'ascIOinputOptions',    True),
            (5, 'ascIOinputParameter1', True),
            (6, 'ascIOinputParameter2', True),
            (7, 'ascIOinputParameter3', True),
            (8, 'ascIOinputParameter4', True),
            (9, 'ascIOinputParameter5', True),  # corrected from MIB notes
        ]
        for row in s.io_input_map:
            for col, key, writable in in_cols:
                oid = _oid(13, 4, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.io_input_map[r][k],
                        lambda v, k=key, r=row: s.io_input_map[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.io_input_map[r][k])

        # ascIOoutputMapTable  .13.5.1.<col>.<row>
        out_cols = [
            (2, 'ascIOoutputFunction', True),
            (3, 'ascIOoutputState',    False),
        ]
        for row in s.io_output_map:
            for col, key, writable in out_cols:
                oid = _oid(13, 5, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.io_output_map[r][k],
                        lambda v, k=key, r=row: s.io_output_map[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.io_output_map[r][k])

    # ==================================================================
    # 5.14  SIU Port 1  (asc.14)
    # ==================================================================

    def _build_siu_port1_group(self):
        s = self.store

        self._reg_int_ro(_oid(14, 1, 0), lambda: s.max_siu_port1_addresses)

        siu_cols = [
            (2, 'siuPort1PhaseOmit', True),
            (3, 'siuPort1PedOmit',   True),
            (4, 'siuPort1Hold',      True),
            (5, 'siuPort1CallVeh',   True),
            (6, 'siuPort1CallPed',   True),
        ]
        for row, siu in s.siu_port1_table.items():
            for col, key, writable in siu_cols:
                oid = _oid(14, 2, 1, col, row)
                if writable:
                    self._reg_int_rw(oid,
                        lambda k=key, r=row: s.siu_port1_table[r][k],
                        lambda v, k=key, r=row: s.siu_port1_table[r].__setitem__(k, v))
                else:
                    self._reg_int_ro(oid, lambda k=key, r=row: s.siu_port1_table[r][k])

    # ==================================================================
    # 5.15  RSU Interface  (asc.15)
    # ==================================================================

    def _build_rsu_interface_group(self):
        s = self.store

        rsu_int = [
            (1, 'rsuCommPort',     True),
            (2, 'rsuCommEnable',   True),
            (3, 'rsuCommProtocol', True),
        ]
        for sub, key, writable in rsu_int:
            oid = _oid(15, sub, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.rsu_scalars[k],
                    lambda v, k=key: s.rsu_scalars.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.rsu_scalars[k])

        self._reg_oct_rw(_oid(15, 4, 0),
            lambda: s.rsu_scalars['rsuCommIpAddress'],
            lambda v: s.rsu_scalars.__setitem__('rsuCommIpAddress', v))

    # ==================================================================
    # 5.16  SPaT  (asc.16)
    # ==================================================================

    def _build_spat_group(self):
        s = self.store

        self._reg_oct_ro(_oid(16, 1, 0), lambda: s.spat_scalars['spatTimestamp'])

        spat_int = [
            (2, 'spatMinEndTime',       False),
            (3, 'spatMaxEndTime',       False),
            (4, 'spatLikelyTime',       False),
            (5, 'spatConfidenceLevel',  False),
            (6, 'spatEnabled',          True),
        ]
        for sub, key, writable in spat_int:
            oid = _oid(16, sub, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.spat_scalars[k],
                    lambda v, k=key: s.spat_scalars.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.spat_scalars[k])

    # ==================================================================
    # 5.18  ECLA  (asc.18)
    # ==================================================================

    def _build_ecla_group(self):
        s = self.store

        ecla_int = [
            (1, 'eclaCommEnable',   True),
            (2, 'eclaCommPort',     True),
            (3, 'eclaCommProtocol', True),
            (5, 'eclaTimeout',      True),
        ]
        for sub, key, writable in ecla_int:
            oid = _oid(18, sub, 0)
            if writable:
                self._reg_int_rw(oid,
                    lambda k=key: s.ecla_scalars[k],
                    lambda v, k=key: s.ecla_scalars.__setitem__(k, v))
            else:
                self._reg_int_ro(oid, lambda k=key: s.ecla_scalars[k])

        self._reg_oct_rw(_oid(18, 4, 0),
            lambda: s.ecla_scalars['eclaCommIpAddress'],
            lambda v: s.ecla_scalars.__setitem__('eclaCommIpAddress', v))

    # ==================================================================
    # 5.19  SMU Monitoring  (asc.19)
    # ==================================================================

    def _build_smu_group(self):
        s = self.store

        # ascSmuTable  .19.1.1.<col>.<row>
        smu_cols = [
            (1, 'ascSmuChannel', False),
            (2, 'ascSmuColor',   False),
            (3, 'ascSmuState',   False),
            (4, 'ascSmuVoltage', False),
        ]
        for row, smu in s.smu_table.items():
            for col, key, writable in smu_cols:
                oid = _oid(19, 1, 1, col, row)
                self._reg_int_ro(oid, lambda k=key, r=row: s.smu_table[r][k])


# ---------------------------------------------------------------------------
# NativeOIDTree — same tree but getters return Python native values
# (int, bytes, str) instead of pysnmp objects.  Used by snmp_server.py.
# ---------------------------------------------------------------------------

class _NativeValue:
    """Thin wrapper so snmp_server can distinguish Counter from Gauge."""
    __slots__ = ('tag', 'value')
    def __init__(self, tag, value):
        self.tag  = tag
        self.value = value

NTAG_INTEGER = 'integer'
NTAG_COUNTER = 'counter'
NTAG_GAUGE   = 'gauge'
NTAG_OCTETS  = 'octets'
NTAG_STRING  = 'string'


class NativeOIDTree:
    """
    Drop-in replacement for OIDTree that returns plain Python values.
    The OIDTree above uses pysnmp types for its return values; this variant
    stores the same data but returns native types so snmp_server.py can
    encode them with its own BER encoder.
    """

    def __init__(self, store):
        self.store = store
        self._entries = []
        self._build()
        self._entries.sort(key=lambda e: e[0])

    # ------------------------------------------------------------------
    # Public API (same as OIDTree)
    # ------------------------------------------------------------------

    def get(self, oid):
        entry = self._lookup(oid)
        if entry is None:
            return None
        try:
            return entry[1]()
        except Exception as e:
            log.warning(f"GET {oid}: {e}")
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
        entry = self._lookup(oid)
        if entry is None or entry[2] is None:
            return False
        try:
            # Coerce: bytes SET value to int if setter expects int
            entry[2](value)
            return True
        except Exception as e:
            log.warning(f"SET {oid}={value}: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _lookup(self, oid):
        lo, hi = 0, len(self._entries) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            e = self._entries[mid]
            if e[0] == oid:   return e
            elif e[0] < oid:  lo = mid + 1
            else:             hi = mid - 1
        return None

    def _next_idx(self, oid):
        lo, hi = 0, len(self._entries)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._entries[mid][0] <= oid: lo = mid + 1
            else:                            hi = mid
        return lo if lo < len(self._entries) else None

    # Registration helpers
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

    def _rs_ro(self, oid, fn):
        v = fn()
        self._reg(oid, lambda fn=fn: (fn() if isinstance(fn(), (bytes,bytearray)) else fn().encode()))

    # ------------------------------------------------------------------
    # Build (mirrors OIDTree._build exactly, using native helpers)
    # ------------------------------------------------------------------

    def _build(self):
        self._build_phase()
        self._build_detector()
        self._build_unit()
        self._build_coord()
        self._build_timebase()
        self._build_preempt()
        self._build_channel()
        self._build_overlap()
        self._build_ts2port1()
        self._build_block()
        self._build_io_mapping()
        self._build_siu_port1()
        self._build_rsu()
        self._build_spat()
        self._build_ecla()
        self._build_smu()

    def _build_phase(self):
        s = self.store
        self._ri_ro(_oid(1,1,0), lambda: s.max_phases)

        for idx, phase in s.phase_table.items():
            row = idx
            int_cols = [
                (2,'phaseWalk',True),(3,'phasePedestrianClear',True),
                (4,'phaseMinimumGreen',True),(5,'phasePassage',True),
                (6,'phaseMaximum1',True),(7,'phaseMaximum2',True),
                (8,'phaseYellowChange',True),(9,'phaseRedClear',True),
                (10,'phaseRedRevert',True),(11,'phaseAddedInitial',True),
                (12,'phaseMaximumInitial',True),(13,'phaseTimeBeforeReduction',True),
                (14,'phaseCarsBeforeReduction',True),(15,'phaseTimeToReduce',True),
                (16,'phaseReduceBy',True),(17,'phaseMinimumGap',True),
                (18,'phaseDynamicMaxLimit',True),(19,'phaseDynamicMaxStep',True),
                (20,'phaseStartup',True),(21,'phaseOptions',True),
                (22,'phaseRing',True),(24,'phaseMaximum3',True),
                (25,'phasePedClearDuringVehicleClear',True),
                (26,'phasePedServiceLimit',True),(27,'phaseDontWalkRevert',True),
                (28,'phasePedAlternateClearance',True),(29,'phasePedAlternateWalk',True),
                (30,'phasePedAdvanceWalkTime',True),(31,'phasePedDelayTime',True),
                (32,'phaseAdvWarnGrnStartTime',True),(33,'phaseAdvWarnRedStartTime',True),
                (34,'phaseAltMinTimeTransition',True),(35,'phaseWalkDuringTransition',True),
                (36,'phasePedClearDuringTransition',True),
            ]
            for col, key, writable in int_cols:
                o = _oid(1,2,1,col,row)
                if writable:
                    self._ri_rw(o,
                        lambda k=key,r=row: s.phase_table[r][k],
                        lambda v,k=key,r=row: s.phase_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.phase_table[r][k])
            # phaseConcurrency col 23
            self._ro_rw(_oid(1,2,1,23,row),
                lambda r=row: s.phase_table[r]['phaseConcurrency'],
                lambda v,r=row: s.phase_table[r].__setitem__('phaseConcurrency',v))

        # phaseStatusGroupTable
        status_cols = [(2,'phaseStatusGroupReds'),(3,'phaseStatusGroupYellows'),
                       (4,'phaseStatusGroupGreens'),(5,'phaseStatusGroupDontWalks'),
                       (6,'phaseStatusGroupPedClears'),(7,'phaseStatusGroupWalks'),
                       (8,'phaseStatusGroupVehCalls'),(9,'phaseStatusGroupPedCalls'),
                       (10,'phaseStatusGroupPhaseOns'),(11,'phaseStatusGroupPhaseNexts')]
        for row in s.phase_status_groups:
            for col, key in status_cols:
                self._ro_ro(_oid(1,3,1,col,row),
                    lambda k=key,r=row: s.phase_status_groups[r][k])

        # phaseControlGroupTable
        ctrl_cols = [(2,'phaseControlGroupPhaseOmit'),(3,'phaseControlGroupPedOmit'),
                     (4,'phaseControlGroupHold'),(5,'phaseControlGroupForceOff'),
                     (6,'phaseControlGroupVehCall'),(7,'phaseControlGroupPedCall')]
        for row in s.phase_control_groups:
            for col, key in ctrl_cols:
                self._ro_rw(_oid(1,4,1,col,row),
                    lambda k=key,r=row: s.phase_control_groups[r][k],
                    lambda v,k=key,r=row: s.phase_control_groups[r].__setitem__(k,v))

        self._ri_ro(_oid(1,5,0), lambda: s.max_phase_sets)

        pset_cols = [
            (3,'phaseSetWalk',True),(4,'phaseSetPedestrianClear',True),
            (5,'phaseSetMinimumGreen',True),(6,'phaseSetPassage',True),
            (7,'phaseSetMaximum1',True),(8,'phaseSetMaximum2',True),
            (9,'phaseSetYellowChange',True),(10,'phaseSetRedClear',True),
            (11,'phaseSetRedRevert',True),(12,'phaseSetAddedInitial',True),
            (13,'phaseSetMaximumInitial',True),(14,'phaseSetTimeBeforeReduction',True),
            (15,'phaseSetCarsBeforeReduction',True),(16,'phaseSetTimeToReduce',True),
            (17,'phaseSetReduceBy',True),(18,'phaseSetMinimumGap',True),
            (19,'phaseSetDynamicMaxLimit',True),(20,'phaseSetDynamicMaxStep',True),
            (24,'phaseSetMaximum3',True),(25,'phaseSetPedClearDuringVehicleClear',True),
            (26,'phaseSetPedServiceLimit',True),(27,'phaseSetDontWalkRevert',True),
            (28,'phaseSetPedAlternateClearance',True),(29,'phaseSetPedAlternateWalk',True),
            (30,'phaseSetPedAdvanceWalkTime',True),(31,'phaseSetPedDelayTime',True),
            (32,'phaseSetAdvWarnGrnStartTime',True),(33,'phaseSetAdvWarnRedStartTime',True),
            (34,'phaseSetAltMinTimeTransition',True),(35,'phaseSetWalkDuringTransition',True),
            (36,'phaseSetPedClearDuringTransition',True),
        ]
        for (ph,ps) in s.phase_set_table:
            for col, key, writable in pset_cols:
                o = _oid(1,6,1,col,ph,ps)
                if writable:
                    self._ri_rw(o,
                        lambda k=key,p=ph,pss=ps: s.phase_set_table[(p,pss)][k],
                        lambda v,k=key,p=ph,pss=ps: s.phase_set_table[(p,pss)].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,p=ph,pss=ps: s.phase_set_table[(p,pss)][k])

    def _build_detector(self):
        s = self.store
        self._ri_ro(_oid(2,1,0), lambda: s.max_vehicle_detectors)
        self._ri_ro(_oid(2,5,0), lambda: s.max_pedestrian_detectors)
        det_cols = [
            (2,'detectorType',True),(3,'detectorCallPhase',True),
            (4,'detectorSwitchPhase',True),(5,'detectorOptions',True),
            (6,'detectorCallDelay',True),(7,'detectorExtension',True),
            (8,'detectorRecallMode',True),(9,'detectorAlarmState',False),
            (10,'detectorAlarmThreshold',True),(11,'detectorVolume',False),
            (12,'detectorOccupancy',False),(13,'detectorClassify',True),
            (15,'detectorZoneLength',True),(16,'detectorQueueLimit',True),
            (17,'detectorQueue',False),(18,'detectorNoActivity',True),
            (19,'detectorMaxPresence',True),(20,'detectorErraticCounts',True),
        ]
        for row in s.detector_table:
            for col, key, writable in det_cols:
                o = _oid(2,2,1,col,row)
                if writable:
                    self._ri_rw(o,
                        lambda k=key,r=row: s.detector_table[r][k],
                        lambda v,k=key,r=row: s.detector_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.detector_table[r][k])
            self._ro_ro(_oid(2,2,1,14,row),
                lambda r=row: s.detector_table[r]['detectorStatus'])

    def _build_unit(self):
        s = self.store
        int_scalars = [
            (1,'unitStartUpFlash',True),(2,'unitAlarmState1',False),
            (3,'unitAlarmState2',False),(4,'unitFlash',True),
            (5,'unitSignalPlan',False),(6,'unitOffset',False),
            (7,'unitMode',False),(8,'unitControl',True),
            (13,'unitFaultMonitor',False),
        ]
        for sub, key, writable in int_scalars:
            o = _oid(3,sub,0)
            if writable:
                self._ri_rw(o,
                    lambda k=key: s.unit_scalars[k],
                    lambda v,k=key: s.unit_scalars.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.unit_scalars[k])
        self._ro_ro(_oid(3,9,0),  lambda: s.unit_scalars['unitInputFunction'])
        self._ro_ro(_oid(3,11,0), lambda: s.unit_scalars['unitRingControl'])
        # counter32 for actuations
        self._reg(_oid(3,10,0),
                  lambda: ('counter', int(s.unit_scalars.get('unitCounterActuations',0))))
        self._ri_ro(_oid(3,12,0), lambda: s.unit_scalars['maxUnitAlarms'])
        self._ro_ro(_oid(3,14,0), lambda: s.unit_scalars['unitControllerID'])
        self._ro_ro(_oid(3,15,0), lambda: s.unit_scalars['unitFirmwareVersion'])
        for row in s.unit_alarm_table:
            self._ri_ro(_oid(3,13,1,1,row), lambda r=row: s.unit_alarm_table[r]['unitAlarmNumber'])
            self._ri_ro(_oid(3,13,1,2,row), lambda r=row: s.unit_alarm_table[r]['unitAlarmCode'])
            self._ro_ro(_oid(3,13,1,3,row), lambda r=row: s.unit_alarm_table[r]['unitAlarmTime'])
            self._ri_ro(_oid(3,13,1,4,row), lambda r=row: s.unit_alarm_table[r]['unitAlarmState'])

    def _build_coord(self):
        s = self.store
        coord_int = [
            (1,'coordOperationalMode',True),(2,'coordPatternNumber',False),
            (3,'coordCycleNumber',False),(4,'coordSplitNumber',False),
            (5,'coordOffset',False),(6,'coordMaximumMode',True),(7,'coordYieldPhase',True),
        ]
        for sub, key, writable in coord_int:
            o = _oid(4,sub,0)
            if writable:
                self._ri_rw(o, lambda k=key: s.coord_scalars[k],
                            lambda v,k=key: s.coord_scalars.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.coord_scalars[k])
        self._ri_ro(_oid(4,8,0), lambda: s.max_cycles)
        for row in s.coord_cycle_table:
            self._ri_ro(_oid(4,9,1,1,row), lambda r=row: s.coord_cycle_table[r]['coordCycleNumber'])
            self._ri_rw(_oid(4,9,1,2,row),
                lambda r=row: s.coord_cycle_table[r]['coordCycleLength'],
                lambda v,r=row: s.coord_cycle_table[r].__setitem__('coordCycleLength',v))
        self._ri_ro(_oid(4,10,0), lambda: s.max_splits)
        for (sp,ph) in s.coord_split_table:
            self._ri_rw(_oid(4,11,1,2,sp,ph),
                lambda spx=sp,phx=ph: s.coord_split_table[(spx,phx)]['coordSplitPhase'],
                lambda v,spx=sp,phx=ph: s.coord_split_table[(spx,phx)].__setitem__('coordSplitPhase',v))
        self._ri_ro(_oid(4,12,0), lambda: s.max_coord_patterns)
        pat_cols = [(2,'coordPatternCycleNum',True),(3,'coordPatternSplitNum',True),
                    (4,'coordPatternOffsetNum',True),(5,'coordPatternMode',True)]
        for row in s.coord_pattern_table:
            self._ri_ro(_oid(4,13,1,1,row), lambda r=row: s.coord_pattern_table[r]['coordPatternNumber'])
            for col, key, writable in pat_cols:
                o = _oid(4,13,1,col,row)
                if writable:
                    self._ri_rw(o,
                        lambda k=key,r=row: s.coord_pattern_table[r][k],
                        lambda v,k=key,r=row: s.coord_pattern_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.coord_pattern_table[r][k])

    def _build_timebase(self):
        s = self.store
        self._ri_rw(_oid(5,1,0),
            lambda: s.timebase_scalars['timebaseAscPatternSync'],
            lambda v: s.timebase_scalars.__setitem__('timebaseAscPatternSync',v))
        start = time.time()
        clock_getters = {
            1: lambda: (time.localtime().tm_wday + 1) % 7 + 1,
            2: lambda: time.localtime().tm_mday,
            3: lambda: time.localtime().tm_mon,
            4: lambda: time.localtime().tm_year,
            5: lambda: time.localtime().tm_hour,
            6: lambda: time.localtime().tm_min,
            7: lambda: time.localtime().tm_sec,
            8: lambda st=start: int(time.time() - st),
        }
        for sub, gfn in clock_getters.items():
            self._ri_ro(_oid(5,2,sub,0), gfn)
        self._ri_ro(_oid(5,3,0), lambda: s.max_time_base_schedules)
        for row in s.timebase_schedule_table:
            for col, key in [(2,'timebaseScheduleMonth'),(3,'timebaseScheduleDay'),(4,'timebaseSchedulePlan')]:
                self._ri_rw(_oid(5,4,1,col,row),
                    lambda k=key,r=row: s.timebase_schedule_table[r][k],
                    lambda v,k=key,r=row: s.timebase_schedule_table[r].__setitem__(k,v))
        self._ri_ro(_oid(5,5,0), lambda: s.max_day_plans)
        for plan in s.day_plan_table:
            for event in s.day_plan_table[plan]:
                for col, key in [(2,'dayPlanHour'),(3,'dayPlanMinute'),(4,'dayPlanPatternNum')]:
                    self._ri_rw(_oid(5,6,1,col,plan,event),
                        lambda k=key,p=plan,e=event: s.day_plan_table[p][e][k],
                        lambda v,k=key,p=plan,e=event: s.day_plan_table[p][e].__setitem__(k,v))

    def _build_preempt(self):
        s = self.store
        self._ri_ro(_oid(6,1,0), lambda: s.max_preempts)
        pre_cols = [
            (2,'preemptState',False),(3,'preemptLinkActive',True),
            (4,'preemptDelay',True),(5,'preemptPhase',True),
            (6,'preemptMinGreen',True),(7,'preemptYellowChange',True),
            (8,'preemptRedClear',True),(9,'preemptTrackGreen',True),
            (10,'preemptDwellTime',True),(11,'preemptExitPhase',True),
            (12,'preemptExitMinGreen',True),(13,'preemptLinkedExit',True),
        ]
        for row in s.preempt_table:
            for col, key, writable in pre_cols:
                o = _oid(6,2,1,col,row)
                if writable:
                    self._ri_rw(o,
                        lambda k=key,r=row: s.preempt_table[r][k],
                        lambda v,k=key,r=row: s.preempt_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.preempt_table[r][k])

    def _build_channel(self):
        s = self.store
        self._ri_ro(_oid(8,1,0), lambda: s.max_channels)
        for row in s.channel_table:
            for col, key in [(2,'channelControlSource'),(3,'channelControlType'),(4,'channelOptions')]:
                self._ri_rw(_oid(8,2,1,col,row),
                    lambda k=key,r=row: s.channel_table[r][k],
                    lambda v,k=key,r=row: s.channel_table[r].__setitem__(k,v))

    def _build_overlap(self):
        s = self.store
        self._ri_ro(_oid(9,1,0), lambda: s.max_overlaps)
        ov_int  = [(2,'overlapType',True),(3,'overlapOptions',True),
                   (6,'overlapYellowChange',True),(7,'overlapRedClear',True),(8,'overlapTrailGreen',True)]
        ov_oct  = [(4,'overlapIncludedPhases'),(5,'overlapModifierPhases'),(9,'overlapStatus')]
        for row in s.overlap_table:
            for col, key, w in ov_int:
                o = _oid(9,2,1,col,row)
                if w:
                    self._ri_rw(o, lambda k=key,r=row: s.overlap_table[r][k],
                                lambda v,k=key,r=row: s.overlap_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.overlap_table[r][k])
            for col, key in ov_oct:
                self._ro_rw(_oid(9,2,1,col,row),
                    lambda k=key,r=row: s.overlap_table[r][k],
                    lambda v,k=key,r=row: s.overlap_table[r].__setitem__(k,v))

    def _build_ts2port1(self):
        s = self.store
        self._ri_ro(_oid(10,1,0), lambda: s.max_port1_addresses)
        ts2_int = [(2,'ts2Port1PhaseOmit',True),(3,'ts2Port1PedOmit',True),
                   (4,'ts2Port1Hold',True),(5,'ts2Port1CallVeh',True),(6,'ts2Port1CallPed',True)]
        for row in s.ts2port1_table:
            for col, key, w in ts2_int:
                o = _oid(10,2,1,col,row)
                if w:
                    self._ri_rw(o, lambda k=key,r=row: s.ts2port1_table[r][k],
                                lambda v,k=key,r=row: s.ts2port1_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.ts2port1_table[r][k])
            self._ro_ro(_oid(10,2,1,7,row), lambda r=row: s.ts2port1_table[r]['ts2Port1IntervalInfo'])

    def _build_block(self):
        s = self.store
        self._ro_rw(_oid(11,1,0),
            lambda: s.asc_block['ascBlockGetControl'],
            lambda v: s.asc_block.__setitem__('ascBlockGetControl',v))
        self._ro_rw(_oid(11,2,0),
            lambda: s.asc_block['ascBlockSetControl'],
            lambda v: s.asc_block.__setitem__('ascBlockSetControl',v))
        self._ro_ro(_oid(11,3,0), lambda: s.asc_block['ascBlockData'])

    def _build_io_mapping(self):
        s = self.store
        io_ctrl = [(1,1,'ascIOmapControlMode',True),(1,2,'ascIOmapControlStatus',False),
                   (1,3,'ascIOmapControlCommand',True)]
        for s1, s2, key, w in io_ctrl:
            o = _oid(13,s1,s2,0)
            if w:
                self._ri_rw(o, lambda k=key: s.io_map_control[k],
                            lambda v,k=key: s.io_map_control.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.io_map_control[k])
        self._ri_ro(_oid(13,2,0), lambda: s.max_io_inputs)
        self._ri_ro(_oid(13,3,0), lambda: s.max_io_outputs)
        in_cols = [(2,'ascIOinputFunction',True),(3,'ascIOinputState',False),
                   (4,'ascIOinputOptions',True),(5,'ascIOinputParameter1',True),
                   (6,'ascIOinputParameter2',True),(7,'ascIOinputParameter3',True),
                   (8,'ascIOinputParameter4',True),(9,'ascIOinputParameter5',True)]
        for row in s.io_input_map:
            for col, key, w in in_cols:
                o = _oid(13,4,1,col,row)
                if w:
                    self._ri_rw(o, lambda k=key,r=row: s.io_input_map[r][k],
                                lambda v,k=key,r=row: s.io_input_map[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.io_input_map[r][k])
        for row in s.io_output_map:
            self._ri_rw(_oid(13,5,1,2,row),
                lambda r=row: s.io_output_map[r]['ascIOoutputFunction'],
                lambda v,r=row: s.io_output_map[r].__setitem__('ascIOoutputFunction',v))
            self._ri_ro(_oid(13,5,1,3,row),
                lambda r=row: s.io_output_map[r]['ascIOoutputState'])

    def _build_siu_port1(self):
        s = self.store
        self._ri_ro(_oid(14,1,0), lambda: s.max_siu_port1_addresses)
        siu_cols = [(2,'siuPort1PhaseOmit',True),(3,'siuPort1PedOmit',True),
                    (4,'siuPort1Hold',True),(5,'siuPort1CallVeh',True),(6,'siuPort1CallPed',True)]
        for row in s.siu_port1_table:
            for col, key, w in siu_cols:
                o = _oid(14,2,1,col,row)
                if w:
                    self._ri_rw(o, lambda k=key,r=row: s.siu_port1_table[r][k],
                                lambda v,k=key,r=row: s.siu_port1_table[r].__setitem__(k,v))
                else:
                    self._ri_ro(o, lambda k=key,r=row: s.siu_port1_table[r][k])

    def _build_rsu(self):
        s = self.store
        rsu_int = [(1,'rsuCommPort',True),(2,'rsuCommEnable',True),(3,'rsuCommProtocol',True)]
        for sub, key, w in rsu_int:
            o = _oid(15,sub,0)
            if w:
                self._ri_rw(o, lambda k=key: s.rsu_scalars[k],
                            lambda v,k=key: s.rsu_scalars.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.rsu_scalars[k])
        self._ro_rw(_oid(15,4,0),
            lambda: s.rsu_scalars['rsuCommIpAddress'],
            lambda v: s.rsu_scalars.__setitem__('rsuCommIpAddress',v))

    def _build_spat(self):
        s = self.store
        self._ro_ro(_oid(16,1,0), lambda: s.spat_scalars['spatTimestamp'])
        spat_int = [(2,'spatMinEndTime',False),(3,'spatMaxEndTime',False),
                    (4,'spatLikelyTime',False),(5,'spatConfidenceLevel',False),(6,'spatEnabled',True)]
        for sub, key, w in spat_int:
            o = _oid(16,sub,0)
            if w:
                self._ri_rw(o, lambda k=key: s.spat_scalars[k],
                            lambda v,k=key: s.spat_scalars.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.spat_scalars[k])

    def _build_ecla(self):
        s = self.store
        ecla_int = [(1,'eclaCommEnable',True),(2,'eclaCommPort',True),
                    (3,'eclaCommProtocol',True),(5,'eclaTimeout',True)]
        for sub, key, w in ecla_int:
            o = _oid(18,sub,0)
            if w:
                self._ri_rw(o, lambda k=key: s.ecla_scalars[k],
                            lambda v,k=key: s.ecla_scalars.__setitem__(k,v))
            else:
                self._ri_ro(o, lambda k=key: s.ecla_scalars[k])
        self._ro_rw(_oid(18,4,0),
            lambda: s.ecla_scalars['eclaCommIpAddress'],
            lambda v: s.ecla_scalars.__setitem__('eclaCommIpAddress',v))

    def _build_smu(self):
        s = self.store
        for row in s.smu_table:
            for col, key in [(1,'ascSmuChannel'),(2,'ascSmuColor'),(3,'ascSmuState'),(4,'ascSmuVoltage')]:
                self._ri_ro(_oid(19,1,1,col,row), lambda k=key,r=row: s.smu_table[r][k])


# ===========================================================================
# Patch NativeOIDTree._build to include standard MIBs
# We monkey-patch here to avoid editing the generated block above.
# ===========================================================================

_native_build_orig = NativeOIDTree._build

def _native_build_patched(self):
    self._build_standard_mibs()
    _native_build_orig(self)

NativeOIDTree._build = _native_build_patched


def _build_standard_mibs(self):
    self._build_system_mib()
    self._build_interfaces_mib()
    self._build_snmp_mib()
    self._build_ntcip1201_mib()

NativeOIDTree._build_standard_mibs = _build_standard_mibs


# ------------------------------------------------------------------
# RFC 1213 system group  —  1.3.6.1.2.1.1
# ------------------------------------------------------------------
def _build_system_mib(self):
    s = self.store.system
    SYS = (1, 3, 6, 1, 2, 1, 1)
    def o(*t): return SYS + t

    self._ro_ro(o(1, 0), lambda: s.sysDescr)
    self._reg(o(2, 0),   lambda: ('oid', s.sysObjectID))
    self._reg(o(3, 0),   lambda: ('timeticks', s.sysUpTime))
    self._ro_rw(o(4, 0),
        lambda: s.sysContact,
        lambda v: setattr(s, 'sysContact', bytes(v)))
    self._ro_rw(o(5, 0),
        lambda: s.sysName,
        lambda v: setattr(s, 'sysName', bytes(v)))
    self._ro_rw(o(6, 0),
        lambda: s.sysLocation,
        lambda v: setattr(s, 'sysLocation', bytes(v)))
    self._ri_ro(o(7, 0), lambda: s.sysServices)

NativeOIDTree._build_system_mib = _build_system_mib


# ------------------------------------------------------------------
# RFC 1213 interfaces group  —  1.3.6.1.2.1.2
# ------------------------------------------------------------------
def _build_interfaces_mib(self):
    s = self.store.interfaces
    IFS = (1, 3, 6, 1, 2, 1, 2)
    def o(*t): return IFS + t

    self._ri_ro(o(1, 0), lambda: s.ifNumber)

    int_rw_cols  = [(8,  'ifAdminStatus')]
    int_ro_cols  = [(1,'ifIndex'),(3,'ifType'),(4,'ifMtu'),(9,'ifOperStatus'),
                    (13,'ifInNUcastPkts'),(14,'ifInDiscards'),(15,'ifInErrors'),
                    (16,'ifInUnknownProtos'),(18,'ifOutUcastPkts'),(19,'ifOutNUcastPkts'),
                    (20,'ifOutDiscards'),(21,'ifOutErrors'),(22,'ifOutQLen'),
                    (12,'ifInUcastPkts')]
    counter_cols = [(11,'ifInOctets'),(17,'ifOutOctets')]
    gauge_cols   = [(5, 'ifSpeed')]
    oct_ro_cols  = [(2,'ifDescr'),(6,'ifPhysAddress')]

    for row in s.if_table:
        for col, key in int_rw_cols:
            self._ri_rw(o(2, 1, col, row),
                lambda k=key, r=row: s.if_table[r][k],
                lambda v, k=key, r=row: s.if_table[r].__setitem__(k, v))
        for col, key in int_ro_cols:
            self._ri_ro(o(2, 1, col, row), lambda k=key, r=row: s.if_table[r][k])
        for col, key in counter_cols:
            self._reg(o(2, 1, col, row), lambda k=key, r=row: ('counter', s.if_table[r][k]))
        for col, key in gauge_cols:
            self._reg(o(2, 1, col, row), lambda k=key, r=row: ('gauge',   s.if_table[r][k]))
        for col, key in oct_ro_cols:
            self._ro_ro(o(2, 1, col, row), lambda k=key, r=row: s.if_table[r][k])
        # ifLastChange  col 10 — TimeTicks
        self._reg(o(2, 1, 10, row),
            lambda r=row: ('timeticks', s.if_table[r]['ifLastChange']))
        # ifSpecific  col 23 — OID
        self._reg(o(2, 1, 23, row),
            lambda r=row: ('oid', s.if_table[r]['ifSpecific']))

NativeOIDTree._build_interfaces_mib = _build_interfaces_mib


# ------------------------------------------------------------------
# RFC 1213 snmp group  —  1.3.6.1.2.1.11
# ------------------------------------------------------------------
def _build_snmp_mib(self):
    s = self.store.snmp_mib
    SNMP = (1, 3, 6, 1, 2, 1, 11)
    def o(*t): return SNMP + t

    counter_scalars = [
        (1,'snmpInPkts'),(2,'snmpOutPkts'),(3,'snmpInBadVersions'),
        (4,'snmpInBadCommunityNames'),(5,'snmpInBadCommunityUses'),
        (6,'snmpInASNParseErrs'),(8,'snmpInTooBigs'),(9,'snmpInNoSuchNames'),
        (10,'snmpInBadValues'),(11,'snmpInReadOnlys'),(12,'snmpInGenErrs'),
        (13,'snmpInTotalReqVars'),(14,'snmpInTotalSetVars'),
        (15,'snmpInGetRequests'),(16,'snmpInGetNexts'),(17,'snmpInSetRequests'),
        (18,'snmpInGetResponses'),(19,'snmpInTraps'),(20,'snmpOutTooBigs'),
        (21,'snmpOutNoSuchNames'),(22,'snmpOutBadValues'),(24,'snmpOutGenErrs'),
        (25,'snmpOutGetRequests'),(26,'snmpOutGetNexts'),(27,'snmpOutSetRequests'),
        (28,'snmpOutGetResponses'),(29,'snmpOutTraps'),
    ]
    for sub, attr in counter_scalars:
        self._reg(o(sub, 0), lambda a=attr: ('counter', getattr(s, a)))

    self._ri_rw(o(30, 0),
        lambda: s.snmpEnableAuthenTraps,
        lambda v: setattr(s, 'snmpEnableAuthenTraps', int(v)))

NativeOIDTree._build_snmp_mib = _build_snmp_mib


# ------------------------------------------------------------------
# NTCIP 1201 global objects  —  1.3.6.1.4.1.1206.4.2.6
# ------------------------------------------------------------------
def _build_ntcip1201_mib(self):
    s = self.store.ntcip1201
    N1201 = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 6)
    def o(*t): return N1201 + t

    self._ro_ro(o(1, 0), lambda: s.globalDescriptor)
    self._ri_rw(o(2, 0),
        lambda: s.globalSetIDParameter,
        lambda v: setattr(s, 'globalSetIDParameter', int(v)))
    self._ri_ro(o(3, 0), lambda: s.globalMaxModules)

    for row, mod in s.module_table.items():
        self._ri_ro(o(4, 1, 1, row),
            lambda r=row: s.module_table[r]['globalModuleNumber'])
        self._reg(o(4, 1, 2, row),
            lambda r=row: ('oid', s.module_table[r]['globalModuleDeviceNode']))
        self._ro_ro(o(4, 1, 3, row),
            lambda r=row: s.module_table[r]['globalModuleVersion'])
        self._ri_ro(o(4, 1, 4, row),
            lambda r=row: s.module_table[r]['globalModuleType'])
        self._ri_ro(o(4, 1, 5, row),
            lambda r=row: s.module_table[r]['globalModuleMinorVersion'])

    self._ro_rw(o(5, 0),
        lambda: s.globalLocalID,
        lambda v: setattr(s, 'globalLocalID', bytes(v)))
    self._ri_rw(o(6, 0),
        lambda: s.globalSystemAccess,
        lambda v: setattr(s, 'globalSystemAccess', int(v)))

NativeOIDTree._build_ntcip1201_mib = _build_ntcip1201_mib


# ===========================================================================
# Patch NativeOIDTree._build to include ring/sequence group (asc.7)
# ===========================================================================

_native_build_v2 = NativeOIDTree._build

def _native_build_v3(self):
    _native_build_v2(self)
    self._build_ring_group()

NativeOIDTree._build = _native_build_v3


def _build_ring_group(self):
    """
    5.8  Ring / Sequence  (asc.7)

    OID layout:
      .7.1.0                         maxRings
      .7.2.0                         maxSequences
      .7.3.1.<col>.<seqNum>.<ringNum>  sequenceTable
        col 3 = sequenceData (OCTET STRING, read-write)
      .7.4.0                         maxRingControlGroups
      .7.5.1.<col>.<grpNum>          ringControlGroupTable
        col 2..9 = control bitmask integers (read-write)
      .7.6.1.<col>.<ringNum>         ringStatusTable
        col 1 = ringStatus (Integer, read-only)
        col 2 = ringOnPhase (Integer, read-only)
        col 3 = ringOnPhaseDuration (Gauge32, read-only)
    """
    s = self.store

    # Scalars
    self._ri_ro(_oid(7, 1, 0), lambda: s.max_rings)
    self._ri_ro(_oid(7, 2, 0), lambda: s.max_sequences)

    # sequenceTable  .7.3.1.3.<seqNum>.<ringNum>
    # (cols 1 and 2 are not-accessible indexes; col 3 is the data)
    for (seq, ring), data in s.sequence_table.items():
        self._ro_rw(
            _oid(7, 3, 1, 3, seq, ring),
            lambda sq=seq, rn=ring: s.sequence_table[(sq, rn)],
            lambda v, sq=seq, rn=ring: s.sequence_table.__setitem__((sq, rn), bytes(v))
        )

    # maxRingControlGroups  .7.4.0
    self._ri_ro(_oid(7, 4, 0), lambda: s.max_ring_control_groups)

    # ringControlGroupTable  .7.5.1.<col>.<grpNum>
    rcg_cols = [
        (2, 'ringControlGroupStopTime'),
        (3, 'ringControlGroupForceOff'),
        (4, 'ringControlGroupMax2'),
        (5, 'ringControlGroupMaxInhibit'),
        (6, 'ringControlGroupPedRecycle'),
        (7, 'ringControlGroupRedRest'),
        (8, 'ringControlGroupOmitRedClear'),
        (9, 'ringControlGroupMax3'),
    ]
    for grp in s.ring_control_groups:
        self._ri_ro(_oid(7, 5, 1, 1, grp), lambda g=grp: g)   # index col (r-o)
        for col, key in rcg_cols:
            self._ri_rw(
                _oid(7, 5, 1, col, grp),
                lambda k=key, g=grp: s.ring_control_groups[g][k],
                lambda v, k=key, g=grp: s.ring_control_groups[g].__setitem__(k, v)
            )

    # ringStatusTable  .7.6.1.<col>.<ringNum>
    for ring in s.ring_status:
        self._ri_ro(_oid(7, 6, 1, 1, ring),
            lambda r=ring: s.ring_status[r]['ringStatus'])
        self._ri_ro(_oid(7, 6, 1, 2, ring),
            lambda r=ring: s.ring_status[r]['ringOnPhase'])
        # ringOnPhaseDuration is Unsigned32 (gauge)
        self._reg(_oid(7, 6, 1, 3, ring),
            lambda r=ring: ('gauge', s.ring_status[r]['ringOnPhaseDuration']))

NativeOIDTree._build_ring_group = _build_ring_group
