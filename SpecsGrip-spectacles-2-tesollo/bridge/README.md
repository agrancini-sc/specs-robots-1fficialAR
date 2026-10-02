# Spectacles → Delto DG-5F bridge

Drives a Tesollo Delto DG-5F-R robot hand from Spectacles hand tracking.

```
Spectacles (Lens)          this PC                         gripper
  SIK hand tracking         bridge.py                      DG-5F-R
  measure 20 angles  ──ws──▶ map → clamp → smooth → slew ──▶ 169.254.186.72:502
       ~60 Hz               DGSDK.dll / MoveServoJoint()      (Modbus TCP)
```

## Reference setup

What this was built and tested against. Every value was read off the real hardware
and DGManager's own files, not assumed:

| | |
|---|---|
| Gripper | **DG-5F-R** (model `24354` = `0x5F22` = `DG_MODEL_DG_5F_RIGHT`) |
| Address | `169.254.186.72:502`, Modbus slave ID 1, over the `Ethernet` NIC |
| Control mode | **DEVELOPER** (`controlMode: 1`) — required by `MoveServoJoint()` |
| Joints | 20 = 5 fingers × 4 |
| SDK | `C:\TESOLLO\DGManager\resources\libs\DGSDK.dll`, v2.0.0, x64, `extern "C"` |
| PC's Wi-Fi IP | whatever `py netcheck.py` prints — this is what the Lens connects to, and it changes with the network |

**"Ready" in DGManager is `SystemStart()`.** Until it runs the gripper accepts no
motion commands. `bridge.py` calls it for you during startup.

### Joint layout

Indices 0–19: thumb, index, middle, ring, pinky — 4 each.
Within a finger `[abduction, mcp, pip, dip]`; the thumb is `[abduction, opposition, mcp, ip]`.
Positive = flexion (curl). The thumb's joint 2 is the distinctive −100..0 opposition axis.

Every limit in `config.json` is the observed min/max across the **100 factory poses**
Tesollo ships in DGManager's DG-5F-R recipe file, so each is known-reachable.

## Setup

### 1. Let the Lens reach this PC

Windows Firewall blocks the port by default. **Check for Block rules first** — if you
ever clicked "Cancel" on a Windows firewall popup for Python, it created an explicit
inbound Block rule, and **Block beats Allow**, so adding an allow rule would do nothing:

```powershell
Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like '*python*' } | ForEach-Object { $_ | Get-NetFirewallRule } | Select-Object DisplayName, Direction, Action, Profile
```

Then check which profile your Wi-Fi is on:

```powershell
Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory
```

If the Block rules are on `Public` and your Wi-Fi is `Public`, the clean fix is to move
the network to `Private` (correct for a home network anyway) — the Block rules stay,
but no longer apply. In an **admin** PowerShell:

```powershell
Set-NetConnectionProfile -Name "<your-wifi-name>" -NetworkCategory Private
New-NetFirewallRule -DisplayName "Delto Hand Bridge" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

Confirm your Wi-Fi IP hasn't changed (DHCP moves it):

```powershell
Get-NetIPAddress -InterfaceAlias Wi-Fi -AddressFamily IPv4 | Select-Object IPAddress
```

### 2. Point the Lens at this PC

The scene already has a **HandBridge** object running `Assets/Scripts/HandBridge.ts`,
with **Status Text** wired to the Debug Panel and the hand settings wired to the
Settings panel switches. **Don't add another one.** The bridge accepts every Lens
connection and moves the robot to whichever packet arrived last, so a second copy
would fight the first for control.

1. Open `SpecsGrip.esproj` in Lens Studio.
2. Select the **HandBridge** object and set **Server Url** to `ws://<your-wifi-ip>:8765`
   (`py netcheck.py` prints the exact URL). It accepts a comma-separated list and
   rotates through them on retry, which saves re-pushing every time your PC's IP changes.
3. Tick **Debug Log** while bringing it up.

### Which hand drives it

**Hand To Track** picks yours; the robot is always the DG-5F-R. Tick **Auto Switch
Hand** to follow whichever hand is visible, handing over only when the current one
leaves view (switching on every flicker would make the robot jitter between poses).

Left-hand input is **mirrored in the Lens**, not in config. A left hand is the mirror
image of a right one, so the palm frame's `forward x side` normal points out the
opposite face; left uncorrected, every signed quantity — abduction and thumb
opposition, 5 joints — would drive backwards. The Lens flips the normal for a left
hand so either hand produces the same robot motion and `config.json` stays tuned once.
The HUD shows `mirrored` when it is active.

Spectacles and the PC must be on the **same private Wi-Fi network**.

### 3. Bring it up — in this order

