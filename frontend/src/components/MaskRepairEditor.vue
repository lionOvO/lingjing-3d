<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref} from 'vue'
import {ElDialog} from 'element-plus'
import {Brush,Eraser,Hand,Undo2,Redo2,Minus,Plus,Maximize,Check} from 'lucide-vue-next'
import {paintForeground,type Bounds} from '../utils/referencePreparation'

const props=defineProps<{original:string;mask:string}>()
const emit=defineEmits<{cancel:[];save:[blob:Blob,bounds:Bounds]}>()
const canvas=ref<HTMLCanvasElement>(),viewport=ref<HTMLDivElement>()
const loading=ref(true),saving=ref(false),error=ref(''),tool=ref<'restore'|'erase'|'pan'>('restore')
const size=ref(12),shape=ref<'circle'|'square'>('circle'),guide=ref(true),space=ref(false)
const zoom=ref(1),imageWidth=ref(1),imageHeight=ref(1),fitted=ref(true)
const undoCount=ref(0),redoCount=ref(0),hover=ref<{x:number;y:number}|null>(null)
const surfaceStyle=computed(()=>({width:`${imageWidth.value*zoom.value}px`,height:`${imageHeight.value*zoom.value}px`}))
const cursorStyle=computed(()=>({left:`${hover.value?.x||0}px`,top:`${hover.value?.y||0}px`,width:`${size.value*zoom.value}px`,height:`${size.value*zoom.value}px`,borderRadius:shape.value==='circle'?'50%':'0'}))
let frame:ImageData,originalPixels:Uint8ClampedArray,last:{x:number;y:number}|null=null
let pan:{x:number;y:number;left:number;top:number}|null=null,activePointer:number|null=null,disposed=false,observer:ResizeObserver|undefined
// Whole-frame snapshots are capped at 64 MB (at least one stroke). Large inputs
// keep fewer steps rather than retaining hundreds of megabytes per gesture.
const undo:Uint8ClampedArray[]=[],redo:Uint8ClampedArray[]=[]
function counts(){undoCount.value=undo.length;redoCount.value=redo.length}
function snapshot(){undo.push(new Uint8ClampedArray(frame.data));redo.length=0;while(undo.length>1&&undo.length*frame.data.byteLength>64*1024*1024)undo.shift();counts()}
function history(forward=false){if(!frame||saving.value||activePointer!==null)return;const from=forward?redo:undo,to=forward?undo:redo;if(!from.length)return;to.push(new Uint8ClampedArray(frame.data));frame.data.set(from.pop()!);canvas.value!.getContext('2d')!.putImageData(frame,0,0);counts()}
function finish(event?:PointerEvent){if(event&&activePointer!==event.pointerId)return;last=null;pan=null;activePointer=null}
function locate(event:PointerEvent){const rect=canvas.value!.getBoundingClientRect();hover.value={x:event.clientX-rect.left,y:event.clientY-rect.top};return{x:(event.clientX-rect.left)/rect.width*imageWidth.value,y:(event.clientY-rect.top)/rect.height*imageHeight.value}}
function pointer(event:PointerEvent,start=false){
 if(loading.value||saving.value||!frame)return
 if(start){if(activePointer!==null||![0,1].includes(event.button))return;activePointer=event.pointerId;canvas.value!.setPointerCapture(event.pointerId)
  if(tool.value==='pan'||space.value||event.button===1){pan={x:event.clientX,y:event.clientY,left:viewport.value!.scrollLeft,top:viewport.value!.scrollTop};hover.value=null;return}
  snapshot()
 }else if(activePointer!==null&&activePointer!==event.pointerId)return
 if(pan){viewport.value!.scrollLeft=pan.left-(event.clientX-pan.x);viewport.value!.scrollTop=pan.top-(event.clientY-pan.y);return}
 const point=locate(event)
 if(activePointer===null)return
 const radius=Math.max(1,Math.min(200,Number(size.value)||1))/2,from=last||point
 paintForeground(frame.data,originalPixels,imageWidth.value,imageHeight.value,from,point,radius,tool.value==='restore',shape.value)
 const left=Math.max(0,Math.floor(Math.min(from.x,point.x)-radius-1)),top=Math.max(0,Math.floor(Math.min(from.y,point.y)-radius-1))
 const right=Math.min(imageWidth.value,Math.ceil(Math.max(from.x,point.x)+radius+1)),bottom=Math.min(imageHeight.value,Math.ceil(Math.max(from.y,point.y)+radius+1))
 if(right>left&&bottom>top)canvas.value!.getContext('2d')!.putImageData(frame,0,0,left,top,right-left,bottom-top)
 last=point
}
async function setZoom(value:number,anchor?:{x:number;y:number}){
 if(loading.value||activePointer!==null)return
 const view=viewport.value!,rect=canvas.value!.getBoundingClientRect(),vr=view.getBoundingClientRect()
 const at=anchor||{x:vr.left+view.clientWidth/2,y:vr.top+view.clientHeight/2}
 const point={x:(at.x-rect.left)/zoom.value,y:(at.y-rect.top)/zoom.value}
 fitted.value=false;zoom.value=Math.max(.02,Math.min(8,value));hover.value=null
 await nextTick();if(disposed||!canvas.value)return
 const after=canvas.value.getBoundingClientRect();view.scrollLeft+=after.left+point.x*zoom.value-at.x;view.scrollTop+=after.top+point.y*zoom.value-at.y
}
function fit(){if(!viewport.value||activePointer!==null)return;fitted.value=true;zoom.value=Math.max(.02,Math.min(1,(viewport.value.clientWidth-64)/imageWidth.value,(viewport.value.clientHeight-64)/imageHeight.value));hover.value=null}
function wheel(event:WheelEvent){if(!event.ctrlKey&&!event.metaKey)return;event.preventDefault();void setZoom(zoom.value*(event.deltaY<0?1.2:1/1.2),{x:event.clientX,y:event.clientY})}
function keydown(event:KeyboardEvent){
 if((event.target as HTMLElement)?.matches('input,select,textarea')||saving.value||loading.value)return
 const key=event.key.toLowerCase()
 if((event.ctrlKey||event.metaKey)&&key==='z'){event.preventDefault();history(event.shiftKey);return}
 if((event.ctrlKey||event.metaKey)&&key==='y'){event.preventDefault();history(true);return}
 if(key===' '){event.preventDefault();space.value=true}
 if(key==='b')tool.value='restore';if(key==='e')tool.value='erase';if(key==='h')tool.value='pan'
 if(key==='[')size.value=Math.max(1,size.value-1);if(key===']')size.value=Math.min(200,size.value+1)
}
function keyup(event:KeyboardEvent){if(event.key===' '){space.value=false;finish()}}
function blur(){space.value=false;finish();hover.value=null}
async function save(){
 if(loading.value||saving.value||activePointer!==null)return
 saving.value=true;error.value=''
 try{
  let left=imageWidth.value,top=imageHeight.value,right=0,bottom=0
  for(let row=0;row<imageHeight.value;row++)for(let col=0;col<imageWidth.value;col++)if(frame.data[(row*imageWidth.value+col)*4+3]>12){left=Math.min(left,col);top=Math.min(top,row);right=Math.max(right,col+1);bottom=Math.max(bottom,row+1)}
  if(right<=left||bottom<=top)throw new Error('主体已全部擦除，请撤销后再保存。')
  const blob=await new Promise<Blob>((resolve,reject)=>canvas.value!.toBlob(v=>v?resolve(v):reject(new Error('保存失败，请重试')),'image/png'))
  if(!disposed)emit('save',blob,{left,top,right,bottom})
 }catch(cause:any){error.value=cause.message}finally{saving.value=false}
}
onMounted(async()=>{
 window.addEventListener('keydown',keydown);window.addEventListener('keyup',keyup);window.addEventListener('blur',blur)
 try{
  const source=new Image(),mask=new Image();source.src=props.original;mask.src=props.mask
  await Promise.all([source.decode(),mask.decode()]);await nextTick()
  if(disposed)return
  if(source.width!==mask.width||source.height!==mask.height)throw new Error('图片尺寸不一致，请关闭后重新抠图。')
  const target=canvas.value!;target.width=imageWidth.value=source.width;target.height=imageHeight.value=source.height
  const ctx=target.getContext('2d')!;ctx.drawImage(source,0,0);originalPixels=ctx.getImageData(0,0,target.width,target.height).data
  ctx.clearRect(0,0,target.width,target.height);ctx.drawImage(mask,0,0);frame=ctx.getImageData(0,0,target.width,target.height)
  loading.value=false;await nextTick();fit()
  observer=new ResizeObserver(()=>{if(fitted.value)fit()});observer.observe(viewport.value!)
 }catch(cause:any){error.value=cause.message}
})
onBeforeUnmount(()=>{disposed=true;observer?.disconnect();window.removeEventListener('keydown',keydown);window.removeEventListener('keyup',keyup);window.removeEventListener('blur',blur);undo.length=0;redo.length=0})
</script>

