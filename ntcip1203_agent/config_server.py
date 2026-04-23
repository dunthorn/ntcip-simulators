"""
config_server.py  —  NTCIP 1203 DMS Configuration Web UI

A lightweight HTTP server that runs alongside the DMS agent and provides
a browser-based interface for inspecting and editing key MIB objects.

Usage (launched automatically by dms_agent.py --config-port 8080):
    python3 -m ntcip1203_agent.dms_agent --config-port 8080

Then open http://localhost:8080 in a browser.

Requires only the Python standard library.
"""

import json
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

log = logging.getLogger('dms_config_server')


# ---------------------------------------------------------------------------
# Object metadata — defines every field shown in the UI
# ---------------------------------------------------------------------------

# Enumeration maps for dropdown fields

# dmsSignAccess: bitmask — bit 0=other, bit 1=walkIn, bit 2=rear, bit 3=front
# Displayed as integer in the UI with a bitmask hint (not a dropdown)
# _SIGN_ACCESS is kept as None so the UI renders a plain text input.

# dmsSignType: INTEGER enumeration per NTCIP 1203 v02 Section 5.2.2
_SIGN_TYPE = {
    1:   'other',
    2:   'bos',
    3:   'cms',
    4:   'vmsChar',
    5:   'vmsLine',
    6:   'vmsFull',
    129: 'portableOther',
    130: 'portableBOS',
    131: 'portableCMS',
    132: 'portableVMSChar',
    133: 'portableVMSLine',
    134: 'portableVMSFull',
}

# dmsSignTechnology: bitmask per NTCIP 1203 v02 Section 5.2.9
# bit 0=other, bit 1=led, bit 2=flipDisc, bit 3=fiberOptic,
# bit 4=shuttered, bit 5=lamp
# Displayed as integer with a bitmask hint (not a dropdown).

# dmsBeaconType: INTEGER enumeration per NTCIP 1203 v02 Section 5.2.8
_BEACON_TYPE   = {0:'none', 1:'oneBeacon', 2:'twoBeacons', 3:'twoBeaconsFront',
                  4:'twoBeaconsRear', 5:'twoBeaconsFrontRear', 6:'other'}

_COLOR_SCHEME  = {1:'monochrome1bit', 2:'monochrome8bit', 3:'colorClassic', 4:'color24bit'}
_CTRL_MODE     = {1:'other', 2:'local', 3:'external', 4:'central', 5:'centralOverride'}
_ILLUM_CTRL    = {1:'other', 2:'photocell', 3:'timer', 4:'manual', 5:'simPhotocell'}
_JUST_LINE     = {1:'other', 2:'left', 3:'center', 4:'right', 5:'full'}
_JUST_PAGE     = {1:'other', 2:'top', 3:'middle', 4:'bottom'}
_CHAR_SET      = {1:'other', 2:'ascii', 3:'latin1', 4:'unicode'}
_FONT_STATUS   = {1:'notUsed', 2:'modifying', 3:'calculatingID', 4:'readyForUse',
                  5:'permanent', 6:'cleared'}

