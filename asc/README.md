# NTCIP 1202 v4.11b SNMP Agent

Derived from NTCIP 1202 v04. Copyright by AASHTO / ITE / NEMA. Used by permission.

A Python SNMP agent implementing the **Actuated Signal Controller (ASC)** MIB defined
in NTCIP 1202 version 4.11b (June 2025), plus the standard MIBs expected by any
SNMP-capable network management system.

---

## Features

- **No third-party dependencies** — pure Python 3.7+ standard library only
- SNMPv1 and SNMPv2c (GET, GETNEXT, GETBULK, SET)
- Separate read-only and read-write community strings
- Live phase simulation: 2-ring NEMA TS-2 dual-barrier sequence updates
  status bitmaps in real time using each phase's actual configured timing
- SNMP group counters increment as the agent handles real traffic

## MIB Coverage

### Standard MIBs

| MIB | OID Root | Description |
|-----|----------|-------------|
| **RFC 1213 system** | `1.3.6.1.2.1.1` | sysDescr, sysObjectID, sysUpTime (live), sysContact, sysName, sysLocation, sysServices |
| **RFC 1213 interfaces** | `1.3.6.1.2.1.2` | ifNumber, ifTable (lo + eth0) with counters, gauges, and admin/oper status |
| **RFC 1213 snmp** | `1.3.6.1.2.1.11` | All snmpIn*/snmpOut* counters, increment live with traffic |
| **NTCIP 1201** | `1.3.6.1.4.1.1206.4.2.6` | globalDescriptor, globalModuleTable (1201 + 1202 entries), globalLocalID, globalSystemAccess |

### NTCIP 1202 v4 ASC MIB Groups

| Group | OID Suffix | Description |
|-------|------------|-------------|
| Phase | `.1` | Phase timing, status bitmaps, control, phase sets |
| Detector | `.2` | Vehicle & pedestrian detectors, volume/occupancy |
| Unit | `.3` | Controller ID, mode, flash, alarm table |
| Coordination | `.4` | Cycle, split, and pattern tables |
| Time Base | `.5` | ASC clock (live), schedules, day plans |
| Preempt | `.6` | Preempt inputs and timing |
| Channel | `.8` | Output channel mapping |
| Overlap | `.9` | Overlap phase configuration |
| TS2 Port 1 | `.10` | NEMA TS-2 Port 1 |
| ASC Block | `.11` | Block upload/download control |
| I/O Mapping | `.13` | Input/output function mapping |
| SIU Port 1 | `.14` | SIU Port 1 |
| RSU Interface | `.15` | Connected vehicle RSU comms |
| SPaT | `.16` | Signal Phase and Timing |
| ECLA | `.18` | External controller link adapter |
| SMU Monitoring | `.19` | Signal monitoring unit |

**Total: 2,739 OIDs registered**

---

## File Structure

```
agent.py          Entry point — CLI, phase simulator thread, wires everything together
mib_data.py       ASCDataStore — all MIB state with realistic defaults
oid_tree.py       NativeOIDTree — sorted binary-search OID→getter/setter map
snmp_server.py    SNMPServer — UDP socket, hand-rolled BER encoder/decoder
standard_mibs.py  SystemMIB, InterfacesMIB, SnmpMIB, NTCIP1201MIB data stores
requirements.txt  (no runtime dependencies)
```

---

## Installation

No packages required — just Python 3.7+.

```bash
# Clone / copy the files, then run directly:
python3 agent.py
```

---

## Usage

```bash
python3 agent.py [options]

  --host HOST            Bind address         (default: 0.0.0.0)
  --port PORT            UDP port             (default: 1161)
  --community STR        Read-only community  (default: public)
  --write-community STR  Read-write community (default: private)
  --phases N             Phase count 2..255   (default: 8)
  --verbose              Debug logging
```

> **Note:** Port 161 requires root. The default port 1161 works without `sudo`.
> Use `sudo python3 agent.py --port 161` for standard SNMP port.

---

## Quick Test

```bash
# Start the agent
python3 agent.py --verbose

# In another terminal:

# Standard MIB-II system group
snmpwalk -v2c -c public localhost:1161 1.3.6.1.2.1.1

# sysDescr
snmpget -v2c -c public localhost:1161 1.3.6.1.2.1.1.1.0

# sysUpTime (live)
snmpget -v2c -c public localhost:1161 1.3.6.1.2.1.1.3.0

# Interface table
snmpwalk -v2c -c public localhost:1161 1.3.6.1.2.1.2

# SNMP counters (increment with each request)
snmpget -v2c -c public localhost:1161 1.3.6.1.2.1.11.1.0

# NTCIP 1201 module table
snmpwalk -v2c -c public localhost:1161 1.3.6.1.4.1.1206.4.2.6

# Full ASC MIB walk
snmpwalk -v2c -c public localhost:1161 1.3.6.1.4.1.1206.4.2.1

# Walk everything from the root
snmpwalk -v2c -c public localhost:1161 1.3.6.1.2.1

# maxPhases
snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1206.4.2.1.1.1.0

# Phase 1 minimum green
snmpget -v2c -c public localhost:1161 1.3.6.1.4.1.1206.4.2.1.1.2.1.4.1

# Set phase 1 minimum green to 8 seconds
snmpset -v2c -c private localhost:1161 \
        1.3.6.1.4.1.1206.4.2.1.1.2.1.4.1 i 8

# Set sysLocation
snmpset -v2c -c private localhost:1161 \
        1.3.6.1.2.1.1.6.0 s "Main St & 1st Ave"

# Watch phase greens bitmap update live
watch -n1 "snmpget -v2c -c public localhost:1161 \
           1.3.6.1.4.1.1206.4.2.1.1.3.1.4.1"

# Watch ASC clock seconds tick
watch -n1 "snmpget -v2c -c public localhost:1161 \
           1.3.6.1.4.1.1206.4.2.1.5.2.7.0"
```

