"""
rmc_oid_tree.py  —  NTCIP 1207 v02 RMC OID Tree

Maps every OID under rmc (1.3.6.1.4.1.1206.4.2.5) to a getter/setter
against the RMCDataStore.

Derived from NTCIP 1207 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import logging

log = logging.getLogger('ntcip1207_oid_tree')

# RMC root: devices.rmc = 1.3.6.1.4.1.1206.4.2.5
_RMC = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 5)

def _oid(*tail):
    return _RMC + tuple(tail)


class RMCOIDTree:
    """
    Sorted OID table for the NTCIP 1207 v02 RMC MIB.
    get() / get_next() / set() interface matches NativeOIDTree from the ASC agent.
    """

    def __init__(self, store):
        self.store    = store
        self._entries = []
        self._build()
        self._entries.sort(key=lambda e: e[0])
        log.info(f"RMC OID tree built: {len(self._entries)} OIDs")

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
        self._build_general_config()
        self._build_mainline_group()
        self._build_metered_lane_group()
        self._build_metering_plan_group()
        self._build_tbc_group()
        self._build_physical_io_group()
        self._build_block_group()

    # ==================================================================
    # 3.2  RMC General Configuration  —  rmc.1
    # ==================================================================

    def _build_general_config(self):
        s = self.store
        g = s.general

        # rmcCommRefreshThresholdTime  .1.1.0
        self._ri_rw(_oid(1, 1, 0),
            lambda: g['rmcCommRefreshThresholdTime'],
            lambda v: g.__setitem__('rmcCommRefreshThresholdTime', v))

        # rmcCalculationInterval  .1.2.0
        self._ri_rw(_oid(1, 2, 0),
            lambda: g['rmcCalculationInterval'],
            lambda v: g.__setitem__('rmcCalculationInterval', v))

    # ==================================================================
    # 3.3  Mainline Lane Configuration, Control and Status  —  rmc.3
    # ==================================================================

    def _build_mainline_group(self):
        s = self.store

        # Scalars
        self._ri_rw(_oid(3, 1, 0),
            lambda: s.mainline_averaging_periods,
            lambda v: setattr(s, 'mainline_averaging_periods', v))
        self._ri_ro(_oid(3, 2, 0), lambda: s.max_mainline_lanes)
        self._ri_ro(_oid(3, 3, 0), lambda: s.num_mainline_lanes)

        # Mainline lane configuration/control table  .3.4.1.<col>.<row>
        int_rw_cols = [
            (2, 'rmcMainlineLaneControlMode'),
            (3, 'rmcMainlineLaneDetectorStation'),
            (4, 'rmcMainlineLaneDetectorChannel'),
        ]
        int_ro_cols = [
            (5, 'rmcMainlineLaneFlowRate'),
            (6, 'rmcMainlineLaneOccupancy'),
            (7, 'rmcMainlineLaneSpeed'),
            (8, 'rmcMainlineLaneStatus'),
        ]

        for row in range(1, s.num_mainline_lanes + 1):
            self._ri_ro(_oid(3, 4, 1, 1, row),
                lambda r=row: s.mainline_lane_table[r]['rmcMainlineLaneIndex'])
            for col, key in int_rw_cols:
                self._ri_rw(_oid(3, 4, 1, col, row),
                    lambda k=key, r=row: s.mainline_lane_table[r][k],
                    lambda v, k=key, r=row: s.mainline_lane_table[r].__setitem__(k, v))
            for col, key in int_ro_cols:
                self._ri_ro(_oid(3, 4, 1, col, row),
                    lambda k=key, r=row: s.mainline_lane_table[r][k])

        # No-activity table scalars
        self._ri_ro(_oid(3, 5, 0), lambda: s.max_mainline_no_activity)
        self._ri_ro(_oid(3, 6, 0), lambda: s.num_mainline_no_activity)

        # No-activity table  .3.7.1.<col>.<row>
        for row, na in s.mainline_no_activity_table.items():
            self._ri_ro(_oid(3, 7, 1, 1, row),
                lambda r=row: s.mainline_no_activity_table[r]['rmcMainlineNoActivityIndex'])
            self._ri_rw(_oid(3, 7, 1, 2, row),
                lambda r=row: s.mainline_no_activity_table[r]['rmcMainlineNoActivityFlowRateMin'],
                lambda v, r=row: s.mainline_no_activity_table[r].__setitem__('rmcMainlineNoActivityFlowRateMin', v))
            self._ri_rw(_oid(3, 7, 1, 3, row),
                lambda r=row: s.mainline_no_activity_table[r]['rmcMainlineNoActivityFlowRateMax'],
                lambda v, r=row: s.mainline_no_activity_table[r].__setitem__('rmcMainlineNoActivityFlowRateMax', v))
            self._ri_rw(_oid(3, 7, 1, 4, row),
                lambda r=row: s.mainline_no_activity_table[r]['rmcMainlineNoActivityDuration'],
                lambda v, r=row: s.mainline_no_activity_table[r].__setitem__('rmcMainlineNoActivityDuration', v))

        # Station aggregates
        ms = s.mainline_station
        self._gauge(_oid(3, 8, 0), lambda: ms['rmcAvgMainlineStationFlowRate'])
        self._gauge(_oid(3, 9, 0), lambda: ms['rmcAvgMainlineStationOccupancy'])
        self._gauge(_oid(3, 10, 0), lambda: ms['rmcAvgMainlineStationSpeed'])
        self._ri_ro(_oid(3, 11, 0), lambda: ms['rmcNumFlowRateLanes'])
        self._ri_ro(_oid(3, 12, 0), lambda: ms['rmcNumOccupancyLanes'])
        self._ri_ro(_oid(3, 13, 0), lambda: ms['rmcNumAvgSpeedLanes'])

        # Mainline lane status table  .3.14.1.<col>.<row>
        for row in range(1, s.num_mainline_lanes + 1):
            self._ri_ro(_oid(3, 14, 1, 1, row),
                lambda r=row: s.mainline_lane_status_table[r]['rmcMainlineLaneStatusIndex'])
            self._gauge(_oid(3, 14, 1, 2, row),
                lambda r=row: s.mainline_lane_status_table[r]['rmcMainlineLaneAvgFlowRate'])
            self._gauge(_oid(3, 14, 1, 3, row),
                lambda r=row: s.mainline_lane_status_table[r]['rmcMainlineLaneAvgOccupancy'])
            self._gauge(_oid(3, 14, 1, 4, row),
                lambda r=row: s.mainline_lane_status_table[r]['rmcMainlineLaneAvgSpeed'])
            self._ri_ro(_oid(3, 14, 1, 5, row),
                lambda r=row: s.mainline_lane_status_table[r]['rmcMainlineLaneStatusFlags'])

        # No-activity duration parameter  .3.15.0
        self._ri_rw(_oid(3, 15, 0),
            lambda: s.mainline_no_activity_table.get(1, {}).get('rmcMainlineNoActivityDuration', 0),
            lambda v: s.mainline_no_activity_table.get(1, {}).__setitem__('rmcMainlineNoActivityDuration', v))

    # ==================================================================
    # 3.4  Metered Lane Configuration, Control and Status  —  rmc.4
    # ==================================================================

    def _build_metered_lane_group(self):
        s = self.store

        # Scalars
        self._ri_ro(_oid(4, 1, 0), lambda: s.max_metered_lanes)
        self._ri_ro(_oid(4, 2, 0), lambda: s.num_metered_lanes)

        # Metered lane configuration/control table  .4.1.1.<col>.<row>
        # (sub-node 4.1 = main config)
        int_rw_cols = [
            (2, 'rmcMeterLaneControlMode'),
            (4, 'rmcMeterLaneRate'),
            (5, 'rmcMeterLaneRateMin'),
            (6, 'rmcMeterLaneRateMax'),
            (7, 'rmcMeterLanePulseTime'),
            (8, 'rmcMeterLaneRedTime'),
            (9, 'rmcMeterLaneYellowTime'),
            (11, 'rmcMeterLanePlanIndex'),
            (12, 'rmcMeterLanePlanLevel'),
        ]
        int_ro_cols = [
            (3, 'rmcMeterLaneState'),
            (10, 'rmcMeterLaneQueueStatus'),
            (13, 'rmcMeterLaneStatus'),
        ]

        for row in range(1, s.num_metered_lanes + 1):
            self._ri_ro(_oid(4, 3, 1, 1, row),
                lambda r=row: s.meter_lane_table[r]['rmcMeterLaneIndex'])
            for col, key in int_rw_cols:
                self._ri_rw(_oid(4, 3, 1, col, row),
                    lambda k=key, r=row: s.meter_lane_table[r][k],
                    lambda v, k=key, r=row: s.meter_lane_table[r].__setitem__(k, v))
            for col, key in int_ro_cols:
                self._ri_ro(_oid(4, 3, 1, col, row),
                    lambda k=key, r=row: s.meter_lane_table[r][k])

        # Dependency group table  .4.2.1.<col>.<row>
        self._ri_ro(_oid(4, 4, 0), lambda: s.max_dependency_groups)
        self._ri_ro(_oid(4, 5, 0), lambda: s.num_dependency_groups)
        for row, dg in s.dependency_group_table.items():
            self._ri_ro(_oid(4, 6, 1, 1, row),
                lambda r=row: s.dependency_group_table[r]['rmcDepGroupIndex'])
            self._ri_rw(_oid(4, 6, 1, 2, row),
                lambda r=row: s.dependency_group_table[r]['rmcDepGroupControlMode'],
                lambda v, r=row: s.dependency_group_table[r].__setitem__('rmcDepGroupControlMode', v))
            self._ri_ro(_oid(4, 6, 1, 3, row),
                lambda r=row: s.dependency_group_table[r]['rmcDepGroupState'])
            self._ri_rw(_oid(4, 6, 1, 4, row),
                lambda r=row: s.dependency_group_table[r]['rmcDepGroupRate'],
                lambda v, r=row: s.dependency_group_table[r].__setitem__('rmcDepGroupRate', v))
            self._ri_ro(_oid(4, 6, 1, 5, row),
                lambda r=row: s.dependency_group_table[r]['rmcDepGroupStatus'])

        # Queue detector table  .4.7.1.<col>.<row>
        self._ri_ro(_oid(4, 7, 0), lambda: s.max_queue_detectors)
        self._ri_ro(_oid(4, 8, 0), lambda: s.num_queue_detectors)
        for row in range(1, s.num_queue_detectors + 1):
            self._ri_ro(_oid(4, 9, 1, 1, row),
                lambda r=row: s.queue_det_table[r]['rmcQueueDetIndex'])
            self._ri_rw(_oid(4, 9, 1, 2, row),
                lambda r=row: s.queue_det_table[r]['rmcQueueDetChannel'],
                lambda v, r=row: s.queue_det_table[r].__setitem__('rmcQueueDetChannel', v))
            self._gauge(_oid(4, 9, 1, 3, row),
                lambda r=row: s.queue_det_table[r]['rmcQueueDetOccupancy'])
            self._ri_rw(_oid(4, 9, 1, 4, row),
                lambda r=row: s.queue_det_table[r]['rmcQueueDetThreshold'],
                lambda v, r=row: s.queue_det_table[r].__setitem__('rmcQueueDetThreshold', v))
            self._ri_ro(_oid(4, 9, 1, 5, row),
                lambda r=row: s.queue_det_table[r]['rmcQueueDetStatus'])

        # Passage detector table  .4.10.1.<col>.<row>
        self._ri_ro(_oid(4, 10, 0), lambda: s.max_passage_detectors)
        self._ri_ro(_oid(4, 11, 0), lambda: s.num_passage_detectors)
        for row in range(1, s.num_passage_detectors + 1):
            self._ri_ro(_oid(4, 12, 1, 1, row),
                lambda r=row: s.passage_det_table[r]['rmcPassageDetIndex'])
            self._ri_rw(_oid(4, 12, 1, 2, row),
                lambda r=row: s.passage_det_table[r]['rmcPassageDetChannel'],
                lambda v, r=row: s.passage_det_table[r].__setitem__('rmcPassageDetChannel', v))
            self._counter(_oid(4, 12, 1, 3, row),
                lambda r=row: s.passage_det_table[r]['rmcPassageDetCount'])
            self._ri_ro(_oid(4, 12, 1, 4, row),
                lambda r=row: s.passage_det_table[r]['rmcPassageDetStatus'])

        # Historic detector reset  .4.13.0
        self._ri_rw(_oid(4, 13, 0),
            lambda: s.historic_det_reset,
            lambda v: setattr(s, 'historic_det_reset', v))

    # ==================================================================
    # 3.5  Metering Plan  —  rmc.5
    # ==================================================================

    def _build_metering_plan_group(self):
        s = self.store

        self._ri_ro(_oid(5, 1, 0), lambda: s.max_metering_plans)
        self._ri_ro(_oid(5, 2, 0), lambda: s.num_metering_plans)
        self._ri_ro(_oid(5, 3, 0), lambda: s.max_levels_per_plan)
        self._ri_ro(_oid(5, 4, 0), lambda: s.num_metering_levels)

        # Metering plan table  .5.5.1.<col>.<plan>
        for p in range(1, s.num_metering_plans + 1):
            self._ri_ro(_oid(5, 5, 1, 1, p),
                lambda r=p: s.metering_plan_table[r]['rmcMeteringPlanIndex'])
            self._ri_rw(_oid(5, 5, 1, 2, p),
                lambda r=p: s.metering_plan_table[r]['rmcMeteringPlanNumLevels'],
                lambda v, r=p: s.metering_plan_table[r].__setitem__('rmcMeteringPlanNumLevels', v))
            self._ro_rw(_oid(5, 5, 1, 3, p),
                lambda r=p: s.metering_plan_table[r]['rmcMeteringPlanName'],
                lambda v, r=p: s.metering_plan_table[r].__setitem__('rmcMeteringPlanName', v))

        # Metering plan level table  .5.6.1.<col>.<plan>.<level>
        for p in range(1, s.num_metering_plans + 1):
            for lv in range(1, s.num_metering_levels + 1):
                key = (p, lv)
                self._ri_ro(_oid(5, 6, 1, 1, p, lv),
                    lambda k=key: s.metering_plan_level_table[k]['rmcMeteringPlanLevelPlanIndex'])
                self._ri_ro(_oid(5, 6, 1, 2, p, lv),
                    lambda k=key: s.metering_plan_level_table[k]['rmcMeteringPlanLevelIndex'])
                self._ri_rw(_oid(5, 6, 1, 3, p, lv),
                    lambda k=key: s.metering_plan_level_table[k]['rmcMeteringPlanLevelRate'],
                    lambda v, k=key: s.metering_plan_level_table[k].__setitem__('rmcMeteringPlanLevelRate', v))
                self._ri_rw(_oid(5, 6, 1, 4, p, lv),
                    lambda k=key: s.metering_plan_level_table[k]['rmcMeteringPlanLevelFlowRateThreshold'],
                    lambda v, k=key: s.metering_plan_level_table[k].__setitem__('rmcMeteringPlanLevelFlowRateThreshold', v))
                self._ri_rw(_oid(5, 6, 1, 5, p, lv),
                    lambda k=key: s.metering_plan_level_table[k]['rmcMeteringPlanLevelOccThreshold'],
                    lambda v, k=key: s.metering_plan_level_table[k].__setitem__('rmcMeteringPlanLevelOccThreshold', v))

    # ==================================================================
    # 3.6  Scheduling Action Objects  —  rmc.6
    # ==================================================================

    def _build_tbc_group(self):
        s = self.store

        # Global TBC scalars
        self._ri_ro(_oid(6, 1, 0), lambda: s.max_tbc_actions)
        self._ri_ro(_oid(6, 2, 0), lambda: s.num_tbc_actions)

        # TBC action table  .6.3.1.<col>.<row>
        for row in range(1, s.num_tbc_actions + 1):
            tbc = s.tbc_table
            self._ri_ro(_oid(6, 3, 1, 1, row),
                lambda r=row: tbc[r]['rmcTbcIndex'])
            for col, key in [(2, 'rmcTbcCommand'), (3, 'rmcTbcMeterLane'),
                             (4, 'rmcTbcPlanIndex'), (5, 'rmcTbcStartTime'),
                             (6, 'rmcTbcDayPlan')]:
                self._ri_rw(_oid(6, 3, 1, col, row),
                    lambda k=key, r=row: tbc[r][k],
                    lambda v, k=key, r=row: tbc[r].__setitem__(k, v))

        # Per-metered-lane TBC scalars (empty tables still need max/num)
        self._ri_ro(_oid(6, 4, 0), lambda: s.max_ml_tbc_actions)
        self._ri_ro(_oid(6, 5, 0), lambda: s.num_ml_tbc_actions)

        # Per-mainline-lane TBC scalars
        self._ri_ro(_oid(6, 7, 0), lambda: s.max_mn_tbc_actions)
        self._ri_ro(_oid(6, 8, 0), lambda: s.num_mn_tbc_actions)

    # ==================================================================
    # 3.7  Physical Input / Output Objects  —  rmc.7
    # ==================================================================

    def _build_physical_io_group(self):
        s = self.store

        # Advance warning sign output
        self._ri_rw(_oid(7, 1, 0),
            lambda: s.adv_warn_sign_output,
            lambda v: setattr(s, 'adv_warn_sign_output', v))

        # Mainline lane input table  .7.2.1.<col>.<row>
        for row in range(1, s.num_mainline_lanes + 1):
            self._ri_ro(_oid(7, 2, 1, 1, row),
                lambda r=row: s.mainline_input_table[r]['rmcMainlineLaneInputIndex'])
            self._ri_rw(_oid(7, 2, 1, 2, row),
                lambda r=row: s.mainline_input_table[r]['rmcMainlineLaneInputChannel'],
                lambda v, r=row: s.mainline_input_table[r].__setitem__('rmcMainlineLaneInputChannel', v))

        # Queue detector input table  .7.3.1.<col>.<row>
        for row in range(1, s.num_queue_detectors + 1):
            self._ri_ro(_oid(7, 3, 1, 1, row),
                lambda r=row: s.queue_det_input_table[r]['rmcQueueDetInputIndex'])
            self._ri_rw(_oid(7, 3, 1, 2, row),
                lambda r=row: s.queue_det_input_table[r]['rmcQueueDetInputChannel'],
                lambda v, r=row: s.queue_det_input_table[r].__setitem__('rmcQueueDetInputChannel', v))

        # Metered lane I/O table  .7.4.1.<col>.<row>
        for row in range(1, s.num_metered_lanes + 1):
            self._ri_ro(_oid(7, 4, 1, 1, row),
                lambda r=row: s.meter_lane_io_table[r]['rmcMeterLaneIOIndex'])
            self._ri_rw(_oid(7, 4, 1, 2, row),
                lambda r=row: s.meter_lane_io_table[r]['rmcMeterLaneIOInputChannel'],
                lambda v, r=row: s.meter_lane_io_table[r].__setitem__('rmcMeterLaneIOInputChannel', v))
            self._ri_rw(_oid(7, 4, 1, 3, row),
                lambda r=row: s.meter_lane_io_table[r]['rmcMeterLaneIOOutputChannel'],
                lambda v, r=row: s.meter_lane_io_table[r].__setitem__('rmcMeterLaneIOOutputChannel', v))

        # Dependency group I/O table  .7.5.1.<col>.<row>
        for row in range(1, s.num_dependency_groups + 1):
            self._ri_ro(_oid(7, 5, 1, 1, row),
                lambda r=row: s.dep_group_io_table[r]['rmcDepGroupIOIndex'])
            self._ri_rw(_oid(7, 5, 1, 2, row),
                lambda r=row: s.dep_group_io_table[r]['rmcDepGroupIOOutputChannel'],
                lambda v, r=row: s.dep_group_io_table[r].__setitem__('rmcDepGroupIOOutputChannel', v))

    # ==================================================================
    # 3.8  Block Objects  —  rmc.8
    # ==================================================================

    def _build_block_group(self):
        s = self.store
        b = s.block

        # rmcBlockGetControl  .8.1.0  (write triggers block assembly)
        self._ri_rw(_oid(8, 1, 0),
            lambda: b['rmcBlockGetControl'],
            lambda v: self._handle_block_get(v))

        # rmcBlockData  .8.2.0  (read-only result)
        self._ro_ro(_oid(8, 2, 0), lambda: b['rmcBlockData'])

        # rmcBlockErrorStatus  .8.3.0
        self._ri_ro(_oid(8, 3, 0), lambda: b['rmcBlockErrorStatus'])

    def _handle_block_get(self, block_type_id):
        """Assemble a simple binary block for the requested block type."""
        import struct
        s = self.store
        b = s.block
        b['rmcBlockGetControl'] = block_type_id

        try:
            if block_type_id == 1:
                # Mainline lane block: index, flowRate, occupancy, speed per lane
                parts = []
                for row in sorted(s.mainline_lane_table):
                    t = s.mainline_lane_table[row]
                    parts.append(struct.pack('>BHHH',
                        t['rmcMainlineLaneIndex'],
                        t['rmcMainlineLaneFlowRate'],
                        t['rmcMainlineLaneOccupancy'],
                        t['rmcMainlineLaneSpeed']))
                b['rmcBlockData']        = b''.join(parts)
                b['rmcBlockErrorStatus'] = 0

            elif block_type_id == 3:
                # Metered lane control block: index, rate, state per lane
                parts = []
                for row in sorted(s.meter_lane_table):
                    t = s.meter_lane_table[row]
                    parts.append(struct.pack('>BHB',
                        t['rmcMeterLaneIndex'],
                        t['rmcMeterLaneRate'],
                        t['rmcMeterLaneState']))
                b['rmcBlockData']        = b''.join(parts)
                b['rmcBlockErrorStatus'] = 0

            else:
                b['rmcBlockData']        = bytes(0)
                b['rmcBlockErrorStatus'] = 1   # invalidBlockType

        except Exception:
            b['rmcBlockData']        = bytes(0)
            b['rmcBlockErrorStatus'] = 2   # resourceError
