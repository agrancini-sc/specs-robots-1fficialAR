/**
 * ToggleSetActive
 *
 * Drop-in for a UIKit Switch / toggle's "On Value Changed" callback:
 *   Script Component -> this component
 *   Function Name    -> setActiveFromValue
 *
 * Switch ON  -> the assigned target object(s) are enabled.
 * Switch OFF -> they're disabled. (Flip with `invert`.)
 *
 * Use ONE component per switch — the callback only passes the value, not which switch fired,
 * so each switch needs its own ToggleSetActive with its own target(s).
 */

@component
export class ToggleSetActive extends BaseScriptComponent {
  @input
  @hint("Object(s) enabled when the switch is ON (disabled when OFF).")
  targets: SceneObject[] = []

  @input
  @hint("Invert: enable on OFF instead of ON.")
  invert: boolean = false

  /** Wire the switch's "On Value Changed" callback here (Function Name = setActiveFromValue). */
  setActiveFromValue(value: number): void {
    const on = this.invert ? !value : !!value
    for (const t of this.targets) {
      if (t) t.enabled = on
    }
  }
}
