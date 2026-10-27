import type { MOUSE } from 'three'
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

// Fit the bounding sphere to the narrower field of view, including portrait
// canvases. The camera offset must be a unit direction times this distance.
export function inspectionDistance(radius:number, verticalFov:number, aspect:number) {
  const vertical=verticalFov*Math.PI/360
  const horizontal=Math.atan(Math.tan(vertical)*Math.max(aspect,.01))
  return Math.max(radius/Math.sin(Math.min(vertical,horizontal))*1.08,.8)
}

export function configureInspectionControls(controls:OrbitControls, mouse:typeof MOUSE, panMode=false) {
  controls.enableRotate=true
  controls.enablePan=true
  controls.enableZoom=true
  controls.screenSpacePanning=true
  controls.mouseButtons.LEFT=panMode?mouse.PAN:mouse.ROTATE
  controls.mouseButtons.MIDDLE=mouse.PAN
  controls.mouseButtons.RIGHT=mouse.PAN
}
