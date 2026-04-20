"""
rmc_mib_data.py  —  NTCIP 1207 v02 RMC MIB Data Store

Derived from NTCIP 1207 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.

Covers all MIB groups defined in Section 3 of NTCIP 1207 v02.14:
  3.2  RMC General Configuration
  3.3  Mainline Lane Configuration, Control and Status
  3.4  Metered Lane Configuration, Control and Status
  3.5  Metering Plan
  3.6  Scheduling Action Objects (Timebase Control)
  3.7  Physical Input / Output Objects
  3.8  Block Objects

OID root:  1.3.6.1.4.1.1206.4.2.5   (devices.rmc)
"""

import time
import socket


# ---------------------------------------------------------------------------
# RMC root OID  —  devices.rmc  =  1.3.6.1.4.1.1206.4.2.5
# ---------------------------------------------------------------------------
RMC_OID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 5)


class RMCDataStore:
    """
    Central in-memory state for all NTCIP 1207 v02 RMC MIB objects.
    Values are Python native types (int, bytes).
    The RMCOIDTree translates them to wire format on the way out.

    Default configuration: 2 mainline lanes, 1 metered lane, 1 metering plan.
    """

    def __init__(self, num_mainline_lanes=2, num_metered_lanes=1,
                 num_metering_plans=4, hostname=None):
        self._start_time = time.time()
        self._hostname = hostname or self._guess_hostname()
        self._num_mainline_lanes = min(max(num_mainline_lanes, 1), 8)
        self._num_metered_lanes  = min(max(num_metered_lanes,  1), 8)
        self._num_metering_plans = min(max(num_metering_plans, 1), 16)

        self._init_general_config()
        self._init_mainline_group()
        self._init_metered_lane_group()
        self._init_metering_plan_group()
        self._init_tbc_group()
        self._init_physical_io_group()
        self._init_block_group()

    @staticmethod
    def _guess_hostname():
        try:
            return socket.gethostname()
        except Exception:
            return 'rmc-simulator'

    # =========================================================================
    # 3.2  RMC General Configuration
    # =========================================================================

    def _init_general_config(self):
        """
        General configuration scalars.

        rmcCommRefreshThresholdTime  (OID .1.1.0)
            Maximum time (seconds) without a management poll before the RMC
            reverts to its last locally-commanded state.  Range 0–65535; 0
            means no timeout.

        rmcCalculationInterval  (OID .1.2.0)
            Interval in seconds over which flow/occupancy/speed averages are
            computed.  Typical field value: 20–60 s.
        """
        self.general = {
            'rmcCommRefreshThresholdTime': 120,   # 120 s default
            'rmcCalculationInterval':       20,   # 20 s averaging interval
        }

    # =========================================================================
    # 3.3  Mainline Lane Configuration, Control and Status
    # =========================================================================

    def _init_mainline_group(self):
        """
        Mainline detector station data.

        Key scalar objects:
          rmcAveragingPeriods         number of calc intervals to average
          rmcMaxMainlineLanes         maximum lanes supported (read-only)
          rmcNumMainlineLanes         actual configured lanes

        rmcMainlineLaneTable  (.3.1.1.<col>.<row>):
          Each row represents one mainline detector station lane.
          Columns include:
            rmcMainlineLaneIndex            row index
            rmcMainlineLaneControlMode      1=localFixed 2=localTrafficResponsive
                                            3=externalFixed 4=externalTrafficResponsive
            rmcMainlineLaneDetectorStation  detector station number (0=none)
            rmcMainlineLaneDetectorChannel  detector channel (0=none)
            rmcMainlineLaneFlowRate         vehicles/hour (measured)
            rmcMainlineLaneOccupancy        percentage × 10 (0–1000)
            rmcMainlineLaneSpeed            km/h × 10
            rmcMainlineLaneStatus           bitmask: bit0=detectorFail bit1=dataError

        rmcMainlaneLaneStatusTable  (.3.2.1.<col>.<row>):
          Live status per lane:
            rmcMainlineLaneStatusIndex
            rmcMainlineLaneAvgFlowRate      avg flow over averaging periods
            rmcMainlineLaneAvgOccupancy
            rmcMainlineLaneAvgSpeed
            rmcMainlineLaneStatusFlags      bitmask
        """
        s = self
        s.mainline_averaging_periods = 3
        s.max_mainline_lanes         = 8
        s.num_mainline_lanes         = self._num_mainline_lanes

        # Configuration / control table
        s.mainline_lane_table = {}
        for i in range(1, s.num_mainline_lanes + 1):
            s.mainline_lane_table[i] = {
                'rmcMainlineLaneIndex':           i,
                'rmcMainlineLaneControlMode':     2,     # localTrafficResponsive
                'rmcMainlineLaneDetectorStation': i,
                'rmcMainlineLaneDetectorChannel': 1,
                'rmcMainlineLaneFlowRate':        1200 + i * 50,   # veh/hr sim
                'rmcMainlineLaneOccupancy':       150,              # 15.0 %
                'rmcMainlineLaneSpeed':           900,              # 90.0 km/h
                'rmcMainlineLaneStatus':          0,                # no faults
            }

        # Status table (live averages)
        s.mainline_lane_status_table = {}
        for i in range(1, s.num_mainline_lanes + 1):
            s.mainline_lane_status_table[i] = {
                'rmcMainlineLaneStatusIndex':  i,
                'rmcMainlineLaneAvgFlowRate':  1200 + i * 50,
                'rmcMainlineLaneAvgOccupancy': 150,
                'rmcMainlineLaneAvgSpeed':     900,
                'rmcMainlineLaneStatusFlags':  0,
            }

        # No-activity table (flow-based no-activity entries)
        s.max_mainline_no_activity     = 4
        s.num_mainline_no_activity     = 1
        s.mainline_no_activity_table   = {
            1: {
                'rmcMainlineNoActivityIndex':         1,
                'rmcMainlineNoActivityFlowRateMin':   0,
                'rmcMainlineNoActivityFlowRateMax':   50,   # veh/hr
                'rmcMainlineNoActivityDuration':      300,  # seconds
            },
        }

        # Station-level aggregates (Section 3.3.8–3.3.10)
        s.mainline_station = {
            'rmcAvgMainlineStationFlowRate':  0,   # set dynamically
            'rmcAvgMainlineStationOccupancy': 0,
            'rmcAvgMainlineStationSpeed':     0,
            'rmcNumFlowRateLanes':            s.num_mainline_lanes,
            'rmcNumOccupancyLanes':           s.num_mainline_lanes,
            'rmcNumAvgSpeedLanes':            s.num_mainline_lanes,
        }

        s._last_mainline_tick = time.time()

    def tick_mainline(self):
        """Advance simulated mainline detector readings."""
        now = time.time()
        dt  = now - self._last_mainline_tick
        self._last_mainline_tick = now

        import math
        t = now % 3600   # cycle over one hour
        # Sinusoidal traffic variation around nominal values
        for i, row in self.mainline_lane_table.items():
            base_flow = 1200 + i * 50
            row['rmcMainlineLaneFlowRate'] = int(
                base_flow + 100 * math.sin(t / 300))
            row['rmcMainlineLaneOccupancy'] = int(
                150 + 30 * math.sin(t / 400))
            row['rmcMainlineLaneSpeed'] = int(
                900 - 20 * math.sin(t / 300))

            # Propagate to status table
            st = self.mainline_lane_status_table[i]
            st['rmcMainlineLaneAvgFlowRate']  = row['rmcMainlineLaneFlowRate']
            st['rmcMainlineLaneAvgOccupancy'] = row['rmcMainlineLaneOccupancy']
            st['rmcMainlineLaneAvgSpeed']     = row['rmcMainlineLaneSpeed']

        # Station aggregates
        flows = [r['rmcMainlineLaneFlowRate']  for r in self.mainline_lane_table.values()]
        occs  = [r['rmcMainlineLaneOccupancy'] for r in self.mainline_lane_table.values()]
        spds  = [r['rmcMainlineLaneSpeed']     for r in self.mainline_lane_table.values()]
        n = len(flows) or 1
        self.mainline_station['rmcAvgMainlineStationFlowRate']  = sum(flows) // n
        self.mainline_station['rmcAvgMainlineStationOccupancy'] = sum(occs)  // n
        self.mainline_station['rmcAvgMainlineStationSpeed']     = sum(spds)  // n

    # =========================================================================
    # 3.4  Metered Lane Configuration, Control and Status
    # =========================================================================

    def _init_metered_lane_group(self):
        """
        Metered lane data.

        rmcMeterLaneTable  (.4.1.1.<col>.<row>):
          rmcMeterLaneIndex
          rmcMeterLaneControlMode      1=dark 2=flash 3=restInGreen
                                       4=localFixed 5=localTrafficResponsive
                                       6=externalFixed 7=externalTrafficResponsive
          rmcMeterLaneState            1=metering 2=notMetering 3=fault
          rmcMeterLaneRate             metering rate (veh/hr), range 1–3600
          rmcMeterLaneRateMin          minimum allowable rate (veh/hr)
          rmcMeterLaneRateMax          maximum allowable rate (veh/hr)
          rmcMeterLanePulseTime        green pulse duration (ms)
          rmcMeterLaneRedTime          minimum red time (ms)
          rmcMeterLaneYellowTime       yellow time (ms)
          rmcMeterLaneQueueStatus      1=normal 2=queueDetected 3=override
          rmcMeterLanePlanIndex        active metering plan (0=none)
          rmcMeterLanePlanLevel        active plan level
          rmcMeterLaneStatus           bitmask: bit0=detectorFail bit1=lampFail

        Queue detector sub-table  (.4.3.1.<col>.<row>):
          rmcQueueDetIndex
          rmcQueueDetChannel
          rmcQueueDetOccupancy         percentage × 10
          rmcQueueDetThreshold         occupancy threshold (pct × 10)
          rmcQueueDetStatus            0=off 1=on (queue detected)

        Passage detector sub-table  (.4.4.1.<col>.<row>):
          rmcPassageDetIndex
          rmcPassageDetChannel
          rmcPassageDetCount           vehicles counted since last reset
          rmcPassageDetStatus          0=ok 1=fault
        """
        s = self
        s.max_metered_lanes = 8
        s.num_metered_lanes = self._num_metered_lanes

        s.meter_lane_table = {}
        for i in range(1, s.num_metered_lanes + 1):
            s.meter_lane_table[i] = {
                'rmcMeterLaneIndex':       i,
                'rmcMeterLaneControlMode': 5,      # localTrafficResponsive
                'rmcMeterLaneState':       1,      # metering
                'rmcMeterLaneRate':        900,    # 900 veh/hr
                'rmcMeterLaneRateMin':     240,    # 240 veh/hr
                'rmcMeterLaneRateMax':     1800,   # 1800 veh/hr
                'rmcMeterLanePulseTime':   2000,   # 2 s green pulse
                'rmcMeterLaneRedTime':     1000,   # 1 s minimum red
                'rmcMeterLaneYellowTime':  500,    # 0.5 s yellow
                'rmcMeterLaneQueueStatus': 1,      # normal
                'rmcMeterLanePlanIndex':   1,
                'rmcMeterLanePlanLevel':   1,
                'rmcMeterLaneStatus':      0,      # no faults
            }

        # Dependency groups (metered lane groups for coordinated control)
        s.max_dependency_groups = 4
        s.num_dependency_groups = 1
        s.dependency_group_table = {
            1: {
                'rmcDepGroupIndex':       1,
                'rmcDepGroupControlMode': 2,   # local
                'rmcDepGroupState':       1,   # active
                'rmcDepGroupRate':        900,
                'rmcDepGroupStatus':      0,
            },
        }

        # Queue detector table
        s.max_queue_detectors = 8
        s.num_queue_detectors = s.num_metered_lanes
        s.queue_det_table = {}
        for i in range(1, s.num_metered_lanes + 1):
            s.queue_det_table[i] = {
                'rmcQueueDetIndex':     i,
                'rmcQueueDetChannel':   i,
                'rmcQueueDetOccupancy': 0,     # 0.0 %
                'rmcQueueDetThreshold': 300,   # 30.0 % threshold
                'rmcQueueDetStatus':    0,     # no queue
            }

        # Passage detector table
        s.max_passage_detectors = 8
        s.num_passage_detectors = s.num_metered_lanes
        s.passage_det_table = {}
        for i in range(1, s.num_metered_lanes + 1):
            s.passage_det_table[i] = {
                'rmcPassageDetIndex':   i,
                'rmcPassageDetChannel': i,
                'rmcPassageDetCount':   0,
                'rmcPassageDetStatus':  0,   # ok
            }

        # Historic detector reset parameter
        s.historic_det_reset = 0   # 0=no reset; 1=reset all counters

        s._last_meter_tick = time.time()

    def tick_metered_lanes(self):
        """Advance simulated metered lane state."""
        now = time.time()
        dt  = now - self._last_meter_tick
        self._last_meter_tick = now

        for i, row in self.meter_lane_table.items():
            # Increment passage detector counts proportional to rate
            self.passage_det_table[i]['rmcPassageDetCount'] = (
                self.passage_det_table[i]['rmcPassageDetCount']
                + int(dt * row['rmcMeterLaneRate'] / 3600)
            ) & 0xFFFFFFFF

    # =========================================================================
    # 3.5  Metering Plan
    # =========================================================================

    def _init_metering_plan_group(self):
        """
        Metering plans define rate levels indexed by mainline conditions.

        rmcMeteringPlanTable  (.5.1.1.<col>.<row>):
          rmcMeteringPlanIndex       plan index
          rmcMeteringPlanNumLevels   number of rate levels in this plan
          rmcMeteringPlanName        DisplayString

        rmcMeteringPlanLevelTable  (.5.2.1.<col>.<row1>.<row2>):
          rmcMeteringPlanLevelPlanIndex
          rmcMeteringPlanLevelIndex
          rmcMeteringPlanLevelRate   metering rate (veh/hr) for this level
          rmcMeteringPlanLevelFlowRateThreshold  mainline flow trigger (veh/hr)
          rmcMeteringPlanLevelOccThreshold       mainline occ trigger (pct × 10)
        """
        s = self
        s.max_metering_plans  = 16
        s.num_metering_plans  = self._num_metering_plans
        s.max_levels_per_plan = 8
        s.num_metering_levels = 4

        s.metering_plan_table = {}
        for p in range(1, s.num_metering_plans + 1):
            s.metering_plan_table[p] = {
                'rmcMeteringPlanIndex':     p,
                'rmcMeteringPlanNumLevels': s.num_metering_levels,
                'rmcMeteringPlanName':      f'Plan {p}'.encode(),
            }

        # Level table: plan × level  →  rate + thresholds
        s.metering_plan_level_table = {}
        # Default rates for 4 levels: high/med/low/min mainline flow → meter rate
        default_levels = [
            # (flowThreshold veh/hr, occThreshold pct×10, meterRate veh/hr)
            (800,  200, 1800),   # level 1: low mainline flow → high meter rate
            (1200, 300, 1200),   # level 2
            (1600, 400,  900),   # level 3
            (2000, 600,  600),   # level 4: high mainline flow → low meter rate
        ]
        for p in range(1, s.num_metering_plans + 1):
            for lv, (ft, ot, mr) in enumerate(default_levels, start=1):
                key = (p, lv)
                s.metering_plan_level_table[key] = {
                    'rmcMeteringPlanLevelPlanIndex':        p,
                    'rmcMeteringPlanLevelIndex':            lv,
                    'rmcMeteringPlanLevelRate':             mr,
                    'rmcMeteringPlanLevelFlowRateThreshold': ft,
                    'rmcMeteringPlanLevelOccThreshold':     ot,
                }

    # =========================================================================
    # 3.6  Scheduling Action Objects (Timebase Control)
    # =========================================================================

    def _init_tbc_group(self):
        """
        Time-Base Control (TBC) action tables schedule automatic transitions
        between metering plans or rates based on time of day.

        rmcTbcTable  (.6.1.1.<col>.<row>):
          rmcTbcIndex
          rmcTbcCommand     1=noChange 2=setMeteringPlan 3=setControlMode 4=setDark
          rmcTbcMeterLane   0=all, 1..n=specific lane
          rmcTbcPlanIndex   target metering plan (used when command=2)
          rmcTbcStartTime   minutes from midnight (0–1439)
          rmcTbcDayPlan     bitmask: Mon=1 Tue=2 Wed=4 Thu=8 Fri=16 Sat=32 Sun=64

        We pre-populate two entries: AM and PM peak plans.
        """
        s = self
        s.max_tbc_actions = 16
        s.num_tbc_actions = 2

        s.tbc_table = {
            1: {
                'rmcTbcIndex':     1,
                'rmcTbcCommand':   2,   # setMeteringPlan
                'rmcTbcMeterLane': 0,   # all lanes
                'rmcTbcPlanIndex': 1,
                'rmcTbcStartTime': 7 * 60,    # 07:00
                'rmcTbcDayPlan':   0b0011111,  # Mon–Fri
            },
            2: {
                'rmcTbcIndex':     2,
                'rmcTbcCommand':   2,
                'rmcTbcMeterLane': 0,
                'rmcTbcPlanIndex': 2,
                'rmcTbcStartTime': 16 * 60,   # 16:00
                'rmcTbcDayPlan':   0b0011111,  # Mon–Fri
            },
        }

        # Per-metered-lane TBC overrides
        s.max_ml_tbc_actions = 8
        s.num_ml_tbc_actions = 0
        s.ml_tbc_table = {}   # empty by default

        # Per-mainline-lane TBC actions
        s.max_mn_tbc_actions = 8
        s.num_mn_tbc_actions = 0
        s.mn_tbc_table = {}

    # =========================================================================
    # 3.7  Physical Input / Output Objects
    # =========================================================================

    def _init_physical_io_group(self):
        """
        Physical I/O object definitions mapping logical lanes to hardware.

        rmcAdvWarnSignOutputNum  (.7.1.0): output channel for advance warning sign

        rmcMainlineLaneInputTable  (.7.2.1.<col>.<row>):
          rmcMainlineLaneInputIndex
          rmcMainlineLaneInputChannel  hardware detector input channel

        rmcQueueDetInputTable  (.7.3.1.<col>.<row>):
          rmcQueueDetInputIndex
          rmcQueueDetInputChannel

        rmcMeterLaneIOTable  (.7.4.1.<col>.<row>):
          rmcMeterLaneIOIndex
          rmcMeterLaneIOInputChannel   passage detector input
          rmcMeterLaneIOOutputChannel  signal output channel
        """
        s = self
        s.adv_warn_sign_output = 1   # output channel 1

        s.mainline_input_table = {}
        for i in range(1, s.num_mainline_lanes + 1):
            s.mainline_input_table[i] = {
                'rmcMainlineLaneInputIndex':   i,
                'rmcMainlineLaneInputChannel': i,
            }

        s.queue_det_input_table = {}
        for i in range(1, s.num_metered_lanes + 1):
            s.queue_det_input_table[i] = {
                'rmcQueueDetInputIndex':   i,
                'rmcQueueDetInputChannel': 10 + i,
            }

        s.meter_lane_io_table = {}
        for i in range(1, s.num_metered_lanes + 1):
            s.meter_lane_io_table[i] = {
                'rmcMeterLaneIOIndex':         i,
                'rmcMeterLaneIOInputChannel':  20 + i,
                'rmcMeterLaneIOOutputChannel': 30 + i,
            }

        s.dep_group_io_table = {}
        for i in range(1, s.num_dependency_groups + 1):
            s.dep_group_io_table[i] = {
                'rmcDepGroupIOIndex':         i,
                'rmcDepGroupIOOutputChannel': 40 + i,
            }

    # =========================================================================
    # 3.8  Block Objects
    # =========================================================================

    def _init_block_group(self):
        """
        Block objects allow efficient bulk GET/SET of related objects.

        rmcBlockGetControl  (.8.1.0):  write a block type ID to trigger assembly
        rmcBlockData        (.8.2.0):  OCTET STRING; assembled block returned here
        rmcBlockErrorStatus (.8.3.0):  0=ok, 1=invalidBlockType, 2=resourceError
        """
        self.block = {
            'rmcBlockGetControl':  0,
            'rmcBlockData':        bytes(0),
            'rmcBlockErrorStatus': 0,
        }
