"""
Minimal RFC 6455 WebSocket server -- Python standard library only.

Deliberately dependency-free so the bridge runs on a bare Python install with
no pip step. Handles text/binary frames, fragmentation, ping/pong and close.
One thread per connection; `on_message(conn, text)` is called from that thread.
"""

import base64
import hashlib
import os
import socket
import struct
import threading
import traceback

_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


class WSConnection:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.alive = True
        self._send_lock = threading.Lock()

    def send_text(self, text: str):
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def _send_frame(self, opcode: int, payload: bytes):
        if not self.alive:
            return
        header = bytearray()
        header.append(0x80 | opcode)  # FIN + opcode
        n = len(payload)
        if n < 126:
            header.append(n)
        elif n < (1 << 16):
            header.append(126)
            header += struct.pack(">H", n)
        else:
            header.append(127)
            header += struct.pack(">Q", n)
        try:
            with self._send_lock:
                self.sock.sendall(bytes(header) + payload)
        except OSError:
            self.alive = False

    def close(self):
        if self.alive:
            try:
                self._send_frame(OP_CLOSE, b"")
            except Exception:
                pass
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class WebSocketServer:
    def __init__(self, host: str, port: int, on_message,
                 on_open=None, on_close=None, log=print):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close
        self.log = log
        self._srv = None
        self._running = False
        self._threads = []
        self.clients = []
        self._clients_lock = threading.Lock()

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == "nt":
            # Do NOT use SO_REUSEADDR here. On Windows it lets a second process
            # bind a port that is already listening; connections then land on
            # whichever instance the OS picks. A forgotten bridge silently steals
            # the Lens's packets and the new one just sits at rx=0. Be exclusive
            # so a double start fails loudly instead.
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._srv.bind((self.host, self.port))
        except OSError as e:
            raise OSError(
                f"cannot bind {self.host}:{self.port} -- another bridge is "
                f"probably already running. Find it with:\n"
                f"    Get-NetTCPConnection -LocalPort {self.port} -State Listen\n"
                f"and stop that process, then retry. ({e})"
            ) from e
        self._srv.listen(8)
        self._running = True
        t = threading.Thread(target=self._accept_loop, daemon=True, name="ws-accept")
        t.start()
        self._threads.append(t)

    def stop(self):
        self._running = False
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
        with self._clients_lock:
            clients = list(self.clients)
        for c in clients:
            c.close()

    def broadcast(self, text: str):
        with self._clients_lock:
            clients = list(self.clients)
        for c in clients:
            c.send_text(text)

    # ---- internals -----------------------------------------------------
    def _accept_loop(self):
        while self._running:
            try:
                sock, addr = self._srv.accept()
            except OSError:
                break
            # Log the raw TCP accept, before any WebSocket handshake. This is
            # what separates "the Lens never reached us at all" (nothing here)
            # from "it reached us but the upgrade failed" (this line, then an
            # error). Without it both look identical from the outside.
            self.log(f"\n[ws] TCP connection from {addr[0]}:{addr[1]}")
            t = threading.Thread(target=self._serve, args=(sock, addr),
                                 daemon=True, name=f"ws-{addr[0]}")
            t.start()
            self._threads.append(t)

    def _serve(self, sock, addr):
        conn = WSConnection(sock, addr)
        try:
            sock.settimeout(10.0)
            if not self._handshake(sock):
                conn.close()
                return
            sock.settimeout(None)
            # Nagle off: these are small, latency-critical frames.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            with self._clients_lock:
                self.clients.append(conn)
            if self.on_open:
                self.on_open(conn)

            self._read_loop(conn)
        except Exception:
            self.log(f"[ws] connection error {addr}:\n{traceback.format_exc()}")
        finally:
            with self._clients_lock:
                if conn in self.clients:
                    self.clients.remove(conn)
            conn.close()
            if self.on_close:
                try:
                    self.on_close(conn)
                except Exception:
                    pass

    def _handshake(self, sock) -> bool:
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return False
            buf += chunk
            if len(buf) > 65536:
                return False

        head, _, _rest = buf.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(b":")
            headers[k.strip().lower().decode("latin-1")] = v.strip().decode("latin-1")

        key = headers.get("sec-websocket-key")
        if not key or "websocket" not in headers.get("upgrade", "").lower():
            first = lines[0].decode("latin-1", errors="replace") if lines else "?"
            self.log(f"[ws] not a WebSocket upgrade -- first line was: {first!r}")
            sock.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return False

        accept = base64.b64encode(
            hashlib.sha1(key.encode("latin-1") + _GUID).digest()
        ).decode("ascii")
        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        sock.sendall(resp.encode("latin-1"))
        return True

    def _recv_exact(self, sock, n: int):
        out = b""
        while len(out) < n:
            chunk = sock.recv(n - len(out))
            if not chunk:
                return None
            out += chunk
        return out

    def _read_loop(self, conn: WSConnection):
        sock = conn.sock
        frag_op = None
        frag_buf = bytearray()

        while conn.alive:
            hdr = self._recv_exact(sock, 2)
            if hdr is None:
                return
            b0, b1 = hdr[0], hdr[1]
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F

            if length == 126:
                ext = self._recv_exact(sock, 2)
                if ext is None:
                    return
                length = struct.unpack(">H", ext)[0]
            elif length == 127:
                ext = self._recv_exact(sock, 8)
                if ext is None:
                    return
                length = struct.unpack(">Q", ext)[0]

            if length > 8 * 1024 * 1024:  # sanity cap
                return

            mask = None
            if masked:
                mask = self._recv_exact(sock, 4)
                if mask is None:
                    return

            payload = self._recv_exact(sock, length) if length else b""
            if payload is None:
                return
            if mask:
                payload = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))

            # control frames may interleave with fragmented data frames
            if opcode == OP_CLOSE:
                conn.alive = False
                return
            if opcode == OP_PING:
                conn._send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue

            if opcode == OP_CONT:
                if frag_op is None:
                    return  # protocol error
                frag_buf += payload
                if fin:
                    self._dispatch(conn, frag_op, bytes(frag_buf))
                    frag_op, frag_buf = None, bytearray()
            else:
                if fin:
                    self._dispatch(conn, opcode, payload)
                else:
                    frag_op = opcode
                    frag_buf = bytearray(payload)

    def _dispatch(self, conn, opcode, payload: bytes):
        if opcode == OP_TEXT:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                return
        elif opcode == OP_BIN:
            text = payload.decode("utf-8", errors="replace")
        else:
            return
        try:
            self.on_message(conn, text)
        except Exception:
            self.log(f"[ws] on_message error:\n{traceback.format_exc()}")
