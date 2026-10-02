"""
Synthetic hand-pose sender -- lets you validate the robot half of the pipeline
with no Spectacles involved. Pure stdlib WebSocket client.

    py test_sender.py --wave            open/close all fingers, 0.5 Hz
    py test_sender.py --sweep           drive ONE joint at a time (use this to
                                        confirm which robot joint is which)
    py test_sender.py --hold 0 0 0 0 ... (20 human-angle values)

Values sent are *human* angles in degrees; the bridge maps them through
config.json exactly as it does for real lens input.
"""

import argparse
import base64
import json
import math
import os
import socket
import struct
import sys
import time

N = 20
NAMES = [
    "thumb_abd", "thumb_opp", "thumb_mcp", "thumb_ip",
    "index_abd", "index_mcp", "index_pip", "index_dip",
    "middle_abd", "middle_mcp", "middle_pip", "middle_dip",
    "ring_abd", "ring_mcp", "ring_pip", "ring_dip",
    "pinky_abd", "pinky_mcp", "pinky_pip", "pinky_dip",
]
# A representative "full flexion" human pose, per joint, for sweeps/waves.
FULL = [30, 90, 50, 70,
        0, 90, 100, 80,
        0, 90, 100, 80,
        0, 90, 100, 80,
        0, 90, 100, 80]


class WSClient:
    def __init__(self, host, port, path="/"):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("latin-1"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("server closed during handshake")
            buf += chunk
        if b"101" not in buf.split(b"\r\n")[0]:
            raise ConnectionError(f"handshake failed: {buf.splitlines()[0]!r}")
        self.sock.settimeout(None)

    def send_text(self, text):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        hdr = bytearray([0x81])  # FIN + text
        n = len(payload)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < (1 << 16):
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        self.sock.sendall(bytes(hdr) + mask + masked)

    def close(self):
        try:
            self.sock.sendall(b"\x88\x80" + os.urandom(4))
        except OSError:
            pass
        self.sock.close()


def send_pose(ws, human):
    f = [human[i * 4:(i + 1) * 4] for i in range(5)]
    ws.send_text(json.dumps({
        "t": int(time.time() * 1000),
        "tracked": True,
        "hand": "right",
        "f": f,
    }, separators=(",", ":")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--hz", type=float, default=60.0)
    ap.add_argument("--wave", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seconds", type=float, default=3.0)
    ap.add_argument("--hold", nargs=N, type=float, metavar="DEG")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this many seconds (0 = run until ctrl-c)")
    args = ap.parse_args()
    deadline = (time.monotonic() + args.seconds) if args.seconds > 0 else float("inf")

    ws = WSClient(args.host, args.port)
    print(f"connected to ws://{args.host}:{args.port}")
    period = 1.0 / args.hz
    t0 = time.monotonic()

    try:
        if args.hold:
            print("holding pose (ctrl-c to stop)")
            while time.monotonic() < deadline:
                send_pose(ws, args.hold)
                time.sleep(period)

        elif args.sweep:
            print("sweeping one joint at a time (ctrl-c to stop)")
            while time.monotonic() < deadline:
                for j in range(N):
                    print(f"  -> joint {j:2d}  {NAMES[j]}")
                    steps = max(2, int(args.sweep_seconds * args.hz))
                    for s in range(steps):
                        phase = math.sin(math.pi * s / steps)  # 0 -> 1 -> 0
                        pose = [0.0] * N
                        pose[j] = FULL[j] * phase
                        send_pose(ws, pose)
                        time.sleep(period)
                    if time.monotonic() >= deadline:
                        break

        else:  # --wave, the default
            print("waving open/close (ctrl-c to stop)")
            while time.monotonic() < deadline:
                t = time.monotonic() - t0
                phase = 0.5 - 0.5 * math.cos(2 * math.pi * 0.5 * t)  # 0..1 @0.5Hz
                pose = [FULL[i] * phase for i in range(N)]
                # keep abduction joints still -- only curl the fingers
                for i in (0, 4, 8, 12, 16):
                    pose[i] = 0.0
                send_pose(ws, pose)
                time.sleep(period)

    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        ws.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
