import {SIK} from "SpectaclesInteractionKit.lspkg/SIK"
import {BaseHand} from "SpectaclesInteractionKit.lspkg/Providers/HandInputData/BaseHand"
import {HandType} from "SpectaclesInteractionKit.lspkg/Providers/HandInputData/HandType"

/**
 * Streams Spectacles hand tracking to the Delto DG-5F bridge over WebSocket.
 *
 * This script is deliberately "dumb": it measures the operator's hand in
 * degrees and sends those raw numbers. All scaling, joint limits, smoothing
 * and rate limiting live in bridge/config.json on the PC, so retuning the
 * robot is a file edit and a 2s restart instead of a Lens rebuild + push.
 *
 * Wire format (one JSON text frame per tick):
 *   {"t":<ms>,"tracked":<bool>,"hand":"right","f":[[4],[4],[4],[4],[4]]}
 * fingers are thumb, index, middle, ring, pinky. Within a finger:
 *   thumb  -> [abduction, opposition, mcp flexion, ip flexion]
 *   others -> [abduction, mcp flexion, pip flexion, dip flexion]
 *
 * Assign `statusText` to see connection state on-device. The Logger panel is
 * only available while tethered to Lens Studio, so without the HUD a failure
 * on the glasses is invisible.
 */

const RAD2DEG = 180.0 / Math.PI

function angleBetween(a: vec3, b: vec3): number {
  const la = a.length
  const lb = b.length
  if (la < 1e-5 || lb < 1e-5) {
    return 0
  }
  let c = a.dot(b) / (la * lb)
  if (c > 1) c = 1
  if (c < -1) c = -1
  return Math.acos(c) * RAD2DEG
}

/** Angle from `from` to `to` measured about `axis`, signed by the right-hand rule. */
function signedAngleAbout(from: vec3, to: vec3, axis: vec3): number {
  const mag = angleBetween(from, to)
  return from.cross(to).dot(axis) < 0 ? -mag : mag
}

/** Component of `v` lying in the plane whose normal is the unit vector `n`. */
function projectOntoPlane(v: vec3, n: vec3): vec3 {
  return v.sub(n.uniformScale(v.dot(n)))
}

const COLOR_OK = new vec4(0.2, 0.9, 0.4, 1.0)
const COLOR_WARN = new vec4(1.0, 0.75, 0.2, 1.0)
const COLOR_BAD = new vec4(1.0, 0.35, 0.35, 1.0)

@component
export class HandBridge extends BaseScriptComponent {
  @input
  @hint("Bridge address(es). Comma-separate several and the Lens cycles through them on each retry -- useful because the network can hand the PC a new IP every so often. Run 'py netcheck.py' on the PC for the current one.")
  serverUrl: string = "ws://192.168.7.148:8765, ws://192.168.124.7:8765"

  @input
  @widget(new ComboBoxWidget([new ComboBoxItem("right"), new ComboBoxItem("left")]))
  @hint("Which of YOUR hands drives the robot. The robot is a DG-5F-R (right hand), so 'right' maps straight across; 'left' is mirrored automatically.")
  handToTrack: string = "right"

  @input
  @hint("Tick to follow whichever hand is visible, switching automatically. The hand above is only the starting preference. Left-hand input is mirrored so the robot moves the same way either way.")
  autoSwitchHand: boolean = false

  @input
  @hint("Send rate in Hz. 60 matches the bridge's default control loop.")
  sendRateHz: number = 60

  @input
  @allowUndefined
  @hint("Optional but STRONGLY recommended: a Text component to show connection status on-device. Park it under the Camera so it is always visible.")
  statusText: Text

  @input
  @hint("Also print status to the Logger panel (only visible while tethered to Lens Studio).")
  debugLog: boolean = false

  private internetModule: InternetModule = require("LensStudio:InternetModule") as InternetModule
  private socket: WebSocket | null = null
  private rightHand: BaseHand | null = null
  private leftHand: BaseHand | null = null
  private activeHand: string = "right"

  private urls: string[] = []
  private urlIndex: number = 0
  private connected: boolean = false
  private connecting: boolean = false
  private nextRetryAt: number = 0
  private retryDelay: number = 1.0
  private lastSendAt: number = 0
  private lastLogAt: number = 0
  private lastHudAt: number = 0

  // --- diagnostics surfaced on the HUD ---
  private state: string = "STARTING"
  private attempts: number = 0
  private packetsSent: number = 0
  private lastError: string = "-"
  private lastCloseCode: number = 0
  private connectedAt: number = 0
  private moduleOk: boolean = false

  onAwake() {
    this.createEvent("OnStartEvent").bind(() => this.onStart())
    this.createEvent("UpdateEvent").bind(() => this.onUpdate())
    this.createEvent("OnDestroyEvent").bind(() => this.closeSocket())
  }

