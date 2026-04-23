"""
dms_mib_data.py  —  NTCIP 1203 v02 DMS MIB Data Store

Derived from NTCIP 1203 v02. Copyright by AASHTO / ITE / NEMA. Used by permission.

Covers all MIB sections defined in Section 5 of NTCIP 1203 v02.35:
  5.2  Sign Configuration and Capability Objects
  5.3  VMS Configuration Objects
  5.4  Font Definition Objects
  5.5  Multi-Configuration Objects
  5.6  Message Objects (permanent / changeable / volatile message tables)
  5.7  Sign Control Objects
  5.8  Illumination / Brightness Objects
  5.9  Scheduling Action Objects
  5.11 Sign Status Objects (core, error, power, temperature)
  5.12 Graphic Definition Objects

OID root:  1.3.6.1.4.1.1206.4.2.3   (devices.dms)
"""

import time
import socket


# ---------------------------------------------------------------------------
# DMS root OID  —  devices.dms  =  1.3.6.1.4.1.1206.4.2.3
# ---------------------------------------------------------------------------
DMS_OID = (1, 3, 6, 1, 4, 1, 1206, 4, 2, 3)

# Memory type constants (used in MessageIDCode / MessageActivationCode)
MSG_MEM_PERMANENT   = 1   # factory-stored messages
MSG_MEM_CHANGEABLE  = 2   # operator-stored messages (survives power cycle)
MSG_MEM_VOLATILE    = 3   # temporary messages (cleared on power cycle)
MSG_MEM_CURRENT     = 4   # pseudo-type: currently-displayed message
MSG_MEM_SCHEDULE    = 5   # schedule-activated messages
MSG_MEM_BLANK       = 6   # blank (no message)