# Section → list of (label, getter, setter_or_None, enum_map_or_None, help_text)
# getter/setter are callables that take/return a DMSDataStore
SECTIONS = [
    {
        'id':    'sign_config',
        'title': 'Sign Configuration',
        'icon':  '🪧',
        'fields': [
            ('Sign Type',          lambda s: s.sign_config['dmsSignType'],
                                   lambda s,v: s.sign_config.__setitem__('dmsSignType', int(v)),
                                   _SIGN_TYPE,
                                   'Type of sign: bos=Blank-Out, cms=Changeable, vmsChar/Line/Full=Variable'),
            ('Sign Access',        lambda s: s.sign_config['dmsSignAccess'],
                                   lambda s,v: s.sign_config.__setitem__('dmsSignAccess', int(v)),
                                   None,
                                   'Bitmask: bit0=other bit1=walkIn bit2=rear bit3=front (e.g. 6 = rear+front)'),
            ('Sign Technology',    lambda s: s.sign_config['dmsSignTechnology'],
                                   lambda s,v: s.sign_config.__setitem__('dmsSignTechnology', int(v)),
                                   None,
                                   'Bitmask: bit0=other bit1=led bit2=flipDisc bit3=fiberOptic bit4=shuttered bit5=lamp'),
            ('Beacon Type',        lambda s: s.sign_config['dmsBeaconType'],
                                   lambda s,v: s.sign_config.__setitem__('dmsBeaconType', int(v)),
                                   _BEACON_TYPE,
                                   'Attached beacon configuration'),
            ('Sign Height (mm)',   lambda s: s.sign_config['dmsSignHeight'],
                                   lambda s,v: s.sign_config.__setitem__('dmsSignHeight', int(v)),
                                   None,
                                   'Cabinet height including border (mm)'),
            ('Sign Width (mm)',    lambda s: s.sign_config['dmsSignWidth'],
                                   lambda s,v: s.sign_config.__setitem__('dmsSignWidth', int(v)),
                                   None,
                                   'Cabinet width including border (mm)'),
            ('H Border (mm)',      lambda s: s.sign_config['dmsHorizontalBorder'],
                                   lambda s,v: s.sign_config.__setitem__('dmsHorizontalBorder', int(v)),
                                   None,
                                   'Horizontal pixel border (mm)'),
            ('V Border (mm)',      lambda s: s.sign_config['dmsVerticalBorder'],
                                   lambda s,v: s.sign_config.__setitem__('dmsVerticalBorder', int(v)),
                                   None,
                                   'Vertical pixel border (mm)'),
            ('Legend',             lambda s: s.sign_config['dmsLegend'].decode('ascii', errors='replace'),
                                   lambda s,v: s.sign_config.__setitem__('dmsLegend', v.encode()[:255]),
                                   None,
                                   'Fixed legend text printed on the sign face (DisplayString)'),
        ],
    },
    {
        'id':    'vms_config',
        'title': 'VMS Configuration',
        'icon':  '📺',
        'fields': [
            ('Width (px)',         lambda s: s.vms_config['vmsSignWidthPixels'],
                                   None, None, 'Sign width in pixels (read-only)'),
            ('Height (px)',        lambda s: s.vms_config['vmsSignHeightPixels'],
                                   None, None, 'Sign height in pixels (read-only)'),
            ('Char Width (px)',    lambda s: s.vms_config['vmsCharacterWidthPixels'],
                                   None, None, 'Character cell width (read-only)'),
            ('Char Height (px)',   lambda s: s.vms_config['vmsCharacterHeightPixels'],
                                   None, None, 'Character cell height (read-only)'),
            ('H Pitch (1/10mm)',   lambda s: s.vms_config['vmsHorizontalPitch'],
                                   None, None, 'Horizontal pixel pitch'),
            ('V Pitch (1/10mm)',   lambda s: s.vms_config['vmsVerticalPitch'],
                                   None, None, 'Vertical pixel pitch'),
            ('Color Scheme',       lambda s: s.multi_cfg['dmsColorScheme'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsColorScheme', int(v)),
                                   _COLOR_SCHEME, 'Display colour capability'),
        ],
    },
    {
        'id':    'multi_defaults',
        'title': 'MULTI Defaults',
        'icon':  '✏️',
        'fields': [
            ('Default Font',       lambda s: s.multi_cfg['dmsDefaultFont'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsDefaultFont', int(v)),
                                   None, 'Default font number (1-based)'),
            ('Line Justification', lambda s: s.multi_cfg['dmsDefaultJustificationLine'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsDefaultJustificationLine', int(v)),
                                   _JUST_LINE, 'Default line justification'),
            ('Page Justification', lambda s: s.multi_cfg['dmsDefaultJustificationPage'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsDefaultJustificationPage', int(v)),
                                   _JUST_PAGE, 'Default page (vertical) justification'),
            ('Page On Time (1/10s)',lambda s: s.multi_cfg['dmsDefaultPageOnTime'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsDefaultPageOnTime', int(v)),
                                   None, 'Default page display duration'),
            ('Page Off Time (1/10s)',lambda s: s.multi_cfg['dmsDefaultPageOffTime'],
                                    lambda s,v: s.multi_cfg.__setitem__('dmsDefaultPageOffTime', int(v)),
                                    None, 'Default page off (flash) duration; 0=static'),
            ('Max Pages',          lambda s: s.multi_cfg['dmsMaxNumberPages'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsMaxNumberPages', int(v)),
                                   None, 'Maximum pages per message'),
            ('Max MULTI Length',   lambda s: s.multi_cfg['dmsMaxMultiStringLength'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsMaxMultiStringLength', int(v)),
                                   None, 'Maximum MULTI string length in bytes'),
            ('Character Set',      lambda s: s.multi_cfg['dmsDefaultCharacterSet'],
                                   lambda s,v: s.multi_cfg.__setitem__('dmsDefaultCharacterSet', int(v)),
                                   _CHAR_SET, 'Default character encoding'),
        ],
    },
    {
        'id':    'sign_control',
        'title': 'Sign Control',
        'icon':  '🎛️',
        'fields': [
            ('Control Mode',       lambda s: s.sign_control['dmsControlMode'],
                                   lambda s,v: s.sign_control.__setitem__('dmsControlMode', int(v)),
                                   _CTRL_MODE, 'Current control authority'),
            ('Active Message',     lambda s: s._active_multi.decode('ascii', errors='replace') or '(blank)',
                                   None, None, 'Currently displayed MULTI string'),
            ('Time Remaining (min)',lambda s: s.sign_control['dmsMessageTimeRemaining'],
                                    None, None, '0 or 65535 = continuous'),
            ('Activate State',     lambda s: {1:'notActivated', 2:'activated'}.get(
                                        s.sign_control['dmsActivateMessageState'], '?'),
                                   None, None, ''),
            ('Last Activate Error', lambda s: {0:'none', 1:'other', 2:'priority',
                                               3:'underrun', 4:'unsupportedMulti',
                                               5:'badCRC', 6:'msgNotDefined'}.get(
                                        s.sign_control['dmsActivateMessageError'], '?'),
                                    None, None, 'Error from most recent activation attempt'),
            ('Comm Loss Time (s)', lambda s: s.sign_control['dmsCommLossTime'],
                                   lambda s,v: s.sign_control.__setitem__('dmsCommLossTime', int(v)),
                                   None, 'Seconds without poll before comm-loss message'),
            ('Short Power Loss (s)',lambda s: s.sign_control['dmsShortPowerLossTime'],
                                    lambda s,v: s.sign_control.__setitem__('dmsShortPowerLossTime', int(v)),
                                    None, 'Power outage shorter than this → short recovery msg'),
            ('Pixel Svc Freq (hr)',lambda s: s.sign_control['dmsPixelServiceFrequency'],
                                   lambda s,v: s.sign_control.__setitem__('dmsPixelServiceFrequency', int(v)),
                                   None, 'How often automatic pixel service runs'),
        ],
    },
    {
        'id':    'illumination',
        'title': 'Illumination',
        'icon':  '💡',
        'fields': [
            ('Illum Control',      lambda s: s.illum['dmsIllumControl'],
                                   lambda s,v: s.illum.__setitem__('dmsIllumControl', int(v)),
                                   _ILLUM_CTRL, 'Brightness control method'),
            ('Manual Level',       lambda s: s.illum['dmsIllumManLevel'],
                                   lambda s,v: s.illum.__setitem__('dmsIllumManLevel', int(v)),
                                   None, 'Target level when in manual mode (1–8)'),
            ('Num Bright Levels',  lambda s: s.illum['dmsIllumNumBrightLevels'],
                                   None, None, 'Number of discrete brightness levels'),
            ('Current Level',      lambda s: s.illum['dmsIllumBrightLevelStatus'],
                                   None, None, 'Active brightness level (live)'),
            ('Photocell Level',    lambda s: s.illum['dmsIllumPhotocellLevelStatus'],
                                   None, None, 'Live photocell reading (0–65535)'),
            ('Light Output',       lambda s: s.illum['dmsIllumLightOutputStatus'],
                                   None, None, 'Actual light output (0–65535)'),
        ],
    },
    {
        'id':    'status',
        'title': 'Status',
        'icon':  '📊',
        'fields': [
            ('Sign Status',        lambda s: f'0x{s.dms_sign_status:04X}',
                                   None, None, 'Error bitmask (0 = no faults)'),
            ('Short Error Status', lambda s: f'0x{s.stat_error["shortErrorStatus"]:04X}',
                                   None, None, 'Summary error flags'),
            ('Door Open',          lambda s: {0:'closed', 1:'open'}.get(s.stat_door_open, '?'),
                                   None, None, ''),
            ('Pixel Failures',     lambda s: s.stat_error['numPixelFailureRows'],
                                   None, None, 'Number of failed pixels'),
            ('Fan Failure',        lambda s: f'0x{s.stat_error["fanFailure"]:02X}',
                                   None, None, 'Fan failure bitmask'),
            ('Cabinet Temp (°C)',  lambda s: f'{s.temp_status["minCabinetTemp"]}–{s.temp_status["maxCabinetTemp"]}',
                                   None, None, 'Min–Max since last reset'),
            ('Ambient Temp (°C)',  lambda s: f'{s.temp_status["minAmbientTemp"]}–{s.temp_status["maxAmbientTemp"]}',
                                   None, None, ''),
            ('Sign Volts (mV)',    lambda s: s.power_status['signVolts'],
                                   None, None, 'AC supply voltage in millivolts'),
            ('Power Source',       lambda s: {1:'ac', 2:'generator', 3:'solar', 4:'battery'}.get(
                                        s.power_status['powerSource'], '?'),
                                   None, None, ''),
            ('Humidity (%)',       lambda s: '-',
                                   None, None, ''),
        ],
    },
    {
        'id':    'messages',
        'title': 'Messages',
        'icon':  '📝',
        'fields': [
            ('Num Permanent',      lambda s: s.num_permanent_messages,
                                   None, None, 'Factory-stored messages'),
            ('Num Changeable',     lambda s: s.num_changeable_messages,
                                   None, None, 'Operator-stored messages'),
            ('Max Changeable',     lambda s: s.max_changeable_messages,
                                   None, None, ''),
            ('Changeable Free (B)',lambda s: s.changeable_free_bytes,
                                   None, None, 'Bytes available in changeable memory'),
            ('Num Volatile',       lambda s: s.num_volatile_messages,
                                   None, None, 'Temporary messages'),
            ('Volatile Free (B)',  lambda s: s.volatile_free_bytes,
                                   None, None, 'Bytes available in volatile memory'),
        ],
    },
    {
        'id':    'color',
        'title': 'Color',
        'icon':  '🎨',
        'fields': [
            ('Color Scheme',            lambda s: s.multi_cfg['dmsColorScheme'],
                                        lambda s,v: s.multi_cfg.__setitem__('dmsColorScheme', int(v)),
                                        {1:'monochrome1bit', 2:'monochrome8bit',
                                         3:'colorClassic',   4:'color24bit'},
                                        'Display colour capability of the sign'),
            ('Default BG Color',        lambda s: s.multi_cfg['dmsDefaultBackgroundColor'],
                                        lambda s,v: s.multi_cfg.__setitem__('dmsDefaultBackgroundColor', int(v)),
                                        {0:'black',1:'red',2:'yellow',3:'green',
                                         4:'cyan',5:'blue',6:'magenta',7:'white',8:'orange',9:'amber'},
                                        'Default background colour (classic scheme)'),
            ('Default FG Color',        lambda s: s.multi_cfg['dmsDefaultForegroundColor'],
                                        lambda s,v: s.multi_cfg.__setitem__('dmsDefaultForegroundColor', int(v)),
                                        {0:'black',1:'red',2:'yellow',3:'green',
                                         4:'cyan',5:'blue',6:'magenta',7:'white',8:'orange',9:'amber'},
                                        'Default foreground colour (classic scheme)'),
            ('Default BG RGB',          lambda s: s.multi_cfg['dmsDefaultBackgroundColorRGB'].hex(),
                                        lambda s,v: s.multi_cfg.__setitem__(
                                            'dmsDefaultBackgroundColorRGB',
                                            bytes.fromhex(v.replace('#','').strip()) if len(v.replace('#','')) == 6
                                            else bytes(3)),
                                        None, 'Default background RGB (hex, e.g. 000000)'),
            ('Default FG RGB',          lambda s: s.multi_cfg['dmsDefaultForegroundColorRGB'].hex(),
                                        lambda s,v: s.multi_cfg.__setitem__(
                                            'dmsDefaultForegroundColorRGB',
                                            bytes.fromhex(v.replace('#','').strip()) if len(v.replace('#','')) == 6
                                            else bytes(3)),
                                        None, 'Default foreground RGB (hex, e.g. ffff00)'),
            ('Monochrome Color',        lambda s: s.vms_config['monochromeColor'].hex(),
                                        lambda s,v: s.vms_config.__setitem__(
                                            'monochromeColor',
                                            bytes.fromhex(v.replace('#','').strip()) if len(v.replace('#','')) == 6
                                            else bytes(3)),
                                        None, 'Physical LED colour for monochrome signs (hex RGB, e.g. ffa500 for amber)'),
        ],
    },
    {
        'id':    'graphics',
        'title': 'Graphics',
        'icon':  '🖼️',
        'fields': [
            ('Max Graphics',         lambda s: s.max_graphics,
                                     None, None, 'Maximum number of storable graphics'),
            ('Num Graphics',         lambda s: s.num_graphics,
                                     None, None, 'Currently defined graphics'),
            ('Max Graphic Size (B)', lambda s: s.max_graphic_size,
                                     None, None, 'Maximum bytes per graphic bitmap'),
            ('Available Mem (B)',    lambda s: s.available_graphic_mem,
                                     None, None, 'Graphic memory remaining (Counter32)'),
            ('Block Size (B)',       lambda s: s.graphic_block_size,
                                     None, None, 'Bytes per bitmap transfer block'),
            # Graphic 1 fields (col 1-10 in dmsGraphicTable)
            ('G1 Number',    lambda s: s.graphic_table[1]['dmsGraphicNumber'],
                             lambda s,v: s.graphic_table[1].__setitem__('dmsGraphicNumber', int(v)),
                             None, 'Logical ID referenced in MULTI [g1]'),
            ('G1 Name',      lambda s: s.graphic_table[1]['dmsGraphicName'].decode('ascii','replace'),
                             lambda s,v: s.graphic_table[1].__setitem__('dmsGraphicName', v.encode()[:64]),
                             None, 'DisplayString name'),
            ('G1 Size',      lambda s: f'{s.graphic_table[1]["dmsGraphicWidth"]}×{s.graphic_table[1]["dmsGraphicHeight"]} px',
                             None, None, 'Width × height (read-only)'),
            ('G1 Type',      lambda s: s.graphic_table[1]['dmsGraphicType'],
                             lambda s,v: s.graphic_table[1].__setitem__('dmsGraphicType', int(v)),
                             {1:'mono8bit', 2:'color8bit', 3:'color24bit'},
                             'Pixel colour depth (dmsGraphicType col 6)'),
            ('G1 Status',    lambda s: s.graphic_table[1]['dmsGraphicStatus'],
                             lambda s,v: s.graphic_table[1].__setitem__('dmsGraphicStatus', int(v)),
                             {1:'notUsed', 2:'modifying', 3:'calculatingID',
                              4:'readyForUse', 5:'permanent', 6:'cleared'},
                             'Graphic lifecycle state (dmsGraphicStatus col 8)'),
            ('G1 Trans. Color',lambda s: s.graphic_table[1]['dmsGraphicTransparentColor'].hex(),
                               lambda s,v: s.graphic_table[1].__setitem__(
                                   'dmsGraphicTransparentColor',
                                   bytes.fromhex(v.replace('#','').strip())
                                   if len(v.replace('#','').strip()) == 6 else bytes(3)),
                               None,
                               'RGB colour treated as transparent, hex (col 9, OctetString e.g. 000000)'),
            ('G1 Transparent', lambda s: s.graphic_table[1]['dmsGraphicTransparentEnabled'],
                               lambda s,v: s.graphic_table[1].__setitem__('dmsGraphicTransparentEnabled', int(v)),
                               {1:'disabled', 2:'enabled'},
                               'Transparent colour enabled (col 10, INTEGER: 1=disabled 2=enabled)'),
        ],
    },
]


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ConfigHandler(BaseHTTPRequestHandler):

    store       = None   # set by ConfigServer before starting
    config_file = None   # set by ConfigServer if --config-file was given

    def log_message(self, fmt, *args):
        log.debug(fmt % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/state':
            self._send_json(self._collect_state())
        elif parsed.path == '/api/save':
            # GET to /api/save triggers a save and returns ok/error
            if not self.config_file:
                self._send_json({'ok': False, 'error': 'No config file specified (use --config-file)'}, status=400)
                return
            try:
                import json as _json
                data = _collect_config_dict(self.store)
                with open(self.config_file, 'w') as f:
                    _json.dump(data, f, indent=2)
                log.info(f"Config saved to {self.config_file!r}")
                self._send_json({'ok': True, 'path': self.config_file})
            except Exception as ex:
                self._send_json({'ok': False, 'error': str(ex)}, status=500)
        elif parsed.path == '/':
            self._send_html(_HTML)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/set':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                data    = json.loads(body)
                section = data['section']
                field   = data['field']
                value   = data['value']
                self._apply_set(section, field, value)
                self._send_json({'ok': True})
            except Exception as ex:
                log.warning(f'Config SET error: {ex}')
                self._send_json({'ok': False, 'error': str(ex)}, status=400)
        else:
            self.send_error(404)

    # ------------------------------------------------------------------

    def _collect_state(self):
        s = self.store
        result = {}
        for sec in SECTIONS:
            fields = {}
            for label, getter, setter, enums, help_text in sec['fields']:
                try:
                    raw = getter(s)
                    fields[label] = {
                        'value':    raw,
                        'writable': setter is not None,
                        'enums':    enums,
                        'help':     help_text,
                    }
                except Exception as ex:
                    fields[label] = {'value': f'ERR: {ex}', 'writable': False,
                                     'enums': None, 'help': ''}
            result[sec['id']] = fields
        return result

    def _apply_set(self, section_id, field_label, value):
        s = self.store
        for sec in SECTIONS:
            if sec['id'] != section_id:
                continue
            for label, getter, setter, enums, _ in sec['fields']:
                if label == field_label:
                    if setter is None:
                        raise ValueError(f'{label} is read-only')
                    setter(s, value)
                    log.info(f'Config SET {section_id}.{field_label} = {value!r}')
                    return
        raise KeyError(f'Unknown field {section_id}/{field_label}')

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# HTML / CSS / JS  (single-file, no external dependencies)
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NTCIP 1203 DMS Config</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

  :root {
    --bg:        #0d0f14;
    --surface:   #151820;
    --border:    #252a35;
    --accent:    #00d4aa;
    --accent2:   #ff6b35;
    --warn:      #f5c842;
    --text:      #c8d0e0;
    --text-dim:  #5a6480;
    --text-head: #e8edf5;
    --mono:      'IBM Plex Mono', monospace;
    --sans:      'IBM Plex Sans', sans-serif;
    --radius:    4px;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-size: 13px;
    min-height: 100vh;
  }

  /* ── Top bar ── */
  header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky; top: 0; z-index: 100;
  }
  header .logo {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    color: var(--accent);
    text-transform: uppercase;
  }
  header .sep { flex: 1; }
  #btn-save {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--bg);
    background: var(--accent);
    border: none;
    border-radius: var(--radius);
    padding: 5px 14px;
    cursor: pointer;
    opacity: 0.85;
    transition: opacity 0.15s;
  }
  #btn-save:hover { opacity: 1; }
  #btn-save:disabled { opacity: 0.35; cursor: default; }
  #status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--text-dim);
    transition: background 0.3s;
  }
  #status-dot.ok  { background: var(--accent); box-shadow: 0 0 8px var(--accent); }
  #status-dot.err { background: var(--accent2); box-shadow: 0 0 8px var(--accent2); }
  #status-label {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
  }
  #active-msg-banner {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--accent);
    padding: 3px 10px;
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ── Layout ── */
  .layout {
    display: grid;
    grid-template-columns: 200px 1fr;
    min-height: calc(100vh - 49px);
  }

  /* ── Sidebar ── */
  nav {
    border-right: 1px solid var(--border);
    padding: 16px 0;
    position: sticky;
    top: 49px;
    height: calc(100vh - 49px);
    overflow-y: auto;
  }
  nav a {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 20px;
    color: var(--text-dim);
    text-decoration: none;
    font-size: 12px;
    font-weight: 400;
    letter-spacing: 0.02em;
    transition: color 0.15s, background 0.15s;
    cursor: pointer;
  }
  nav a:hover { color: var(--text); background: rgba(255,255,255,0.03); }
  nav a.active { color: var(--accent); background: rgba(0,212,170,0.06); }
  nav a .icon { font-size: 14px; width: 18px; text-align: center; }

  /* ── Main ── */
  main {
    padding: 0;
    overflow-y: auto;
  }

  section.panel {
    display: none;
    padding: 28px 32px;
  }
  section.panel.active { display: block; }

  .panel-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 24px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }
  .panel-header h2 {
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 600;
    color: var(--text-head);
    letter-spacing: 0.05em;
  }
  .panel-header .badge {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    border: 1px solid var(--border);
    padding: 2px 7px;
    border-radius: 20px;
  }

  /* ── Field grid ── */
  .field-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 12px;
  }

  .field-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    transition: border-color 0.2s;
  }
  .field-card:hover { border-color: #2e3548; }
  .field-card.writable { border-left: 2px solid var(--accent); }
  .field-card.modified { border-left: 2px solid var(--warn); animation: flash 0.4s; }

  @keyframes flash {
    0%  { background: rgba(245,200,66,0.12); }
    100%{ background: var(--surface); }
  }

  .field-label {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    text-transform: uppercase;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .field-label .w-badge {
    font-size: 8px;
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 2px;
    padding: 0 4px;
    letter-spacing: 0.05em;
  }

  .field-value {
    font-family: var(--mono);
    font-size: 14px;
    font-weight: 400;
    color: var(--text-head);
    word-break: break-all;
  }

  .field-help {
    font-size: 10px;
    color: var(--text-dim);
    margin-top: 5px;
    line-height: 1.4;
  }

  /* ── Inline editor ── */
  .field-editor {
    margin-top: 8px;
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .field-editor input,
  .field-editor select {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-head);
    font-family: var(--mono);
    font-size: 12px;
    padding: 5px 8px;
    outline: none;
    transition: border-color 0.15s;
  }
  .field-editor input:focus,
  .field-editor select:focus { border-color: var(--accent); }
  .field-editor button {
    background: var(--accent);
    color: var(--bg);
    border: none;
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    padding: 5px 12px;
    cursor: pointer;
    transition: opacity 0.15s;
    white-space: nowrap;
  }
  .field-editor button:hover { opacity: 0.85; }
  .field-editor button.cancel {
    background: transparent;
    color: var(--text-dim);
    border: 1px solid var(--border);
  }

  /* ── Toast ── */
  #toast {
    position: fixed;
    bottom: 24px; right: 24px;
    background: var(--surface);
    border: 1px solid var(--accent);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 11px;
    padding: 10px 16px;
    border-radius: var(--radius);
    opacity: 0;
    transform: translateY(8px);
    transition: opacity 0.2s, transform 0.2s;
    pointer-events: none;
    z-index: 999;
  }
  #toast.show { opacity: 1; transform: translateY(0); }
  #toast.err  { border-color: var(--accent2); color: var(--accent2); }

  /* ── Activate panel ── */
  .activate-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 24px;
  }
  .activate-box h3 {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    text-transform: uppercase;
    margin-bottom: 14px;
  }
  .activate-row { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
  .activate-field { display: flex; flex-direction: column; gap: 4px; flex: 1; min-width: 160px; }
  .activate-field label {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--text-dim);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .activate-field select,
  .activate-field input {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-head);
    font-family: var(--mono);
    font-size: 12px;
    padding: 7px 10px;
    outline: none;
  }
  .activate-field select:focus,
  .activate-field input:focus { border-color: var(--accent); }
  .btn-activate {
    background: var(--accent);
    color: var(--bg);
    border: none;
    border-radius: var(--radius);
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    padding: 8px 20px;
    cursor: pointer;
    letter-spacing: 0.04em;
    transition: opacity 0.15s;
  }
  .btn-activate:hover { opacity: 0.85; }
  .btn-blank {
    background: transparent;
    color: var(--accent2);
    border: 1px solid var(--accent2);
  }

  .msg-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 16px;
    font-family: var(--mono);
    font-size: 11px;
  }
  .msg-table th {
    text-align: left;
    padding: 6px 10px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    letter-spacing: 0.06em;
    font-size: 10px;
    text-transform: uppercase;
  }
  .msg-table td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: top;
  }
  .msg-table tr:hover td { background: rgba(255,255,255,0.02); }
  .msg-table td.multi { color: var(--accent); max-width: 300px; word-break: break-all; }
  .msg-table td.active { color: var(--warn); font-weight: 600; }
  .multi-input {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-head);
    font-family: var(--mono);
    font-size: 11px;
    padding: 4px 8px;
    outline: none;
  }
  .multi-input:focus { border-color: var(--accent); }
  .btn-tiny {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 10px;
    padding: 3px 8px;
    border-radius: var(--radius);
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .btn-tiny:hover { border-color: var(--accent); color: var(--accent); }
  .btn-tiny.activate-btn { border-color: var(--accent2); color: var(--accent2); }
  .btn-tiny.activate-btn:hover { background: var(--accent2); color: var(--bg); }
</style>
</head>
<body>

<header>
  <div class="logo">NTCIP 1203 ▸ DMS Config</div>
  <div class="sep"></div>
  <div id="active-msg-banner">—</div>
  <button id="btn-save" onclick="saveConfig()" title="Save configuration to file">💾 Save Config</button>
  <div id="status-dot"></div>
  <div id="status-label">connecting…</div>
</header>

<div class="layout">
  <nav id="nav"></nav>
  <main id="main"></main>
</div>

<div id="toast"></div>

<script>
const SECTIONS_META = [
  { id:'sign_config',    title:'Sign Configuration', icon:'🪧' },
  { id:'vms_config',     title:'VMS Configuration',  icon:'📺' },
  { id:'multi_defaults', title:'MULTI Defaults',      icon:'✏️' },
  { id:'sign_control',   title:'Sign Control',        icon:'🎛️' },
  { id:'illumination',   title:'Illumination',        icon:'💡' },
  { id:'status',         title:'Status',              icon:'📊' },
  { id:'messages',       title:'Messages',            icon:'📝' },
  { id:'color',          title:'Color',               icon:'🎨' },
  { id:'graphics',       title:'Graphics',            icon:'🖼️' },
  { id:'msg_editor',     title:'Message Editor',      icon:'🖊️' },
];

let state = {};
let activeSection = SECTIONS_META[0].id;

// Track which (sectionId, fieldLabel) pairs have uncommitted edits.
// Key: "sectionId::fieldLabel"
const dirtyFields = new Set();

function markDirty(sectionId, label) { dirtyFields.add(sectionId + '::' + label); }
function clearDirty(sectionId, label) { dirtyFields.delete(sectionId + '::' + label); }
function isDirty(sectionId, label) { return dirtyFields.has(sectionId + '::' + label); }

// ── Build nav ──
const nav = document.getElementById('nav');
SECTIONS_META.forEach(s => {
  const a = document.createElement('a');
  a.dataset.id = s.id;
  a.innerHTML = `<span class="icon">${s.icon}</span>${s.title}`;
  a.addEventListener('click', () => setSection(s.id));
  nav.appendChild(a);
});

// ── Build main panels ──
const main = document.getElementById('main');
SECTIONS_META.forEach(s => {
  const sec = document.createElement('section');
  sec.className = 'panel';
  sec.id = 'panel-' + s.id;
  sec.innerHTML = `
    <div class="panel-header">
      <h2>${s.icon} ${s.title.toUpperCase()}</h2>
      <span class="badge" id="badge-${s.id}"></span>
    </div>
    <div id="content-${s.id}"></div>`;
  main.appendChild(sec);
});

// ── Section switching ──
function setSection(id) {
  activeSection = id;
  document.querySelectorAll('nav a').forEach(a =>
    a.classList.toggle('active', a.dataset.id === id));
  document.querySelectorAll('section.panel').forEach(s =>
    s.classList.toggle('active', s.id === 'panel-' + id));
  renderSection(id);
}

// ── Fetch state ──
async function fetchState() {
  try {
    const r = await fetch('/api/state');
    if (!r.ok) throw new Error(r.status);
    state = await r.json();
    setStatus('ok', 'live');
    renderSection(activeSection);
    updateBanner();
  } catch(e) {
    setStatus('err', 'offline');
  }
}

function setStatus(cls, label) {
  const dot = document.getElementById('status-dot');
  const lbl = document.getElementById('status-label');
  dot.className = '';
  dot.classList.add(cls);
  lbl.textContent = label;
}

function updateBanner() {
  const ctrl = state.sign_control;
  if (!ctrl) return;
  const msg = ctrl['Active Message']?.value || '(blank)';
  document.getElementById('active-msg-banner').textContent = '▶ ' + msg;
}

// ── Render a section ──
function renderSection(id) {
  if (id === 'msg_editor') { renderMsgEditor(); return; }
  const sec = state[id];
  if (!sec) return;
  const container = document.getElementById('content-' + id);
  const fields = Object.entries(sec);
  document.getElementById('badge-' + id).textContent = fields.length + ' objects';

  // Find or create the grid — never destroy it during refresh
  let grid = container.querySelector('.field-grid');
  if (!grid) {
    container.innerHTML = '';
    grid = document.createElement('div');
    grid.className = 'field-grid';
    container.appendChild(grid);
  }

  fields.forEach(([label, info]) => {
    const cardId = 'card-' + id + '-' + encodeField(label);
    let card = document.getElementById(cardId);

    if (!card) {
      // First render — build the card from scratch
      card = document.createElement('div');
      card.className = 'field-card' + (info.writable ? ' writable' : '');
      card.dataset.section = id;
      card.dataset.field = label;
      card.id = cardId;

      const labelEl = document.createElement('div');
      labelEl.className = 'field-label';
      labelEl.innerHTML = label + (info.writable
        ? ' <span class="w-badge">RW</span>' : '');

      const valEl = document.createElement('div');
      valEl.className = 'field-value';
      valEl.id = 'val-' + id + '-' + encodeField(label);
      valEl.textContent = formatValue(info.value, info.enums);

      card.appendChild(labelEl);
      card.appendChild(valEl);

      if (info.help) {
        const helpEl = document.createElement('div');
        helpEl.className = 'field-help';
        helpEl.textContent = info.help;
        card.appendChild(helpEl);
      }

      if (info.writable) {
        const editorEl = buildEditor(id, label, info);
        card.appendChild(editorEl);
      }

      grid.appendChild(card);
    } else {
      // Subsequent refresh — only update the value display if field is not dirty
      if (!isDirty(id, label)) {
        const valEl = document.getElementById('val-' + id + '-' + encodeField(label));
        if (valEl) valEl.textContent = formatValue(info.value, info.enums);
      }
    }
  });
}

// ── Message editor panel ──
function renderMsgEditor() {
  const container = document.getElementById('content-msg_editor');
  const badge = document.getElementById('badge-msg_editor');
  badge.textContent = 'changeable messages';

  // Activate box
  let html = `
  <div class="activate-box">
    <h3>Activate Message</h3>
    <div class="activate-row">
      <div class="activate-field">
        <label>Memory Type</label>
        <select id="act-memtype">
          <option value="1">Permanent</option>
          <option value="2" selected>Changeable</option>
          <option value="3">Volatile</option>
          <option value="6">Blank</option>
        </select>
      </div>
      <div class="activate-field">
        <label>Message #</label>
        <input type="number" id="act-msgnum" value="1" min="1" max="255">
      </div>
      <div class="activate-field">
        <label>Duration (min, 0=cont)</label>
        <input type="number" id="act-duration" value="0" min="0" max="65535">
      </div>
      <div class="activate-field">
        <label>Priority</label>
        <input type="number" id="act-priority" value="200" min="1" max="255">
      </div>
      <button class="btn-activate" onclick="activateMessage()">▶ Activate</button>
      <button class="btn-activate btn-blank" onclick="blankSign()">✕ Blank</button>
    </div>
  </div>`;

  // Permanent messages table
  html += `<h3 style="font-family:var(--mono);font-size:11px;color:var(--text-dim);
    letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px;">
    Permanent Messages (read-only)</h3>
  <table class="msg-table">
    <thead><tr><th>#</th><th>MULTI String</th><th>CRC</th><th>Status</th></tr></thead>
    <tbody id="perm-tbody"></tbody>
  </table>`;

  // Changeable messages table
  html += `<h3 style="font-family:var(--mono);font-size:11px;color:var(--text-dim);
    letter-spacing:.08em;text-transform:uppercase;margin:20px 0 10px;">
    Changeable Messages</h3>
  <table class="msg-table">
    <thead><tr><th>#</th><th>MULTI String</th><th>CRC</th><th>Status</th><th></th></tr></thead>
    <tbody id="chg-tbody"></tbody>
  </table>`;

  container.innerHTML = html;
  loadMessageTables();
}

async function loadMessageTables() {
  const r = await fetch('/api/state');
  const s = await r.json();
  // We fetch raw message data via a dedicated endpoint
  const mr = await fetch('/api/messages');
  if (!mr.ok) return;
  const msgs = await mr.json();

  const permTbody = document.getElementById('perm-tbody');
  const chgTbody  = document.getElementById('chg-tbody');
  if (!permTbody || !chgTbody) return;

  const activeMT = msgs.active_mem_type;
  const activeMN = msgs.active_msg_num;

  msgs.permanent.forEach(m => {
    const isActive = (activeMT === 1 && activeMN === m.num);
    permTbody.innerHTML += `<tr>
      <td>${m.num}</td>
      <td class="multi ${isActive ? 'active' : ''}">${escHtml(m.multi) || '(blank)'}</td>
      <td>0x${m.crc.toString(16).padStart(4,'0')}</td>
      <td>${m.status}</td>
    </tr>`;
  });

  msgs.changeable.forEach(m => {
    const isActive = (activeMT === 2 && activeMN === m.num);
    chgTbody.innerHTML += `<tr>
      <td>${m.num}</td>
      <td class="multi ${isActive ? 'active' : ''}">
        <input class="multi-input" id="chg-multi-${m.num}"
          value="${escHtml(m.multi)}" placeholder="MULTI string…">
      </td>
      <td id="chg-crc-${m.num}">0x${m.crc.toString(16).padStart(4,'0')}</td>
      <td>${m.status}</td>
      <td>
        <button class="btn-tiny" onclick="saveChangeable(${m.num})">Save</button>
        <button class="btn-tiny activate-btn" onclick="quickActivate(2,${m.num})">▶</button>
      </td>
    </tr>`;
  });
}

async function saveChangeable(num) {
  const val = document.getElementById('chg-multi-' + num)?.value || '';
  await fetch('/api/set_multi', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mem_type: 2, msg_num: num, multi: val})
  });
  showToast('Saved changeable message ' + num);
  loadMessageTables();
}

