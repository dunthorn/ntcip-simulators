"""
snmp_server.py — Lightweight SNMPv1/v2c server (UDP and/or TCP)

Implements just enough BER/ASN.1 to handle GET, GETNEXT, GETBULK, and SET
PDUs without requiring pysnmp.  Delegates all OID resolution to an OIDTree
that returns Python native values (int, bytes, str).

TCP transport follows RFC 3430: each SNMP message is prefixed with a 4-byte
big-endian length field.

Derived from NTCIP 1202 v04. Copyright by AASHTO / ITE / NEMA. Used by permission.
"""

import socket
import struct
import logging
import threading

log = logging.getLogger('snmp_server')

# ---------------------------------------------------------------------------
# ASN.1 / BER tag constants
# ---------------------------------------------------------------------------
TAG_INTEGER       = 0x02
TAG_OCTET_STRING  = 0x04
TAG_NULL          = 0x05
TAG_OID           = 0x06
TAG_SEQUENCE      = 0x30
TAG_IPADDRESS     = 0x40
TAG_COUNTER32     = 0x41
TAG_GAUGE32       = 0x42
TAG_TIMETICKS     = 0x43
TAG_OPAQUE        = 0x44
TAG_COUNTER64     = 0x46
TAG_NO_SUCH_OBJ   = 0x80
TAG_NO_SUCH_INST  = 0x81
TAG_END_OF_MIB    = 0x82

# PDU types
PDU_GET       = 0xA0
PDU_GETNEXT   = 0xA1
PDU_RESPONSE  = 0xA2
PDU_SET       = 0xA3
PDU_GETBULK   = 0xA5

# Error codes
ERR_NONE      = 0
ERR_TOO_BIG   = 1
ERR_NO_SUCH   = 2
ERR_BAD_VALUE = 3
ERR_READ_ONLY = 4
ERR_GENERAL   = 5


# ---------------------------------------------------------------------------
# BER encoding helpers
# ---------------------------------------------------------------------------

def _encode_length(n):
    if n < 0x80:
        return bytes([n])
    elif n < 0x100:
        return bytes([0x81, n])
    elif n < 0x10000:
        return bytes([0x82, n >> 8, n & 0xFF])
    else:
        return bytes([0x83, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])


def _tlv(tag, content):
    return bytes([tag]) + _encode_length(len(content)) + content


def _encode_integer(v):
    """Signed big-endian minimal BER encoding (two's complement)."""
    v = int(v)
    if v == 0:
        return _tlv(TAG_INTEGER, b'\x00')
    result = []
    n = v
    while True:
        result.append(n & 0xFF)
        n >>= 8
        if (v > 0 and n == 0) or (v < 0 and n == -1):
            break
    if v > 0 and (result[-1] & 0x80):
        result.append(0x00)
    elif v < 0 and not (result[-1] & 0x80):
        result.append(0xFF)
    result.reverse()
    return _tlv(TAG_INTEGER, bytes(result))


def _encode_unsigned(tag, v):
    v = int(v) & 0xFFFFFFFF
    b = v.to_bytes(4, 'big')
    i = 0
    while i < 3 and b[i] == 0:
        i += 1
    raw = b[i:]
    if raw[0] & 0x80:
        raw = b'\x00' + raw
    return _tlv(tag, raw)


def _encode_oid(oid_tuple):
    if len(oid_tuple) < 2:
        raise ValueError("OID must have at least 2 components")
    encoded = [oid_tuple[0] * 40 + oid_tuple[1]]
    for arc in oid_tuple[2:]:
        if arc == 0:
            encoded.append(0)
        else:
            parts = []
            while arc:
                parts.append(arc & 0x7F)
                arc >>= 7
            parts.reverse()
            for i, p in enumerate(parts):
                encoded.append(p | (0x80 if i < len(parts) - 1 else 0))
    return _tlv(TAG_OID, bytes(encoded))


def _encode_octet_string(v):
    if isinstance(v, str):
        v = v.encode()
    return _tlv(TAG_OCTET_STRING, bytes(v))


