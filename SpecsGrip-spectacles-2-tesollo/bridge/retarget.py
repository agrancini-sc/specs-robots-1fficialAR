"""
Human hand angles -> DG-5F joint targets.

The lens sends raw, physically meaningful human measurements (per-finger
flexion + abduction in degrees). Everything opinionated -- scaling, limits,
smoothing, slew -- happens here, so retuning is a config edit and a restart
rather than a Lens rebuild.

Safety ordering matters and is applied in this order:
    map -> hard clamp -> EMA smooth -> slew limit
Clamping before smoothing means a wild input can never pull the smoothed value
outside the safe band, and the slew limit is applied last so it is the final
authority on how fast a joint may move.
"""

N_JOINTS = 20


def _lerp_map(v, in_lo, in_hi, out_lo, out_hi):
    if in_hi == in_lo:
        return out_lo
    t = (v - in_lo) / (in_hi - in_lo)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return out_lo + t * (out_hi - out_lo)


class Retargeter:
    def __init__(self, cfg: dict):
        joints = cfg["joints"]
        if len(joints) != N_JOINTS:
            raise ValueError(f"config must define {N_JOINTS} joints, got {len(joints)}")

        self.names = [j["name"] for j in joints]
        self.in_lo = [float(j["in"][0]) for j in joints]
        self.in_hi = [float(j["in"][1]) for j in joints]
        self.out_lo = [float(j["out"][0]) for j in joints]
        self.out_hi = [float(j["out"][1]) for j in joints]
        # hard limits are stored lo/hi normalised so out[] may be inverted
        self.hard_lo = [float(min(j["hard"])) for j in joints]
        self.hard_hi = [float(max(j["hard"])) for j in joints]

        ctrl = cfg["control"]
        self.alpha = float(ctrl["smoothing_alpha"])
        self.max_dps = float(ctrl["max_deg_per_sec"])

        self.smoothed = [0.0] * N_JOINTS
        self.commanded = list(float(v) for v in ctrl["neutral_pose_deg"])
        self._primed = False

    def reset_to(self, pose):
        self.smoothed = [float(v) for v in pose]
        self.commanded = [float(v) for v in pose]
        self._primed = True

    def map_only(self, human_deg):
        """Map + hard clamp, no temporal filtering. Used for previewing a pose."""
        out = [0.0] * N_JOINTS
        for i in range(N_JOINTS):
            v = _lerp_map(float(human_deg[i]), self.in_lo[i], self.in_hi[i],
                          self.out_lo[i], self.out_hi[i])
            if v < self.hard_lo[i]:
                v = self.hard_lo[i]
            elif v > self.hard_hi[i]:
                v = self.hard_hi[i]
            out[i] = v
        return out

    def step(self, human_deg, dt: float):
        """One control tick. Returns the 20 joint degrees to command."""
        target = self.map_only(human_deg)

        if not self._primed:
            # Snap the filter to the first sample so the hand does not lurch
            # from neutral to the operator's pose on the first frame.
            self.smoothed = list(target)
            self._primed = True
        else:
            a = self.alpha
            for i in range(N_JOINTS):
                self.smoothed[i] += a * (target[i] - self.smoothed[i])

        max_step = self.max_dps * max(dt, 1e-4)
        for i in range(N_JOINTS):
            delta = self.smoothed[i] - self.commanded[i]
            if delta > max_step:
                delta = max_step
            elif delta < -max_step:
                delta = -max_step
            self.commanded[i] += delta

        return list(self.commanded)

    def hold(self):
        """Watchdog / tracking-lost path: keep the last commanded pose."""
        return list(self.commanded)