async function quickActivate(memType, msgNum) {
  const duration = 0;
  const priority = 200;
  await fetch('/api/activate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mem_type: memType, msg_num: msgNum,
                          duration, priority})
  });
  showToast(`Activated mem:${memType} msg:${msgNum}`);
  fetchState();
}

async function activateMessage() {
  const memType  = parseInt(document.getElementById('act-memtype').value);
  const msgNum   = parseInt(document.getElementById('act-msgnum').value);
  const duration = parseInt(document.getElementById('act-duration').value);
  const priority = parseInt(document.getElementById('act-priority').value);
  await fetch('/api/activate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mem_type: memType, msg_num: msgNum, duration, priority})
  });
  showToast(`Activated mem:${memType} msg:${msgNum}`);
  fetchState();
}

async function blankSign() {
  await fetch('/api/activate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mem_type: 6, msg_num: 0, duration: 0, priority: 255})
  });
  showToast('Sign blanked');
  fetchState();
}

// ── Field editor ──
function buildEditor(sectionId, label, info) {
  const wrap = document.createElement('div');
  wrap.className = 'field-editor';

  let input;
  if (info.enums) {
    input = document.createElement('select');
    Object.entries(info.enums).forEach(([k, v]) => {
      const opt = document.createElement('option');
      opt.value = k;
      opt.textContent = v;
      if (parseInt(k) === parseInt(info.value)) opt.selected = true;
      input.appendChild(opt);
    });
  } else {
    input = document.createElement('input');
    input.type = 'text';
    input.value = info.value;
  }

  // Mark field dirty whenever the user changes the input
  input.addEventListener('change', () => markDirty(sectionId, label));
  input.addEventListener('input',  () => markDirty(sectionId, label));
  input.addEventListener('focus',  () => markDirty(sectionId, label));

  const btn = document.createElement('button');
  btn.textContent = 'Set';
  btn.addEventListener('click', async () => {
    const val = input.value;
    try {
      const r = await fetch('/api/set', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({section: sectionId, field: label, value: val})
      });
      const data = await r.json();
      if (data.ok) {
        clearDirty(sectionId, label);
        const card = btn.closest('.field-card');
        card.classList.add('modified');
        setTimeout(() => card.classList.remove('modified'), 600);
        showToast('Set ' + label);
        fetchState();
      } else {
        showToast('Error: ' + data.error, true);
      }
    } catch(e) {
      showToast('Error: ' + e.message, true);
    }
  });

  // Cancel button — clears dirty state and restores last known value
  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = '✕';
  cancelBtn.className = 'cancel';
  cancelBtn.title = 'Discard changes';
  cancelBtn.addEventListener('click', () => {
    clearDirty(sectionId, label);
    // Restore value from last fetched state
    const sec = state[sectionId];
    if (sec && sec[label]) {
      const v = sec[label].value;
      if (info.enums) {
        for (const opt of input.options)
          opt.selected = parseInt(opt.value) === parseInt(v);
      } else {
        input.value = v;
      }
    }
    cancelBtn.style.display = 'none';
  });
  cancelBtn.style.display = 'none';

  // Show cancel only when dirty
  const origMark = markDirty;
  input.addEventListener('change', () => { cancelBtn.style.display = ''; });
  input.addEventListener('input',  () => { cancelBtn.style.display = ''; });

  wrap.appendChild(input);
  wrap.appendChild(btn);
  wrap.appendChild(cancelBtn);
  return wrap;
}