---

## OID Quick Reference

```
Standard MIBs:
  sysDescr       1.3.6.1.2.1.1.1.0
  sysObjectID    1.3.6.1.2.1.1.2.0
  sysUpTime      1.3.6.1.2.1.1.3.0
  sysContact     1.3.6.1.2.1.1.4.0   (read-write)
  sysName        1.3.6.1.2.1.1.5.0   (read-write)
  sysLocation    1.3.6.1.2.1.1.6.0   (read-write)
  ifNumber       1.3.6.1.2.1.2.1.0
  ifDescr.N      1.3.6.1.2.1.2.2.1.2.N
  ifAdminStatus  1.3.6.1.2.1.2.2.1.8.N  (read-write)
  snmpInPkts     1.3.6.1.2.1.11.1.0

NTCIP 1201:
  globalDescriptor    1.3.6.1.4.1.1206.4.2.6.1.0
  globalMaxModules    1.3.6.1.4.1.1206.4.2.6.3.0
  globalModuleTable   1.3.6.1.4.1.1206.4.2.6.4.1.<col>.<row>
    col 2 = deviceNode OID
    col 3 = version string
    col 4 = module type

NTCIP 1202 ASC root:  1.3.6.1.4.1.1206.4.2.1
  maxPhases           .1.1.0
  phaseTable          .1.2.1.<col>.<phase>
    col 4  = phaseMinimumGreen  (seconds)
    col 5  = phasePassage       (deciseconds)
    col 6  = phaseMaximum1      (seconds)
    col 8  = phaseYellowChange  (deciseconds)
    col 9  = phaseRedClear      (deciseconds)
  phaseStatusGroup    .1.3.1.<col>.1
    col 2  = reds bitmap
    col 4  = greens bitmap
    col 10 = phaseOns bitmap
  ascClock            .5.2.<sub>.0
    sub 5  = hours
    sub 6  = minutes
    sub 7  = seconds
```

---

## Extending

To add more MIB objects:

1. Add data fields to the relevant class in `mib_data.py` or `standard_mibs.py`
2. Register OID getters/setters in `oid_tree.py` using the `_ri_ro` / `_ri_rw` /
   `_ro_ro` / `_ro_rw` helpers, or `_reg` for special types (counter, gauge, oid)

Natural next additions:
- Ring/sequence tables (asc.7) for explicit ring-barrier configuration
- Priority inputs (rsuAsc, asc.17) for transit signal priority
- TRAP support (RFC 1215 / SNMPv2c notifications)
- SNMPv3 USM authentication and privacy

---

## Role in a Connected Vehicle Simulation Environment

This ASC simulator covers the controller side of the CV interface. In a full
simulation environment it sits alongside a dedicated RSU simulator, with each
device managed independently over SNMP and connected to each other via the
ASC→RSU data interface (SPaT/MAP):

```
  ┌─────────────────────────────┐
  │   Traffic Management System │
  │   / Network Management      │
  └──────────┬──────────────────┘
             │
     ┌───────┴────────┐  SNMP        ┌────────────────────┐
     │                │  1201+1218   │                    │
     │   RSU sim      │◄─────────────│   ASC sim          │
     │  (NTCIP 1218)  │              │  (NTCIP 1202)      │
     │                │  SPaT / MAP  │                    │
     │                │◄─────────────│  ascSpat (asc.16)  │
     └───────┬────────┘  data feed   │  rsuAsc  (asc.17)  │
             │                       └────────────────────┘
             │  V2X broadcast                  │
             │  (simulated)                    │ SNMP
             ▼                                 │ 1201+1202
        [OBUs / other                          ▼
         CV devices]               ┌────────────────────┐
                                   │  Field Mgmt System │
                                   │  / NMS             │
                                   └────────────────────┘
```

**ASC simulator** (this repo) covers:
- Full NTCIP 1202 v4 ASC MIB (phases, detectors, coordination, preempt, etc.)
- Ring/sequence tables with live phase simulation
- ASC→RSU interface objects: `ascRsuPort` (asc.15), `ascSpat` (asc.16), `rsuAsc` (asc.17)
- Standard MIBs: RFC 1213 system/interfaces/snmp, NTCIP 1201

**RSU simulator** (separate) covers:
- NTCIP 1218 RSU MIB (store-and-repeat message tables, radio config, antenna status,
  security/certificate objects, performance counters)
- Reads SPaT timing from the ASC simulator to populate message store tables
- Standard MIBs: RFC 1213 system/interfaces/snmp, NTCIP 1201