  private onStart() {
    // Fail loudly and visibly rather than throwing into the void.
    if (this.internetModule === undefined || this.internetModule === null) {
      this.state = "NO INTERNET MODULE"
      this.lastError = "require('LensStudio:InternetModule') returned nothing"
      this.renderHud(true)
      return
    }
    this.moduleOk = true

    // The network can reassign the PC's IP, and re-pushing a Lens just
    // to change one string is slow. Accept several and rotate on each retry.
    this.urls = this.serverUrl
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    if (this.urls.length === 0) {
      this.state = "NO URL SET"
      this.lastError = "Server Url is empty"
      this.renderHud(true)
      return
    }

    // Resolve both hands up front so switching is instant and cannot fail
    // mid-session.
    try {
      this.rightHand = SIK.HandInputData.getHand("right" as HandType)
      this.leftHand = SIK.HandInputData.getHand("left" as HandType)
      this.activeHand = this.handToTrack === "left" ? "left" : "right"
    } catch (e) {
      this.state = "HAND INIT FAILED"
      this.lastError = `${e}`
      this.renderHud(true)
      return
    }

    print(`[HandBridge] tracking ${this.handToTrack} hand -> ${this.urls.join(" | ")}`)
    this.renderHud(true)
    this.connect()
  }

  private currentUrl(): string {
    return this.urls[this.urlIndex % this.urls.length]
  }

  private handObject(which: string): BaseHand | null {
    return which === "left" ? this.leftHand : this.rightHand
  }

  /**
   * Decides which hand is driving this frame.
   *
   * With autoSwitchHand off this is just the Inspector choice. With it on we
   * keep the current hand while it stays visible -- switching on every frame
   * a hand flickers out would make the robot jitter between two poses -- and
   * only hand over when the current one is gone and the other is present.
   */
  private pickHand(): BaseHand | null {
    const current = this.handObject(this.activeHand)
    if (!this.autoSwitchHand) {
      this.activeHand = this.handToTrack === "left" ? "left" : "right"
      return this.handObject(this.activeHand)
    }
    if (current !== null && current.isTracked()) {
      return current
    }
    const other = this.activeHand === "left" ? "right" : "left"
    const otherObj = this.handObject(other)
    if (otherObj !== null && otherObj.isTracked()) {
      this.activeHand = other
      return otherObj
    }
    return current
  }

  // ---- UI hooks ------------------------------------------------------
  /**
   * Wire to a UIKit Switch's "On Value Changed Callbacks". The switch passes
   * its value (0..1) and fires on every frame while the knob animates, so the
   * state is set from that value instead of flipped -- a plain flip would
   * toggle a dozen times per press. Called with no argument it just flips.
   */
  public toggleAutoSwitchHand(value?: number | boolean) {
    const on = this.resolveToggle(value, this.autoSwitchHand)
    if (on === this.autoSwitchHand) {
      return
    }
    this.autoSwitchHand = on
    print(`[HandBridge] auto switch hand ${on ? "on" : "off"}`)
    this.renderHud(true)
  }

  /** Same wiring as toggleAutoSwitchHand. Off -> left hand, on -> right hand. */
  public toggleHandToTrack(value?: number | boolean) {
    const on = this.resolveToggle(value, this.handToTrack === "right")
    const hand = on ? "right" : "left"
    if (hand === this.handToTrack) {
      return
    }
    this.handToTrack = hand
    // Take effect now rather than on the next send; with autoSwitchHand on
    // this becomes the hand we hold onto while it stays visible.
    this.activeHand = hand
    print(`[HandBridge] tracking ${hand} hand`)
    this.renderHud(true)
  }

  private resolveToggle(value: number | boolean | undefined, current: boolean): boolean {
    if (typeof value === "boolean") {
      return value
    }
    if (typeof value === "number") {
      return value > 0.5
    }
    return !current
  }