// ── Save config to file ──
async function saveConfig() {
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.textContent = '⏳ Saving…';
  try {
    const r = await fetch('/api/save');
    const data = await r.json();
    if (data.ok) {
      showToast('Saved to ' + data.path);
      btn.textContent = '✓ Saved';
      setTimeout(() => { btn.textContent = '💾 Save Config'; btn.disabled = false; }, 2000);
    } else {
      showToast(data.error || 'Save failed', true);
      btn.textContent = '💾 Save Config';
      btn.disabled = false;
    }
  } catch(e) {
    showToast('Save error: ' + e.message, true);
    btn.textContent = '💾 Save Config';
    btn.disabled = false;
  }
}

// ── Utilities ──
function formatValue(val, enums) {
  if (val === null || val === undefined) return '—';
  if (enums && enums[parseInt(val)] !== undefined)
    return `${enums[parseInt(val)]} (${val})`;
  return String(val);
}

function encodeField(label) {
  return label.replace(/[^a-zA-Z0-9]/g, '_');
}

function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

let toastTimer;
function showToast(msg, isErr=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ''; }, 2500);
}

// ── Init ──
setSection(SECTIONS_META[0].id);
fetchState();
setInterval(fetchState, 3000);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Server class
# ---------------------------------------------------------------------------

class ConfigServer:
    """
    Wraps HTTPServer in a daemon thread.  Call start() after setting store.
    """

    def __init__(self, store, host='0.0.0.0', port=8080, config_file=None):
        self._store       = store
        self._host        = host
        self._port        = port
        self._config_file = config_file
        self._server      = None
        self._thread      = None

    def start(self):
        # Load saved config before starting the server
        if self._config_file:
            self._load(self._config_file)

        # Create a fresh handler subclass per server instance so that
        # multiple ConfigServer instances don't share class-level state.
        store       = self._store
        config_file = self._config_file

        class _Handler(ConfigHandler):
            pass

        _Handler.store       = store
        _Handler.config_file = config_file
        _patch_handler(_Handler, store)

        self._server = HTTPServer((self._host, self._port), _Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name='dms-config-http',
            daemon=True,
        )
        self._thread.start()
        log.info(f"Config UI: http://{self._host}:{self._port}/")
        if self._config_file:
            log.info(f"Config file: {self._config_file}")

    def stop(self):
        if self._server:
            self._server.shutdown()

    def _load(self, path):
        """Load a previously saved config JSON into the store."""
        import json as _json, os
        if not os.path.exists(path):
            log.info(f"Config file {path!r} not found, using defaults.")
            return
        try:
            with open(path) as f:
                data = _json.load(f)
            s = self._store
            _apply_config_dict(s, data)
            log.info(f"Loaded config from {path!r}")
        except Exception as ex:
            log.warning(f"Failed to load config {path!r}: {ex}")