def _encode_value(val):
    """
    Encode a Python value to BER.
      int                → INTEGER
      bytes/bytearray    → OCTET STRING
      str                → OCTET STRING (UTF-8)
      ('counter', int)   → Counter32
      ('gauge',   int)   → Gauge32
      ('timeticks', int) → TimeTicks
      ('oid', tuple)     → OBJECT IDENTIFIER
      (int_tag, bytes)   → raw TLV
    """
    if isinstance(val, tuple) and len(val) == 2:
        kind, raw = val
        if kind == 'counter':   return _encode_unsigned(TAG_COUNTER32, raw)
        if kind == 'gauge':     return _encode_unsigned(TAG_GAUGE32, raw)
        if kind == 'timeticks': return _encode_unsigned(TAG_TIMETICKS, raw)
        if kind == 'oid':       return _encode_oid(raw)
        if isinstance(kind, int): return _tlv(kind, bytes(raw))
    if isinstance(val, bool):
        return _encode_integer(int(val))
    if isinstance(val, int):
        return _encode_integer(val)
    if isinstance(val, (bytes, bytearray)):
        return _encode_octet_string(val)
    if isinstance(val, str):
        return _encode_octet_string(val.encode())
    return _tlv(TAG_NULL, b'')


def _encode_varbind(oid_tuple, val):
    return _tlv(TAG_SEQUENCE, _encode_oid(oid_tuple) + _encode_value(val))


def _encode_no_such_object(oid_tuple):
    return _tlv(TAG_SEQUENCE, _encode_oid(oid_tuple) + _tlv(TAG_NO_SUCH_OBJ, b''))


def _encode_end_of_mib(oid_tuple):
    return _tlv(TAG_SEQUENCE, _encode_oid(oid_tuple) + _tlv(TAG_END_OF_MIB, b''))


# ---------------------------------------------------------------------------
# BER decoding helpers
# ---------------------------------------------------------------------------

def _decode_length(data, pos):
    b = data[pos]; pos += 1
    if b < 0x80:
        return b, pos
    num_bytes = b & 0x7F
    length = 0
    for _ in range(num_bytes):
        length = (length << 8) | data[pos]
        pos += 1
    return length, pos


def _decode_tlv(data, pos):
    tag = data[pos]; pos += 1
    length, pos = _decode_length(data, pos)
    content = data[pos:pos + length]
    return tag, content, pos + length


def _decode_integer(content):
    if not content:
        return 0
    v = content[0]
    if v & 0x80:
        v -= 256
    for b in content[1:]:
        v = (v << 8) | b
    return v


