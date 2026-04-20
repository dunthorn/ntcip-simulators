# NTCIP Simulator Suite

A Python SNMP agent suite implementing:
- **NTCIP 1202 v4.11b** — Actuated Signal Controller (ASC)
- **NTCIP 1203 v03**    — Dynamic Message Sign (DMS)
- **NTCIP 1207 v02**    — Ramp Meter Control (RMC)
- **NTCIP 1218 v01**    — Roadside Unit (RSU)

No third-party dependencies — Python 3.7+ standard library only.

Derived from NTCIP 1202 v04, NTCIP 1203 v03, NTCIP 1207 v02, and NTCIP 1218 v01.
Copyright by AASHTO / ITE / NEMA. Used by permission.

---

## Directory Structure

```
simulation/
├── common/                   Shared infrastructure
│   ├── snmp_server.py        UDP + TCP SNMP server (BER encoder/decoder)
│   └── standard_mibs.py      RFC 1213 system/interfaces/snmp + NTCIP 1201
│
├── ntcip1202_agent/          ASC simulator (NTCIP 1202 v4.11b)
│   ├── agent.py              Entry point
│   ├── mib_data.py           ASCDataStore — all 1202 MIB state
│   ├── oid_tree.py           NativeOIDTree — 2,759 OIDs
│   └── README.md
│
├── ntcip1203_agent/          DMS simulator (NTCIP 1203 v03)
│   ├── dms_agent.py          Entry point
│   ├── dms_mib_data.py       DMSDataStore — all 1203 MIB state
│   ├── dms_oid_tree.py       DMSOIDTree — 1,096+ OIDs
│   └── README.md
│
├── ntcip1207_agent/          RMC simulator (NTCIP 1207 v02)
│   ├── rmc_agent.py          Entry point
│   ├── rmc_mib_data.py       RMCDataStore — all 1207 MIB state
│   ├── rmc_oid_tree.py       RMCOIDTree — 209+ OIDs
│   └── README.md
│
├── ntcip1218_agent/          RSU simulator (NTCIP 1218 v01)
│   ├── rsu_agent.py          Entry point
│   ├── rsu_mib_data.py       RSUDataStore — all 1218 MIB state
│   ├── rsu_oid_tree.py       RSUOIDTree — 130 OIDs
│   ├── spat_bridge.py        Reads ASC phase state, encodes live SPaT payload
│   └── README.md
│
└── requirements.txt          (no runtime dependencies)
```

---

## Quick Start

All commands are run from the `simulation/` directory.

```bash
# ASC simulator — UDP (default), port 1161
python3 -m ntcip1202_agent.agent

# ASC simulator — TCP
python3 -m ntcip1202_agent.agent --transport tcp

# ASC simulator — both UDP and TCP
python3 -m ntcip1202_agent.agent --transport both --port 1161

# RSU simulator — polls ASC for SPaT data
python3 -m ntcip1218_agent.rsu_agent --port 1162 --asc-host 127.0.0.1 --asc-port 1161
```

Run both together (recommended):

```bash
# Terminal 1
python3 -m ntcip1202_agent.agent --port 1161 --transport both

# Terminal 2
python3 -m ntcip1218_agent.rsu_agent --port 1162 --asc-port 1161

# Terminal 3
python3 -m ntcip1207_agent.rmc_agent --port 1163

# Terminal 4
python3 -m ntcip1203_agent.dms_agent --port 1164
```

---

## Options

### ASC agent (`ntcip1202_agent.agent`)

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `1161` | UDP/TCP port |
| `--community` | `public` | Read-only community |
| `--write-community` | `private` | Read-write community |
| `--phases` | `8` | Number of phases (2–255) |
| `--transport` | `udp` | `udp`, `tcp`, or `both` |
| `--verbose` | off | Debug logging |

### RSU agent (`ntcip1218_agent.rsu_agent`)

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `1162` | UDP/TCP port |
| `--community` | `public` | Read-only community |
| `--write-community` | `private` | Read-write community |
| `--asc-host` | `127.0.0.1` | ASC host for SPaT bridge |
| `--asc-port` | `1161` | ASC SNMP port |
| `--lat` | `32.729` | RSU latitude (decimal degrees) |
| `--lon` | `-97.508` | RSU longitude (decimal degrees) |
| `--verbose` | off | Debug logging |

### RMC agent (`ntcip1207_agent.rmc_agent`)

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

### DMS agent (`ntcip1203_agent.dms_agent`)

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `1164` | UDP/TCP port |
| `--community` | `public` | Read-only community |
| `--write-community` | `private` | Read-write community |
| `--transport` | `udp` | `udp`, `tcp`, or `both` |
| `--sign-width-px` | `96` | Sign width in pixels |
| `--sign-height-px` | `32` | Sign height in pixels |
| `--changeable` | `10` | Changeable message slots |
| `--volatile` | `5` | Volatile message slots |
| `--verbose` | off | Debug logging |

---

## OID Roots

| MIB | OID |
|-----|-----|
| RFC 1213 system | `1.3.6.1.2.1.1` |
| RFC 1213 interfaces | `1.3.6.1.2.1.2` |
| RFC 1213 snmp | `1.3.6.1.2.1.11` |
| NTCIP 1201 global | `1.3.6.1.4.1.1206.4.2.6` |
| NTCIP 1202 ASC | `1.3.6.1.4.1.1206.4.2.1` |
| NTCIP 1203 DMS | `1.3.6.1.4.1.1206.4.2.3` |
| NTCIP 1207 RMC | `1.3.6.1.4.1.1206.4.2.5` |
| NTCIP 1218 RSU | `1.3.6.1.4.1.1206.4.2.18` |

---

## System Architecture

```
  ┌──────────────────────────────────────┐
  │   Traffic Management System          │
  │   / Network Management               │
  └───┬──────────┬──────────┬────────────┘
      │ SNMP     │ SNMP     │ SNMP      SNMP (1201+1202)
      │ (1218)   │ (1207)   │ (1203)  ┌────────────────┐
  ┌───┴──────┐ ┌─┴───────┐ ┌┴──────┐  │  ASC sim       │
  │ RSU sim  │ │ RMC sim │ │DMS sim│  │  (NTCIP 1202)  │
  │ (1218)   │ │ (1207)  │ │(1203) │  └────────────────┘
  └───┬──────┘ └─────────┘ └───────┘
      │ V2X broadcast
      ▼
  [OBUs / CV devices]
```

---

## TCP Framing

The TCP transport automatically detects the client's framing mode per connection:

- **RFC 3430** (4-byte length prefix): used by modern NTCIP management systems
- **Raw BER** (no prefix, SEQUENCE tag sent directly): used by many older NTCIP systems

Both modes are handled transparently on the same port with no configuration required.