def _collect_config_dict(store):
    """Serialise all writable scalar fields to a plain dict."""
    s = store
    return {
        'sign_config': {
            'dmsSignAccess':       s.sign_config['dmsSignAccess'],
            'dmsSignType':         s.sign_config['dmsSignType'],
            'dmsSignHeight':       s.sign_config['dmsSignHeight'],
            'dmsSignWidth':        s.sign_config['dmsSignWidth'],
            'dmsHorizontalBorder': s.sign_config['dmsHorizontalBorder'],
            'dmsVerticalBorder':   s.sign_config['dmsVerticalBorder'],
            'dmsBeaconType':       s.sign_config['dmsBeaconType'],
            'dmsSignTechnology':   s.sign_config['dmsSignTechnology'],
            'dmsLegend':           s.sign_config['dmsLegend'].decode('ascii', errors='replace'),
        },
        'multi_cfg': {
            'dmsDefaultBackgroundColor':          s.multi_cfg['dmsDefaultBackgroundColor'],
            'dmsDefaultForegroundColor':           s.multi_cfg['dmsDefaultForegroundColor'],
            'dmsDefaultFlashOn':                   s.multi_cfg['dmsDefaultFlashOn'],
            'dmsDefaultFlashOff':                  s.multi_cfg['dmsDefaultFlashOff'],
            'dmsDefaultFont':                      s.multi_cfg['dmsDefaultFont'],
            'dmsDefaultJustificationLine':         s.multi_cfg['dmsDefaultJustificationLine'],
            'dmsDefaultJustificationPage':         s.multi_cfg['dmsDefaultJustificationPage'],
            'dmsDefaultPageOnTime':                s.multi_cfg['dmsDefaultPageOnTime'],
            'dmsDefaultPageOffTime':               s.multi_cfg['dmsDefaultPageOffTime'],
            'dmsDefaultCharacterSet':              s.multi_cfg['dmsDefaultCharacterSet'],
            'dmsColorScheme':                      s.multi_cfg['dmsColorScheme'],
            'dmsMaxNumberPages':                   s.multi_cfg['dmsMaxNumberPages'],
            'dmsMaxMultiStringLength':             s.multi_cfg['dmsMaxMultiStringLength'],
            'dmsDefaultFlashOnActivate':           s.multi_cfg['dmsDefaultFlashOnActivate'],
            'dmsDefaultFlashOffActivate':          s.multi_cfg['dmsDefaultFlashOffActivate'],
            'dmsDefaultFontActivate':              s.multi_cfg['dmsDefaultFontActivate'],
            'dmsDefaultJustificationLineActivate': s.multi_cfg['dmsDefaultJustificationLineActivate'],
            'dmsDefaultJustificationPageActivate': s.multi_cfg['dmsDefaultJustificationPageActivate'],
            'dmsDefaultPageOnTimeActivate':        s.multi_cfg['dmsDefaultPageOnTimeActivate'],
            'dmsDefaultPageOffTimeActivate':       s.multi_cfg['dmsDefaultPageOffTimeActivate'],
        },
        'sign_control': {
            'dmsControlMode':            s.sign_control['dmsControlMode'],
            'dmsCommLossTime':           s.sign_control['dmsCommLossTime'],
            'dmsShortPowerLossTime':     s.sign_control['dmsShortPowerLossTime'],
            'dmsPixelServiceFrequency':  s.sign_control['dmsPixelServiceFrequency'],
            'dmsPixelServiceDuration':   s.sign_control['dmsPixelServiceDuration'],
        },
        'illum': {
            'dmsIllumControl':  s.illum['dmsIllumControl'],
            'dmsIllumManLevel': s.illum['dmsIllumManLevel'],
        },
        'changeable_messages': {
            str(n): row['dmsMessageMultiString'].decode('ascii', errors='replace')
            for n, row in s.changeable_msg_table.items()
            if row['dmsMessageMultiString']
        },
        'graphics': {
            str(gi): {
                'dmsGraphicNumber':             row['dmsGraphicNumber'],
                'dmsGraphicName':               row['dmsGraphicName'].decode('ascii', errors='replace'),
                'dmsGraphicType':               row['dmsGraphicType'],
                'dmsGraphicStatus':             row['dmsGraphicStatus'],
                'dmsGraphicTransparentEnabled': row['dmsGraphicTransparentEnabled'],
                'dmsGraphicTransparentColor':   row['dmsGraphicTransparentColor'].hex(),
            }
            for gi, row in s.graphic_table.items()
            if row['dmsGraphicStatus'] != 1   # skip notUsed rows
        },
        'color': {
            'dmsColorScheme':              s.multi_cfg['dmsColorScheme'],
            'dmsDefaultBackgroundColor':   s.multi_cfg['dmsDefaultBackgroundColor'],
            'dmsDefaultForegroundColor':   s.multi_cfg['dmsDefaultForegroundColor'],
            'dmsDefaultBackgroundColorRGB': s.multi_cfg['dmsDefaultBackgroundColorRGB'].hex(),
            'dmsDefaultForegroundColorRGB': s.multi_cfg['dmsDefaultForegroundColorRGB'].hex(),
            'monochromeColor':             s.vms_config['monochromeColor'].hex(),
        },
    }