def _decode_oid(content):
    arcs = []
    first = content[0]
    arcs.append(first // 40)
    arcs.append(first % 40)
    i = 1
    while i < len(content):
        arc = 0
        while True:
            b = content[i]; i += 1
            arc = (arc << 7) | (b & 0x7F)
            if not (b & 0x80):
                break
        arcs.append(arc)
    return tuple(arcs)


def _decode_varbind_list(data, pos, end):
    varbinds = []
    while pos < end:
        seq_tag, seq_content, pos = _decode_tlv(data, pos)
        inner = 0
        oid_tag, oid_content, inner = _decode_tlv(seq_content, inner)
        val_tag, val_content, inner = _decode_tlv(seq_content, inner)
        oid = _decode_oid(oid_content)
        if val_tag == TAG_INTEGER:
            val = _decode_integer(val_content)
        elif val_tag == TAG_OCTET_STRING:
            val = bytes(val_content)
        else:
            val = (val_tag, bytes(val_content))
        varbinds.append((oid, val))
    return varbinds


# ---------------------------------------------------------------------------
# SNMP message parsing
# ---------------------------------------------------------------------------

class SNMPMessage:
    """Parsed SNMP v1/v2c message."""

    def __init__(self):
        self.version        = 1
        self.community      = b''
        self.pdu_type       = 0
        self.request_id     = 0
        self.error_status   = 0
        self.error_index    = 0
        self.non_repeaters  = 0
        self.max_repetitions = 0
        self.varbinds       = []

    @staticmethod
    def decode(data):
        msg = SNMPMessage()
        pos = 0
        outer_tag, outer_content, _ = _decode_tlv(data, pos)
        pos = 0
        tag, content, pos = _decode_tlv(outer_content, pos)
        msg.version = _decode_integer(content)
        tag, content, pos = _decode_tlv(outer_content, pos)
        msg.community = bytes(content)
        msg.pdu_type = outer_content[pos]
        pdu_length, ppos = _decode_length(outer_content, pos + 1)
        pdu_content = outer_content[ppos:ppos + pdu_length]
        ppos2 = 0
        tag, content, ppos2 = _decode_tlv(pdu_content, ppos2)
        msg.request_id = _decode_integer(content)
        tag, content, ppos2 = _decode_tlv(pdu_content, ppos2)
        msg.error_status = _decode_integer(content)
        msg.non_repeaters = msg.error_status
        tag, content, ppos2 = _decode_tlv(pdu_content, ppos2)
        msg.error_index = _decode_integer(content)
        msg.max_repetitions = msg.error_index
        tag, vbl_content, ppos2 = _decode_tlv(pdu_content, ppos2)
        msg.varbinds = _decode_varbind_list(vbl_content, 0, len(vbl_content))
        return msg


# ---------------------------------------------------------------------------
# SNMP response encoding
# ---------------------------------------------------------------------------

def _encode_response(version, community, request_id,
                     error_status, error_index, varbind_encodings):
    vbl     = b''.join(varbind_encodings)
    vbl_seq = _tlv(TAG_SEQUENCE, vbl)
    pdu_content = (_encode_integer(request_id) + _encode_integer(error_status) +
                   _encode_integer(error_index) + vbl_seq)
    pdu = _tlv(PDU_RESPONSE, pdu_content)
    msg_content = _encode_integer(version) + _encode_octet_string(community) + pdu
    return _tlv(TAG_SEQUENCE, msg_content)


# ---------------------------------------------------------------------------
# PDU dispatcher (shared by both transports)
# ---------------------------------------------------------------------------

class _Dispatcher:
    """
    Handles SNMP PDU dispatch: community check, GET/GETNEXT/GETBULK/SET.
    Used by both UDPSNMPServer and TCPSNMPServer.
    """

    def __init__(self, oid_tree, ro_communities, rw_communities, snmp_mib=None):
        self.oid_tree        = oid_tree
        self.ro_communities  = set(ro_communities)
        self.rw_communities  = set(rw_communities)
        self._snmp_mib       = snmp_mib

    def handle(self, data, addr):
        """Decode data, dispatch, return encoded response bytes or None."""
        m = self._snmp_mib
        try:
            msg = SNMPMessage.decode(data)
        except Exception as e:
            log.debug(f"Decode error from {addr}: {e}")
            if m: m.on_parse_error()
            return None

        if m: m.on_in_packet()

        community = msg.community
        is_rw = community in self.rw_communities
        is_ro = community in self.ro_communities or is_rw

        if not is_ro:
            log.warning(f"Unknown community '{community}' from {addr}")
            if m: m.on_bad_community()
            return None

        log.debug(f"PDU 0x{msg.pdu_type:02X} from {addr} "
                  f"community={community} varbinds={len(msg.varbinds)}")

        n    = len(msg.varbinds)
        resp = None
        if msg.pdu_type == PDU_GET:
            if m: m.on_get(n)
            resp = self._handle_get(msg)
        elif msg.pdu_type == PDU_GETNEXT:
            if m: m.on_getnext(n)
            resp = self._handle_getnext(msg)
        elif msg.pdu_type == PDU_GETBULK:
            if m: m.on_getbulk(n)
            resp = self._handle_getbulk(msg)
        elif msg.pdu_type == PDU_SET:
            if not is_rw:
                return _encode_response(msg.version, community,
                                        msg.request_id, ERR_READ_ONLY, 1, [])
            if m: m.on_set(n)
            resp = self._handle_set(msg)
        else:
            log.debug(f"Unsupported PDU 0x{msg.pdu_type:02X}")

        if resp and m:
            m.on_out_packet()
            m.on_response_sent()
        return resp

    def _handle_get(self, msg):
        vb_enc = []; err_s = ERR_NONE; err_i = 0
        for i, (oid, _) in enumerate(msg.varbinds):
            val = self.oid_tree.get(oid)
            if val is None:
                if msg.version == 0:
                    err_s = ERR_NO_SUCH; err_i = i + 1
                    vb_enc = [_encode_no_such_object(o) for o, _ in msg.varbinds]
                    break
                vb_enc.append(_encode_no_such_object(oid))
            else:
                vb_enc.append(_encode_varbind(oid, val))
        return _encode_response(msg.version, msg.community, msg.request_id,
                                err_s, err_i, vb_enc)

    def _handle_getnext(self, msg):
        vb_enc = []; err_s = ERR_NONE; err_i = 0
        for i, (oid, _) in enumerate(msg.varbinds):
            next_oid, val = self.oid_tree.get_next(oid)
            if next_oid is None:
                if msg.version == 0:
                    err_s = ERR_NO_SUCH; err_i = i + 1
                    vb_enc = [_encode_no_such_object(o) for o, _ in msg.varbinds]
                    break
                vb_enc.append(_encode_end_of_mib(oid))
            else:
                vb_enc.append(_encode_varbind(next_oid, val))
        return _encode_response(msg.version, msg.community, msg.request_id,
                                err_s, err_i, vb_enc)

    def _handle_getbulk(self, msg):
        nr = max(0, msg.non_repeaters)
        mr = max(0, msg.max_repetitions)
        vbs = msg.varbinds
        vb_enc = []
        for oid, _ in vbs[:nr]:
            next_oid, val = self.oid_tree.get_next(oid)
            vb_enc.append(_encode_varbind(next_oid, val) if next_oid
                          else _encode_end_of_mib(oid))
        if mr > 0 and len(vbs) > nr:
            rep_oids = [oid for oid, _ in vbs[nr:]]
            for _ in range(mr):
                all_eom = True
                for j, oid in enumerate(rep_oids):
                    next_oid, val = self.oid_tree.get_next(oid)
                    if next_oid is None:
                        vb_enc.append(_encode_end_of_mib(oid))
                    else:
                        vb_enc.append(_encode_varbind(next_oid, val))
                        rep_oids[j] = next_oid
                        all_eom = False
                if all_eom:
                    break
        return _encode_response(msg.version, msg.community, msg.request_id,
                                ERR_NONE, 0, vb_enc)

    def _handle_set(self, msg):
        vb_enc = []; err_s = ERR_NONE; err_i = 0
        for i, (oid, val) in enumerate(msg.varbinds):
            ok = self.oid_tree.set(oid, val)
            if not ok:
                if msg.version == 0:
                    err_s = ERR_NO_SUCH; err_i = i + 1
                    vb_enc = [_encode_no_such_object(o) for o, _ in msg.varbinds]
                    break
                vb_enc.append(_encode_no_such_object(oid))
            else:
                stored = self.oid_tree.get(oid)
                vb_enc.append(_encode_varbind(oid, stored if stored is not None else val))
        return _encode_response(msg.version, msg.community, msg.request_id,
                                err_s, err_i, vb_enc)


# ---------------------------------------------------------------------------
# UDP transport
# ---------------------------------------------------------------------------

class UDPSNMPServer:
    """
    SNMP over UDP (RFC 1157 / RFC 3416).
    One datagram = one SNMP message.
    """

    def __init__(self, dispatcher, host='0.0.0.0', port=161):
        self._dispatcher = dispatcher
        self._host       = host
        self._port       = port
        self._sock       = None
        self._running    = False
        self._thread     = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name='SNMP-UDP')
        self._thread.start()
        log.info(f"SNMP UDP listening on {self._host}:{self._port}")

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()

    def _loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                resp = self._dispatcher.handle(data, addr)
                if resp:
                    self._sock.sendto(resp, addr)
            except OSError:
                break
            except Exception as e:
                log.warning(f"UDP handler error: {e}")


