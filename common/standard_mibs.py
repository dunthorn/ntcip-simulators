"""
standard_mibs.py — Standard MIB data stores

Implements:
  - RFC 1213 MIB-II system group      (1.3.6.1.2.1.1)
  - RFC 1213 MIB-II interfaces group  (1.3.6.1.2.1.2)
  - RFC 1213 MIB-II snmp group        (1.3.6.1.2.1.11)
  - NTCIP 1201 global object defs     (1.3.6.1.4.1.1206.4.2.6)
"""

import time
import socket


# ---------------------------------------------------------------------------
# MIB-II system group  —  1.3.6.1.2.1.1
# ---------------------------------------------------------------------------

class SystemMIB:
    """
    RFC 1213 system group objects.
    sysUpTime is computed live from agent start time.
    sysDescr, sysContact, sysName, sysLocation are writable.
    """

    # sysServices: value 6 = (physical=1) + (datalink=2) + (application=?) 
    # For an ASC we use 6 (physical + datalink), per RFC 1213 guidance for
    # devices that act primarily at layers 1 and 2.
    SERVICES_ASC = 6

    def __init__(self, hostname=None):
        self._start_time = time.time()
        _host = hostname or self._guess_hostname()

        self.sysDescr    = (
            b'NTCIP 1202 v4 Actuated Signal Controller Simulator; '
            b'Python SNMP Agent'
        )
        # sysObjectID: use the asc node OID  1.3.6.1.4.1.1206.4.2.1
        self.sysObjectID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 1)

        self.sysContact  = b'ntcip@nema.org'
        self.sysName     = _host.encode() if isinstance(_host, str) else _host
        self.sysLocation = b'Intersection 1 / Main St & 1st Ave'
        self.sysServices = self.SERVICES_ASC

    @property
    def sysUpTime(self):
        """TimeTicks: hundredths of seconds since agent start."""
        return int((time.time() - self._start_time) * 100) & 0xFFFFFFFF

    @staticmethod
    def _guess_hostname():
        try:
            return socket.gethostname()
        except Exception:
            return 'asc-simulator'


# ---------------------------------------------------------------------------
# MIB-II interfaces group  —  1.3.6.1.2.1.2
# ---------------------------------------------------------------------------

class InterfacesMIB:
    """
    RFC 1213 interfaces group.
    We expose two interfaces:
      1 — loopback   (lo)
      2 — Ethernet   (eth0, representative management interface)

    Counters are static (non-zero plausible defaults).
    ifOperStatus is kept in sync: up(1) / down(2).
    """

    IF_TYPE_OTHER     = 1
    IF_TYPE_LOOPBACK  = 24
    IF_TYPE_ETHERLIKE = 6

    def __init__(self):
        self.ifNumber = 2

        # ifTable rows keyed by ifIndex (1-based)
        self.if_table = {
            1: {
                'ifIndex':       1,
                'ifDescr':       b'lo',
                'ifType':        self.IF_TYPE_LOOPBACK,
                'ifMtu':         65536,
                'ifSpeed':       10_000_000,        # 10 Mbps (loopback nominal)
                'ifPhysAddress': b'',               # no MAC for loopback
                'ifAdminStatus': 1,                 # up(1)
                'ifOperStatus':  1,                 # up(1)
                'ifLastChange':  0,                 # TimeTicks
                'ifInOctets':    0,
                'ifInUcastPkts': 0,
                'ifInNUcastPkts':0,
                'ifInDiscards':  0,
                'ifInErrors':    0,
                'ifInUnknownProtos': 0,
                'ifOutOctets':   0,
                'ifOutUcastPkts':0,
                'ifOutNUcastPkts':0,
                'ifOutDiscards': 0,
                'ifOutErrors':   0,
                'ifOutQLen':     0,
                'ifSpecific':    (0, 0),            # zeroDotZero
            },
            2: {
                'ifIndex':       2,
                'ifDescr':       b'eth0',
                'ifType':        self.IF_TYPE_ETHERLIKE,
                'ifMtu':         1500,
                'ifSpeed':       100_000_000,       # 100 Mbps
                'ifPhysAddress': b'\x02\x00\x00\xA5\xC0\x00',  # placeholder MAC
                'ifAdminStatus': 1,
                'ifOperStatus':  1,
                'ifLastChange':  0,
                'ifInOctets':    1_048_576,
                'ifInUcastPkts': 8192,
                'ifInNUcastPkts':0,
                'ifInDiscards':  0,
                'ifInErrors':    0,
                'ifInUnknownProtos': 0,
                'ifOutOctets':   524_288,
                'ifOutUcastPkts':4096,
                'ifOutNUcastPkts':0,
                'ifOutDiscards': 0,
                'ifOutErrors':   0,
                'ifOutQLen':     0,
                'ifSpecific':    (0, 0),
            },
        }
        # Fix the placeholder MAC
        self.if_table[2]['ifPhysAddress'] = bytes([0x02, 0x00, 0x00, 0xA5, 0xC0, 0x01])


