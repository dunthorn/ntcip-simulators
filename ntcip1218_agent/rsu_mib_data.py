"""
rsu_mib_data.py  —  NTCIP 1218 v01 RSU MIB Data Store

Derived from NTCIP 1218 v01. Copyright by AASHTO / ITE / NEMA. Used by permission.

Covers all MIB groups defined in Section 5 of NTCIP 1218 v01.38:
  5.2  RSU Radios
  5.3  RSU GNSS
  5.4  RSU Message Store-and-Repeat (immediate / repeat tables)
  5.5  RSU Received Message Log
  5.6  RSU System
  5.7  RSU Notifications
  5.8  RSU Performance
  5.9  RSU Security (enrollment + application certificates)

OID root:  1.3.6.1.4.1.1206.4.2.18   (devices.rsu)
"""

import time
import socket


# ---------------------------------------------------------------------------
# RSU root OID  —  devices.rsu  =  1.3.6.1.4.1.1206.4.2.18
# (NTCIP 8004 devices node is 1.3.6.1.4.1.1206.4.2;
#  asc=1, rsu=18 per the NTCIP enterprise assignments)
# ---------------------------------------------------------------------------
RSU_OID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 18)


class RSUDataStore:
    """
    Central in-memory state for all NTCIP 1218 RSU MIB objects.
    Values are Python native types (int, bytes, str).
    The RSUOIDTree translates them to wire format on the way out.
    """

    def __init__(self, hostname=None, latitude=None, longitude=None):
        self._start_time = time.time()
        self._hostname = hostname or self._guess_hostname()
        self._latitude  = latitude  or 32_729_000   # 10^-7 degrees, ~Tampa FL
        self._longitude = longitude or -97_508_000   # 10^-7 degrees

        self._init_radio_group()
        self._init_gnss_group()
        self._init_msg_repeat_group()
        self._init_rcv_msg_group()
        self._init_system_group()
        self._init_notification_group()
        self._init_performance_group()
        self._init_security_group()

    @staticmethod
    def _guess_hostname():
        try:
            return socket.gethostname()
        except Exception:
            return 'rsu-simulator'

    # =========================================================================
    # 5.2  RSU Radios
    # =========================================================================

    def _init_radio_group(self):
        """
        Radio table: one row per radio interface.
        We simulate two radios:
          1 — DSRC / 5.9 GHz WAVE (C-V2X or 802.11p)
          2 — (optional) backup / secondary radio, marked as unused

        Key objects per row (rsuRadioTable):
          rsuRadioIndex            index
          rsuRadioChanMode         1=alternating, 2=continuous, 3=singleChannel
          rsuRadioChannel          DSRC channel number (172=SCH, 178=CCH)
          rsuRadioTxPower          transmit power in 0.5 dBm units (range -128..+63)
          rsuRadioRxThreshold      minimum RSSI threshold in 0.5 dBm units
          rsuRadioType             1=DSRC, 2=C-V2X, 3=other
          rsuRadioMacAddr          MAC address (6 bytes)
          rsuRadioPowerSave        0=disabled, 1=enabled
          rsuRadioDesc             DisplayString description
        """
        self.max_radios = 1

        self.radio_table = {
            1: {
                'rsuRadioIndex':       1,
                'rsuRadioChanMode':    2,              # continuous(2)
                'rsuRadioChannel':     178,            # CCH
                'rsuRadioTxPower':     44,             # 22 dBm (44 * 0.5)
                'rsuRadioRxThreshold': -174,           # -87 dBm
                'rsuRadioType':        1,              # DSRC(1)
                'rsuRadioMacAddr':     bytes([0x02, 0x00, 0x18, 0x52, 0x53, 0x55]),
                'rsuRadioPowerSave':   0,              # disabled
                'rsuRadioDesc':        b'DSRC Radio 1 - 5.9 GHz',
            },
        }

    # =========================================================================
    # 5.3  RSU GNSS
    # =========================================================================

    def _init_gnss_group(self):
        """
        GNSS (GPS) status objects.
        Coordinates stored as integers in units of 10^-7 degrees (WGS-84).
        """
        self.gnss_status = {
            'rsuGnssOutputPort':     0,              # 0 = no output port
            'rsuGnssOutputInterface': b'',
            # Live properties
            'rsuGnssStatus':         2,              # valid(2); see MIB enum
            # Coordinates: 10^-7 degrees
            'rsuGnssLatitude':       self._latitude,
            'rsuGnssLongitude':      self._longitude,
            'rsuGnssElevation':      500,            # 0.1 m units → 50 m
            # Speed/heading
            'rsuGnssSpeed':          0,              # 0.02 m/s units
            'rsuGnssHeading':        0,              # 0.0125 degrees units
            # Time (filled dynamically)
            'rsuGnssYear':           0,
            'rsuGnssMonth':          0,
            'rsuGnssDay':            0,
            'rsuGnssHour':           0,
            'rsuGnssMinute':         0,
            'rsuGnssSecond':         0,
            'rsuGnssOffset':         0,              # leap-second offset
        }

    @property
    def _gnss_time(self):
        t = time.gmtime()
        return t

    # =========================================================================
    # 5.4  RSU Message Store-and-Repeat
    # =========================================================================

    def _init_msg_repeat_group(self):
        """
        The store-and-repeat subsystem is the heart of an RSU — it holds
        the messages (SPaT, MAP, BSM, etc.) that the RSU continuously
        broadcasts over the V2X radio.

        rsuMsgRepeatTable: each row is one message to broadcast.
        Key columns:
          rsuMsgRepeatIndex        table index
          rsuMsgRepeatPsid         PSID (Provider Service Identifier, 4 bytes)
          rsuMsgRepeatTxChannel    channel to broadcast on
          rsuMsgRepeatTxInterval   interval in milliseconds
          rsuMsgRepeatDeliveryStart  start time (YYYYMMDDHHMMSS, 13 bytes)
          rsuMsgRepeatDeliveryStop   stop time
          rsuMsgRepeatEnable       1=enabled, 2=disabled
          rsuMsgRepeatStatus       1=active, 2=inactive, 3=error
          rsuMsgRepeatPriority     0-7 (DSRC user priority)
          rsuMsgRepeatOptions      bitmask
          rsuMsgRepeatPayload      the encoded message (OCTET STRING)

        PSIDs (SAE J2735):
          0x8002 = SPaT   0x8003 = MAP   0x8014 = RTCM   0x20 = BSM

        We pre-populate two rows:
          1 — SPaT (updated by SPaTBridge from ASC)
          2 — MAP  (static intersection geometry)
        """
        self.max_msg_repeat = 4

        _empty_time = b'\x00' * 13   # YYYYMMDDHHMMSSs

        self.msg_repeat_table = {
            1: {
                'rsuMsgRepeatIndex':         1,
                'rsuMsgRepeatPsid':          bytes([0x00, 0x00, 0x80, 0x02]),  # SPaT
                'rsuMsgRepeatTxChannel':     172,           # SCH 172
                'rsuMsgRepeatTxInterval':    100,           # 100 ms = 10 Hz
                'rsuMsgRepeatDeliveryStart': _empty_time,
                'rsuMsgRepeatDeliveryStop':  _empty_time,
                'rsuMsgRepeatEnable':        1,             # enabled
                'rsuMsgRepeatStatus':        1,             # active
                'rsuMsgRepeatPriority':      6,             # high priority
                'rsuMsgRepeatOptions':       0,
                'rsuMsgRepeatPayload':       bytes(64),     # placeholder; filled by SPaTBridge
            },
            2: {
                'rsuMsgRepeatIndex':         2,
                'rsuMsgRepeatPsid':          bytes([0x00, 0x00, 0x80, 0x03]),  # MAP
                'rsuMsgRepeatTxChannel':     172,
                'rsuMsgRepeatTxInterval':    1000,          # 1 Hz
                'rsuMsgRepeatDeliveryStart': _empty_time,
                'rsuMsgRepeatDeliveryStop':  _empty_time,
                'rsuMsgRepeatEnable':        1,
                'rsuMsgRepeatStatus':        1,
                'rsuMsgRepeatPriority':      5,
                'rsuMsgRepeatOptions':       0,
                'rsuMsgRepeatPayload':       bytes(128),    # placeholder MAP payload
            },
        }

        # rsuIFMStatusTable: status of the store-and-repeat interface
        # (one row per active message, mirrors msg_repeat_table)
        self.ifm_status_table = {
            1: {
                'rsuIFMIndex':      1,
                'rsuIFMPsid':       bytes([0x00, 0x00, 0x80, 0x02]),
                'rsuIFMDsrcMsgId':  19,   # SAE J2735 SPAT message ID
                'rsuIFMTxChannel':  172,
                'rsuIFMEnable':     1,
                'rsuIFMStatus':     1,
            },
            2: {
                'rsuIFMIndex':      2,
                'rsuIFMPsid':       bytes([0x00, 0x00, 0x80, 0x03]),
                'rsuIFMDsrcMsgId':  18,   # SAE J2735 MAP message ID
                'rsuIFMTxChannel':  172,
                'rsuIFMEnable':     1,
                'rsuIFMStatus':     1,
            },
        }

    # =========================================================================
    # 5.5  RSU Received Message Log
    # =========================================================================

    def _init_rcv_msg_group(self):
        """
        Configuration for received-message logging (e.g. BSMs from vehicles).
        rsuReceivedMsgTable configures which PSIDs to log.
        """
        self.max_rcv_msg = 4

        self.rcv_msg_table = {
            1: {
                'rsuReceivedMsgIndex':    1,
                'rsuReceivedMsgPsid':     bytes([0x00, 0x00, 0x00, 0x20]),  # BSM
                'rsuReceivedMsgChannel':  172,
                'rsuReceivedMsgInterval': 0,    # 0 = log all
                'rsuReceivedMsgEnable':   2,    # disabled by default
                'rsuReceivedMsgStatus':   2,    # inactive
                'rsuReceivedMsgOptions':  0,
                'rsuReceivedMsgPayload':  bytes(0),
            },
        }

    # =========================================================================
    # 5.6  RSU System
    # =========================================================================

    def _init_system_group(self):
        """
        System identification and operational state.
        rsuMode:  1=operational, 2=standby, 3=test, 4=maintenance
        """
        self.system = {
            'rsuMode':               1,        # operational(1)
            'rsuModeStatus':         0,        # no error
            'rsuID':                 b'RSU-001\x00',
            'rsuFirmwareVersion':    b'1218v01.00\x00',
            'rsuLocationDesc':       b'Intersection / Main St & 1st Ave',
            'rsuMibVersion':         b'NTCIP1218v01',
            # Clock source: 1=GPS, 2=NTP, 3=free-run
            'rsuClockSource':        1,        # GPS
            'rsuClockSourceStatus':  1,        # valid(1)
            # Time offset from UTC in seconds
            'rsuClockOffset':        0,
            # 5-byte BCD timestamp: YY MM DD HH MM
            'rsuTimestamp':          bytes(5),
            # Immediate-msg forwarding parameters
            'rsuIFMRepeatEnable':    1,        # enabled
        }

    # =========================================================================
    # 5.7  RSU Notifications (traps)
    # =========================================================================

    def _init_notification_group(self):
        """
        Trap / notification configuration.
        rsuNotifTable: one row per configured notification destination.
        """
        self.max_notifications = 2

        self.notif_table = {
            1: {
                'rsuNotifIndex':     1,
                'rsuNotifDest':      bytes([0, 0, 0, 0]),   # IP address
                'rsuNotifPort':      162,
                'rsuNotifEnable':    2,   # disabled
                'rsuNotifStatus':    2,   # inactive
            },
        }

    # =========================================================================
    # 5.8  RSU Performance
    # =========================================================================

    def _init_performance_group(self):
        """
        Performance counters.  Most increment with simulated activity.
        All are Counter32 unless noted.
        """
        self.perf = {
            # Transmitted
            'rsuMsgRepeatTxCount':       0,   # total messages transmitted
            'rsuMsgRepeatTxError':       0,
            # Received
            'rsuRcvMsgCount':            0,   # total messages received
            'rsuRcvMsgError':            0,
            # Radio
            'rsuRadioTxCount':           0,
            'rsuRadioRxCount':           0,
            # GNSS
            'rsuGnssLockStatus':         1,   # 1=locked, 2=unlocked
            'rsuGnssFixCount':           0,
        }
        self._last_perf_tick = time.time()

    def tick_performance(self):
        """Called periodically to advance simulated counters."""
        now = time.time()
        dt  = now - self._last_perf_tick
        self._last_perf_tick = now
        # ~10 SPaT + 1 MAP tx per second
        self.perf['rsuMsgRepeatTxCount'] = (
            self.perf['rsuMsgRepeatTxCount'] + int(dt * 11)
        ) & 0xFFFFFFFF
        self.perf['rsuRadioTxCount'] = (
            self.perf['rsuRadioTxCount'] + int(dt * 11)
        ) & 0xFFFFFFFF
        # Occasional simulated BSM receive
        self.perf['rsuRcvMsgCount'] = (
            self.perf['rsuRcvMsgCount'] + int(dt * 3)
        ) & 0xFFFFFFFF
        self.perf['rsuRadioRxCount'] = (
            self.perf['rsuRadioRxCount'] + int(dt * 3)
        ) & 0xFFFFFFFF
        self.perf['rsuGnssFixCount'] = (
            self.perf['rsuGnssFixCount'] + int(dt)
        ) & 0xFFFFFFFF

    # =========================================================================
    # 5.9  RSU Security
    # =========================================================================

    def _init_security_group(self):
        """
        Certificate management objects.
        rsuSecEnrollCertTable: enrollment certificates (one RSU has typically 1-2)
        rsuSecAppCertTable:    application (pseudonym) certificates (pool)

        For the simulator we populate realistic but static placeholder values.
        """
        self.max_sec_enroll_certs = 1
        self.max_sec_app_certs    = 4

        _future_expiry = b'20271231235959'   # YYYYMMDDHHMMSS (14 bytes)
        _dummy_cert    = bytes(64)            # placeholder DER-encoded cert stub

        # Enrollment certificate table
        self.sec_enroll_cert_table = {
            1: {
                'rsuSecEnrollCertIndex':       1,
                'rsuSecEnrollCertStatus':      1,   # valid(1)
                'rsuSecEnrollCertValidRegion': bytes(4),   # lat/lon bounding box TLV
                'rsuSecEnrollCertExpiration':  _future_expiry,
                'rsuSecEnrollCertUrl':         b'https://scms.example.com/enroll\x00',
                'rsuSecEnrollCertId':          _dummy_cert[:20],
            },
        }

        # Application (pseudonym) certificate table
        self.sec_app_cert_table = {}
        for i in range(1, self.max_sec_app_certs + 1):
            self.sec_app_cert_table[i] = {
                'rsuSecAppCertIndex':      i,
                'rsuSecAppCertStatus':     1,    # valid(1)
                'rsuSecAppCertExpiration': _future_expiry,
                'rsuSecAppCertId':         _dummy_cert[:20],
                # rsuSecAppCertExpirationPending (v01A addition): 0=no, 1=yes
                'rsuSecAppCertExpirationPending': 0,
            }

        # Security system scalars
        self.sec_system = {
            'rsuSecCredStatus':        1,   # valid(1)
            'rsuSecCertRevocStatus':   1,   # valid(1)
            'rsuSecCredExpiration':    _future_expiry,
            'rsuSecCertRevocUrl':      b'https://scms.example.com/crl\x00',
            'rsuSecCredDownloadUrl':   b'https://scms.example.com/creds\x00',
            'rsuSecCredDownloadEnable':2,   # disabled
            'rsuSecCertRevocEnable':   1,   # enabled
        }
