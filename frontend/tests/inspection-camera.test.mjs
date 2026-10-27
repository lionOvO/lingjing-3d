import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import {PerspectiveCamera,MOUSE,Vector3} from 'three'
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js'
const source=fs.readFileSync(new URL('../src/utils/inspectionCamera.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {inspectionDistance,configureInspectionControls}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'))

test('portrait and wide canvases fit the full model sphere with inspection margin',()=>{
 for(const aspect of [.35,.8,1,1.8,3]){
  const radius=2,vertical=42*Math.PI/360,horizontal=Math.atan(Math.tan(vertical)*aspect)
  const distance=inspectionDistance(radius,42,aspect)
  assert.ok(distance*Math.sin(Math.min(vertical,horizontal))>=radius*1.079)
 }
 const oldDistance=2/Math.tan(42*Math.PI/360)*1.18*Math.hypot(1,.58,1)
 assert.ok(inspectionDistance(2,42,1.5)<oldDistance*.75)
})

// Real OrbitControls with a local EventTarget; no browser or renderer required.
class Canvas extends EventTarget{
 style={};clientWidth=800;clientHeight=600
 root=new EventTarget()
 getRootNode(){return this.root}
 setPointerCapture(){}
 releasePointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:800,height:600}}
}
function pointer(canvas,type,button,x,y,shiftKey=false){
 const event=new Event(type,{cancelable:true})
 Object.assign(event,{pointerId:1,pointerType:'mouse',button,clientX:x,clientY:y,pageX:x,pageY:y,shiftKey,ctrlKey:false,metaKey:false})
 canvas.dispatchEvent(event)
}
test('rotate, right/middle pan, Shift pan and wheel zoom work consecutively without changing mode',()=>{
 const canvas=new Canvas(),camera=new PerspectiveCamera(42,4/3,.01,100)
 camera.position.set(3,2,4)
 const controls=new OrbitControls(camera,canvas)
 configureInspectionControls(controls,MOUSE)
 const drag=(button,shift=false)=>{pointer(canvas,'pointerdown',button,300,250,shift);pointer(canvas,'pointermove',button,370,280,shift);pointer(canvas,'pointerup',button,370,280,shift)}
 const initial=camera.position.clone()
 drag(0)
 assert.ok(camera.position.distanceTo(initial)>.1)
 assert.ok(controls.target.length()<1e-8,'rotation keeps the inspection center')
 for(const [button,shift] of [[2,false],[1,false],[0,true]]){
  const target=controls.target.clone(),offset=camera.position.clone().sub(target)
  drag(button,shift)
  assert.ok(controls.target.distanceTo(target)>.1,'pan moves the inspection center')
  assert.ok(camera.position.clone().sub(controls.target).distanceTo(offset)<1e-8,'pan preserves viewing direction')
 }
 const distance=camera.position.distanceTo(controls.target),wheel=new Event('wheel',{cancelable:true})
 Object.assign(wheel,{deltaY:-100,deltaMode:0,clientX:400,clientY:300,ctrlKey:false})
 canvas.dispatchEvent(wheel)
 assert.ok(camera.position.distanceTo(controls.target)<distance)
 const center=controls.target.clone();drag(0)
 assert.ok(controls.target.distanceTo(center)<1e-8,'rotation remains available after pan and zoom')
 controls.dispose()
})