# ---------------------------------------------------------------------------
# MIB-II snmp group  —  1.3.6.1.2.1.11
# ---------------------------------------------------------------------------

class SnmpMIB:
    """
    RFC 1213 snmp group.
    Counters increment as the server processes requests.
    The SNMPServer calls increment_*() as it handles PDUs.
    """

    def __init__(self):
        self.snmpInPkts              = 0
        self.snmpOutPkts             = 0
        self.snmpInBadVersions       = 0
        self.snmpInBadCommunityNames = 0
        self.snmpInBadCommunityUses  = 0
        self.snmpInASNParseErrs      = 0
        self.snmpInTooBigs           = 0
        self.snmpInNoSuchNames       = 0
        self.snmpInBadValues         = 0
        self.snmpInReadOnlys         = 0
        self.snmpInGenErrs           = 0
        self.snmpInTotalReqVars      = 0
        self.snmpInTotalSetVars      = 0
        self.snmpInGetRequests       = 0
        self.snmpInGetNexts          = 0
        self.snmpInSetRequests       = 0
        self.snmpInGetResponses      = 0
        self.snmpInTraps             = 0
        self.snmpOutTooBigs          = 0
        self.snmpOutNoSuchNames      = 0
        self.snmpOutBadValues        = 0
        self.snmpOutGenErrs          = 0
        self.snmpOutGetRequests      = 0
        self.snmpOutGetNexts         = 0
        self.snmpOutSetRequests      = 0
        self.snmpOutGetResponses     = 0
        self.snmpOutTraps            = 0
        self.snmpEnableAuthenTraps   = 2    # disabled(2)

    def _inc(self, attr, n=1):
        setattr(self, attr, (getattr(self, attr) + n) & 0xFFFFFFFF)

    def on_in_packet(self):          self._inc('snmpInPkts')
    def on_out_packet(self):         self._inc('snmpOutPkts')
    def on_bad_version(self):        self._inc('snmpInBadVersions')
    def on_bad_community(self):      self._inc('snmpInBadCommunityNames')
    def on_parse_error(self):        self._inc('snmpInASNParseErrs')
    def on_get(self, n_vars):
        self._inc('snmpInGetRequests')
        self._inc('snmpInTotalReqVars', n_vars)
    def on_getnext(self, n_vars):
        self._inc('snmpInGetNexts')
        self._inc('snmpInTotalReqVars', n_vars)
    def on_set(self, n_vars):
        self._inc('snmpInSetRequests')
        self._inc('snmpInTotalSetVars', n_vars)
    def on_getbulk(self, n_vars):
        self._inc('snmpInGetNexts')         # GETBULK counts as GetNext in v1 MIB
        self._inc('snmpInTotalReqVars', n_vars)
    def on_response_sent(self):      self._inc('snmpOutGetResponses')


# ---------------------------------------------------------------------------
# NTCIP 1201 Global Object Definitions  —  1.3.6.1.4.1.1206.4.2.6
# ---------------------------------------------------------------------------
#
# NTCIP 1201 v03 globalModuleTable columns (confirmed by PRL):
#   2.2.3.1  moduleNumber      INTEGER
#   2.2.3.2  moduleDeviceNode  OBJECT IDENTIFIER
#   2.2.3.3  moduleMake        DisplayString
#   2.2.3.4  moduleModel       DisplayString
#   2.2.3.5  moduleVersion     DisplayString   <-- col 5, OCTET STRING
#   2.2.3.6  moduleType        INTEGER (1=ntcip 2=national 3=private)
#
# We register two modules:
#   1 — NTCIP 1201 itself  (global device definitions)
#   2 — The device-specific MIB (1202/1203/1207/1218 depending on agent)
# ---------------------------------------------------------------------------

class NTCIP1201MIB:
    """
    Minimal NTCIP 1201 global object definitions.
    Enough to satisfy manager "device inventory" queries.
    """

    MOD_TYPE_NTCIP     = 1
    MOD_TYPE_NATIONAL  = 2
    MOD_TYPE_PRIVATE   = 3

    def __init__(self):
        self.globalMaxModules = 2

        self.module_table = {
            1: {
                'moduleNumber':     1,
                'moduleDeviceNode': (1, 3, 6, 1, 4, 1, 1206, 4, 2, 6),
                'moduleMake':       b'AASHTO/ITE/NEMA',
                'moduleModel':      b'NTCIP 1201',
                'moduleVersion':    b'03.00',
                'moduleType':       self.MOD_TYPE_NTCIP,
            },
            2: {
                'moduleNumber':     2,
                'moduleDeviceNode': (1, 3, 6, 1, 4, 1, 1206, 4, 2, 1),  # default ASC; overridden per agent
                'moduleMake':       b'Simulator',
                'moduleModel':      b'NTCIP 1202',
                'moduleVersion':    b'04.11',
                'moduleType':       self.MOD_TYPE_NTCIP,
            },
        }

        self.globalDescriptor   = b'NTCIP Device Simulator'
        self.globalSetIDParameter = 0
        self.globalLocalID        = b'\x00' * 4
        self.globalSystemAccess   = 4              # readWrite(4)
