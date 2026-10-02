"""
Spectacles -> Delto DG-5F bridge.

    Spectacles lens --(WebSocket, JSON, ~60Hz)--> this process --(DGSDK.dll)--> gripper

Run `py bridge.py --dry-run` first: it exercises the whole pipeline (lens,
network, retargeting, safety) and prints what it *would* command, without
opening a connection to the robot at all.

Keys while running:  [space] arm/disarm   [n] go to neutral   [q] quit
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from retarget import N_JOINTS, Retargeter          # noqa: E402
from wsserver import WebSocketServer                # noqa: E402

try:
    import msvcrt
except ImportError:
    msvcrt = None


HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# Shared state written by WS threads, read by the control loop.
# --------------------------------------------------------------------------
class InputState:
    def __init__(self):
        self.lock = threading.Lock()
        self.human = [0.0] * N_JOINTS
        self.tracked = False
        self.last_rx = 0.0
        self.packets = 0
        self.bad_packets = 0
        self.hand = "?"

    def update(self, human, tracked, hand):
        with self.lock:
            self.human = human
            self.tracked = tracked
            self.hand = hand
            self.last_rx = time.monotonic()
            self.packets += 1

    def snapshot(self):
        with self.lock:
            return list(self.human), self.tracked, self.last_rx, self.packets, self.hand


class NullRobot:
    """--dry-run stand-in: same surface as DG5F, touches nothing."""
    def version(self):
        return (0, 0, 0)

    def configure_system(self, **kw):
        pass

    def configure_options(self, **kw):
        pass

    def connect(self, timeout=0.0):
        return True

    def system_start(self):
        pass

    def set_pid(self, *a, **k):
        pass

    def move_servo_joint(self, degrees):
        return 0

    def read(self):
        return None

    def close(self):
        pass


def parse_packet(text):
    """
    Accepts either the lens format:
        {"tracked":true,"hand":"right","f":[[4],[4],[4],[4],[4]]}
    or a flat form used by test_sender.py:
        {"tracked":true,"j":[20 floats]}
    Returns (human20, tracked, hand) or None if unusable.
    """
    msg = json.loads(text)
    if not isinstance(msg, dict):
        return None
    if msg.get("cmd"):
        return None

    tracked = bool(msg.get("tracked", True))
    hand = str(msg.get("hand", "?"))

    if "j" in msg:
        vals = msg["j"]
    elif "f" in msg:
        fingers = msg["f"]
        if not isinstance(fingers, list) or len(fingers) != 5:
            return None
        vals = []
        for f in fingers:
            if not isinstance(f, list) or len(f) != 4:
                return None
            vals.extend(f)
    else:
        return None

    if len(vals) != N_JOINTS:
        return None

    out = []
    for v in vals:
        fv = float(v)
        if fv != fv or fv in (float("inf"), float("-inf")):  # NaN / inf guard
            return None
        out.append(fv)
    return out, tracked, hand


def dgmanager_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq DGManager.exe", "/NH"],
                           capture_output=True, text=True, timeout=8)
        return "DGManager.exe" in r.stdout
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Spectacles -> Delto DG-5F bridge")
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--dry-run", action="store_true",
                    help="do not connect to the robot; print what would be sent")
    ap.add_argument("--auto-arm", action="store_true",
                    help="arm immediately instead of waiting for [space]")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    ctrl = cfg["control"]
    rate_hz = float(ctrl["rate_hz"])
    period = 1.0 / rate_hz
    watchdog_s = float(ctrl["watchdog_ms"]) / 1000.0
    neutral = [float(v) for v in ctrl["neutral_pose_deg"]]

    retarget = Retargeter(cfg)
    retarget.reset_to(neutral)
    state = InputState()

    # Safety invariant: a relaxed flat hand (all human angles 0) must command
    # the neutral pose. If a config edit breaks this, the hand assumes a
    # non-neutral posture the moment it loses the operator -- say so loudly.
    rest = retarget.map_only([0.0] * N_JOINTS)
    drift = [(retarget.names[i], rest[i]) for i in range(N_JOINTS)
             if abs(rest[i] - neutral[i]) > 1.0]
    if drift:
        print("  !! config warning: neutral human hand does not map to the neutral pose:")
        for name, v in drift:
            print(f"       {name:<12} -> {v:+.1f} deg")
        print("     See _zero_invariant in config.json.\n")

    # ---- robot ---------------------------------------------------------
    if args.dry_run:
        robot = NullRobot()
        print("[bridge] DRY RUN -- robot will not be touched.")
    else:
        if dgmanager_running():
            print("\n  !! DGManager.exe is running.")
            print("     The gripper accepts one client at a time, so the connection")
            print("     below will almost certainly fail. Close DGManager first.\n")
        from dg5f import DG5F, DGError
        g = cfg["gripper"]
        robot = DG5F()
        print(f"[bridge] DGSDK version {'.'.join(map(str, robot.version()))}")
        try:
            # Order matters and mirrors DGManager exactly: options are applied
            # only once the link is up, otherwise the SDK cannot resolve the
            # model and returns NOT_FOUND_MODEL (111).
            robot.configure_system(
                ip=g["ip"], port=int(g["port"]), slave_id=int(g["slave_id"]),
                read_timeout=int(g["read_timeout"]),
                control_mode=int(g["control_mode"]),
            )
            print(f"[bridge] connecting to {g['ip']}:{g['port']} ...")
            if robot.connect(timeout=10.0):
                print("[bridge] link up.")
            else:
                print("[bridge] warning: no connect confirmation, continuing anyway.")
            robot.configure_options(model=int(g["model"]))
            print("[bridge] options applied.")
            robot.system_start()          # == DGManager's "Ready"
            time.sleep(0.5)
            p = g["pid"]
            robot.set_pid(float(p["p"]), float(p["d"]), float(p["i"]),
                          float(p["i_limit"]), int(p["mode"]))
            print("[bridge] gripper ready (SystemStart done, PID applied).")
        except DGError as e:
            print(f"[bridge] FAILED: {e}")
            if e.code == 111:
                print("         The model was rejected. This usually means the")
                print("         connection was not established -- check the cable,")
                print("         and that nothing else holds 169.254.186.72:502.")
            robot.close()
            return 1

    # ---- websocket -----------------------------------------------------
    def on_message(conn, text):
        parsed = None
        try:
            parsed = parse_packet(text)
        except (ValueError, TypeError):
            parsed = None
        if parsed is None:
            with state.lock:
                state.bad_packets += 1
            return
        human, tracked, hand = parsed
        state.update(human, tracked, hand)

    def on_open(conn):
        print(f"\n[bridge] lens connected from {conn.addr[0]}")

    def on_close(conn):
        print(f"\n[bridge] lens disconnected {conn.addr[0]}")

    srv_cfg = cfg["server"]
    server = WebSocketServer(srv_cfg["host"], int(srv_cfg["port"]),
                             on_message=on_message, on_open=on_open, on_close=on_close)
    try:
        server.start()
    except OSError as e:
        print(f"\n[bridge] {e}\n")
        if not args.dry_run:
            robot.close()
        return 1
    print(f"[bridge] websocket listening on ws://{srv_cfg['host']}:{srv_cfg['port']}")
    print("[bridge] keys: [space] arm/disarm   [n] neutral   [q] quit")

    armed = bool(args.auto_arm)
    if armed:
        print("[bridge] ARMED (--auto-arm)")
    else:
        print("[bridge] DISARMED -- press [space] to arm.")

    last_tick = time.monotonic()
    last_status = 0.0
    err_count = 0
    last_err = 0
    running = True
    goto_neutral_until = 0.0

    try:
        while running:
            now = time.monotonic()
            dt = now - last_tick
            if dt < period:
                time.sleep(max(0.0, period - dt))
                now = time.monotonic()
                dt = now - last_tick
            last_tick = now

            # ---- keyboard ----
            if msvcrt:
                while msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch in (b" ",):
                        armed = not armed
                        if armed:
                            # Re-prime so arming never causes a jump: start from
                            # wherever the fingers currently are.
                            retarget.reset_to(retarget.commanded)
                        print(f"\n[bridge] {'ARMED' if armed else 'DISARMED'}")
                    elif ch in (b"q", b"Q", b"\x03"):
                        running = False
                    elif ch in (b"n", b"N"):
                        goto_neutral_until = now + float(ctrl["return_seconds"])
                        print("\n[bridge] returning to neutral")

            human, tracked, last_rx, packets, hand = state.snapshot()
            fresh = (now - last_rx) < watchdog_s if last_rx else False

            if now < goto_neutral_until:
                # slew toward neutral using the same rate limiter
                target = neutral
                max_step = retarget.max_dps * dt
                for i in range(N_JOINTS):
                    d = target[i] - retarget.commanded[i]
                    d = max(-max_step, min(max_step, d))
                    retarget.commanded[i] += d
                    retarget.smoothed[i] = retarget.commanded[i]
                cmd = list(retarget.commanded)
                reason = "neutral"
            elif fresh and tracked:
                cmd = retarget.step(human, dt)
                reason = "tracking"
            else:
                cmd = retarget.hold()
                reason = "no-signal" if not fresh else "hand-lost"

            if armed:
                code = robot.move_servo_joint(cmd)
                if code != 0:
                    err_count += 1
                    last_err = code

            # ---- status line ----
            if now - last_status > 0.25:
                last_status = now
                flag = "ARMED " if armed else "disarm"
                err = ""
                if err_count:
                    err = f" err={err_count}(last={last_err})"
                bad = ""
                with state.lock:
                    if state.bad_packets:
                        bad = f" bad={state.bad_packets}"
                preview = " ".join(f"{v:6.1f}" for v in cmd[:8])
                # Say out loud why the hand is not moving, rather than making
                # the operator infer it from a six-letter flag.
                if not armed:
                    hint = "  <-- DISARMED, nothing will move: press [space]"
                elif reason == "no-signal":
                    hint = "  <-- armed but no data: start test_sender.py or the Lens"
                elif reason == "hand-lost":
                    hint = "  <-- armed, but the tracker cannot see the hand"
                else:
                    hint = ""
                sys.stdout.write(
                    f"\r[{flag}] {reason:<10} hand={hand:<5} rx={packets:<6}"
                    f"{bad}{err}  j0-7: {preview}{hint}   ")
                sys.stdout.flush()

    except KeyboardInterrupt:
        pass
    finally:
        print("\n[bridge] shutting down ...")
        server.stop()
        if armed and not args.dry_run and ctrl.get("return_to_neutral_on_exit", True):
            print("[bridge] returning to neutral ...")
            secs = float(ctrl["return_seconds"])
            steps = max(1, int(secs * rate_hz))
            start = list(retarget.commanded)
            for s in range(steps + 1):
                t = s / steps
                pose = [start[i] + (neutral[i] - start[i]) * t for i in range(N_JOINTS)]
                robot.move_servo_joint(pose)
                time.sleep(period)
        robot.close()
        print("[bridge] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
