# ntcip1203_agent — NTCIP 1203 v03 Dynamic Message Sign (DMS) Simulator

A Python SNMP agent implementing the **NTCIP 1203 v03** Dynamic Message Sign MIB.

> Derived from NTCIP 1203 v03. Copyright by AASHTO / ITE / NEMA. Used by permission.

---

## Overview

NTCIP 1203 defines the management interface for **Dynamic Message Signs (DMS)** —
roadside changeable message signs (also called VMS or CMS) used to display real-time
traffic messages, speed limits, amber alerts, and incident warnings.

This simulator implements all major MIB sections from Section 5 of the standard:

| Section | Group | OID Suffix |
|---------|-------|------------|
| 5.2 | Sign Configuration and Capability | `.1` |
| 5.3 | VMS Configuration (pixel matrix) | `.2` |
| 5.4 | Font Definition Objects | `.3` |
| 5.5 | MULTI Configuration Objects | `.4` |
| 5.6 | Message Objects (permanent / changeable / volatile) | `.5` |
| 5.7 | Sign Control Objects | `.6` |
| 5.8 | Illumination / Brightness | `.7` |
| 5.9 | Scheduling Action Objects | `.8` |
| 5.11 | Sign Status (core, errors, power, temperature) | `.9` |
| 5.12 | Graphic Definition Objects | `.10` |

---

## Files

| File | Purpose |
|------|---------|
| `dms_agent.py` | Entry point, argument parsing, SNMP server startup |
| `dms_mib_data.py` | `DMSDataStore` — all 1203 MIB state |
| `dms_oid_tree.py` | `DMSOIDTree` — OID → getter/setter mappings |
| `README.md` | This file |

---

## Quick Start

Run from the repository root:

```bash
# Default: 96×32 px LED sign, UDP, port 1164
python3 -m ntcip1203_agent.dms_agent

# TCP transport, larger sign, more message slots
python3 -m ntcip1203_agent.dms_agent \
    --transport tcp \
    --sign-width-px 176 \
    --sign-height-px 48 \
    --changeable 20 \
    --volatile 10

# Run alongside the full suite
# Terminal 1 — ASC
python3 -m ntcip1202_agent.agent --port 1161 --transport both

# Terminal 2 — RSU
python3 -m ntcip1218_agent.rsu_agent --port 1162 --asc-port 1161

# Terminal 3 — RMC
python3 -m ntcip1207_agent.rmc_agent --port 1163

# Terminal 4 — DMS
python3 -m ntcip1203_agent.dms_agent --port 1164
```

---

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `1164` | UDP/TCP port |
| `--community` | `public` | Read-only community |
| `--write-community` | `private` | Read-write community |
| `--transport` | `udp` | `udp`, `tcp`, or `both` |
| `--sign-width-px` | `96` | Sign width in pixels |
| `--sign-height-px` | `32` | Sign height in pixels |
| `--changeable` | `10` | Number of changeable message slots |
| `--volatile` | `5` | Number of volatile message slots |
| `--verbose` | off | Debug logging |

---

## OID Root

```
1.3.6.1.4.1.1206.4.2.3   (devices.dms)
```

Key OID landmarks:

| Object | OID |
|--------|-----|
| dmsSignType | `1.3.6.1.4.1.1206.4.2.3.1.2.0` |
| vmsSignWidthPixels | `1.3.6.1.4.1.1206.4.2.3.2.4.0` |
| vmsSignHeightPixels | `1.3.6.1.4.1.1206.4.2.3.2.3.0` |
| dmsColorScheme | `1.3.6.1.4.1.1206.4.2.3.4.21.0` |
| dmsControlMode | `1.3.6.1.4.1.1206.4.2.3.6.1.0` |
| dmsActivateMessage | `1.3.6.1.4.1.1206.4.2.3.6.3.0` |
| dmsActivateMessageState | `1.3.6.1.4.1.1206.4.2.3.6.25.0` |
| dmsMessageTimeRemaining | `1.3.6.1.4.1.1206.4.2.3.6.4.0` |
| dmsMessageTableSource | `1.3.6.1.4.1.1206.4.2.3.6.5.0` |
| dmsIllumControl | `1.3.6.1.4.1.1206.4.2.3.7.1.0` |
| dmsIllumPhotocellLevelStatus | `1.3.6.1.4.1.1206.4.2.3.7.3.0` |
| dmsIllumBrightLevelStatus | `1.3.6.1.4.1.1206.4.2.3.7.5.0` |
| dmsSignStatus | `1.3.6.1.4.1.1206.4.2.3.9.1.0` |
| dmsMaxCabinetTemp | `1.3.6.1.4.1.1206.4.2.3.9.12.0` |

---

## Message Activation

To display a message, SET `dmsActivateMessage` (OID `.6.3.0`) with a 12-byte
`MessageActivationCode`:

```
Bytes 0-1:  duration in minutes (0 or 0xFFFF = continuous)
Byte  2:    priority (0-255; 255 = highest)
Byte  3:    memory type (1=permanent 2=changeable 3=volatile 6=blank)
Bytes 4-5:  message number (1-based within memory type)
Bytes 6-7:  message CRC-16 (0 = skip CRC check)
Bytes 8-11: source IP address (0.0.0.0 for local/central)
```

Example: activate permanent message 2 continuously at priority 200:
```
00 00   # duration = 0 (continuous)
C8      # priority = 200
01      # memory type = permanent
00 02   # message number = 2
00 00   # CRC = 0 (skip check)
00 00 00 00   # source IP
```

After activation, read `dmsActivateMessageState` (`.6.25.0`) — `2` = activated.
Read `dmsMessageTableSource` (`.6.5.0`) for the 5-byte MessageIDCode of the
currently-displayed message.

---

## Pre-populated Messages

### Permanent (read-only, memory type 1):
| # | Content |
|---|---------|
| 1 | *(blank)* |
| 2 | `SPEED\nLIMIT 55` |
| 3 | `REDUCE\nSPEED` |

### Changeable (memory type 2):
Slots 1–10 are initially blank (`dmsMessageStatus = notUsed`). Write a MULTI
string to `dmsMessageMultiString` then activate.

---

## MULTI Format

Message content uses the MULTI markup language (Section 6 of NTCIP 1203 v03).
Common tags supported by this simulator:

| Tag | Effect |
|-----|--------|
| `[nl]` | New line |
| `[np]` | New page |
| `[fo1]` | Select font 1 (Standard 5×7) |
| `[fo2]` | Select font 2 (Small 3×5) |
| `[pt30o0]` | Page on 3.0 s, off 0 s |
| `[jl3]` | Center justification |
| `[fl]` | Flash text |

---

## Simulation Behaviour

The background simulation thread (10-second tick) advances:

- **Photocell level** — sinusoidal 24-hour day/night cycle drives brightness levels 1–8.
- **Temperatures** — cabinet and ambient temperatures drift slowly over time.
- **Message expiry** — timed activations (finite duration) automatically expire and revert
  to the configured `dmsEndDurationMessage`.

---

## Scheduling

Two pre-populated action table entries:
- **Entry 1** — Activates permanent message 2 ("SPEED LIMIT 55") Mon–Fri 06:00–22:00.
- **Entry 2** — Activates blank Mon–Sun 22:00–06:00.

The action table (`dmsActionTable`, OID `.8.2`) can be modified via SNMP SET.
