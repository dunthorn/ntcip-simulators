"""
mib_data.py — ASC MIB Data Store
Holds the in-memory state for all NTCIP 1202 v4 objects.

Derived from NTCIP 1202 v04. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import time
import struct

from common.standard_mibs import SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB


class ASCDataStore:
    """
    Central data store for all ASC MIB objects plus standard MIBs.
    All values are stored as Python native types; the OIDTree translates
    them to pysnmp value objects on the way out.
    """

    def __init__(self, num_phases=8, hostname=None):
        self.num_phases = min(max(num_phases, 2), 255)

        # Standard MIBs
        self.system     = SystemMIB(hostname=hostname)
        self.interfaces = InterfacesMIB()
        self.snmp_mib   = SnmpMIB()
        self.ntcip1201  = NTCIP1201MIB()

        self._init_phase_group()
        self._init_detector_group()
        self._init_unit_group()
        self._init_coord_group()
        self._init_timebase_group()
        self._init_preempt_group()
        self._init_ring_group()
        self._init_channel_group()
        self._init_overlap_group()
        self._init_ts2port1_group()
        self._init_block_group()
        self._init_io_mapping_group()
        self._init_siu_port1_group()
        self._init_rsu_interface_group()
        self._init_spat_group()
        self._init_ecla_group()
        self._init_smu_group()

    # =========================================================================
    # 5.2  Phase Parameters
    # =========================================================================

    def _init_phase_group(self):
        n = self.num_phases

        # 5.2.1 maxPhases
        self.max_phases = n

        # 5.2.2 phaseTable — indexed 1..maxPhases
        # Realistic NEMA TS-2 defaults (timing in seconds unless noted)
        self.phase_table = {}
        for i in range(1, n + 1):
            self.phase_table[i] = {
                # phaseNumber is the index (not-accessible)
                'phaseWalk':                    7,    # seconds
                'phasePedestrianClear':         14,   # seconds
                'phaseMinimumGreen':            5,    # seconds
                'phasePassage':                 30,   # deciseconds (3.0 s)
                'phaseMaximum1':                30,   # seconds
                'phaseMaximum2':                45,   # seconds
                'phaseYellowChange':            40,   # deciseconds (4.0 s)
                'phaseRedClear':                20,   # deciseconds (2.0 s)
                'phaseRedRevert':               20,   # deciseconds (2.0 s)
                'phaseAddedInitial':            0,    # seconds
                'phaseMaximumInitial':          25,   # seconds
                'phaseTimeBeforeReduction':     0,    # seconds
                'phaseCarsBeforeReduction':     0,    # vehicles
                'phaseTimeToReduce':            0,    # seconds
                'phaseReduceBy':                0,    # deciseconds
                'phaseMinimumGap':              30,   # deciseconds (3.0 s)
                'phaseDynamicMaxLimit':         0,    # seconds
                'phaseDynamicMaxStep':          0,    # deciseconds
                'phaseStartup':                 3,    # greenWalk(3)
                'phaseOptions':                 0x00000001,  # bit0: phase enabled
                'phaseRing':                    1 if i <= n // 2 else 2,
                'phaseConcurrency':             bytes([0] * 32),
                'phaseMaximum3':                60,   # seconds
                'phasePedClearDuringVehicleClear': 0,
                'phasePedServiceLimit':         0,
                'phaseDontWalkRevert':          0,
                'phasePedAlternateClearance':   0,
                'phasePedAlternateWalk':        0,
                'phasePedAdvanceWalkTime':      0,
                'phasePedDelayTime':            0,
                'phaseAdvWarnGrnStartTime':     0,
                'phaseAdvWarnRedStartTime':     0,
                'phaseAltMinTimeTransition':    0,
                'phaseWalkDuringTransition':    0,
                'phasePedClearDuringTransition': 0,
            }


        # Set phaseConcurrency for each phase.
        # Each phase lists the phase on the other ring that may run with it
        # (its concurrent partner at the same barrier crossing).
        # Standard 8-phase dual-ring layout:
        #   Ring 1: 1 2 | 3 4   Ring 2: 5 6 | 7 8   (| = barrier)
        # Concurrent pairs: (1,5) (2,6) (3,7) (4,8)
        half = n // 2
        for i in range(1, n + 1):
            partner = (i + half) if i <= half else (i - half)
            if 1 <= partner <= n:
                self.phase_table[i]['phaseConcurrency'] = bytes([partner])

        # 5.2.3 phaseStatusGroupTable — 1 group for all phases
        self.phase_status_groups = {
            1: {
                'phaseStatusGroupReds':     bytes([0xFF, 0x00]),   # all red initially
                'phaseStatusGroupYellows':  bytes([0x00, 0x00]),
                'phaseStatusGroupGreens':   bytes([0x00, 0x00]),
                'phaseStatusGroupDontWalks': bytes([0xFF, 0x00]),
                'phaseStatusGroupPedClears': bytes([0x00, 0x00]),
                'phaseStatusGroupWalks':    bytes([0x00, 0x00]),
                'phaseStatusGroupVehCalls': bytes([0x00, 0x00]),
                'phaseStatusGroupPedCalls': bytes([0x00, 0x00]),
                'phaseStatusGroupPhaseOns': bytes([0x00, 0x00]),
                'phaseStatusGroupPhaseNexts': bytes([0x00, 0x00]),
            }
        }
        self.max_phase_status_groups = 1

        # 5.2.4 phaseControlGroupTable — 1 control group
        self.phase_control_groups = {
            1: {
                'phaseControlGroupPhaseOmit':  bytes([0x00, 0x00]),
                'phaseControlGroupPedOmit':    bytes([0x00, 0x00]),
                'phaseControlGroupHold':       bytes([0x00, 0x00]),
                'phaseControlGroupForceOff':   bytes([0x00, 0x00]),
                'phaseControlGroupVehCall':    bytes([0x00, 0x00]),
                'phaseControlGroupPedCall':    bytes([0x00, 0x00]),
            }
        }
        self.max_phase_control_groups = 1

        # 5.2.5 Phase Sets
        self.max_phase_sets = 4
        self.phase_set_table = {}  # (phaseNumber, setNumber) -> dict
        for phase in range(1, n + 1):
            for ps in range(1, self.max_phase_sets + 1):
                base = self.phase_table[phase]
                self.phase_set_table[(phase, ps)] = {
                    'phaseSetWalk':                  base['phaseWalk'],
                    'phaseSetPedestrianClear':       base['phasePedestrianClear'],
                    'phaseSetMinimumGreen':          base['phaseMinimumGreen'],
                    'phaseSetPassage':               base['phasePassage'],
                    'phaseSetMaximum1':              base['phaseMaximum1'],
                    'phaseSetMaximum2':              base['phaseMaximum2'],
                    'phaseSetYellowChange':          base['phaseYellowChange'],
                    'phaseSetRedClear':              base['phaseRedClear'],
                    'phaseSetRedRevert':             base['phaseRedRevert'],
                    'phaseSetAddedInitial':          base['phaseAddedInitial'],
                    'phaseSetMaximumInitial':        base['phaseMaximumInitial'],
                    'phaseSetTimeBeforeReduction':   base['phaseTimeBeforeReduction'],
                    'phaseSetCarsBeforeReduction':   base['phaseCarsBeforeReduction'],
                    'phaseSetTimeToReduce':          base['phaseTimeToReduce'],
                    'phaseSetReduceBy':              base['phaseReduceBy'],
                    'phaseSetMinimumGap':            base['phaseMinimumGap'],
                    'phaseSetDynamicMaxLimit':       base['phaseDynamicMaxLimit'],
                    'phaseSetDynamicMaxStep':        base['phaseDynamicMaxStep'],
                    'phaseSetMaximum3':              base['phaseMaximum3'],
                    'phaseSetPedClearDuringVehicleClear': base['phasePedClearDuringVehicleClear'],
                    'phaseSetPedServiceLimit':       base['phasePedServiceLimit'],
                    'phaseSetDontWalkRevert':        base['phaseDontWalkRevert'],
                    'phaseSetPedAlternateClearance': base['phasePedAlternateClearance'],
                    'phaseSetPedAlternateWalk':      base['phasePedAlternateWalk'],
                    'phaseSetPedAdvanceWalkTime':    base['phasePedAdvanceWalkTime'],
                    'phaseSetPedDelayTime':          base['phasePedDelayTime'],
                    'phaseSetAdvWarnGrnStartTime':   base['phaseAdvWarnGrnStartTime'],
                    'phaseSetAdvWarnRedStartTime':   base['phaseAdvWarnRedStartTime'],
                    'phaseSetAltMinTimeTransition':  base['phaseAltMinTimeTransition'],
                    'phaseSetWalkDuringTransition':  base['phaseWalkDuringTransition'],
                    'phaseSetPedClearDuringTransition': base['phasePedClearDuringTransition'],
                }

    # =========================================================================
    # 5.8  Ring / Sequence Parameters  (asc.7)
    # =========================================================================

    def _init_ring_group(self):
        """
        Initialise ring topology, sequence plans, ring control, and ring status.

        Standard dual-ring, dual-barrier layout for n phases:
          Ring 1: phases 1 .. n//2   (e.g. 1 2 3 4 for n=8)
          Ring 2: phases n//2+1 .. n (e.g. 5 6 7 8 for n=8)

        Sequence plan 1 (the default) encodes the standard order: each ring
        lists its phases in numerical order.  Barriers are implied by
        phaseConcurrency — the MIB does not store them separately.

        Ring status (ringOnPhase, ringStatus, ringOnPhaseDuration) is updated
        in real time by PhaseSimulator.
        """
        n    = self.num_phases
        half = n // 2

        self.max_rings    = 2
        self.max_sequences = 1   # one sequence plan (the standard order)

        # sequenceTable: keyed (sequenceNumber, ringNumber) -> sequenceData bytes
        # sequenceData is an octet string where each byte is a phase number,
        # in the order they will be served within that ring.
        self.sequence_table = {}
        for seq in range(1, self.max_sequences + 1):
            # Ring 1: phases 1..half in order
            self.sequence_table[(seq, 1)] = bytes(range(1, half + 1))
            # Ring 2: phases half+1..n in order
            self.sequence_table[(seq, 2)] = bytes(range(half + 1, n + 1))

        # maxRingControlGroups = ceil(maxRings / 8)
        self.max_ring_control_groups = (self.max_rings + 7) // 8  # = 1

        # ringControlGroupTable: one group (covers rings 1-8)
        # All control bits start at 0 (no remote overrides active)
        self.ring_control_groups = {}
        for grp in range(1, self.max_ring_control_groups + 1):
            self.ring_control_groups[grp] = {
                'ringControlGroupStopTime':     0,
                'ringControlGroupForceOff':     0,
                'ringControlGroupMax2':         0,
                'ringControlGroupMaxInhibit':   0,
                'ringControlGroupPedRecycle':   0,
                'ringControlGroupRedRest':      0,
                'ringControlGroupOmitRedClear': 0,
                'ringControlGroupMax3':         0,
            }

        # ringStatusTable: one row per ring, updated live by PhaseSimulator
        # ringStatus bits encode the current interval (see MIB section 5.8.6.1)
        #   Bits 2-0: coded status  6 = Red Rest (all-red / startup)
        #   Bit 11:   Don't Walk
        self.ring_status = {}
        for ring in range(1, self.max_rings + 1):
            self.ring_status[ring] = {
                'ringStatus':          0x0846,  # DontWalk + RedRest at startup
                'ringOnPhase':         0,        # 0 = no phase currently on
                'ringOnPhaseDuration': 0,        # deciseconds
            }


    # =========================================================================
    # 5.3  Detector Parameters
    # =========================================================================

    def _init_detector_group(self):
        n = self.num_phases  # one detector per phase by default
        self.max_vehicle_detectors = n
        self.max_pedestrian_detectors = n
        self.detector_table = {}
        for i in range(1, n + 1):
            self.detector_table[i] = {
                'detectorType':           1,   # passThrough(1)
                'detectorCallPhase':      i,
                'detectorSwitchPhase':    0,
                'detectorOptions':        0,
                'detectorCallDelay':      0,
                'detectorExtension':      0,
                'detectorRecallMode':     2,   # noRecall(2)
                'detectorAlarmState':     1,   # noAlarm(1)
                'detectorAlarmThreshold': 0,
                'detectorVolume':         0,
                'detectorOccupancy':      0,
                'detectorClassify':       0,
                'detectorStatus':         bytes([0x00]),
                'detectorZoneLength':     6,   # meters
                'detectorQueueLimit':     0,
                'detectorQueue':          0,
                'detectorNoActivity':     0,
                'detectorMaxPresence':    0,
                'detectorErraticCounts':  0,
            }

    # =========================================================================
    # 5.4  Unit Parameters
    # =========================================================================

    def _init_unit_group(self):
        self.unit_scalars = {
            # 5.4.1
            'unitStartUpFlash':             6,    # seconds
            # 5.4.2
            'unitAlarmState1':              0,
            # 5.4.3
            'unitAlarmState2':              0,
            # 5.4.4
            'unitFlash':                    0,    # 0=no flash
            # 5.4.5
            'unitSignalPlan':               1,
            # 5.4.6
            'unitOffset':                   0,
            # 5.4.7
            'unitMode':                     1,    # act(1)
            # 5.4.8
            'unitControl':                  0,
            # 5.4.9
            'unitInputFunction':            bytes([0] * 2),
            # Timers / counters
            'unitCounterActuations':        0,
            # 5.4.11 unitRingControl
            'unitRingControl':              bytes([0, 0]),
            # 5.4.12 unitAlarmTable placeholder
            'maxUnitAlarms':                1,
            # 5.4.13
            'unitFaultMonitor':             0,
            # 5.4.14
            'unitControllerID':             b'ASC-001\x00',
            # 5.4.15
            'unitFirmwareVersion':          b'1202v04.00\x00',
        }
        self.unit_alarm_table = {
            1: {
                'unitAlarmNumber':  1,
                'unitAlarmCode':    0,
                'unitAlarmTime':    bytes(5),    # 5-byte timestamp
                'unitAlarmState':   1,           # noAlarm(1)
            }
        }

    # =========================================================================
    # 5.5  Coordination Parameters
    # =========================================================================

    def _init_coord_group(self):
        self.max_cycles = 4
        self.max_splits = 4
        self.max_coord_patterns = 16

        self.coord_scalars = {
            'coordOperationalMode':     0,    # free(0)
            'coordPatternNumber':       0,
            'coordCycleNumber':         0,
            'coordSplitNumber':         0,
            'coordOffset':              0,
            'coordMaximumMode':         1,
            'coordYieldPhase':          0,
        }

        # coordCycleTable
        self.coord_cycle_table = {}
        for i in range(1, self.max_cycles + 1):
            self.coord_cycle_table[i] = {
                'coordCycleNumber':  i,
                'coordCycleLength':  90 if i == 1 else 0,   # seconds
            }

        # coordSplitTable — splits in tenths of cycle for each phase
        n = self.num_phases
        self.coord_split_table = {}
        for sp in range(1, self.max_splits + 1):
            for ph in range(1, n + 1):
                # Default: equal splits
                self.coord_split_table[(sp, ph)] = {
                    'coordSplitPhase':  100 // n,  # percent of cycle
                }

        # coordPatternTable
        self.coord_pattern_table = {}
        for i in range(1, self.max_coord_patterns + 1):
            self.coord_pattern_table[i] = {
                'coordPatternNumber':    i,
                'coordPatternCycleNum':  1,
                'coordPatternSplitNum':  1,
                'coordPatternOffsetNum': 0,
                'coordPatternMode':      0,    # free(0)
            }

    # =========================================================================
    # 5.6  Time Base Parameters
    # =========================================================================

    def _init_timebase_group(self):
        self.max_time_base_schedules = 4
        self.max_day_plans = 4
        self.max_day_plan_events = 8

        self.timebase_scalars = {
            'timebaseAscPatternSync':   0,
        }

        # ASC clock objects (5.6.2–5.6.9)
        now = time.localtime()
        self.asc_clock = {
            'ascTimeDayOfWeek':    now.tm_wday + 1,   # 1=Sunday NTCIP style
            'ascTimeDayOfMonth':   now.tm_mday,
            'ascTimeMonthOfYear':  now.tm_mon,
            'ascTimeYear':         now.tm_year,
            'ascTimeHours':        now.tm_hour,
            'ascTimeMinutes':      now.tm_min,
            'ascTimeSeconds':      now.tm_sec,
            'ascTimeSystemStart':  0,    # seconds since startup
        }

        self.timebase_schedule_table = {}
        for i in range(1, self.max_time_base_schedules + 1):
            self.timebase_schedule_table[i] = {
                'timebaseScheduleMonth':  0,
                'timebaseScheduleDay':    0,
                'timebaseSchedulePlan':   1,
            }

        self.day_plan_table = {}
        for plan in range(1, self.max_day_plans + 1):
            self.day_plan_table[plan] = {}
            for event in range(1, self.max_day_plan_events + 1):
                self.day_plan_table[plan][event] = {
                    'dayPlanHour':       0,
                    'dayPlanMinute':     0,
                    'dayPlanPatternNum': 0,
                }

    # =========================================================================
    # 5.7  Preempt Parameters
    # =========================================================================

    def _init_preempt_group(self):
        self.max_preempts = 2

        self.preempt_table = {}
        for i in range(1, self.max_preempts + 1):
            self.preempt_table[i] = {
                'preemptState':          1,    # noPreempt(1)
                'preemptLinkActive':     0,
                'preemptDelay':          0,    # seconds
                'preemptPhase':          0,
                'preemptMinGreen':       10,   # seconds
                'preemptYellowChange':   40,   # deciseconds
                'preemptRedClear':       20,   # deciseconds
                'preemptTrackGreen':     0,    # seconds
                'preemptDwellTime':      0,    # seconds
                'preemptExitPhase':      0,
                'preemptExitMinGreen':   5,    # seconds
                'preemptLinkedExit':     0,
            }

    # =========================================================================
    # 5.9  Channel Parameters
    # =========================================================================

    def _init_channel_group(self):
        self.max_channels = self.num_phases

        self.channel_table = {}
        for i in range(1, self.max_channels + 1):
            self.channel_table[i] = {
                'channelControlSource':  i,      # maps to phase i
                'channelControlType':    1,       # vehicle(1)
                'channelOptions':        0,
            }

    # =========================================================================
    # 5.10  Overlap Parameters
    # =========================================================================

    def _init_overlap_group(self):
        self.max_overlaps = 4

        self.overlap_table = {}
        for i in range(1, self.max_overlaps + 1):
            self.overlap_table[i] = {
                'overlapType':         2,            # vehicleGreenYellowRed(2)
                'overlapOptions':      0,
                'overlapIncludedPhases': bytes(4),   # bitmask
                'overlapModifierPhases': bytes(4),
                'overlapStatus':       bytes([0x00]),
                'overlapYellowChange': 40,           # deciseconds
                'overlapRedClear':     20,           # deciseconds
                'overlapTrailGreen':   0,
            }

    # =========================================================================
    # 5.11  TS2 Port 1 Parameters
    # =========================================================================

    def _init_ts2port1_group(self):
        self.max_port1_addresses = 8

        self.ts2port1_table = {}
        for i in range(1, self.max_port1_addresses + 1):
            self.ts2port1_table[i] = {
                'ts2Port1PhaseOmit':   0,
                'ts2Port1PedOmit':     0,
                'ts2Port1Hold':        0,
                'ts2Port1CallVeh':     0,
                'ts2Port1CallPed':     0,
                'ts2Port1IntervalInfo': bytes(2),
            }

    # =========================================================================
    # 5.12  ASC Block Objects
    # =========================================================================

    def _init_block_group(self):
        self.asc_block = {
            'ascBlockGetControl':   bytes(4),
            'ascBlockSetControl':   bytes(4),
            'ascBlockData':         bytes(256),
        }

    # =========================================================================
    # 5.13  I/O Mapping
    # =========================================================================

    def _init_io_mapping_group(self):
        self.max_io_inputs  = 64
        self.max_io_outputs = 64

        self.io_map_control = {
            'ascIOmapControlMode':    1,   # normal(1)
            'ascIOmapControlStatus':  1,   # ok(1)
            'ascIOmapControlCommand': 0,
        }

        self.io_input_map  = {}
        self.io_output_map = {}
        for i in range(1, self.max_io_inputs + 1):
            self.io_input_map[i] = {
                'ascIOinputFunction':   0,
                'ascIOinputState':      0,
                'ascIOinputOptions':    0,
                'ascIOinputParameter1': 0,
                'ascIOinputParameter2': 0,
                'ascIOinputParameter3': 0,
                'ascIOinputParameter4': 0,
                'ascIOinputParameter5': 0,
            }
        for i in range(1, self.max_io_outputs + 1):
            self.io_output_map[i] = {
                'ascIOoutputFunction':  0,
                'ascIOoutputState':     0,
            }

    # =========================================================================
    # 5.14  SIU Port 1 Parameters
    # =========================================================================

    def _init_siu_port1_group(self):
        self.max_siu_port1_addresses = 8

        self.siu_port1_table = {}
        for i in range(1, self.max_siu_port1_addresses + 1):
            self.siu_port1_table[i] = {
                'siuPort1PhaseOmit': 0,
                'siuPort1PedOmit':   0,
                'siuPort1Hold':      0,
                'siuPort1CallVeh':   0,
                'siuPort1CallPed':   0,
            }

    # =========================================================================
    # 5.15  RSU Interface
    # =========================================================================

    def _init_rsu_interface_group(self):
        self.rsu_scalars = {
            'rsuCommPort':          0,
            'rsuCommEnable':        0,
            'rsuCommProtocol':      0,
            'rsuCommIpAddress':     bytes(4),
        }

    # =========================================================================
    # 5.16  SPaT
    # =========================================================================

    def _init_spat_group(self):
        self.spat_scalars = {
            'spatTimestamp':         bytes(5),   # 5-byte OER timestamp
            'spatMinEndTime':        0,
            'spatMaxEndTime':        0,
            'spatLikelyTime':        0,
            'spatConfidenceLevel':   0,
            'spatEnabled':           0,
        }

    # =========================================================================
    # 5.18  ECLA
    # =========================================================================

    def _init_ecla_group(self):
        self.ecla_scalars = {
            'eclaCommEnable':       0,
            'eclaCommPort':         0,
            'eclaCommProtocol':     0,
            'eclaCommIpAddress':    bytes(4),
            'eclaTimeout':          0,
        }

    # =========================================================================
    # 5.19  SMU Monitoring
    # =========================================================================

    def _init_smu_group(self):
        n_channels = self.max_channels if hasattr(self, 'max_channels') else self.num_phases

        self.smu_table = {}
        for i in range(1, n_channels * 3 + 1):
            self.smu_table[i] = {
                'ascSmuChannel':    ((i - 1) // 3) + 1,
                'ascSmuColor':      ((i - 1) % 3) + 1,   # 1=red, 2=yellow, 3=green
                'ascSmuState':      1,                    # normal(1)
                'ascSmuVoltage':    120,                  # tenths of volts (12.0V)
            }
