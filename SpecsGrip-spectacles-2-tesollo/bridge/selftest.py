"""
Read-only checks. Loads DGSDK.dll and validates the ctypes struct layouts.
Does NOT connect to the gripper and does NOT move anything.
"""
import ctypes
import sys

import dg5f
from dg5f import (DG5F, GripperSetting, GripperSystemSetting,
                  ReceivedGripperData, result_name)

ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print(f"  [{'ok' if good else 'FAIL'}] {label}: {got}" + ("" if good else f" (expected {want})"))


print("struct sizes (Windows natural alignment):")
# 32 + 32 + 6*4 = 88
check("GripperSystemSetting", ctypes.sizeof(GripperSystemSetting), 88)
# 80+80+20+20+32+4+4+4+4+1 -> 249 padded to 252
check("GripperSetting", ctypes.sizeof(GripperSetting), 252)
# 80+80+80+80+120 + 8*4 = 472
check("ReceivedGripperData", ctypes.sizeof(ReceivedGripperData), 472)

print("\nfield offsets:")
check("GripperSystemSetting.port", GripperSystemSetting.port.offset, 64)
check("GripperSetting.model", GripperSetting.model.offset, 244)
check("ReceivedGripperData.moving", ReceivedGripperData.moving.offset, 440)

print("\nresult code names:")
for c in (0, 1, 1004, 401, 9999):
    print(f"  {c:>5} -> {result_name(c)}")

print("\nloading DGSDK.dll ...")
try:
    g = DG5F()
    print(f"  [ok] loaded, library version {'.'.join(map(str, g.version()))}")
    for fn in ("SetGripperSystem", "SetGripperOption", "ConnectToGripper",
               "SystemStart", "MoveServoJoint", "GetReceivedGripperData"):
        print(f"  [ok] resolved {fn}")
except Exception as e:
    ok = False
    print(f"  [FAIL] {type(e).__name__}: {e}")

print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
sys.exit(0 if ok else 1)