def _apply_config_dict(store, data):
    """Restore writable fields from a config dict."""
    s = store

    sc = data.get('sign_config', {})
    for key in ('dmsSignAccess','dmsSignType','dmsSignHeight','dmsSignWidth',
                'dmsHorizontalBorder','dmsVerticalBorder','dmsBeaconType','dmsSignTechnology'):
        if key in sc:
            s.sign_config[key] = int(sc[key])
    if 'dmsLegend' in sc:
        s.sign_config['dmsLegend'] = str(sc['dmsLegend']).encode()

    mc = data.get('multi_cfg', {})
    int_keys = ('dmsDefaultBackgroundColor','dmsDefaultForegroundColor',
                'dmsDefaultFlashOn','dmsDefaultFlashOff','dmsDefaultFont',
                'dmsDefaultJustificationLine','dmsDefaultJustificationPage',
                'dmsDefaultPageOnTime','dmsDefaultPageOffTime',
                'dmsDefaultCharacterSet','dmsColorScheme','dmsMaxNumberPages',
                'dmsMaxMultiStringLength','dmsDefaultFlashOnActivate',
                'dmsDefaultFlashOffActivate','dmsDefaultFontActivate',
                'dmsDefaultJustificationLineActivate','dmsDefaultJustificationPageActivate',
                'dmsDefaultPageOnTimeActivate','dmsDefaultPageOffTimeActivate')
    for key in int_keys:
        if key in mc:
            s.multi_cfg[key] = int(mc[key])

    ctrl = data.get('sign_control', {})
    for key in ('dmsControlMode','dmsCommLossTime','dmsShortPowerLossTime',
                'dmsPixelServiceFrequency','dmsPixelServiceDuration'):
        if key in ctrl:
            s.sign_control[key] = int(ctrl[key])

    il = data.get('illum', {})
    for key in ('dmsIllumControl','dmsIllumManLevel'):
        if key in il:
            s.illum[key] = int(il[key])

    msgs = data.get('changeable_messages', {})
    for num_str, multi in msgs.items():
        n = int(num_str)
        if n in s.changeable_msg_table:
            mb = multi.encode()
            row = s.changeable_msg_table[n]
            row['dmsMessageMultiString'] = mb
            row['dmsMessageCRC']         = s._crc16(mb)
            row['dmsMessageStatus']      = 4 if mb else 1

    gfx = data.get('graphics', {})
    for gi_str, gdata in gfx.items():
        gi = int(gi_str)
        if gi in s.graphic_table:
            row = s.graphic_table[gi]
            for key in ('dmsGraphicNumber','dmsGraphicType','dmsGraphicStatus',
                        'dmsGraphicTransparentEnabled'):
                if key in gdata:
                    row[key] = int(gdata[key])
            if 'dmsGraphicName' in gdata:
                row['dmsGraphicName'] = str(gdata['dmsGraphicName']).encode()
            if 'dmsGraphicTransparentColor' in gdata:
                try:
                    row['dmsGraphicTransparentColor'] = bytes.fromhex(
                        str(gdata['dmsGraphicTransparentColor']))
                except Exception:
                    pass

    col = data.get('color', {})
    for key in ('dmsColorScheme','dmsDefaultBackgroundColor','dmsDefaultForegroundColor'):
        if key in col:
            s.multi_cfg[key] = int(col[key])
    for key in ('dmsDefaultBackgroundColorRGB','dmsDefaultForegroundColorRGB'):
        if key in col:
            try:
                s.multi_cfg[key] = bytes.fromhex(col[key])
            except Exception:
                pass
    if 'monochromeColor' in col:
        try:
            s.vms_config['monochromeColor'] = bytes.fromhex(col['monochromeColor'])
        except Exception:
            pass