> **All commands below run from this folder.** Do this first in every new terminal,
> or you'll get `can't open file ... bridge.py: [Errno 2] No such file or directory`:
>
> ```powershell
> cd path\to\SpecsGrip\bridge
> ```
>
> (Or stay in the project root and prefix the path: `py bridge\bridge.py --dry-run`.)

**a. Robot untouched, full pipeline:**

```bash
py bridge.py --dry-run --auto-arm
```

Then in a second terminal:

```bash
py test_sender.py --wave
```

You should see `tracking` and joint numbers moving. Nothing is connected to the robot.

**b. Check the SDK bindings (read-only, no connection, no motion):**

```bash
py selftest.py
```

**c. Real robot.** Close DGManager first — the gripper accepts **one client at a
time**, and DGManager holds the connection while it is open. Then:

```bash
py bridge.py
```

It starts **disarmed**. Press `space` to arm when you're ready for it to move.

**d. Verify the mapping** — with the bridge armed, run `py test_sender.py --sweep`.
It drives one joint at a time and prints which. Watch the hand and confirm each
joint is the one named. This is the fastest way to catch a sign or index error.

**e. Finally, the Lens.** Push to Spectacles and move your hand.

## Keys

| key | action |
|---|---|
| `space` | arm / disarm |
| `n` | slew back to neutral |
| `q` | quit (returns to neutral, then `SystemStop` + disconnect) |

## Tuning

All of it is in `config.json` — **no Lens rebuild needed**, just restart `bridge.py`.
The Lens only ever sends raw human angles; every opinion lives on this side.

- `smoothing_alpha` — lower = smoother, laggier. Start here if motion looks jittery.
- `max_deg_per_sec` — the slew cap. **Your main protection** against a tracking
  glitch snapping a finger. Lower it if anything looks violent.
- `joints[].out` — scaling per joint. **Swap the two values to invert a joint.**
- `joints[].hard` — the clamp. Applied after mapping; nothing gets past it.

### The zero invariant

Each `in`/`out` pair places human 0 at robot 0, so a relaxed flat hand commands the
all-zeros neutral pose. `bridge.py` checks this at startup and warns if an edit
breaks it. Keep it — it's what makes "hand goes flat" a predictable resting state.

## Safety

Applied in this order, every tick: **map → hard clamp → EMA smooth → slew limit.**
Clamping before smoothing means a wild input can't drag the smoothed value outside
the safe band; the slew limit runs last so it's the final authority on speed.

- Starts **disarmed**; nothing moves until you press `space`.
- Arming re-primes the filter from the current pose, so arming never causes a jump.
- **Watchdog** (`watchdog_ms`, default 300 ms): if packets stop, the hand **freezes**
  at its last commanded pose — it does not go limp and does not snap home.
- Hand lost by the tracker → same freeze.
- Clean exit slews back to neutral, then `SystemStop()` + disconnect.

## Reading the on-device HUD

The Logger panel only works while tethered to Lens Studio, so the Lens draws its own
status in the **Debug Panel**. It's already wired up: the panel's text is assigned to
HandBridge's **Status Text** input, and the panel follows your view. It shows state,
URL, attempt count, packets sent, tracking state and the last error.

| HUD state | What it means | Where to look |
|---|---|---|
| `CONNECTED` + green | working | if the hand still doesn't move: is the bridge **armed**? |
| `CONNECTED` + amber | socket fine, hand not visible | hold your hand in view of the glasses |
| `CONNECTING` forever | no answer from the PC | bridge not running, wrong IP, or firewall |
| `CLOSED` code **1006** | never reached the PC at all | firewall Block rule, wrong IP, or Wi-Fi client isolation |
| `SOCKET ERROR` | no route, or `ws://` refused | check `netcheck.py`; if the network is fine, try a `wss://` tunnel |
| `CREATE FAILED` | `createWebSocket` threw immediately | usually the URL scheme was rejected, or Internet permission is not granted |
| `NO INTERNET MODULE` | the module did not load | check the Lens's internet permission in Project Settings |

Cross-check against the bridge terminal, which now logs the raw TCP accept:

- **`[ws] TCP connection from ...` appears** → the Lens reached your PC. Any failure
  after this is a WebSocket/protocol problem, not a network one.
- **Nothing at all** → packets never arrived. Firewall, IP, or client isolation.
  This distinction is the single most useful thing when the Lens "won't connect".

## Troubleshooting

**`can't open file '...\bridge.py': [Errno 2] No such file or directory`.** Your
terminal is in the project root, not this folder. `cd bridge` first, or run
`py bridge\bridge.py`.

**Lens won't connect.** Most likely, in order: firewall rule not added; PC's Wi-Fi IP
changed; Spectacles on a different network.

If plain `ws://` is rejected outright, the Lens Studio typings document
`createWebSocket` with a `wss` URL, and it's marked `@wearableOnly` — **it will not
connect from Lens Studio Preview, only from the device.** If you need TLS, put a
tunnel in front (`ngrok http 8765` or a Cloudflare tunnel) and use the `wss://` URL
it gives you; no code change needed, just the `Server Url` field.

**`SetGripperOption failed: NOT_FOUND_MODEL` (111).** The model is only resolvable
once the link is up, so options must be applied *after* `ConnectToGripper()` — which
is why DGManager applies them from inside its onConnected callback. `bridge.py` does
the same. If you still see it, the connection itself is failing; run:

```bash
py connecttest.py
```

That walks the sequence step by step and never engages the servos.

**`ConnectToGripper failed: SOCK_EXCEPTION`.** DGManager is still open, or something
else holds the socket. Check:

```powershell
Get-NetTCPConnection -RemotePort 502 | Select-Object OwningProcess, State
```

**`NOT_SUPPORTED_CONTROL_MODE_OPERATOR`.** `MoveServoJoint()` is DEVELOPER-mode only.
Keep `gripper.control_mode: 1`.

**Hand moves but the wrong finger/direction.** Run `--sweep` and fix the offending
joint's `out` pair in `config.json`. Abduction and thumb opposition are signed
against a palm-local frame, so their sign depends on handedness — inverting in
config is the intended fix, not editing the Lens.

**Fingers drift or feel mushy.** Tune `gripper.pid`. `P=1.0, D=3.0` are the factory
DG-5F developer-recipe defaults.

## Files

| file | role |
|---|---|
| `bridge.py` | main loop, arming, watchdog, status |
| `dg5f.py` | ctypes binding to `DGSDK.dll` |
| `retarget.py` | mapping, clamping, smoothing, slew |
| `wsserver.py` | RFC 6455 server, stdlib only (no pip install) |
| `test_sender.py` | synthetic poses: `--wave`, `--sweep`, `--hold` |
| `selftest.py` | struct-layout + DLL-load checks, read-only |
| `connecttest.py` | connect + telemetry check; never engages servos or moves |
| `config.json` | all tuning |