class DMSDataStore:
    """
    Central in-memory state for all NTCIP 1203 v02 DMS MIB objects.
    Values are Python native types (int, bytes).
    The DMSOIDTree translates them to wire format on the way out.

    Default configuration: 96×32 px full-matrix LED sign, monochrome,
    3 permanent messages, 10 changeable message slots.
    """

    def __init__(self, sign_width_px=96, sign_height_px=32,
                 char_width_px=5, char_height_px=7,
                 num_changeable=10, num_volatile=5, hostname=None):
        self._start_time     = time.time()
        self._hostname       = hostname or self._guess_hostname()
        self._sign_w         = sign_width_px
        self._sign_h         = sign_height_px
        self._char_w         = char_width_px
        self._char_h         = char_height_px
        self._num_changeable = num_changeable
        self._num_volatile   = num_volatile

        self._init_sign_config()
        self._init_vms_config()
        self._init_font_group()
        self._init_multi_config()
        self._init_message_group()
        self._init_sign_control()
        self._init_illumination()
        self._init_scheduling()
        self._build_schedule_messages()   # populate schedule msg table from action table
        self._init_sign_status()
        self._init_graphic_group()

    @staticmethod
    def _guess_hostname():
        try:
            return socket.gethostname()
        except Exception:
            return 'dms-simulator'

    # =========================================================================
    # 5.2  Sign Configuration and Capability Objects  (dms.1)
    # =========================================================================

    def _init_sign_config(self):
        """
        Physical sign description.

        dmsSignAccess    1=other 2=walkIn 3=pullOut 4=rear
        dmsSignType      1=other 2=bos 3=cms 4=vms 5=pflash 6=toc
        dmsSignHeight    sign cabinet height in mm (including border)
        dmsSignWidth     sign cabinet width in mm (including border)
        dmsHorizontalBorder  pixel border width in mm
        dmsVerticalBorder    pixel border height in mm
        dmsLegend        DisplayString — fixed legend text on sign face
        dmsBeaconType    0=none 1=oneBeacon 2=twoBeacon ... 6=other
        dmsSignTechnology  bitmask: bit0=otherTech bit1=led bit2=flipDisc
                                    bit3=fiberOptic bit4=shuttered bit5=lamp
        """
        self.sign_config = {
            'dmsSignAccess':       0b00000110,           # bit1=walkIn + bit2=rear
            'dmsSignType':         6,                    # vmsFull(6) — full matrix LED sign
            'dmsSignHeight':       914,                  # 914 mm ≈ 36"
            'dmsSignWidth':        2438,                 # 2438 mm ≈ 96"
            'dmsHorizontalBorder': 25,                   # 25 mm
            'dmsVerticalBorder':   25,
            'dmsLegend':           b'',                  # no fixed legend
            'dmsBeaconType':       0,                    # no beacon
            'dmsSignTechnology':   0b00000010,           # LED only (bit 1)
        }

    # =========================================================================
    # 5.3  VMS Configuration Objects  (dms.2)
    # =========================================================================

    def _init_vms_config(self):
        """
        Pixel matrix and pitch dimensions.

        vmsCharacterHeightPixels  height of each character cell in pixels
        vmsCharacterWidthPixels   width (0 = variable-width font)
        vmsSignHeightPixels       total sign height in pixels
        vmsSignWidthPixels        total sign width in pixels
        vmsHorizontalPitch        horizontal pitch in 1/10 mm units
        vmsVerticalPitch          vertical pitch in 1/10 mm units
        monochromeColor           OCTET STRING (3 bytes): R, G, B of the
                                  single display colour for monochrome signs
        """
        self.vms_config = {
            'vmsCharacterHeightPixels': self._char_h,
            'vmsCharacterWidthPixels':  self._char_w,
            'vmsSignHeightPixels':      self._sign_h,
            'vmsSignWidthPixels':       self._sign_w,
            'vmsHorizontalPitch':       100,  # 10.0 mm
            'vmsVerticalPitch':         100,  # 10.0 mm
            'monochromeColor':          bytes([0xFF, 0xA5, 0x00]),  # amber
        }

    # =========================================================================
    # 5.4  Font Definition Objects  (dms.3)
    # =========================================================================

    def _init_font_group(self):
        """
        Font table.  Each row defines a bitmap font.

        dmsNumFonts              number of defined fonts
        fontTable:
          fontIndex              row index (1-based)
          fontNumber             logical font ID referenced in MULTI [fo…]
          fontName               DisplayString
          fontHeight             cell height in pixels
          fontCharSpacing        inter-character spacing in pixels
          fontLineSpacing        inter-line spacing in pixels
          fontVersionID          CRC-16 of font bitmap data
          fontStatus             1=notUsed 2=modifying 3=calculatingID
                                 4=readyForUse 5=permanent 6=cleared
        dmsMaxFontChars          max characters per font
        characterTable:
          chTableFontIndex       parent font index
          chTableCharIndex       character code (ASCII)
          chTableCharWidth       character width in pixels
          chTableCharPattern     OCTET STRING: packed bitmap

        We define two fonts:
          1 — 5×7 standard (ID 1, "Standard5x7")
          2 — 3×5 small    (ID 2, "Small3x5")
        """
        self.num_fonts        = 2
        self.max_font_chars   = 96   # printable ASCII
        self.max_char_size    = 64   # max bytes per character bitmap

        self.font_table = {
            1: {
                'fontIndex':        1,
                'fontNumber':       1,
                'fontName':         b'Standard5x7',
                'fontHeight':       7,
                'fontCharSpacing':  1,
                'fontLineSpacing':  4,
                'fontVersionID':    0xA1B2,   # simulated CRC
                'fontStatus':       4,        # readyForUse
            },
            2: {
                'fontIndex':        2,
                'fontNumber':       2,
                'fontName':         b'Small3x5',
                'fontHeight':       5,
                'fontCharSpacing':  1,
                'fontLineSpacing':  2,
                'fontVersionID':    0xC3D4,
                'fontStatus':       4,
            },
        }

        # Build a minimal character table: width + empty bitmap per character
        # Full bitmaps would require embedded font data — we use placeholder bytes.
        self.char_table = {}
        for fi in range(1, self.num_fonts + 1):
            row = self.font_table[fi]
            w   = 5 if fi == 1 else 3
            h   = row['fontHeight']
            bmp_bytes = (w * h + 7) // 8
            for ch in range(0x20, 0x7F):   # printable ASCII
                self.char_table[(fi, ch)] = {
                    'chTableFontIndex':   fi,
                    'chTableCharIndex':   ch,
                    'chTableCharWidth':   w,
                    'chTableCharPattern': bytes(bmp_bytes),
                }

    # =========================================================================
    # 5.5  Multi-Configuration Objects  (dms.4)
    # =========================================================================

    def _init_multi_config(self):
        """
        MULTI tag defaults and sign capabilities.

        Colors encoded as INTEGER enumerations for classic scheme:
          0=black 1=red 2=yellow 3=green 4=cyan 5=blue 6=magenta 7=white
          8=orange 9=amber

        Flash times in 1/10 second units.
        Page times in 1/10 second units.

        dmsColorScheme  1=monochrome1bit 2=monochrome8bit
                        3=colorClassic 4=color24bit
        dmsSupportedMultiTags  OCTET STRING (4 bytes, bitmask):
          byte 0 bit 0 = [cb] color background
          byte 0 bit 1 = [pb] page background
          byte 0 bit 2 = [cf] color foreground
          byte 0 bit 3 = [cr] color rectangle
          byte 0 bit 4 = [f]  field
          byte 0 bit 5 = [fl] flash
          byte 0 bit 6 = [fo] font
          byte 0 bit 7 = [g]  graphic
          byte 1 bit 0 = [hc] hex character
          byte 1 bit 1 = [jl] justification line
          byte 1 bit 2 = [jp] justification page
          byte 1 bit 3 = [ms] manufacturer specific
          byte 1 bit 4 = [mv] moving text
          byte 1 bit 5 = [nl] new line
          byte 1 bit 6 = [np] new page
          byte 1 bit 7 = [pt] page time
          byte 2 bit 0 = [sc] spacing character
          byte 2 bit 1 = [tr] text rectangle
        """
        self.multi_cfg = {
            # Background / foreground defaults (classic color scheme integers)
            'dmsDefaultBackgroundColor':         0,    # black
            'dmsDefaultForegroundColor':         7,    # white
            # Flash defaults (1/10 s)
            'dmsDefaultFlashOn':                 5,    # 0.5 s
            'dmsDefaultFlashOff':                5,
            'dmsDefaultFlashOnActivate':         5,
            'dmsDefaultFlashOffActivate':        5,
            # Font defaults
            'dmsDefaultFont':                    1,
            'dmsDefaultFontActivate':            1,
            # Justification defaults
            # Line: 1=other 2=left 3=center 4=right 5=full
            # Page: 1=other 2=top 3=middle 4=bottom
            'dmsDefaultJustificationLine':       3,    # center
            'dmsDefaultJustificationPage':       2,    # top
            'dmsDefaultJustificationLineActivate':  3,
            'dmsDefaultJustificationPageActivate':  2,
            # Page time defaults (1/10 s)
            'dmsDefaultPageOnTime':              30,   # 3.0 s
            'dmsDefaultPageOffTime':              0,   # static (no flash)
            'dmsDefaultPageOnTimeActivate':      30,
            'dmsDefaultPageOffTimeActivate':      0,
            # RGB defaults (for color24bit scheme; ignored in monochrome)
            'dmsDefaultBackgroundColorRGB':      bytes([0, 0, 0]),
            'dmsDefaultForegroundColorRGB':      bytes([255, 255, 255]),
            'dmsDefaultBackgroundColorRGBActivate': bytes([0, 0, 0]),
            'dmsDefaultForegroundColorRGBActivate': bytes([255, 255, 255]),
            # Character set
            # 1=other 2=ascii 3=latin1 4=unicode
            'dmsDefaultCharacterSet':            2,    # ASCII
            # Color scheme
            'dmsColorScheme':                    1,    # monochrome1bit
            # Supported MULTI tags bitmask (4 bytes)
            # Support: [fo][nl][np][pt][jl][jp][fl][hc]
            'dmsSupportedMultiTags':             bytes([0b01111110, 0b10100110, 0b00000000, 0x00]),
            # Limits
            'dmsMaxNumberPages':                  6,
            'dmsMaxMultiStringLength':           256,
        }

    # =========================================================================
    # 5.6  Message Objects  (dms.5)
    # =========================================================================

    def _init_message_group(self):
        """
        Message table — stores permanent, changeable, and volatile messages.

        Each message row (dmsMessageTable):
          dmsMessageMemoryType     1=permanent 2=changeable 3=volatile
                                   4=current 5=schedule 6=blank
          dmsMessageNumber         row index within memory type
          dmsMessageMultiString    MULTI-encoded message text (OCTET STRING)
          dmsMessageOwner          DisplayString identifying who set this
          dmsMessageCRC            CRC-16 of the MULTI string
          dmsMessageBeacon         0=none 1=activate beacon with message
          dmsMessagePixelService   0=disabled 1=enabled (pixel test w/ msg)
          dmsMessageRunTimePriority  1=lowest … 255=highest
          dmsMessageStatus         1=notUsed 2=modifying 3=validating
                                   4=valid 5=error 6=blank

        Permanent messages (read-only, factory-set):
          1 — blank (memType=blank in activation, but stored as perm)
          2 — "SPEED LIMIT 55"
          3 — "REDUCE SPEED"

        Changeable messages:
          1..num_changeable — initially blank (status=notUsed)

        Volatile messages:
          1..num_volatile — initially blank (status=notUsed)
        """
        self.num_permanent_messages   = 3
        self.num_changeable_messages  = self._num_changeable
        self.max_changeable_messages  = self._num_changeable
        self.num_volatile_messages    = self._num_volatile
        self.max_volatile_messages    = self._num_volatile

        # Memory usage tracking (bytes)
        self.changeable_free_bytes    = 4096
        self.volatile_free_bytes      = 2048

        def _crc16(data: bytes) -> int:
            crc = 0xFFFF
            for b in data:
                crc ^= b
                for _ in range(8):
                    if crc & 1:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1
            return crc & 0xFFFF

        def _msg(mem_type, num, multi, owner=b'FACTORY', priority=128):
            mb = multi if isinstance(multi, bytes) else multi.encode()
            return {
                'dmsMessageMemoryType':       mem_type,
                'dmsMessageNumber':           num,
                'dmsMessageMultiString':      mb,
                'dmsMessageOwner':            owner,
                'dmsMessageCRC':              _crc16(mb),
                'dmsMessageBeacon':           0,
                'dmsMessagePixelService':     0,
                'dmsMessageRunTimePriority':  priority,
                'dmsMessageStatus':           4 if mb else 1,  # valid or notUsed
            }

        # Permanent messages (read-only)
        self.permanent_msg_table = {
            1: _msg(MSG_MEM_PERMANENT, 1, '',           priority=100),
            2: _msg(MSG_MEM_PERMANENT, 2, 'SPEED\nLIMIT 55', priority=200),
            3: _msg(MSG_MEM_PERMANENT, 3, 'REDUCE\nSPEED',   priority=200),
        }

        # Changeable messages
        self.changeable_msg_table = {}
        for i in range(1, self._num_changeable + 1):
            self.changeable_msg_table[i] = _msg(MSG_MEM_CHANGEABLE, i, b'')

        # Volatile messages
        self.volatile_msg_table = {}
        for i in range(1, self._num_volatile + 1):
            self.volatile_msg_table[i] = _msg(MSG_MEM_VOLATILE, i, b'')

        # Validate message error (from last validate attempt)
        self.validate_msg_error = 0   # 0=none

        # Schedule messages (memType=5): one row per action table entry.
        # These are read-only snapshots of the messages the action table
        # will activate.  The TMS reads them to know what will display.
        # We populate them after _init_scheduling() is called, so they
        # are built lazily on first access via _build_schedule_messages().
        self.schedule_msg_table = {}

        # Current message (memType=4): a single read-only row reflecting
        # whatever is presently displayed on the sign.
        self.current_msg_table = {
            1: _msg(MSG_MEM_CURRENT, 1, b'', priority=0),
        }

        # CRC helper for external use
        self._crc16 = _crc16

    def _build_schedule_messages(self):
        """
        Build/refresh the schedule message table from the action table.
        Called after scheduling is initialised, and whenever the action
        table changes.  One row per action table entry; content mirrors
        the referenced permanent/changeable message.
        """
        def _msg_for_code(msg_code: bytes):
            """Resolve a 5-byte MessageIDCode to (multiString, crc)."""
            if len(msg_code) < 3:
                return b'', 0
            mem_type = msg_code[0]
            msg_num  = (msg_code[1] << 8) | msg_code[2]
            if mem_type == MSG_MEM_PERMANENT and msg_num in self.permanent_msg_table:
                row = self.permanent_msg_table[msg_num]
                return row['dmsMessageMultiString'], row['dmsMessageCRC']
            if mem_type == MSG_MEM_CHANGEABLE and msg_num in self.changeable_msg_table:
                row = self.changeable_msg_table[msg_num]
                return row['dmsMessageMultiString'], row['dmsMessageCRC']
            return b'', 0

        self.schedule_msg_table = {}
        for idx, action in self.action_table.items():
            multi, crc = _msg_for_code(action['dmsActionMsgCode'])
            self.schedule_msg_table[idx] = {
                'dmsMessageMemoryType':       MSG_MEM_SCHEDULE,
                'dmsMessageNumber':           idx,
                'dmsMessageMultiString':      multi,
                'dmsMessageOwner':            b'SCHEDULE',
                'dmsMessageCRC':              crc,
                'dmsMessageBeacon':           0,
                'dmsMessagePixelService':     0,
                'dmsMessageRunTimePriority':  128,
                'dmsMessageStatus':           4 if multi else 1,
            }

    # =========================================================================
    # 5.7  Sign Control Objects  (dms.6)
    # =========================================================================

    def _init_sign_control(self):
        """
        Operational control objects.

        dmsControlMode   1=other 2=local 3=external 4=central 5=centralOverride
        dmsSoftwareReset  write 1 to reset
        dmsActivateMessage  MessageActivationCode OCTET STRING (12 bytes):
          bytes 0-1: duration (minutes; 0=continuous; 65535=until next change)
          byte  2:   priority (0..255)
          byte  3:   memory type
          bytes 4-5: message number
          bytes 6-7: message CRC
          bytes 8-11: source IP address (0.0.0.0 = local)

        dmsMessageTimeRemaining  minutes remaining for current activation
        dmsMessageTableSource    MessageIDCode of active message (8 bytes):
          byte  0:   memory type
          bytes 1-2: message number
          bytes 3-4: CRC
        dmsMessageRequesterID    DisplayString
        dmsMessageSourceMode     same enum as dmsControlMode
        dmsShortPowerLossRecoveryMessage  MessageIDCode
        dmsLongPowerLossRecoveryMessage   MessageIDCode
        dmsShortPowerLossTime            INTEGER (0..65535 seconds)
        dmsResetMessage                  MessageIDCode
        dmsCommLossMessage               MessageIDCode
        dmsCommLossTime                  INTEGER (0..65535 seconds)
        dmsPowerLossMessage              MessageIDCode
        dmsEndDurationMessage            MessageIDCode
        dmsMemoryMgmt                    write to clear message memory
        dmsActivateMessageError          error code from last activation
        dmsMultiSyntaxError              MULTI parsing error code
        dmsMultiSyntaxErrorPosition      character position of syntax error
        dmsOtherMultiError               other MULTI error details
        dmsPixelServiceDuration          INTEGER (0..65535 minutes)
        dmsPixelServiceFrequency         INTEGER (0..65535 hours)
        dmsPixelServiceTime              time until next pixel service (min)
        dmsMessageCodeOfActivationError  MessageIDCode of failed activation
        dmsActivateMessageState          1=notActivated 2=activated
        """
        _blank_code = bytes([MSG_MEM_BLANK, 0, 0, 0, 0])  # 5-byte MessageIDCode

        self.sign_control = {
            'dmsControlMode':                     4,     # central
            'dmsSoftwareReset':                   0,
            # 12-byte activation code; initially activates permanent msg 1 (blank)
            'dmsActivateMessage':                 bytes(12),
            'dmsMessageTimeRemaining':            0,     # continuous
            # 5-byte MessageIDCode (memType + msgNum 2B + CRC 2B)
            'dmsMessageTableSource':              _blank_code,
            'dmsMessageRequesterID':              b'',
            'dmsMessageSourceMode':               4,     # central
            'dmsShortPowerLossRecoveryMessage':   _blank_code,
            'dmsLongPowerLossRecoveryMessage':    _blank_code,
            'dmsShortPowerLossTime':              5,     # 5 seconds
            'dmsResetMessage':                    _blank_code,
            'dmsCommLossMessage':                 _blank_code,
            'dmsCommLossTime':                    30,    # 30 seconds
            'dmsPowerLossMessage':                _blank_code,
            'dmsEndDurationMessage':              _blank_code,
            'dmsMemoryMgmt':                      0,
            'dmsActivateMessageError':            0,     # 0=none
            'dmsMultiSyntaxError':                0,     # 0=other (no error)
            'dmsMultiSyntaxErrorPosition':        0,
            'dmsOtherMultiError':                 0,
            'dmsPixelServiceDuration':            5,     # 5 minutes
            'dmsPixelServiceFrequency':           24,    # every 24 hours
            'dmsPixelServiceTime':                0,
            'dmsMessageCodeOfActivationError':    _blank_code,
            'dmsActivateMessageState':            1,     # notActivated
        }

        # Track currently displayed message for status reporting
        self._active_mem_type = MSG_MEM_BLANK
        self._active_msg_num  = 0
        self._active_multi    = b''
        self._active_end_time = None   # None = continuous

    def activate_message(self, activation_code: bytes):
        """
        Process a dmsActivateMessage SET.  Parses the 12-byte code and
        updates sign control state accordingly.
        Returns True on success, sets dmsActivateMessageError otherwise.
        """
        if len(activation_code) < 8:
            self.sign_control['dmsActivateMessageError'] = 3   # syntaxMULTI
            return False

        duration   = (activation_code[0] << 8) | activation_code[1]
        priority   = activation_code[2]
        mem_type   = activation_code[3]
        msg_num    = (activation_code[4] << 8) | activation_code[5]
        msg_crc    = (activation_code[6] << 8) | activation_code[7]

        # Locate the message
        if mem_type == MSG_MEM_BLANK:
            self._active_mem_type = MSG_MEM_BLANK
            self._active_msg_num  = 0
            self._active_multi    = b''
        elif mem_type == MSG_MEM_PERMANENT and msg_num in self.permanent_msg_table:
            row = self.permanent_msg_table[msg_num]
            if row['dmsMessageCRC'] != msg_crc and msg_crc != 0:
                self.sign_control['dmsActivateMessageError'] = 5   # badCRC
                self.sign_control['dmsActivateMessageState'] = 1
                return False
            self._active_mem_type = mem_type
            self._active_msg_num  = msg_num
            self._active_multi    = row['dmsMessageMultiString']
        elif mem_type == MSG_MEM_CHANGEABLE and msg_num in self.changeable_msg_table:
            row = self.changeable_msg_table[msg_num]
            if row['dmsMessageStatus'] != 4:   # must be valid
                self.sign_control['dmsActivateMessageError'] = 6   # msgNotDefined
                self.sign_control['dmsActivateMessageState'] = 1
                return False
            self._active_mem_type = mem_type
            self._active_msg_num  = msg_num
            self._active_multi    = row['dmsMessageMultiString']
        elif mem_type == MSG_MEM_VOLATILE and msg_num in self.volatile_msg_table:
            row = self.volatile_msg_table[msg_num]
            if row['dmsMessageStatus'] != 4:
                self.sign_control['dmsActivateMessageError'] = 6
                self.sign_control['dmsActivateMessageState'] = 1
                return False
            self._active_mem_type = mem_type
            self._active_msg_num  = msg_num
            self._active_multi    = row['dmsMessageMultiString']
        else:
            self.sign_control['dmsActivateMessageError'] = 6   # msgNotDefined
            self.sign_control['dmsActivateMessageState'] = 1
            return False

        # Update source code
        crc = self._crc16(self._active_multi) if self._active_multi else 0
        self.sign_control['dmsMessageTableSource'] = bytes([
            self._active_mem_type,
            (self._active_msg_num >> 8) & 0xFF,
            self._active_msg_num & 0xFF,
            (crc >> 8) & 0xFF,
            crc & 0xFF,
        ])
        self.sign_control['dmsActivateMessageError'] = 0
        self.sign_control['dmsActivateMessageState'] = 2   # activated
        self.sign_control['dmsActivateMessage']      = activation_code

        # Keep current_msg_table (memType=4) in sync
        self.current_msg_table[1].update({
            'dmsMessageMultiString':     self._active_multi,
            'dmsMessageCRC':             crc,
            'dmsMessageStatus':          4 if self._active_multi else 1,
            'dmsMessageRunTimePriority': priority,
        })

        if duration == 0 or duration == 0xFFFF:
            self._active_end_time = None
            self.sign_control['dmsMessageTimeRemaining'] = 65535
        else:
            self._active_end_time = time.time() + duration * 60
            self.sign_control['dmsMessageTimeRemaining'] = duration

        return True

    def tick_control(self):
        """Called periodically — expire timed messages."""
        if self._active_end_time is not None:
            remaining = max(0, int((self._active_end_time - time.time()) / 60))
            self.sign_control['dmsMessageTimeRemaining'] = remaining
            if remaining == 0:
                # Switch to end-duration message
                end_code = self.sign_control['dmsEndDurationMessage']
                self._active_mem_type = end_code[0] if end_code else MSG_MEM_BLANK
                self._active_end_time = None

    # =========================================================================
    # 5.8  Illumination / Brightness Objects  (dms.7)
    # =========================================================================

    def _init_illumination(self):
        """
        Brightness control.

        dmsIllumControl   1=other 2=photocell 3=timer 4=manual 5=simPhotocell
        dmsIllumMaxPhotocellLevel  INTEGER (0..65535)
        dmsIllumPhotocellLevelStatus  INTEGER (live photocell reading)
        dmsIllumNumBrightLevels    number of discrete brightness levels
        dmsIllumBrightLevelStatus  current brightness level (1-based)
        dmsIllumManLevel           target level for manual mode (1-based)
        dmsIllumBrightnessValues   TABLE: level + input_range + output
        dmsIllumLightOutputStatus  INTEGER (0..65535) — actual light output
        dmsIllumBrightnessValuesError  0=other 1=none 2=illumNotSupported
        """
        self.illum = {
            'dmsIllumControl':             2,     # photocell
            'dmsIllumMaxPhotocellLevel':   65535,
            'dmsIllumPhotocellLevelStatus': 32768,  # mid-range (day)
            'dmsIllumNumBrightLevels':     8,
            'dmsIllumBrightLevelStatus':   6,      # level 6 of 8
            'dmsIllumManLevel':            4,
            'dmsIllumLightOutputStatus':   50000,
            'dmsIllumBrightnessValuesError': 1,    # none
        }

        # Brightness table: 8 levels, each maps a photocell range to output
        self.illum_brightness_table = {}
        for lv in range(1, 9):
            self.illum_brightness_table[lv] = {
                'dmsIllumBrightnessLevel':      lv,
                'dmsIllumPhotocellLevelRange':  lv * 8191,   # photocell threshold
                'dmsIllumBrightnessOutput':     lv * 8191,   # light output
            }

        self._last_illum_tick = time.time()

    def tick_illumination(self):
        """Simulate photocell-driven brightness variation (day/night cycle)."""
        import math
        t = time.time()
        # Simulate a 24-hour photocell cycle
        cycle = (t % 86400) / 86400   # 0.0–1.0 over a day
        # Peak at noon (0.5), minimum at midnight (0.0 or 1.0)
        level = 0.5 - 0.5 * math.cos(2 * math.pi * cycle)
        pc = int(level * 65535)
        self.illum['dmsIllumPhotocellLevelStatus'] = pc
        # Map photocell to brightness level
        lv = max(1, min(8, int(level * 8) + 1))
        self.illum['dmsIllumBrightLevelStatus']  = lv
        self.illum['dmsIllumLightOutputStatus']  = int(level * 65535)

    # =========================================================================
    # 5.9  Scheduling Action Objects  (dms.8)
    # =========================================================================

    def _init_scheduling(self):
        """
        Time-based action table — schedules automatic message activations.

        dmsActionNumberEntries  number of entries in action table
        dmsActionTable:
          dmsActionIndex
          dmsActionMsgCode     MessageIDCode (5 bytes) to activate
          dmsActionStartMinute  minutes from midnight (0..1439)
          dmsActionStopMinute   minutes from midnight
          dmsActionDayBitmap    bitmask: Mon=0x01 Tue=0x02 ... Sun=0x40

        Pre-populated with two entries:
          1 — Permanent message 2 ("SPEED LIMIT 55") displayed 06:00–22:00 weekdays
          2 — Blank displayed 22:00–06:00 (outside hours, clears sign)
        """
        self.action_num_entries = 2

        def _code(mem_type, msg_num, crc):
            return bytes([mem_type,
                          (msg_num >> 8) & 0xFF, msg_num & 0xFF,
                          (crc >> 8) & 0xFF,     crc & 0xFF])

        p2_crc = self.permanent_msg_table[2]['dmsMessageCRC']

        self.action_table = {
            1: {
                'dmsActionIndex':      1,
                'dmsActionMsgCode':    _code(MSG_MEM_PERMANENT, 2, p2_crc),
                'dmsActionStartMinute': 6 * 60,    # 06:00
                'dmsActionStopMinute':  22 * 60,   # 22:00
                'dmsActionDayBitmap':   0b00111110, # Mon–Fri
            },
            2: {
                'dmsActionIndex':      2,
                'dmsActionMsgCode':    _code(MSG_MEM_BLANK, 0, 0),
                'dmsActionStartMinute': 22 * 60,
                'dmsActionStopMinute':   6 * 60,
                'dmsActionDayBitmap':   0b01111111, # all days
            },
        }

    # =========================================================================
    # 5.11  Sign Status  (dms.9)
    # =========================================================================

    def _init_sign_status(self):
        """
        Sign status objects.  OID layout: dms.9 = signStat node.

        The internal sub-node structure follows the v01/v02 MIB grouping that
        most deployed TMS systems expect, where dms.9.7 is the statError
        sub-node (not a scalar).  This is the layout observed in the field:

          dms.9.1.0    dmsSignStatus        bitmask: visible operational faults
          dms.9.2.1    multiFieldTable      MULTI field values (table)
          dms.9.3.0    currentSpeed         km/h (from [f] speed field)
          dms.9.4.0    currentSpeedLimit    km/h
          dms.9.5.0    watchdogFailureCount Counter32
          dms.9.6.0    dmsStatDoorOpen      0=closed 1=open

          dms.9.7      statError sub-node
            dms.9.7.1.0  shortErrorStatus       bitmask (2 bytes)
            dms.9.7.2.0  numPixelFailureRows     INTEGER
            dms.9.7.3.1  pixelFailureTable       TABLE
            dms.9.7.4.0  pixelTestActivation     0=noTest 1=test
            dms.9.7.5.0  stuckOnLampFailure      bitmask
            dms.9.7.6.0  stuckOffLampFailure     bitmask
            dms.9.7.7.0  lampTestActivation      0=noTest 1=test
            dms.9.7.8.0  fanFailure              bitmask
            dms.9.7.9.0  fanTestActivation       0=noTest 1=test
            dms.9.7.10.0 controllerErrorStatus   bitmask

          dms.9.8      powerStatus sub-node
            dms.9.8.1.0  signVolts              millivolts (AC supply)
            dms.9.8.2.0  lowFuelThreshold       litres
            dms.9.8.3.0  fuelLevel              litres
            dms.9.8.4.0  engineRPM              rpm
            dms.9.8.5.0  lineVolts              millivolts (line input)
            dms.9.8.6.0  powerSource            1=ac 2=generator 3=solar 4=battery

          dms.9.9      tempStatus sub-node
            dms.9.9.1.0  minCabinetTemp         °C
            dms.9.9.2.0  maxCabinetTemp         °C
            dms.9.9.3.0  minAmbientTemp         °C
            dms.9.9.4.0  maxAmbientTemp         °C
            dms.9.9.5.0  minSignHousingTemp     °C
            dms.9.9.6.0  maxSignHousingTemp     °C
        """
        # Core status  (dms.9.1.0)
        self.dms_sign_status = 0    # 0 = no faults (bitmask)

        # MULTI field table  (dms.9.2.1.<col>.<row>)
        self.num_multi_field_rows = 0
        self.multi_field_table    = {}   # empty in simulation

        # Speed info  (dms.9.3.0, .9.4.0)
        self.current_speed       = 0
        self.current_speed_limit = 0

        # Watchdog / door  (dms.9.5.0, .9.6.0)
        self.watchdog_failure_count = 0
        self.stat_door_open         = 0   # 0=closed

        # statError sub-node  (dms.9.7.x)
        self.stat_error = {
            'shortErrorStatus':       0,   # .9.7.1.0
            'numPixelFailureRows':     0,   # .9.7.2.0
            'pixelTestActivation':     0,   # .9.7.4.0  0=noTest
            'stuckOnLampFailure':      0,   # .9.7.5.0
            'stuckOffLampFailure':     0,   # .9.7.6.0
            'lampTestActivation':      0,   # .9.7.7.0
            'fanFailure':              0,   # .9.7.8.0
            'fanTestActivation':       0,   # .9.7.9.0
            'controllerErrorStatus':   0,   # .9.7.10.0
        }
        self.pixel_failure_table = {}   # (.9.7.3.1.<col>.<row>) — empty

        # powerStatus sub-node  (dms.9.8.x)
        self.power_status = {
            'signVolts':        120000,  # 120 V in mV  .9.8.1.0
            'lowFuelThreshold': 10,      # litres        .9.8.2.0
            'fuelLevel':        0,       #               .9.8.3.0
            'engineRPM':        0,       #               .9.8.4.0
            'lineVolts':        120000,  # 120 V in mV  .9.8.5.0
            'powerSource':      1,       # ac(1)         .9.8.6.0
        }

        # tempStatus sub-node  (dms.9.9.x)
        self.temp_status = {
            'minCabinetTemp':     15,   # .9.9.1.0
            'maxCabinetTemp':     42,   # .9.9.2.0
            'minAmbientTemp':     10,   # .9.9.3.0
            'maxAmbientTemp':     38,   # .9.9.4.0
            'minSignHousingTemp': 12,   # .9.9.5.0
            'maxSignHousingTemp': 55,   # .9.9.6.0
        }

        self._last_status_tick = time.time()

    def tick_status(self):
        """Gently vary simulated temperature readings."""
        import math
        t  = time.time()
        self._last_status_tick = t
        base = 28 + 14 * math.sin(t / 3600)
        self.temp_status['maxCabinetTemp'] = int(base)
        self.temp_status['minCabinetTemp'] = int(base - 13)
        ambient = 22 + 10 * math.sin(t / 7200)
        self.temp_status['maxAmbientTemp'] = int(ambient)
        self.temp_status['minAmbientTemp'] = int(ambient - 12)

    # =========================================================================
    # 5.12  Graphic Definition Objects  (dms.10)
    # =========================================================================

    def _init_graphic_group(self):
        """
        Graphic (bitmap image) storage.

        dmsMaxNumberGraphics    maximum number of stored graphics
        dmsNumGraphics          currently defined graphics
        dmsMaxGraphicSize       max size in bytes of a single graphic
        dmsAvailableGraphicMemory  bytes of graphic memory remaining
        dmsGraphicBlockSize     bytes per transfer block

        dmsGraphicTable:
          dmsGraphicIndex
          dmsGraphicNumber       logical ID referenced in MULTI [g…]
          dmsGraphicName         DisplayString
          dmsGraphicHeight       pixels
          dmsGraphicWidth        pixels
          dmsGraphicType         1=mono8bit 2=color8bit 3=color24bit
          dmsGraphicID           CRC-16 of graphic data
          dmsGraphicStatus       1=notUsed 2=modifying 3=calculatingID
                                 4=readyForUse 5=permanent 6=cleared

        dmsGraphicBitmapTable  per-block bitmap transfer table
          (used during upload; we provide a single placeholder block per graphic)

        We pre-define one graphic: a 16×16 mono arrow.
        """
        self.max_graphics          = 8
        self.num_graphics          = 1
        self.max_graphic_size      = 4096   # bytes
        self.available_graphic_mem = 32768
        self.graphic_block_size    = 64     # bytes per block

        # 16×16 mono arrow placeholder (32 bytes = 256 bits)
        _arrow_bmp = bytes([
            0b00010000, 0b00000000,
            0b00111000, 0b00000000,
            0b01111100, 0b00000000,
            0b11111110, 0b00000000,
            0b11111111, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
            0b00111000, 0b00000000,
        ])

        def _crc16(data):
            crc = 0xFFFF
            for b in data:
                crc ^= b
                for _ in range(8):
                    crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
            return crc & 0xFFFF

        self.graphic_table = {}

        # Pre-populate all max_graphics rows so the TMS never gets NoSuchName
        # when it iterates up to dmsMaxNumberGraphics.  Empty slots are notUsed(1).
        _empty_gfx = {
            'dmsGraphicNumber':              0,
            'dmsGraphicName':                b'',
            'dmsGraphicHeight':              0,
            'dmsGraphicWidth':               0,
            'dmsGraphicType':                1,              # mono8bit
            'dmsGraphicID':                  0,
            'dmsGraphicStatus':              1,              # notUsed
            'dmsGraphicTransparentColor':    bytes([0, 0, 0]),
            'dmsGraphicTransparentEnabled':  1,              # disabled
        }
        for gi in range(1, self.max_graphics + 1):
            self.graphic_table[gi] = dict(_empty_gfx, **{'dmsGraphicIndex': gi,
                                                          'dmsGraphicNumber': gi})

        # Overwrite row 1 with the pre-defined arrow graphic
        self.graphic_table[1].update({
            'dmsGraphicNumber':              1,
            'dmsGraphicName':                b'Arrow16x16',
            'dmsGraphicHeight':              16,
            'dmsGraphicWidth':               16,
            'dmsGraphicType':                1,              # mono8bit
            'dmsGraphicID':                  _crc16(_arrow_bmp),
            'dmsGraphicStatus':              4,              # readyForUse
            'dmsGraphicTransparentColor':    bytes([0, 0, 0]),
            'dmsGraphicTransparentEnabled':  1,              # disabled
        })

        self.num_graphics = 1   # only one actually defined

        # Bitmap data — one placeholder block per graphic row so GETNEXT walks
        # don't fall off the table for rows 2-8 (which are notUsed but readable).
        self.graphic_bitmap_table = {}
        for gi in range(1, self.max_graphics + 1):
            self.graphic_bitmap_table[(gi, 1)] = {
                'dmsGraphicBitmapIndex':  gi,
                'dmsGraphicBlockIndex':   1,
                'dmsGraphicBlockBitmap':  bytes(0),    # empty for notUsed rows
            }

        # Row 1 has actual bitmap data
        self.graphic_bitmap_table[(1, 1)] = {
            'dmsGraphicBitmapIndex':  1,
            'dmsGraphicBlockIndex':   1,
            'dmsGraphicBlockBitmap':  _arrow_bmp,
        }