def _patch_handler(handler_cls, store):
    """
    Add /api/messages and /api/activate and /api/set_multi endpoints
    by monkey-patching do_GET / do_POST on the handler class.
    """
    from ntcip1203_agent.dms_mib_data import (
        MSG_MEM_PERMANENT, MSG_MEM_CHANGEABLE, MSG_MEM_VOLATILE, MSG_MEM_BLANK
    )

    _STATUS_MAP = {1:'notUsed', 2:'modifying', 3:'validating',
                   4:'valid', 5:'error', 6:'blank'}

    original_GET  = handler_cls.do_GET
    original_POST = handler_cls.do_POST

    def do_GET(self):
        if self.path == '/api/messages':
            s = self.store
            data = {
                'active_mem_type': s._active_mem_type,
                'active_msg_num':  s._active_msg_num,
                'permanent': [
                    {'num': n,
                     'multi': r['dmsMessageMultiString'].decode('ascii','replace'),
                     'crc':   r['dmsMessageCRC'],
                     'status': _STATUS_MAP.get(r['dmsMessageStatus'], '?')}
                    for n, r in sorted(s.permanent_msg_table.items())
                ],
                'changeable': [
                    {'num': n,
                     'multi': r['dmsMessageMultiString'].decode('ascii','replace'),
                     'crc':   r['dmsMessageCRC'],
                     'status': _STATUS_MAP.get(r['dmsMessageStatus'], '?')}
                    for n, r in sorted(s.changeable_msg_table.items())
                ],
            }
            self._send_json(data)
        else:
            original_GET(self)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/set_multi':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                data     = json.loads(body)
                mem_type = int(data['mem_type'])
                msg_num  = int(data['msg_num'])
                multi    = data['multi'].encode()
                s        = self.store
                if mem_type == MSG_MEM_CHANGEABLE:
                    row = s.changeable_msg_table.get(msg_num)
                elif mem_type == MSG_MEM_VOLATILE:
                    row = s.volatile_msg_table.get(msg_num)
                else:
                    row = None
                if row is None:
                    raise KeyError(f'No message at memType={mem_type} num={msg_num}')
                row['dmsMessageMultiString'] = multi
                row['dmsMessageCRC']         = s._crc16(multi)
                row['dmsMessageStatus']      = 4 if multi else 1
                self._send_json({'ok': True})
            except Exception as ex:
                self._send_json({'ok': False, 'error': str(ex)}, status=400)

        elif parsed.path == '/api/activate':
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            try:
                data     = json.loads(body)
                mem_type = int(data['mem_type'])
                msg_num  = int(data.get('msg_num', 0))
                duration = int(data.get('duration', 0))
                priority = int(data.get('priority', 200))

                # Look up CRC for the message
                s = self.store
                if mem_type == MSG_MEM_PERMANENT:
                    row = s.permanent_msg_table.get(msg_num, {})
                elif mem_type == MSG_MEM_CHANGEABLE:
                    row = s.changeable_msg_table.get(msg_num, {})
                elif mem_type == MSG_MEM_VOLATILE:
                    row = s.volatile_msg_table.get(msg_num, {})
                else:
                    row = {}
                crc = row.get('dmsMessageCRC', 0)

                act_code = bytes([
                    (duration >> 8) & 0xFF, duration & 0xFF,
                    priority & 0xFF,
                    mem_type & 0xFF,
                    (msg_num >> 8) & 0xFF, msg_num & 0xFF,
                    (crc >> 8) & 0xFF, crc & 0xFF,
                    0, 0, 0, 0,   # source IP = 0.0.0.0
                ])
                ok = s.activate_message(act_code)
                self._send_json({'ok': ok,
                                 'error': '' if ok else 'activation failed'})
            except Exception as ex:
                self._send_json({'ok': False, 'error': str(ex)}, status=400)

        else:
            original_POST(self)

    handler_cls.do_GET  = do_GET
    handler_cls.do_POST = do_POST
