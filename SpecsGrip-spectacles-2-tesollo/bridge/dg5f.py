"""
ctypes binding for the Tesollo DGSDK (Delto Gripper DG-5F).

Wraps C:\\TESOLLO\\DGManager\\resources\\libs\\DGSDK.dll -- the same library
DGManager itself drives. Struct layouts come from DGDataTypes.h; on Windows the
headers do NOT apply #pragma pack (it is guarded by #ifdef __linux__), so
natural alignment applies, which is what ctypes does by default.

Startup order is mandated by DGSDK.h:
    SetGripperSystem -> SetGripperOption -> ConnectToGripper -> SystemStart
SystemStart() is what DGManager's "Ready" button does: until it runs, the
gripper accepts no motion commands.
"""

import ctypes
import os
import threading
import time
from ctypes import c_char, c_float, c_int, c_int8, c_uint16

MAX_JOINT_COUNT = 20
MAX_FINGER_COUNT = 5

DEFAULT_SDK_DIR = r"C:\TESOLLO\DGManager\resources\libs"
DEFAULT_DEP_DIR = r"C:\TESOLLO\DGManager\resources\windows_dependency"

# DG_MODEL
MODEL_DG_5F_LEFT = 0x5F12   # 24338
MODEL_DG_5F_RIGHT = 0x5F22  # 24354

# CONTROL_MODE
CONTROL_MODE_OPERATOR = 0
CONTROL_MODE_DEVELOPER = 1

# COMMUNICATION_MODE
COMM_MODE_ETHERNET = 0
COMM_MODE_RS485 = 1


class GripperSystemSetting(ctypes.Structure):
    _fields_ = [
        ("comport", c_char * 32),
        ("ip", c_char * 32),
        ("port", c_int),
        ("readTimeout", c_int),
        ("controlMode", c_int),
        ("communicationMode", c_int),
        ("slaveID", c_int),
        ("baudrate", c_int),
    ]


class GripperSetting(ctypes.Structure):
    _fields_ = [
        ("jointOffset", c_float * MAX_JOINT_COUNT),
        ("jointInpose", c_float * MAX_JOINT_COUNT),
        ("tcpInpose", c_float * MAX_FINGER_COUNT),
        ("orientationInpose", c_float * MAX_FINGER_COUNT),
        ("receivedDataType", c_int * 8),
        ("movingInpose", c_float),
        ("jointCount", c_int),
        ("fingerCount", c_int),
        ("model", c_int),
        ("dutyByteLength", c_int8),
    ]


class ReceivedGripperData(ctypes.Structure):
    _fields_ = [
        ("joint", c_float * MAX_JOINT_COUNT),
        ("current", c_int * MAX_JOINT_COUNT),
        ("velocity", c_int * MAX_JOINT_COUNT),
        ("temperature", c_float * MAX_JOINT_COUNT),
        ("TCP", c_float * (6 * MAX_FINGER_COUNT)),
        ("moving", c_int),
        ("targetArrived", c_int),
        ("blendMoveState", c_int),
        ("currentBlendIndex", c_int),
        ("productID", c_int),
        ("firmwareVersion", c_int),
        ("moduleErrorCode", c_int),
        ("controlPeriod", c_int),
    ]


class ReceivedFingertipSensorData(ctypes.Structure):
    _fields_ = [
        ("sensorType", c_int),
        ("attachedFinger", c_int * MAX_FINGER_COUNT),
        ("forceTorque", c_float * (6 * MAX_FINGER_COUNT)),
        ("tactile", c_uint16 * (18 * MAX_FINGER_COUNT)),
    ]


