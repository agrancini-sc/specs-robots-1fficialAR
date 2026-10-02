<h1 align="center">Spectacles Robotics Projects</h1>

<p align="center">
  <b>An unofficial collection of robotics projects built on Snap Spectacles.</b>
</p>

<p align="center">
  <a href="#projects">Projects</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#contributors">Contributors</a> •
  <a href="#licenses">Licenses</a>
</p>

---

> [!IMPORTANT]
> **This repository is unofficial.** It is not developed, maintained, endorsed, or
> supported by Snap Inc. Every project here was built by independent developers and is
> tracked in one place purely for discoverability. For official Spectacles samples, see
> [Snapchat/Spectacles-Sample](https://github.com/Snapchat/Spectacles-Sample).

## About

Augmented reality is turning out to be a natural interface for robotics: you can see what
the robot sees, understand what it intends to do, and direct it with your hands instead of
a gamepad or a terminal. This repo tracks projects that explore that intersection on
[Snap Spectacles](https://www.spectacles.com/) — teleoperation, navigation, sensor
visualization, LLM-driven control, and even physical games — across quadrupeds, humanoids,
and desktop robots.

Each project lives in its own top-level folder and is imported with its **full original
commit history**, so authorship and development context are preserved. Nothing here is a
rewrite — these are the upstream projects, mirrored.

## Projects

| Project | Robot(s) | Interaction | Author |
|---|---|---|---|
| [Spectacles-2-Unitree](#spectacles-2-unitree) | Unitree G1 humanoid | Hand-tracked teleoperation | [TastyDucks](https://github.com/TastyDucks) |
| [spectacles-reachy-mini](#spectacles-reachy-mini) | Reachy Mini | Puppeteering + LLM assistant | [V4C38](https://github.com/V4C38) |
| [spectacles-dimensional-os](#spectacles-dimensional-os) | Unitree Go2 + G1 | Navigation + LiDAR visualization | [V4C38](https://github.com/V4C38) |
| [VectAR-Airhokey](#vectar-airhokey) | Anki Vector | AR air hockey vs. a real robot | [PtPavloTkachenko](https://github.com/PtPavloTkachenko) |
| [so101-helper](#so101-helper) | Hugging Face SO-101 arm | Assembly, calibration & on-LAN control | [a-sumo](https://github.com/a-sumo) |
| [specs-microduck](#specs-microduck) | Pollen Robotics Micro Duck | Hand-gesture teleoperation | [kgediya](https://github.com/kgediya) |
| [SpecsGrip-spectacles-2-tesollo](#specsgrip-spectacles-2-tesollo) | Tesollo Delto DG-5F robot hand | Bare-hand finger teleoperation | [amirmohideen](https://github.com/amirmohideen) |

---

### Spectacles-2-Unitree

📁 [`Spectacles-2-Unitree/`](./Spectacles-2-Unitree) &nbsp;•&nbsp; 🔗 Upstream: [TastyDucks/Spectacles-Sample](https://github.com/TastyDucks/Spectacles-Sample/tree/main/Spectacles-2-Unitree) &nbsp;•&nbsp; 📝 Originally proposed as [Spectacles-Sample#5](https://github.com/Snapchat/Spectacles-Sample/pull/5)

Teleoperation of a **Unitree G1 humanoid** from Spectacles — in simulation or on real
hardware. You drive the robot's arms and hands directly with your own, and see its camera
feed streamed back into the lens.

A good reference for several Spectacles techniques at once: **hand tracking** mapped onto
an inverse-kinematics solver, **WebSockets** for low-latency robot control, **dynamic
texture creation** for the live video feed, and **world querying** for spatial awareness.

**What's inside**
- `Unitree.esproj` — the Lens Studio project
- `coordination-server/` — Python relay between the lens and the robot
- `unitree-client/` — robot-side client with a Pinocchio/CasADi IK solver for the G1
- `.devcontainer/` + `Dockerfile` — containerized build for the Python components

> Hand tracking is off by default. See the project README for the toggle.

---

### spectacles-reachy-mini

📁 [`spectacles-reachy-mini/`](./spectacles-reachy-mini) &nbsp;•&nbsp; 🔗 Upstream: [V4C38/spectacles-reachy-mini](https://github.com/V4C38/spectacles-reachy-mini) &nbsp;•&nbsp; 🎬 [Demo video](https://youtu.be/o7Qg9_Oi4b0)

Control a [**Reachy Mini**](https://huggingface.co/spaces/pollen-robotics/Reachy_Mini)
desktop robot from Spectacles in two distinct modes:

- **Puppeteer Mode** — you grab a floating target in AR and the robot continuously looks
  at it. Direct, physical, immediate.
- **Assistant Mode** — you talk to an LLM agent (ChatGPT) that has custom tools wired up
  to actually move the robot.

The contrast between the two is the interesting part: the same hardware feels like a
different machine depending on whether a human or a model is holding the controls. Most
logic lives in the lens rather than in Python, which makes it approachable for Lens Studio
developers who don't want to fight firmware.

**What's inside**
- `lens-studio/` — the spatial UI, interaction logic, and state machine
- `reachy-mini-app/` — Python app exposing an extended robot API over WebSocket

> No robot? There's a **simulation mode** — pick "I have no Reachy Mini" in the setup wizard.

---

### spectacles-dimensional-os

📁 [`spectacles-dimensional-os/`](./spectacles-dimensional-os) &nbsp;•&nbsp; 🔗 Upstream: [V4C38/spectacles-dimensional-os](https://github.com/V4C38/spectacles-dimensional-os)

**AR as an interface for robot navigation and sensor data.** Drive a **Unitree Go2**
quadruped or **G1** humanoid and see its world model — including streamed **LiDAR** — laid
over your own, through the Spectacles 2024 developer kit.

The physical stack (navigation, sensor streaming) is handled by
[**Dimensional OS**](https://github.com/dimensionalOS/dimos), so the project can focus on
the interface question: what does a robot's intent look like when you can see it in space?
It also digs into **pose drift** — keeping the AR frame and the robot frame agreeing over
time, which is the unglamorous problem that decides whether any of this feels real.

**What's inside**
- `lens-studio/` — the Spectacles AR interface
- `dimos-ar/` — Python bridge to Dimensional OS
- `launcher/` — startup tooling
- `assets/` — demo media and reference material

---

### VectAR-Airhokey

📁 [`VectAR-Airhokey/`](./VectAR-Airhokey) &nbsp;•&nbsp; 🔗 Upstream: [PtPavloTkachenko/VectAR-Airhokey](https://github.com/PtPavloTkachenko/VectAR-Airhokey)

**Play air hockey against a real robot.** A physical
[Anki Vector](https://en.wikipedia.org/wiki/Anki_(company)) defends his goal on your actual
table while you smash a virtual neon puck at him. The puck, the field, the score chip and
the lightning are AR — the goalie is a real machine, with his own drives, saves,
trash-talk, and sore-loser dance.

```
Spectacles lens  ── ws ──  Mac game server  ── gRPC ──  Vector robot
(puck physics,             (goalie AI,                  (drives, saves,
 score, AR field)           safety, voice)               talks, dances)
```

This is the most hardware-involved project in the collection, and the most complete: it
ships a **pairing wizard** that onboards a factory-reset Vector over Bluetooth, points him
at a bundled [wire-pod](https://github.com/kercre123/wire-pod) server, joins him to Wi-Fi,
and authorizes your Mac. Both **stock** and **OSKR/dev** robots are verified end-to-end.
There's also a browser console for monitoring and a mouse-playable practice field with a
simulated goalie, so you can work on the game without the robot present.

**What's inside**
- `lens/` — the Lens Studio 5.15 project (`robo-hockey-515.esproj`)
- `lens-523/` — the same game migrated to Lens Studio 5.23 for newer SPECS hardware
- `server/` — Python 3.12 game server, goalie AI, and pairing wizard (web console on `:8780`)
- `docs/` — unusually thorough: architecture, BLE protocol, pairing deep-dives, QA matrices

> ⚠️ **Heads up on size:** this project ships two Vector firmware OTA images (~369 MB) via
> Git LFS so a stock robot can be flashed over your own LAN with nothing to download by
> hand. They are the bulk of this repo's LFS footprint. Without them the installer still
> works by streaming from the Internet Archive — slower, and only while that stays up.

---

### so101-helper

📁 [`so101-helper/`](./so101-helper) &nbsp;•&nbsp; 🔗 Upstream: [a-sumo/so101-helper](https://github.com/a-sumo/so101-helper) &nbsp;•&nbsp; 🕶️ Lens: [**SO-101 Toolbox**](https://www.spectacles.com/lens/f3862663be534dcaa8518858c9a2bbe1?type=SNAPCODE&metadata=01) &nbsp;•&nbsp; 💬 [r/Spectacles thread](https://www.reddit.com/r/Spectacles/comments/1w46n77/comment/p7689nn/)

The companion repository for **SO-101 Toolbox** — a Lens that helps you **assemble,
inspect, and operate** the [Hugging Face **SO-101**](https://github.com/huggingface/lerobot)
robotic arm from Spectacles. Where the other projects here stream a robot's state into AR,
this one walks the whole path from a box of parts to a moving arm: a guided 3D assembly
sequence, a calibration flow, and live control of the real hardware.

The design choice worth noting is where the control loop runs. Commands and telemetry never
leave your LAN — they travel directly between the Spectacles and a bridge on the computer
that's physically wired to the arm. A hosted endpoint is used only for DNS and a one-time
pairing handshake; it never sees a command, a joint angle, or the locally generated TLS
key. That's what makes a physical robot on a home network reachable from a Lens without
port forwarding or a cloud relay.

**What's inside**
- `so101_bridge.py` — USB bridge to the SO-101 servos
- `bridge/` — the trusted local WSS helper and one-time pairing (`local_wss_helper.py`), plus the arm's kinematics (`so101_kinematics.urdf`)
- `assembly.html` · `calibration.html` · `index.html` + `src/` — Vite web tools (three.js + `urdf-loader`) for the guided assembly animation and calibration
- `public/` — assembly meshes (`.glb`), URDFs, and annotated step sequences
- `docs/` — assembly, calibration, and real-arm setup guides

> This folder is the helper/walkthrough, not a Lens Studio project — the SO-101 Toolbox Lens
> itself is installed from the [Lens link](https://www.spectacles.com/lens/f3862663be534dcaa8518858c9a2bbe1?type=SNAPCODE&metadata=01) above.

---

### specs-microduck

📁 [`specs-microduck/`](./specs-microduck) &nbsp;•&nbsp; 🔗 Upstream: [kgediya/specs-microduck](https://github.com/kgediya/specs-microduck)

Teleoperate a [**Pollen Robotics Micro Duck**](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
biped with your **bare hands**. Tilt your palm to drive, roll your wrist to steer, and fire
off pinch gestures — index to quack and open the beak, middle for a soccer kick, ring for a
360° roll-recovery, and a double-pinch to switch between walking legs and skating rollers.

Under the playful surface it's a careful bit of hand-tracking engineering: knuckle-anchored
orientation vectors to kill pinch jitter, Schmitt-trigger hysteresis and adaptive low-pass
smoothing on the input, and acceleration-ramp limiting feeding a **MuJoCo** reinforcement-
learning locomotion policy. An in-lens HUD shows speed, turn rate, live pitch/roll, ping
latency, and a palm-attached steering compass; gesture packets stream over a **WebSocket**
relay at 30–50 Hz.

**What's inside**
- `Micro Duck Proto/` — the Lens Studio project (`Micro Duck Proto.esproj`), TypeScript + Spectacles Interaction Kit hand tracking
- `bridge.py` — a zero-dependency (stdlib-only) Python WebSocket relay between the Spectacles and the simulator
- `simulator-integration/` — `setup_simulator.py` clones Pollen's [Micro Duck simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator) and injects the Spectacles controller source (`spectacles.js`)
- `simulate_gestures.py` — replays synthetic gestures so you can drive the sim without the glasses

> No glasses handy? Run `bridge.py` alongside `simulate_gestures.py` against the simulator to exercise the full control path from your keyboard.

---

### SpecsGrip-spectacles-2-tesollo

📁 [`SpecsGrip-spectacles-2-tesollo/`](./SpecsGrip-spectacles-2-tesollo) &nbsp;•&nbsp; 🔗 Upstream: [amirmohideen/SpecsGrip](https://github.com/amirmohideen/SpecsGrip)

Control all 20 joints of a [**Tesollo Delto DG-5F**](https://www.tesollo.com/) robot hand
with your **bare hand**. The Lens measures every finger joint from Spectacles hand
tracking — curl, spread, and thumb opposition — and streams the raw angles at 60 Hz to a
small bridge on a Windows PC, which drives the hand in real time through Tesollo's own SDK.

The interesting split is where the decisions live. The Lens only measures; every opinion —
scaling, joint limits, smoothing, speed caps — sits in one `config.json` on the PC, so
retuning the robot is a two-second bridge restart instead of a Lens rebuild. Safety runs in
a fixed order every tick (scale → clamp to limits taken from Tesollo's 100 factory poses →
smooth → speed-limit), the bridge starts disarmed, and the hand freezes in place if the
signal drops. Left hands are mirrored in the Lens by flipping the palm frame, so either
hand drives the right-handed robot the same way.

**What's inside**
- `SpecsGrip.esproj` — the Lens Studio project; `Assets/Scripts/HandBridge.ts` does the measuring and streaming
- `bridge/` — zero-dependency (stdlib-only) Python bridge: WebSocket server, retargeting and safety pipeline, and `ctypes` bindings to Tesollo's `DGSDK.dll`
- `bridge/test_sender.py` · `netcheck.py` · `connecttest.py` — synthetic hand poses, a network preflight, and a read-only gripper check

> No robot handy? `py bridge.py --dry-run --auto-arm` plus `py test_sender.py --wave` runs the whole pipeline without touching the hand. The bridge is Windows-only for now — it drives the `DGSDK.dll` that ships with Tesollo's DGManager.

---

## Getting Started

**These projects use [Git LFS](https://git-lfs.com/)** for 3D assets, textures, meshes, demo
media, and robot firmware. Install it *before* cloning, or the large files will arrive as
text pointers instead of real content:

```bash
git lfs install
git clone https://github.com/agrancini-sc/specs-robots-1fficialAR.git
```

Already cloned without it? Recover with:

```bash
git lfs install && git lfs pull
```

**Only want one project?** A full clone pulls roughly **650 MB** of LFS content, most of it
the Vector firmware images. Skip the download and fetch just the folder you need:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/agrancini-sc/specs-robots-1fficialAR.git
cd specs-robots-1fficialAR
git lfs pull --include="spectacles-reachy-mini/**"   # ← swap for the project you want
```

Then open the project you want:

- **Lens side** — open the `.esproj` (or the `lens-studio/` folder) in
  [Lens Studio](https://ar.snap.com/lens-studio), then push to your Spectacles.
- **Robot side** — follow that project's own README for the Python app, container, or
  bridge. Each project's setup steps are authoritative; this file only points you at them.

> Each project has its own README with detailed setup, architecture notes, and
> customization guides. Start there.

## Contributors

All credit for this work belongs to its original authors. This repo aggregates; it does not
claim authorship.

**Spectacles-2-Unitree** — © 2025 Patrick Rose, Vincent Trastour, Arthur Baney, and
Alessio Grancini. Committed and submitted upstream by
[**@TastyDucks**](https://github.com/TastyDucks). Includes Python, STL, and URDF files
derived from [Unitree's `avp_teleoperate`](https://github.com/unitreerobotics/avp_teleoperate)
(Apache 2.0) — see the project's
[`ATTRIBUTION.md`](./Spectacles-2-Unitree/ATTRIBUTION.md) for the full third-party list.

**spectacles-reachy-mini** — © 2026 [**@V4C38**](https://github.com/V4C38).

**spectacles-dimensional-os** — © 2026 [**@V4C38**](https://github.com/V4C38) and the
`spectacles-dimensional-os` contributors. Built on
[Dimensional OS](https://github.com/dimensionalOS/dimos).

**VectAR-Airhokey** — © 2026 **Pavlo Tkachenko**
([**@PtPavloTkachenko**](https://github.com/PtPavloTkachenko)). Robot onboarding builds on
[wire-pod](https://github.com/kercre123/wire-pod) by
[@kercre123](https://github.com/kercre123); the AR Vector mesh comes from Anki's
`anki_vector` SDK (Apache 2.0). See the project's
[`THIRD_PARTY_NOTICES.md`](./VectAR-Airhokey/THIRD_PARTY_NOTICES.md) for the full list.

**so101-helper** — © 2026 **Armand Sumo** ([**@a-sumo**](https://github.com/a-sumo)),
released under Apache 2.0. See the project's [`LICENSE`](./so101-helper/LICENSE) and
[`NOTICE`](./so101-helper/NOTICE).

**specs-microduck** — © 2026 **Krunal Gediya**
([**@kgediya**](https://github.com/kgediya)). The Micro Duck simulator is by
[Pollen Robotics](https://www.pollen-robotics.com/), hosted on
[Hugging Face Spaces](https://huggingface.co/spaces/pollen-robotics/microduck-simulator);
physics by [MuJoCo](https://github.com/google-deepmind/mujoco).

**SpecsGrip-spectacles-2-tesollo** — © 2026 **Amir Mohideen Basheer Khan**
([**@amirmohideen**](https://github.com/amirmohideen)). Drives the robot through Tesollo's
DGSDK, which ships with Tesollo's DGManager and is not included here.

Robot platforms referenced here are products of
[Unitree Robotics](https://www.unitree.com/),
[Pollen Robotics](https://www.pollen-robotics.com/),
[Hugging Face](https://huggingface.co/), [Tesollo](https://www.tesollo.com/), and Anki /
Digital Dream Labs, and are trademarks of their respective owners.

## Licenses

Most projects in this repo are **MIT licensed**; **so101-helper** is **Apache 2.0**. Each
folder keeps its own `LICENSE` file with the original copyright notice intact:

| Project | License |
|---|---|
| [Spectacles-2-Unitree](./Spectacles-2-Unitree/LICENSE) | MIT |
| [spectacles-reachy-mini](./spectacles-reachy-mini/LICENSE) | MIT |
| [spectacles-dimensional-os](./spectacles-dimensional-os/LICENSE) | MIT |
| [VectAR-Airhokey](./VectAR-Airhokey/LICENSE) | MIT |
| [so101-helper](./so101-helper/LICENSE) | Apache 2.0 |
| [specs-microduck](./specs-microduck/LICENSE) | MIT |
| [SpecsGrip-spectacles-2-tesollo](./SpecsGrip-spectacles-2-tesollo/LICENSE) | MIT |

Third-party components retain their own licenses (Apache 2.0, BSD, LGPL v3, and others) as
documented within each project.

## Contributing

Know of a Spectacles robotics project that belongs here? Open an issue with a link. If it's
your own project and you'd rather it **not** be mirrored, open an issue and it will be
removed.
