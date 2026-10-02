"""
Connection diagnostic. Verifies the SetGripperSystem -> Connect -> SetGripperOption
sequence against the real gripper.

Deliberately does NOT call SystemStart() and NEVER sends a motion command, so the
servos stay disengaged and the hand cannot move. Safe to run at any time.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dg5f import DG5F, DGError, result_name  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
g = cfg["gripper"]

print("NOTE: this script never calls SystemStart() and never commands motion.\n")

robot = DG5F()
print(f"1. DGSDK version {'.'.join(map(str, robot.version()))}")

try:
    robot.configure_system(
        ip=g["ip"], port=int(g["port"]), slave_id=int(g["slave_id"]),
        read_timeout=int(g["read_timeout"]), control_mode=int(g["control_mode"]),
    )
    print(f"2. SetGripperSystem ok  ({g['ip']}:{g['port']}, "
          f"controlMode={g['control_mode']}, slaveID={g['slave_id']})")

    print("3. ConnectToGripper ...", end=" ", flush=True)
    confirmed = robot.connect(timeout=10.0)
    print("link confirmed" if confirmed else "NO confirmation (continuing)")

    robot.configure_options(model=int(g["model"]))
    print(f"4. SetGripperOption ok  (model={g['model']} = 0x{int(g['model']):04X})")

    time.sleep(0.5)
    data = robot.read()
    print(f"5. telemetry: productID={data.productID} "
          f"firmware={data.firmwareVersion} "
          f"controlPeriod={data.controlPeriod} "
          f"moduleErrorCode={data.moduleErrorCode}")
    joints = ", ".join(f"{v:.1f}" for v in list(data.joint)[:8])
    print(f"   current joints[0:8]: {joints}")
    print(f"   communication period: {robot.communication_period()}")

    print("\nSEQUENCE OK -- bridge.py should now reach 'gripper ready'.")

except DGError as e:
    print(f"\nFAILED at {e.func}: {result_name(e.code)}")
    sys.exit(1)
finally:
    robot.disconnect()
    print("disconnected.")