# DG_RESULT, transcribed by counting the implicit enum values in DGDataTypes.h.
# The gaps matter: the 100-block jumps from 103 to 105, so everything after is
# offset by one from the obvious guess.
RESULT_NAMES = {
    0: "NONE (ok)",
    1: "SYSTEM_SETTING_NOT_PERFORMED",
    100: "VALUE_IS_NEGATIVE",
    101: "OVERFLOW_JOINT_COUNT",
    102: "OVERFLOW_FINGER_COUNT",
    103: "OVERFLOW_TCP_COUNT",
    105: "OVERFLOW_ADD_BLEND_SIZE",
    106: "OVERFLOW_RECIPE_BLEND_SIZE",
    107: "BLEND_SIZE_ZERO",
    108: "NOT_SUPPORTED_MODEL",
    109: "DATA_IS_ZERO",
    110: "DATA_IS_NOT_BOOLEAN",
    111: "NOT_FOUND_MODEL (model number rejected -- are you connected yet?)",
    112: "OVERFLOW_RECIPE_POSE_COUNT",
    113: "OVERFLOW_RECIPE_GAIN_COUNT",
    114: "OVERFLOW_RECIPE_GRASP_COUNT",
    115: "INVALID_CONTROL_MODE",
    116: "INVALID_GRASP_MODE_DATA",
    117: "OVERFLOW_GRASP_OPTION_DATA",
    118: "OVERFLOW_MAX_BYTE_DATA",
    119: "OVERFLOW_CURRENT_LIMIT",
    120: "IS_NOT_TORQUE_CONTROL_MODE",
    121: "NOT_SUPPORTED_DATA_TYPE",
    122: "BACKUP_START",
    123: "INVALID_PASSWORD",
    124: "OVERFLOW_GPIO_COUNT",
    125: "OVERFLOW_GRASP_FORCE",
    126: "OVERFLOW_BLEND_WAIT_TIME",
    127: "NOT_FOUND_RESTORE_DATA",
    128: "RESTORE_START",
    200: "NOT_ARRIVED",
    201: "NOT_START_BLEND_MOVE",
    202: "ALREADY_BLEND_MOVE_STATE",
    203: "ALREADY_TCP_MOVE",
    204: "RECIPE_IS_NOT_JOINT_MODE",
    205: "ACTIVATE_CURRENT_CONTROL_MODE",
    206: "ACTIVATE_GRASP_MOTION",
    207: "ACTIVATE_MANUAL_CONTROL_MODE",
    500: "SOCK_EXCEPTION",
    501: "SOCK_FAILED_WSA_START_UP",
    1002: "NO_GRASP_OBJECT",
    1003: "ONLY_SUPPORTED_3FINGER",
    1004: "NOT_SUPPORTED_CONTROL_MODE_OPERATOR (needs DEVELOPER mode)",
    1005: "NOT_SUPPORTED_CONTROL_MODE_DEVELOPER",
    1006: "NOT_SUPPORTED_PORT_NUM",
    2000: "PORT_EXCEPTION",
    2001: "PORT_FAILED_START_UP",
    2002: "PORT_SET_CONFIG_ERROR",
    2003: "PORT_SET_TIMEOUT_ERROR",
    2004: "PORT_SET_COMMASK_ERROR",
    2009: "DIAGNOSING_SYSTEM",
}

for _i in range(401, 426):
    RESULT_NAMES[_i] = f"MODULE_FAULT_{_i - 400}"


# Callback prototypes (void(void)) used to learn when the link is actually up.
CONNECTED_CB = ctypes.CFUNCTYPE(None)
DISCONNECTED_CB = ctypes.CFUNCTYPE(None)


def result_name(code: int) -> str:
    return RESULT_NAMES.get(code, f"UNKNOWN({code})")


class DGError(RuntimeError):
    def __init__(self, func: str, code: int):
        self.func = func
        self.code = code
        super().__init__(f"{func} failed: {result_name(code)}")