<template>
 <ElDialog :model-value="true" title="精细修补抠图" class="mask-dialog" width="calc(100vw - 32px)" top="3vh" append-to-body :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving" @close="emit('cancel')">
  <div class="repair-workspace">
   <aside class="repair-tools" aria-label="修补工具">
    <div class="repair-tool-group"><span class="repair-label">操作方式</span><div class="repair-tool-modes"><button :disabled="loading||saving" :aria-pressed="tool==='restore'" @click="tool='restore'"><Brush :size="17"/>恢复 <kbd>B</kbd></button><button :disabled="loading||saving" :aria-pressed="tool==='erase'" @click="tool='erase'"><Eraser :size="17"/>擦除 <kbd>E</kbd></button><button :disabled="loading||saving" :aria-pressed="tool==='pan'" @click="tool='pan'"><Hand :size="17"/>移动画布 <kbd>H</kbd></button></div></div>
    <div class="repair-tool-group"><label class="repair-label" for="repair-brush-size">画笔直径 · 原图像素</label><div class="repair-size"><input id="repair-brush-size" v-model.number="size" type="number" min="1" max="200" :disabled="saving" @change="size=Math.round(Math.max(1,Math.min(200,Number(size)||1)))"/><span>px</span></div><input v-model.number="size" aria-label="调整画笔直径" type="range" min="1" max="200" step="1" :disabled="saving"/><div class="repair-presets"><button v-for="n in [1,4,12,32]" :key="n" :disabled="saving" :aria-pressed="size===n" @click="size=n">{{n}} px</button></div></div>
    <div class="repair-tool-group"><span class="repair-label">画笔形状</span><div class="repair-shapes"><button :disabled="saving" :aria-pressed="shape==='circle'" @click="shape='circle'"><i class="shape-circle"/>圆形</button><button :disabled="saving" :aria-pressed="shape==='square'" @click="shape='square'"><i/>方形</button></div></div>
    <label class="repair-guide"><input v-model="guide" type="checkbox" :disabled="saving"/>显示原图定位底图</label>
    <p class="repair-help">恢复会取回原图像素。放大后用 1–4 px 画笔处理细节。<br/>按住空格或鼠标中键拖动画布，Ctrl + 滚轮缩放。</p>
   </aside>
   <div class="repair-main">
    <div class="repair-viewbar"><div><button :disabled="loading||saving" title="缩小" aria-label="缩小画布" @click="setZoom(zoom/1.5)"><Minus :size="16"/></button><label class="repair-zoom"><select aria-label="画布缩放" :value="zoom" :disabled="loading||saving" @change="setZoom(Number(($event.target as HTMLSelectElement).value))"><option :value="zoom" hidden>{{Math.round(zoom*100)}}%</option><option v-for="n in [.25,.5,1,2,4,8]" :key="n" :value="n">{{n*100}}%</option></select></label><button :disabled="loading||saving" title="放大" aria-label="放大画布" @click="setZoom(zoom*1.5)"><Plus :size="16"/></button><button :disabled="loading||saving" @click="fit"><Maximize :size="16"/>适合窗口</button></div><div><button :disabled="!undoCount||saving" title="Ctrl+Z" @click="history()"><Undo2 :size="16"/>撤销</button><button :disabled="!redoCount||saving" title="Ctrl+Shift+Z" @click="history(true)"><Redo2 :size="16"/>重做</button></div></div>
    <div ref="viewport" class="repair-viewport" :class="{'is-panning':tool==='pan'||space}" @wheel="wheel">
     <div class="repair-stage"><div class="repair-surface" :style="surfaceStyle"><img v-if="guide" :src="props.original" alt="半透明原图，仅用于定位"/><canvas ref="canvas" aria-label="抠图编辑画布" @contextmenu.prevent @pointerdown.prevent="pointer($event,true)" @pointermove="pointer($event)" @pointerup="finish" @pointercancel="finish" @lostpointercapture="finish" @pointerleave="hover=null"/><span v-if="hover&&tool!=='pan'&&!space" class="repair-cursor" :class="{'is-erasing':tool==='erase'}" :style="cursorStyle"/></div></div>
    </div>
    <p class="repair-canvas-status" role="status">{{loading?'正在加载原图…':`${imageWidth} × ${imageHeight} px · ${tool==='restore'?'恢复遗漏部件':tool==='erase'?'擦除多余背景':'拖动画布查看细节'} · ${size} px ${shape==='circle'?'圆形':'方形'}画笔`}}</p>
   </div>
  </div>
  <p v-if="error" class="repair-error" role="alert">{{error}}</p>
  <template #footer><div class="repair-footer"><span>完成后返回对照预览，确认图片即可开始生成。</span><div><button class="repair-cancel" :disabled="saving" @click="emit('cancel')">放弃本次修补</button><button class="repair-save" :disabled="loading||saving" @click="save"><Check :size="16"/>{{saving?'正在保存…':'完成修补，返回预览'}}</button></div></div></template>
 </ElDialog>
