import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import {computed,nextTick,ref,watch,effectScope} from 'vue'

const component=fs.readFileSync(new URL('../src/components/ImagePreparation.vue',import.meta.url),'utf8')
const script=component.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const compiled=ts.transpileModule(script,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const utility=ts.transpileModule(fs.readFileSync(new URL('../src/utils/referencePreparation.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {fitReference,sharpenReference}=await import('data:text/javascript;base64,'+Buffer.from(utility).toString('base64'))

test('crop controls stay interactive, decoding is reused and stale exports cannot replace the latest crop',async()=>{
 const globals=['Image','document','window','requestAnimationFrame','cancelAnimationFrame']
 const previous=Object.fromEntries(globals.map(key=>[key,globalThis[key]]))
 const timers=new Map(),frames=new Map(),exports=[]
 let serial=0,decodes=0,cleanup,holdExport=false
 class Canvas {
  width=0;height=0
  getContext(){return {drawImage(){},fillRect(){},getImageData:(x,y,w,h)=>({data:new Uint8ClampedArray(w*h*4).fill(255)}),putImageData(){}}}
  toBlob(callback){const blob=new Blob([JSON.stringify({width:this.width,height:this.height})],{type:'image/png'});if(holdExport)exports.push(()=>callback(blob));else callback(blob)}
 }
 globalThis.Image=class {width=200;height=100;async decode(){decodes++}}
 globalThis.document={createElement:()=>new Canvas()}
 globalThis.window={setTimeout:fn=>{timers.set(++serial,fn);return serial},clearTimeout:id=>timers.delete(id)}
 globalThis.requestAnimationFrame=fn=>{frames.set(++serial,fn);return serial}
 globalThis.cancelAnimationFrame=id=>frames.delete(id)
 const scope=effectScope()
 try{
  const api={get:async()=>({data:{configured:false}}),post:async()=>({data:{background_kind:'simple',background_color:'#808080',subject_bounds:null,warnings:[]}})}
  const create=new Function('computed','nextTick','onUnmounted','ref','watch','api','fitReference','sharpenReference','defineProps','withDefaults','defineEmits',compiled+'\nreturn {x,width,margin,prepared,rendering,controlsLocked,working,previewCanvas,livePreview,render,setSource,details,schedule}')
  const file=new File(['test'],'source.png',{type:'image/png'})
  const state=scope.run(()=>create(computed,nextTick,fn=>cleanup=fn,ref,watch,api,fitReference,sharpenReference,()=>({file}), (props,defaults)=>({...defaults,...props}),()=>()=>{}))
  const settle=async()=>{for(let i=0;i<5;i++)await Promise.resolve();await nextTick()}
  await settle()
  state.previewCanvas.value=new Canvas()
  state.x.value=15;await nextTick()
  assert.equal(state.rendering.value,true)
  assert.equal(state.working.value,true,'submission remains blocked until the current PNG is ready')
  assert.equal(state.controlsLocked.value,false,'exporting must not disable sliders')
  for(let i=16;i<=30;i++){state.x.value=i;await nextTick()}
  assert.equal(timers.size,1,'rapid input coalesces into one final export')
  assert.equal(frames.size,1,'rapid input coalesces preview work into one animation frame')
  const draw=[...frames.values()][0];frames.clear();draw();await settle()
  assert.equal(state.livePreview.value,true)
  await state.render()
  assert.equal(decodes,1,'preview and final export share the decoded source')
  assert.ok(state.prepared.value instanceof File)
  assert.deepEqual(JSON.parse(await state.prepared.value.text()),{width:1024,height:1024})
  assert.equal(state.details().source_bounds.left,60,'export uses the last selected crop in original image pixels')
  assert.equal(state.rendering.value,false)
  assert.equal(state.livePreview.value,false)

  holdExport=true
  state.x.value=40;await nextTick()
  const oldRender=state.render();await settle()
  assert.equal(exports.length,1)
  state.x.value=50;await nextTick()
  exports.shift()();await oldRender
  assert.equal(state.prepared.value,null,'stale asynchronous PNG must never be submitted')
  assert.equal(state.rendering.value,true)
  holdExport=false;await state.render()
  assert.equal(state.details().source_bounds.left,100)
  assert.equal(decodes,1)

  state.setSource(new File(['replacement'],'replacement.png',{type:'image/png'}));await state.render()
  assert.equal(decodes,2,'a changed source invalidates the decode cache')
  cleanup()
  assert.equal(timers.size,0)
  assert.equal(frames.size,0)
 }finally{
  scope.stop()
  for(const key of globals){if(previous[key]===undefined)delete globalThis[key];else globalThis[key]=previous[key]}
 }
})