  // ---- networking ----------------------------------------------------
  private connect() {
    if (this.connecting || this.connected || !this.moduleOk) {
      return
    }
    this.connecting = true
    this.attempts += 1
    this.state = "CONNECTING"
    const url = this.currentUrl()
    this.renderHud(true)
    print(`[HandBridge] connect attempt ${this.attempts} -> ${url}`)

    try {
      const sock = this.internetModule.createWebSocket(url)
      sock.binaryType = "blob"
      this.socket = sock

      sock.onopen = () => {
        this.connected = true
        this.connecting = false
        this.retryDelay = 1.0
        this.connectedAt = getTime()
        this.state = "CONNECTED"
        this.lastError = "-"
        this.renderHud(true)
        print("[HandBridge] connected")
      }
      sock.onclose = (event: WebSocketCloseEvent) => {
        this.connected = false
        this.connecting = false
        this.lastCloseCode = event.code
        // 1006 = abnormal close: no close frame. Almost always "never actually
        // reached the server" -- wrong IP, firewall, or client isolation.
        this.lastError = event.code === 1006
          ? "1006 abnormal: never reached the PC (IP? firewall? Wi-Fi client isolation?)"
          : `closed, code ${event.code}`
        this.state = "CLOSED"
        this.scheduleRetry()
        this.renderHud(true)
        print(`[HandBridge] closed, code ${event.code}`)
      }
      sock.onerror = () => {
        this.connected = false
        this.connecting = false
        this.state = "SOCKET ERROR"
        this.lastError = "onerror -- no route to the PC, or ws:// refused"
        this.scheduleRetry()
        this.renderHud(true)
        print("[HandBridge] socket error")
      }
    } catch (e) {
      this.connecting = false
      this.state = "CREATE FAILED"
      // A synchronous throw usually means the URL scheme was rejected outright.
      this.lastError = `createWebSocket threw: ${e}`
      this.scheduleRetry()
      this.renderHud(true)
      print(`[HandBridge] createWebSocket threw: ${e}`)
    }
  }

  private scheduleRetry() {
    this.socket = null
    // Move to the next candidate URL so a stale IP cannot wedge us forever.
    if (this.urls.length > 1) {
      this.urlIndex = (this.urlIndex + 1) % this.urls.length
    }
    this.nextRetryAt = getTime() + this.retryDelay
    // back off to at most 5s so a sleeping PC does not spam the log
    this.retryDelay = Math.min(this.retryDelay * 1.6, 5.0)
  }

  private closeSocket() {
    if (this.socket !== null) {
      try {
        this.socket.close()
      } catch (e) {
        // already gone
      }
      this.socket = null
    }
    this.connected = false
  }

  // ---- HUD -----------------------------------------------------------
  private renderHud(force: boolean) {
    if (this.statusText === undefined || this.statusText === null) {
      return
    }
    const now = getTime()
    if (!force && now - this.lastHudAt < 0.25) {
      return
    }
    this.lastHudAt = now

    const activeObj = this.handObject(this.activeHand)
    const tracked = activeObj !== null && activeObj.isTracked()
    let hint = ""
    if (this.state === "CONNECTED") {
      hint = tracked ? "streaming" : "connected, but hand not visible"
    } else if (this.state === "CONNECTING") {
      hint = "waiting for the PC to answer..."
    } else {
      hint = `retry in ${Math.max(0, this.nextRetryAt - now).toFixed(1)}s`
    }

    const uptime = this.connected ? `${(now - this.connectedAt).toFixed(0)}s` : "-"

    const urlLabel = this.urls.length > 1
      ? `${this.currentUrl()}  [${(this.urlIndex % this.urls.length) + 1}/${this.urls.length}]`
      : (this.urls.length === 1 ? this.currentUrl() : this.serverUrl)

    this.statusText.text =
      `DG-5F BRIDGE\n` +
      `state : ${this.state}\n` +
      `url   : ${urlLabel}\n` +
      `try   : ${this.attempts}   up: ${uptime}\n` +
      `sent  : ${this.packetsSent}\n` +
      `hand  : ${this.activeHand}${this.autoSwitchHand ? " (auto)" : ""}` +
      `${this.activeHand === "left" ? " mirrored" : ""} ` +
      `${tracked ? "TRACKED" : "not visible"}\n` +
      `note  : ${hint}\n` +
      `err   : ${this.lastError}`

    try {
      const c = this.state === "CONNECTED"
        ? (tracked ? COLOR_OK : COLOR_WARN)
        : (this.state === "CONNECTING" ? COLOR_WARN : COLOR_BAD)
      this.statusText.textFill.color = c
    } catch (e) {
      // some Text configurations do not expose textFill; the text still updates
    }
  }

  // ---- per-frame -----------------------------------------------------
  private onUpdate() {
    if (!this.moduleOk) {
      return
    }
    const now = getTime()

    if (!this.connected) {
      this.renderHud(false)
      if (!this.connecting && now >= this.nextRetryAt) {
        this.connect()
      }
      return
    }

    const minInterval = 1.0 / Math.max(1, this.sendRateHz)
    if (now - this.lastSendAt < minInterval) {
      return
    }
    this.lastSendAt = now

    const hand = this.pickHand()
    if (hand === null) {
      return
    }

    const tracked = hand.isTracked()
    const fingers = tracked ? this.measure(hand, this.activeHand === "left") : [
      [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]
    ]

    const payload = {
      t: Math.round(now * 1000),
      tracked: tracked,
      hand: this.activeHand,
      f: fingers
    }

    try {
      this.socket.send(JSON.stringify(payload))
      this.packetsSent += 1
    } catch (e) {
      this.connected = false
      this.state = "SEND FAILED"
      this.lastError = `${e}`
      this.scheduleRetry()
    }

    this.renderHud(false)

    if (this.debugLog && now - this.lastLogAt > 1.0) {
      this.lastLogAt = now
      if (tracked) {
        const fmt = (a: number[]) => a.map((v) => v.toFixed(0)).join(",")
        print(`[HandBridge] T[${fmt(fingers[0])}] I[${fmt(fingers[1])}] ` +
              `M[${fmt(fingers[2])}] R[${fmt(fingers[3])}] P[${fmt(fingers[4])}]`)
      } else {
        print("[HandBridge] hand not tracked")
      }
    }
  }