</template>

<style scoped>
:global(.el-dialog.mask-dialog){max-width:1500px;height:min(94dvh,980px);display:flex;flex-direction:column;--el-dialog-bg-color:#203c57;--el-text-color-primary:#edf5fc;--el-text-color-regular:#c4d7e8;--el-dialog-border-radius:18px;padding:22px;color:#edf5fc;box-shadow:0 24px 90px #081a32a0}
:global(.mask-dialog .el-dialog__header){padding-bottom:18px}:global(.mask-dialog .el-dialog__title){font:500 22px 'Noto Serif SC',serif}:global(.mask-dialog .el-dialog__body){padding:0;flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column}:global(.mask-dialog .el-dialog__footer){padding-top:18px}
.repair-workspace{flex:1;min-height:0;display:grid;grid-template-columns:210px minmax(0,1fr);border:1px solid #bad2e140;border-radius:12px;overflow:hidden;background:#294963}.repair-tools{overflow-y:auto;padding:18px 15px;display:flex;flex-direction:column;gap:18px}.repair-tool-group{display:grid;gap:12px}.repair-label{color:#c4d7e8;font-size:12px}.repair-tool-modes{display:grid;gap:8px}.repair-workspace button,.repair-footer button{font:500 12px 'Noto Sans SC',sans-serif;min-height:36px;display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid #b5d2e93d;border-radius:7px;padding:8px 11px;background:#b5d2e90b;color:#edf5fc;cursor:pointer}.repair-workspace button:hover:not(:disabled){background:#b5d2e925}.repair-workspace button[aria-pressed=true]{background:#b5d2e9;color:#203c57;border-color:#b5d2e9}.repair-workspace button:disabled,.repair-footer button:disabled{opacity:.4;cursor:not-allowed}.repair-tool-modes button{justify-content:flex-start}.repair-tool-modes kbd{margin-left:auto;font:11px monospace;opacity:.65}.repair-size{display:flex;align-items:center;gap:10px;color:#c4d7e8;font:12px monospace}.repair-size input{width:100%;min-width:0;background:#173149;border:1px solid #b5d2e95c;border-radius:6px;padding:9px;color:#edf5fc;font:14px monospace}.repair-tools input[type=range]{width:100%;accent-color:#b5d2e9;cursor:pointer}.repair-presets,.repair-shapes{display:flex;gap:6px}.repair-presets button{font:11px monospace;padding:5px 6px;min-height:30px;flex:1;white-space:nowrap}.repair-shapes button{flex:1}.repair-shapes i{width:11px;height:11px;border:1.5px solid currentColor}.shape-circle{border-radius:50%}.repair-guide{font-size:12px;display:flex;gap:8px;align-items:center;color:#edf5fc}.repair-guide input{accent-color:#b5d2e9}.repair-help{font-size:11px;line-height:1.9;color:#c4d7e8;margin:0}.repair-main{min-width:0;min-height:0;background:#172e44;display:flex;flex-direction:column}.repair-viewbar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 14px;flex-wrap:wrap;border-bottom:1px solid #bad2e130}.repair-viewbar>div{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.repair-viewbar button{min-height:34px;padding:7px 9px}.repair-zoom select{height:34px;color:#edf5fc;background:#203c57;border:1px solid #b5d2e94d;border-radius:6px;font:12px monospace;padding:4px 6px;width:78px}.repair-viewport{flex:1;min-height:140px;overflow:auto;overscroll-behavior:contain;scrollbar-color:#6f91ac #172e44;position:relative}.repair-stage{display:grid;place-items:center;min-width:100%;min-height:100%;width:max-content;padding:32px;box-sizing:border-box}.repair-surface{position:relative;flex:none;background:repeating-conic-gradient(#d4e0e8 0% 25%,#b1c2ce 0% 50%) 50%/20px 20px;box-shadow:0 0 0 1px #b5d2e970}.repair-surface img{position:absolute;inset:0;width:100%;height:100%;opacity:.25;pointer-events:none}.repair-surface canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:none;image-rendering:pixelated}.repair-cursor{position:absolute;transform:translate(-50%,-50%);border:1px solid #fff;outline:1px solid #173149;box-sizing:border-box;pointer-events:none;z-index:2;background:#b5d2e91a}.repair-cursor.is-erasing{border-color:#ffd4ca;background:#ffb7a51a}.is-panning canvas{cursor:grab}.is-panning canvas:active{cursor:grabbing}.repair-canvas-status{font:11px/1.6 monospace;color:#c4d7e8;margin:0;padding:9px 14px}.repair-footer{display:flex;align-items:center;justify-content:space-between;gap:16px}.repair-footer>span{color:#c4d7e8;font-size:12px;text-align:left}.repair-footer>div{display:flex;gap:12px}.repair-footer .repair-save{background:#b5d2e9;color:#203c57;font-weight:650}.repair-error{color:#ffd4ca;font-size:12px;margin:10px 0}.repair-workspace :focus-visible,.repair-footer button:focus-visible{outline:2px solid #b5d2e9;outline-offset:3px}
@media(max-width:760px){:global(.el-dialog.mask-dialog){width:calc(100vw - 16px)!important;padding:15px;margin-top:1vh!important}.repair-workspace{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr)}.repair-tools{padding:10px 12px;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.repair-tools .repair-tool-group:first-child{grid-column:1/-1}.repair-tool-modes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.repair-tool-modes button{padding:7px 3px;gap:4px;justify-content:center;white-space:nowrap;font-size:11px}.repair-guide{grid-column:1/-1}.repair-tool-modes kbd,.repair-help,.repair-presets{display:none}.repair-tool-group{gap:7px}.repair-guide{align-self:center}.repair-tools input[type=range]{margin:0}.repair-size input{padding:6px}.repair-viewport{min-height:120px}.repair-viewbar{gap:8px;padding:8px}.repair-viewbar button{font-size:11px;padding:6px;gap:4px}.repair-footer{align-items:stretch;flex-direction:column;gap:10px}.repair-footer>span{font-size:11px}.repair-footer>div{justify-content:flex-end}.repair-shapes button{padding:7px}.repair-label{font-size:11px}}
</style>
