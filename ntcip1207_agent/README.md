# ntcip1207_agent — NTCIP 1207 v02 Ramp Meter Control (RMC) Simulator

A Python SNMP agent implementing the **NTCIP 1207 v02** Ramp Meter Control MIB.

> Derived from NTCIP 1207 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.

---

## Overview

NTCIP 1207 defines the management interface for **Ramp Meter Control (RMC)** units —
the field devices that regulate on-ramp traffic flow via metered signals to optimise
freeway throughput and reduce congestion.

This simulator implements all MIB groups from Section 3 of the standard:

| Section | Group | OID Suffix |
|---------|-------|------------|
| 3.2 | General Configuration | `.1` |
| 3.3 | Mainline Lane Configuration, Control & Status | `.3` |
| 3.4 | Metered Lane Configuration, Control & Status | `.4` |
| 3.5 | Metering Plan | `.5` |
| 3.6 | Scheduling / Timebase Control (TBC) | `.6` |
| 3.7 | Physical Input / Output | `.7` |
| 3.8 | Block Objects | `.8` |

---

## Files

| File | Purpose |
|------|---------|
| `rmc_agent.py` | Entry point, argument parsing, SNMP server startup |
| `rmc_mib_data.py` | `RMCDataStore` — all 1207 MIB state |
| `rmc_oid_tree.py` | `RMCOIDTree` — OID → getter/setter mappings |
| `README.md` | This file |

---

## Quick Start

Run from the repository root:

```bash
# Default: UDP, port 1163, 2 mainline lanes, 1 metered lane
python3 -m ntcip1207_agent.rmc_agent

# TCP transport
python3 -m ntcip1207_agent.rmc_agent --transport tcp

# Larger freeway ramp: 4 mainline lanes, 2 metered lanes, 8 plans
python3 -m ntcip1207_agent.rmc_agent \
    --mainline-lanes 4 \
    --metered-lanes 2 \
    --metering-plans 8 \
    --port 1163

# Run alongside the ASC and RSU simulators
# Terminal 1 — ASC
python3 -m ntcip1202_agent.agent --port 1161 --transport both

# Terminal 2 — RSU
python3 -m ntcip1218_agent.rsu_agent --port 1162 --asc-port 1161

# Terminal 3 — RMC
python3 -m ntcip1207_agent.rmc_agent --port 1163
```

---

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `1163` | UDP/TCP port |
| `--community` | `public` | Read-only community |
| `--write-community` | `private` | Read-write community |
| `--transport` | `udp` | `udp`, `tcp`, or `both` |
| `--mainline-lanes` | `2` | Mainline detector lanes (1–8) |
| `--metered-lanes` | `1` | Metered lanes (1–8) |
| `--metering-plans` | `4` | Metering plans (1–16) |
| `--verbose` | off | Debug logging |

---

## OID Root

```
1.3.6.1.4.1.1206.4.2.5   (devices.rmc)
```

Key OID landmarks:

| Object | OID |
|--------|-----|
| rmcCommRefreshThresholdTime | `1.3.6.1.4.1.1206.4.2.5.1.1.0` |
| rmcCalculationInterval | `1.3.6.1.4.1.1206.4.2.5.1.2.0` |
| rmcNumMainlineLanes | `1.3.6.1.4.1.1206.4.2.5.3.3.0` |
| rmcMainlineLaneFlowRate (lane 1) | `1.3.6.1.4.1.1206.4.2.5.3.4.1.5.1` |
| rmcNumMeteredLanes | `1.3.6.1.4.1.1206.4.2.5.4.2.0` |
| rmcMeterLaneRate (lane 1) | `1.3.6.1.4.1.1206.4.2.5.4.3.1.4.1` |
| rmcMeterLaneState (lane 1) | `1.3.6.1.4.1.1206.4.2.5.4.3.1.3.1` |
| rmcAvgMainlineStationFlowRate | `1.3.6.1.4.1.1206.4.2.5.3.8.0` |
| rmcBlockGetControl | `1.3.6.1.4.1.1206.4.2.5.8.1.0` |
| rmcBlockData | `1.3.6.1.4.1.1206.4.2.5.8.2.0` |

---

## Simulation Behaviour

The agent runs a background simulation thread (at `rmcCalculationInterval` rate) that:

- **Mainline detectors** — sinusoidally varies flow rate, occupancy, and speed to
  simulate realistic traffic patterns across a one-hour cycle.
- **Passage detectors** — increments vehicle counts proportional to the active
  metering rate.
- **Station aggregates** — computes lane averages for
  `rmcAvgMainlineStationFlowRate`, `rmcAvgMainlineStationOccupancy`, and
  `rmcAvgMainlineStationSpeed`.

All metered lanes start in `localTrafficResponsive` mode at 900 veh/hr.  Two
Timebase Control entries schedule Plan 1 at 07:00 and Plan 2 at 16:00, Monday–Friday.

---

## Block Objects

Two block types are implemented (write the type ID to `rmcBlockGetControl`,
then read `rmcBlockData`):

| Type ID | Block |
|---------|-------|
| `1` | Mainline lane block (index + flow + occ + speed per lane) |
| `3` | Metered lane control block (index + rate + state per lane) |

Unknown type IDs set `rmcBlockErrorStatus` to `1` (invalidBlockType).