  // ---- measurement ---------------------------------------------------
  /**
   * Builds a palm-local frame, then reads each finger against it.
   *
   * forward : wrist -> middle knuckle (down the palm)
   * side    : pinky knuckle -> index knuckle, orthogonalised
   * normal  : palm normal, forward x side
   *
   * Flexion angles are unsigned angles between consecutive bone vectors,
   * which is robust because fingers only bend one way. Abduction and thumb
   * opposition are signed about the palm frame, so their sign depends on
   * handedness -- if a joint drives the wrong way on the robot, swap that
   * joint's two "out" values in bridge/config.json rather than editing this.
   */
  private measure(hand: BaseHand, isLeft: boolean): number[][] {
    const wrist = hand.wrist.position
    const idxK = hand.indexKnuckle.position
    const midK = hand.middleKnuckle.position
    const pkyK = hand.pinkyKnuckle.position

    const forward = midK.sub(wrist).normalize()
    const sideRaw = idxK.sub(pkyK).normalize()
    let normal = forward.cross(sideRaw)
    if (normal.length < 1e-5) {
      return [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    }
    normal = normal.normalize()
    // A left hand is the mirror image of a right one, so forward x side points
    // out of the opposite face of the palm. Left as-is, every signed quantity
    // (abduction, thumb opposition) would come out negated and those five
    // joints would drive backwards. Flipping the normal restores a consistent
    // chirality, so either hand produces the same motion on the right-handed
    // robot and config.json needs no per-hand tuning.
    if (isLeft) {
      normal = normal.uniformScale(-1)
    }
    const side = normal.cross(forward).normalize()

    // --- thumb ---
    const tCmc = hand.thumbBaseJoint.position
    const tMcp = hand.thumbKnuckle.position
    const tIp = hand.thumbMidJoint.position
    const tTip = hand.thumbTip.position

    const tMeta = tMcp.sub(tCmc)
    const tProx = tIp.sub(tMcp)
    const tDist = tTip.sub(tIp)

    // Opposition: rotate the thumb metacarpal about the palm's forward axis.
    // ~0 when the thumb lies out to the side, ~90 when swung across the palm.
    const tMetaInPlane = projectOntoPlane(tMeta, forward)
    const opposition = Math.abs(signedAngleAbout(side, tMetaInPlane, forward))
    // Abduction: how far the thumb opens within the palm plane.
    const tMetaOnPalm = projectOntoPlane(tMeta, normal)
    const thumbAbd = signedAngleAbout(forward, tMetaOnPalm, normal)

    const thumb = [
      thumbAbd,
      opposition,
      angleBetween(tMeta, tProx),
      angleBetween(tProx, tDist)
    ]

    return [
      thumb,
      this.measureFinger(hand.indexKnuckle.position, hand.indexMidJoint.position,
                         hand.indexUpperJoint.position, hand.indexTip.position,
                         wrist, forward, normal),
      this.measureFinger(hand.middleKnuckle.position, hand.middleMidJoint.position,
                         hand.middleUpperJoint.position, hand.middleTip.position,
                         wrist, forward, normal),
      this.measureFinger(hand.ringKnuckle.position, hand.ringMidJoint.position,
                         hand.ringUpperJoint.position, hand.ringTip.position,
                         wrist, forward, normal),
      this.measureFinger(hand.pinkyKnuckle.position, hand.pinkyMidJoint.position,
                         hand.pinkyUpperJoint.position, hand.pinkyTip.position,
                         wrist, forward, normal)
    ]
  }

  private measureFinger(mcp: vec3, pip: vec3, dip: vec3, tip: vec3,
                        wrist: vec3, forward: vec3, normal: vec3): number[] {
    const meta = mcp.sub(wrist)
    const prox = pip.sub(mcp)
    const mid = dip.sub(pip)
    const dist = tip.sub(dip)

    const proxOnPalm = projectOntoPlane(prox, normal)
    const abduction = signedAngleAbout(forward, proxOnPalm, normal)

    return [
      abduction,
      angleBetween(meta, prox),
      angleBetween(prox, mid),
      angleBetween(mid, dist)
    ]
  }
}