# ---------------------------------------------------------------------------
# TCP transport
# ---------------------------------------------------------------------------

class TCPSNMPServer:
    """
    SNMP over TCP (RFC 3430).

    Framing: each message is preceded by a 4-byte big-endian length field.
    Each connected client gets its own thread.  The server accepts connections
    on a single listener thread and spawns a handler thread per client.

    Clients may keep the connection open and send multiple messages sequentially;
    each is handled independently.
    """

    # Maximum message size we'll accept (64 KiB is generous for SNMP)
    MAX_MSG_SIZE = 65535

    def __init__(self, dispatcher, host='0.0.0.0', port=161):
        self._dispatcher = dispatcher
        self._host       = host
        self._port       = port
        self._sock       = None
        self._running    = False
        self._thread     = None

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.listen(16)
        self._running = True
        self._thread  = threading.Thread(target=self._accept_loop, daemon=True,
                                         name='SNMP-TCP-accept')
        self._thread.start()
        log.info(f"SNMP TCP listening on {self._host}:{self._port}")

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            t = threading.Thread(target=self._client_loop,
                                 args=(conn, addr), daemon=True,
                                 name=f'SNMP-TCP-{addr[0]}:{addr[1]}')
            t.start()

    def _client_loop(self, conn, addr):
        log.debug(f"TCP client connected: {addr}")
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            while self._running:
                # Read 4-byte length prefix
                hdr = self._recv_exact(conn, 4)
                if not hdr:
                    break
                msg_len = struct.unpack('>I', hdr)[0]
                if msg_len == 0 or msg_len > self.MAX_MSG_SIZE:
                    log.warning(f"TCP {addr}: invalid message length {msg_len}, closing")
                    break
                data = self._recv_exact(conn, msg_len)
                if not data:
                    break
                resp = self._dispatcher.handle(data, addr)
                if resp:
                    # Send with 4-byte length prefix
                    conn.sendall(struct.pack('>I', len(resp)) + resp)
        except OSError as e:
            log.debug(f"TCP {addr} closed: {e}")
        except Exception as e:
            log.warning(f"TCP {addr} error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass
            log.debug(f"TCP client disconnected: {addr}")

    @staticmethod
    def _recv_exact(conn, n):
        """Read exactly n bytes from a TCP socket, or return None on EOF."""
        buf = b''
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf


# ---------------------------------------------------------------------------
# SNMPServer — public façade (backwards-compatible with existing code)
# ---------------------------------------------------------------------------

class SNMPServer:
    """
    Public entry point.  Starts UDP, TCP, or both transports.

    Backwards-compatible with the previous single-transport API:
      SNMPServer(oid_tree, host, port, ro_communities, rw_communities, snmp_mib)
    still works and defaults to UDP only.

    New parameter:
      transport  'udp' (default) | 'tcp' | 'both'
    """

    def __init__(self, oid_tree, host='0.0.0.0', port=161,
                 ro_communities=None, rw_communities=None,
                 snmp_mib=None, transport='udp'):

        self._dispatcher = _Dispatcher(
            oid_tree,
            ro_communities=ro_communities or [b'public'],
            rw_communities=rw_communities or [b'private'],
            snmp_mib=snmp_mib,
        )

        transport = transport.lower()
        self._udp = self._tcp = None

        if transport in ('udp', 'both'):
            self._udp = UDPSNMPServer(self._dispatcher, host, port)
        if transport in ('tcp', 'both'):
            self._tcp = TCPSNMPServer(self._dispatcher, host, port)

        if self._udp is None and self._tcp is None:
            raise ValueError(f"Unknown transport '{transport}'; use udp, tcp, or both")

        self._transport = transport
        self._host      = host
        self._port      = port

    def start(self):
        if self._udp: self._udp.start()
        if self._tcp: self._tcp.start()

    def stop(self):
        if self._udp: self._udp.stop()
        if self._tcp: self._tcp.stop()