class DG5F:
    """Thin, explicit wrapper. One instance owns the SDK's global state."""

    def __init__(self, sdk_dir: str = DEFAULT_SDK_DIR, dep_dir: str = DEFAULT_DEP_DIR):
        dll_path = os.path.join(sdk_dir, "DGSDK.dll")
        if not os.path.isfile(dll_path):
            raise FileNotFoundError(f"DGSDK.dll not found at {dll_path}")

        # DGSDK.dll links against the MSVC runtime shipped alongside DGManager.
        for d in (sdk_dir, dep_dir):
            if os.path.isdir(d):
                try:
                    os.add_dll_directory(d)
                except (OSError, AttributeError):
                    pass

        self.lib = ctypes.CDLL(dll_path)
        self._bind()
        self._started = False
        self._connected = False
        self._connected_evt = threading.Event()
        self._cb_connected = None
        self._cb_disconnected = None

    def _bind(self):
        L = self.lib
        L.GetLibraryVersion.argtypes = [ctypes.POINTER(c_int)]
        L.GetLibraryVersion.restype = None

        L.SetGripperSystem.argtypes = [GripperSystemSetting]
        L.SetGripperSystem.restype = c_int

        L.SetGripperOption.argtypes = [GripperSetting]
        L.SetGripperOption.restype = c_int

        for name in ("ConnectToGripper", "DisconnectToGripper", "SystemStart", "SystemStop"):
            fn = getattr(L, name)
            fn.argtypes = []
            fn.restype = c_int

        L.MoveServoJoint.argtypes = [ctypes.POINTER(c_float)]
        L.MoveServoJoint.restype = c_int

        L.MoveJointAll.argtypes = [ctypes.POINTER(c_float)]
        L.MoveJointAll.restype = c_int

        L.SetMotionTimeAllEqual.argtypes = [c_int]
        L.SetMotionTimeAllEqual.restype = c_int

        L.SetControlPIDMode.argtypes = [c_int]
        L.SetControlPIDMode.restype = c_int

        L.SetJointGainPIDAllEqual.argtypes = [c_float, c_float, c_float, c_float]
        L.SetJointGainPIDAllEqual.restype = c_int

        L.SetLowPassFilterAlpha.argtypes = [c_int, c_float]
        L.SetLowPassFilterAlpha.restype = c_int

        L.GetReceivedGripperData.argtypes = [ctypes.POINTER(ReceivedGripperData)]
        L.GetReceivedGripperData.restype = c_int

        L.GetCommunicationPeriod.argtypes = [ctypes.POINTER(c_int)]
        L.GetCommunicationPeriod.restype = c_int

        L.ManualTeachMode.argtypes = [c_int]
        L.ManualTeachMode.restype = c_int

        L.SetCurrentControlMode.argtypes = [c_int]
        L.SetCurrentControlMode.restype = c_int

    # ---- helpers -------------------------------------------------------
    @staticmethod
    def _check(func: str, code: int, allow=(0,)):
        if code not in allow:
            raise DGError(func, code)
        return code

    def version(self):
        buf = (c_int * 3)()
        self.lib.GetLibraryVersion(buf)
        return tuple(buf)

    # ---- lifecycle -----------------------------------------------------
    def configure_system(self, ip: str, port: int = 502, slave_id: int = 1,
                         read_timeout: int = 60000,
                         control_mode: int = CONTROL_MODE_DEVELOPER,
                         comm_mode: int = COMM_MODE_ETHERNET):
        """Step 1. Must precede everything else (DGSDK.h says so explicitly)."""
        sys_setting = GripperSystemSetting(
            comport=b"COM3",
            ip=ip.encode("ascii"),
            port=port,
            readTimeout=read_timeout,
            controlMode=control_mode,
            communicationMode=comm_mode,
            slaveID=slave_id,
            baudrate=1,
        )
        self._check("SetGripperSystem", self.lib.SetGripperSystem(sys_setting))

    def configure_options(self, model: int = MODEL_DG_5F_RIGHT,
                          moving_inpose: float = 0.3, joint_inpose: float = 10.0,
                          received_data_type=(1, 2, 3, 4, 5, 6, 7, 8)):
        """
        Step 3 -- AFTER ConnectToGripper().

        Called before the link is up, the SDK cannot resolve `model` against the
        live device and returns NOT_FOUND_MODEL (111). DGManager gets this right
        by calling it from inside its onConnected callback.
        """
        opt = GripperSetting()
        for i in range(MAX_JOINT_COUNT):
            opt.jointOffset[i] = 0.0
            opt.jointInpose[i] = joint_inpose
        for i in range(MAX_FINGER_COUNT):
            opt.tcpInpose[i] = 0.0
            opt.orientationInpose[i] = 0.0
        for i, v in enumerate(received_data_type):
            opt.receivedDataType[i] = int(v)
        opt.movingInpose = moving_inpose
        # DGManager passes 0 for these three and lets the SDK derive them
        # from `model` -- see src/main/Main.js in its app.asar.
        opt.jointCount = 0
        opt.fingerCount = 0
        opt.dutyByteLength = 0
        opt.model = model
        self._check("SetGripperOption", self.lib.SetGripperOption(opt))

    def _install_callbacks(self):
        # ctypes callbacks must be kept referenced or they get collected and
        # the SDK calls into freed memory.
        self._cb_connected = CONNECTED_CB(self._on_connected)
        self._cb_disconnected = DISCONNECTED_CB(self._on_disconnected)
        self.lib.CallbackForOnConnected.argtypes = [CONNECTED_CB]
        self.lib.CallbackForOnConnected.restype = c_int
        self.lib.CallbackForOnDisconnected.argtypes = [DISCONNECTED_CB]
        self.lib.CallbackForOnDisconnected.restype = c_int
        self.lib.CallbackForOnConnected(self._cb_connected)
        self.lib.CallbackForOnDisconnected(self._cb_disconnected)

    def _on_connected(self):
        self._connected_evt.set()

    def _on_disconnected(self):
        self._connected_evt.clear()
        self._connected = False

    def connect(self, timeout: float = 10.0) -> bool:
        """
        Step 2. Returns True if the SDK confirmed the link within `timeout`.

        ConnectToGripper() returns immediately; the link is only really up once
        the onConnected callback fires. Applying options before that is what
        produces NOT_FOUND_MODEL.
        """
        self._install_callbacks()
        self._connected_evt.clear()
        self._check("ConnectToGripper", self.lib.ConnectToGripper())
        # Mark connected either way so close() still tears the socket down.
        self._connected = True

        if self._connected_evt.wait(timeout):
            return True

        # Fallback: if the callback never fires but traffic is flowing, treat
        # that as connected too.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self.communication_period() > 0:
                return True
            time.sleep(0.1)
        return False

    def system_start(self):
        """Equivalent to DGManager's 'Ready' button."""
        self._check("SystemStart", self.lib.SystemStart())
        self._started = True

    def system_stop(self):
        if self._started:
            code = self.lib.SystemStop()
            self._started = False
            return code
        return 0

    def disconnect(self):
        if self._connected:
            code = self.lib.DisconnectToGripper()
            self._connected = False
            return code
        return 0

    # ---- tuning --------------------------------------------------------
    def set_pid(self, p: float, d: float, i: float = 0.0, i_limit: float = 0.0,
                pid_mode: int = 0):
        """pid_mode: 0 = PD, 1 = PID. Factory DG-5F developer defaults are P=1, D=3."""
        self._check("SetControlPIDMode", self.lib.SetControlPIDMode(pid_mode))
        self._check("SetJointGainPIDAllEqual",
                    self.lib.SetJointGainPIDAllEqual(p, d, i, i_limit))

    def set_low_pass_filter(self, enabled: bool, alpha: float):
        self._check("SetLowPassFilterAlpha",
                    self.lib.SetLowPassFilterAlpha(1 if enabled else 0, alpha))

    # ---- motion --------------------------------------------------------
    def move_servo_joint(self, degrees):
        """Immediate, non-interpolated move of all 20 joints. DEVELOPER mode only."""
        buf = (c_float * MAX_JOINT_COUNT)(*[float(v) for v in degrees])
        return self.lib.MoveServoJoint(buf)

    def move_joint_all(self, degrees):
        """Interpolated move honouring the configured motion time."""
        buf = (c_float * MAX_JOINT_COUNT)(*[float(v) for v in degrees])
        return self.lib.MoveJointAll(buf)

    def set_motion_time_all(self, ms: int):
        return self.lib.SetMotionTimeAllEqual(int(ms))

    # ---- telemetry -----------------------------------------------------
    def read(self) -> ReceivedGripperData:
        data = ReceivedGripperData()
        self.lib.GetReceivedGripperData(ctypes.byref(data))
        return data

    def communication_period(self) -> int:
        out = c_int(0)
        self.lib.GetCommunicationPeriod(ctypes.byref(out))
        return out.value

    def close(self):
        try:
            self.system_stop()
        finally:
            self.disconnect()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
