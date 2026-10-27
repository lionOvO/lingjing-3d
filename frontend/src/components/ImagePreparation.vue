<script setup lang="ts">
import {computed,nextTick,onUnmounted,ref,watch} from 'vue'
import {Scan,RotateCcw,Download,Check,LoaderCircle} from 'lucide-vue-next'
import api from '../services/api'
import {fitReference,sharpenReference,type Bounds} from '../utils/referencePreparation'
import MaskRepairEditor from './MaskRepairEditor.vue'
type Assessment={version:number;width:number;height:number;background_kind:string;background_color:string;framing_method:string;subject_bounds:{x:number;y:number;right:number;bottom:number}|null;foreground_fraction:number|null;edge_contact:string[];sharpness:number;warnings:{code:string;message:string}[];recommendation:string}
type VisionAdvice={subject_type:string;description:string;bounds:{x:number;y:number;right:number;bottom:number}|null;keep_parts:string[];exclude_parts:string[];warnings:string[];confidence:number;recommended_model:string;model:string}
type VisionReview={verdict:'pass'|'fail'|'uncertain';missing_parts:string[];background_residue:string[];explanation:string;model:string;confidence:number}
const props=withDefaults(defineProps<{file:File;allowOriginal?:boolean;submitting?:boolean;submissionError?:string;applyLabel?:string}>(),{allowOriginal:false,submitting:false,submissionError:'',applyLabel:'使用此图，前往生成设置'})
const emit=defineEmits<{apply:[file:File,details:Record<string,unknown>];original:[];change:[];busy:[value:boolean];'original-safe':[value:boolean]}>()
const source=ref(''),originalSource=ref(''),output=ref(''),error=ref(''),busy=ref(false),analyzing=ref(false),rendering=ref(false),removed=ref(false),prepared=ref<File|null>(null),assessment=ref<Assessment|null>(null)
const renderError=ref(''),sourceSize=ref({width:0,height:0}),previewCanvas=ref<HTMLCanvasElement|null>(null),livePreview=ref(false)
// Exporting a PNG must never interrupt a pointer drag.
const controlsLocked=computed(()=>busy.value||analyzing.value||visionBusy.value||flowBusy.value||statusChecking.value||editing.value||props.submitting)
const x=ref(0),y=ref(0),width=ref(100),height=ref(100),margin=ref(2.5),centered=ref(true),enhance=ref(false),sourceAspect=ref(1),hasAlpha=ref(false)
const foregroundModel=ref('isnet-anime'),usedModel=ref('')
const segmentationChoice=ref('auto'),smartEnabled=ref(true),flowBusy=ref(false),statusChecking=ref(true),flowStage=ref('')
const cutoutLabel=computed(()=>flowStage.value==='recognize'?'正在识别主体…':flowStage.value==='cutout'?'正在去除背景…':flowStage.value==='review'?'正在检查抠图…':removed.value?'重新自动抠图':'自动抠图')
const visionConfigured=ref(false),visionBusy=ref(false),visionActive=ref(false),visionError=ref(''),visionAdvice=ref<VisionAdvice|null>(null),visionReview=ref<VisionReview|null>(null)
const manualConfirmed=ref(false),editing=ref(false),manualEdits=ref(0)
const visionReady=computed(()=>!visionActive.value||visionReview.value?.verdict==='pass'||manualConfirmed.value)
const background=ref<'preserve'|'neutral'|'white'|'transparent'>('preserve')
const sourceBounds=ref({left:0,top:0,right:0,bottom:0}),drawing=ref({x:0,y:0,width:0,height:0})
const working=computed(()=>busy.value||analyzing.value||rendering.value||visionBusy.value||flowBusy.value||statusChecking.value||editing.value)
const originalSafe=computed(()=>!!assessment.value&&assessment.value.background_kind!=='complex')
const generationSafe=computed(()=>originalSafe.value||hasAlpha.value)
const previewStyle=computed(()=>hasAlpha.value&&['white','neutral'].includes(background.value)?{backgroundImage:'none',backgroundColor:background.value==='white'?'#ffffff':'#808080'}:{})
const warnings=computed(()=>{
 const items=[...(assessment.value?.warnings||[])],bounds=assessment.value?.subject_bounds
 if(bounds&&(x.value>bounds.x||y.value>bounds.y||x.value+width.value<bounds.right||y.value+height.value<bounds.bottom))items.push({code:'manual-crop',message:'当前裁剪可能切到原图轮廓，请对照确认头发、四肢和配饰是否完整。'})
 return items
})
const cropStyle=computed(()=>({left:`${x.value}%`,top:`${y.value}%`,width:`${Math.min(width.value,100-x.value)}%`,height:`${Math.min(height.value,100-y.value)}%`}))
const backgroundChoices=computed(()=>[{value:'preserve' as const,label:removed.value?'保留抠图结果':'保留原图背景'},{value:'neutral' as const,label:'中性灰底'},{value:'white' as const,label:'白底'},{value:'transparent' as const,label:'透明底'}])
let version=0,request=0,visionRequest=0,flowRequest=0,timer:number|undefined,disposed=false
function revoke(value:string){if(value)URL.revokeObjectURL(value)}
let cachedSource:Promise<{image:HTMLImageElement;preview:HTMLCanvasElement}>|null=null,previewFrame=0
function setSource(file:File){revoke(source.value);source.value=URL.createObjectURL(file);cachedSource=null;livePreview.value=false;schedule()}
function loadSource(){
 if(!cachedSource){
  const url=source.value
  cachedSource=(async()=>{
   const image=new Image();image.src=url;await image.decode()
   if(image.width*image.height>20_000_000)throw new Error('图片超过 2000 万像素，请缩小后处理')
   const preview=document.createElement('canvas'),scale=Math.min(1,512/Math.max(image.width,image.height))
   preview.width=Math.max(1,Math.round(image.width*scale));preview.height=Math.max(1,Math.round(image.height*scale))
   preview.getContext('2d')!.drawImage(image,0,0,preview.width,preview.height)
   return {image,preview}
  })()
 }
 return cachedSource
}
function schedule(){
 version++;manualConfirmed.value=false;visionReview.value=null;prepared.value=null;rendering.value=true;emit('change')
 window.clearTimeout(timer)
 if(!previewFrame)previewFrame=requestAnimationFrame(()=>{previewFrame=0;void drawPreview()})
 // Only the settled selection is exported at full resolution.
 timer=window.setTimeout(()=>void render(),250)
}
async function drawPreview(){
 const current=version
 try{
  const {image,preview}=await loadSource()
  if(current!==version||disposed)return
  sourceAspect.value=image.width/image.height;sourceSize.value={width:image.width,height:image.height}
  const frame=makeFrame(preview,384)
  if(previewCanvas.value){previewCanvas.value.getContext('2d')!.drawImage(frame.canvas,0,0);livePreview.value=true;hasAlpha.value=frame.alpha}
 }catch{/* The final export reports invalid selections without flashing an error during a drag. */}
}
function details(){return {version:4,mode:'prepared',strategy:removed.value?'foreground-preview':'preserve-character',manual_review_confirmed:manualConfirmed.value,manual_mask_edits:manualEdits.value,background:hasAlpha.value?'transparent':background.value,preview_background:background.value,foreground_model:usedModel.value||null,background_removed:hasAlpha.value,width:1024,height:1024,crop:{x:x.value,y:y.value,width:width.value,height:height.value},margin:margin.value,centered:centered.value,enhance:enhance.value,source_bounds:sourceBounds.value,output_placement:drawing.value,assessment:assessment.value,review_warnings:warnings.value,vision_advice:visionAdvice.value,vision_review:visionActive.value?visionReview.value:null}}
async function inspectVision(review=false,fromFlow=false){
 if((working.value&&!fromFlow)||!visionConfigured.value||review&&!prepared.value)return false
 const id=++visionRequest,current=version;visionBusy.value=true;visionError.value='';manualConfirmed.value=false;emit('change')
 try{
  const body=new FormData();body.append('image',props.file);if(review)body.append('candidate',prepared.value!)
  const {data}=await api.post('/studio/images/vision-preparation',body,{timeout:100000})
  if(id!==visionRequest||disposed||current!==version)return false
  visionActive.value=true
  if(review)visionReview.value=data
  else{visionAdvice.value=data;if(segmentationChoice.value==='auto')foregroundModel.value=data.recommended_model;visionReview.value=null}
  emit('change')
  return true
 }catch(e:any){if(id===visionRequest&&!disposed)visionError.value=e.message||'视觉分析失败，请稍后重试';return false}
 finally{if(id===visionRequest&&!disposed)visionBusy.value=false}
}
function applyVisionBounds(){
 const box=visionAdvice.value?.bounds;if(!box)return
 x.value=box.x;y.value=box.y;width.value=box.right-box.x;height.value=box.bottom-box.y;schedule()
}
function applyAutomaticBounds(){
 const box=visionAdvice.value?.bounds
 // A user's crop always wins. AI bounds are only a padded initial proposal.
 if(!box||visionAdvice.value!.confidence<.75||x.value!==0||y.value!==0||width.value!==100||height.value!==100)return
 x.value=Math.max(0,Math.floor(box.x-3));y.value=Math.max(0,Math.floor(box.y-3))
 width.value=Math.min(100,Math.ceil(box.right+3))-x.value;height.value=Math.min(100,Math.ceil(box.bottom+3))-y.value
}
void api.get('/studio/images/vision-status').then(({data})=>{if(!disposed)visionConfigured.value=data.configured}).catch(()=>{}).finally(()=>{if(!disposed){statusChecking.value=false;if(!visionConfigured.value)segmentationChoice.value='u2net'}})
async function automaticCutout(){
 if(working.value)return
 const id=++flowRequest,currentFile=props.file
 const current=()=>!disposed&&id===flowRequest&&currentFile===props.file
 flowBusy.value=true;error.value='';visionError.value='';visionReview.value=null;emit('change')
 try{
  if(visionConfigured.value&&smartEnabled.value){
   flowStage.value='recognize'
   if(!await inspectVision(false,true)||!current())return
   applyAutomaticBounds();await nextTick()
  }else{visionActive.value=false}
  if(segmentationChoice.value!=='auto')foregroundModel.value=segmentationChoice.value
  flowStage.value='cutout'
  if(!await removeBackground()||!current())return
  // Wait for the final PNG, including Vue's background-control watcher, before
  // reviewing. Never submit a preview from before the cutout completed.
  await nextTick();window.clearTimeout(timer);await render()
  if(!current()||!prepared.value)return
  if(visionConfigured.value&&smartEnabled.value){flowStage.value='review';await inspectVision(true,true)}
 }finally{if(current()){flowBusy.value=false;flowStage.value=''}}
}
function changeSmartMode(){if(!smartEnabled.value&&segmentationChoice.value==='auto')segmentationChoice.value='u2net';visionActive.value=false;visionReview.value=null;emit('change')}
function makeFrame(image:HTMLImageElement|HTMLCanvasElement,size:number){
 const sx=Math.round(image.width*x.value/100),sy=Math.round(image.height*y.value/100)
 const sw=Math.max(1,Math.round(image.width*Math.min(width.value,100-x.value)/100)),sh=Math.max(1,Math.round(image.height*Math.min(height.value,100-y.value)/100))
 const crop=document.createElement('canvas');crop.width=sw;crop.height=sh
 const ctx=crop.getContext('2d')!;ctx.drawImage(image,sx,sy,sw,sh,0,0,sw,sh)
 const pixels=ctx.getImageData(0,0,sw,sh).data
 let alpha=false,visible=false,left=sw,top=sh,right=0,bottom=0
 for(let row=0;row<sh;row++)for(let col=0;col<sw;col++){
  const a=pixels[(row*sw+col)*4+3]
  if(a<250)alpha=true
  if(a>12){visible=true;left=Math.min(left,col);top=Math.min(top,row);right=Math.max(right,col+1);bottom=Math.max(bottom,row+1)}
 }
 if(!visible)throw new Error('裁剪区域没有可见主体，请调整范围')
 if(!centered.value||!alpha){
  left=0;top=0;right=sw;bottom=sh
  if(centered.value&&!removed.value&&assessment.value?.subject_bounds){
   const box=assessment.value.subject_bounds,pad=Math.max(image.width,image.height)*.025
   left=Math.max(0,Math.floor(image.width*box.x/100-sx-pad));top=Math.max(0,Math.floor(image.height*box.y/100-sy-pad))
   right=Math.min(sw,Math.ceil(image.width*box.right/100-sx+pad));bottom=Math.min(sh,Math.ceil(image.height*box.bottom/100-sy+pad))
  }
 }
 const placement=fitReference({left,top,right,bottom},margin.value,size)
 const canvas=document.createElement('canvas');canvas.width=size;canvas.height=size
 const target=canvas.getContext('2d')!;target.imageSmoothingEnabled=true;target.imageSmoothingQuality='high'
 if(!alpha){target.fillStyle=assessment.value?.background_color||'#808080';target.fillRect(0,0,size,size)}
 target.drawImage(crop,left,top,right-left,bottom-top,placement.x,placement.y,placement.width,placement.height)
 if(enhance.value){const frame=target.getImageData(0,0,size,size);frame.data.set(sharpenReference(frame.data,size,size));target.putImageData(frame,0,0)}
 return {canvas,alpha,placement,bounds:{left:sx+left,top:sy+top,right:sx+right,bottom:sy+bottom}}
}
async function render(){
 const current=version
 renderError.value=''
 try{
  const {image}=await loadSource()
  if(current!==version||disposed)return
  sourceAspect.value=image.width/image.height;sourceSize.value={width:image.width,height:image.height}
  const frame=makeFrame(image,1024)
  const blob=await new Promise<Blob>((resolve,reject)=>frame.canvas.toBlob(v=>v?resolve(v):reject(new Error('图片导出失败')),'image/png'))
  if(current!==version||disposed)return
  hasAlpha.value=frame.alpha;sourceBounds.value=frame.bounds;drawing.value=frame.placement
  revoke(output.value);output.value=URL.createObjectURL(blob);prepared.value=new File([blob],`${props.file.name.replace(/\.[^.]+$/,'')}-prepared.png`,{type:'image/png'})
  livePreview.value=false
 }catch(e:any){if(current===version&&!disposed){renderError.value=e.message;revoke(output.value);output.value='';livePreview.value=false}}
 finally{if(current===version&&!disposed)rendering.value=false}
}
async function analyze(){
 const id=++request;analyzing.value=true;assessment.value=null;error.value='';emit('change')
 try{const body=new FormData();body.append('image',props.file);const {data}=await api.post('/studio/images/analyze-reference',body,{timeout:45000});if(id!==request||disposed)return;assessment.value=data;schedule()}
 catch{if(id===request&&!disposed){error.value='输入检查暂不可用，已保留原图。可以手动调整构图并检查人物完整性。';schedule()}}
 finally{if(id===request&&!disposed)analyzing.value=false}
}
async function removeBackground(){
 if(busy.value||analyzing.value)return false
 const id=++request;busy.value=true;error.value='';visionReview.value=null;prepared.value=null;emit('change')
 try{const body=new FormData();body.append('image',props.file);body.append('model',foregroundModel.value);body.append('crop',JSON.stringify({x:x.value,y:y.value,width:Math.min(width.value,100-x.value),height:Math.min(height.value,100-y.value)}));const {data,headers}=await api.post('/studio/images/remove-background',body,{responseType:'blob',timeout:220000});if(id!==request||disposed)return false;removed.value=true;manualEdits.value=0;usedModel.value=headers['x-foreground-model']||foregroundModel.value;background.value='preserve';setSource(new File([data],'foreground.png',{type:'image/png'}));return true}
 catch{if(id===request&&!disposed)error.value='抠图未完成，请点击“自动抠图”重试，或在高级调整中更换分割方式。';return false}
 finally{if(id===request&&!disposed)busy.value=false}
}
function openRepair(){if(!working.value&&!props.submitting&&removed.value){editing.value=true;error.value=''}}
function closeRepair(){editing.value=false}
function saveRepair(blob:Blob,bounds:Bounds){
 // The editor returns original-resolution pixels and their visible bounds.
 // Expand the crop so a restored tip/hand is retained in the generation input.
 const cw=sourceSize.value.width,ch=sourceSize.value.height
 if(cw&&ch){
  const right=Math.max(x.value+Math.min(width.value,100-x.value),Math.ceil(bounds.right/cw*100))
  const bottom=Math.max(y.value+Math.min(height.value,100-y.value),Math.ceil(bounds.bottom/ch*100))
  x.value=Math.min(x.value,Math.floor(bounds.left/cw*100));y.value=Math.min(y.value,Math.floor(bounds.top/ch*100))
  width.value=right-x.value;height.value=bottom-y.value
 }
 manualEdits.value++;closeRepair();setSource(new File([blob],'foreground-repaired.png',{type:'image/png'}))
}
function reset(){closeRepair();manualEdits.value=0;error.value='';renderError.value='';removed.value=false;usedModel.value='';hasAlpha.value=false;x.value=0;y.value=0;width.value=100;height.value=100;margin.value=2.5;centered.value=true;enhance.value=false;background.value='preserve';setSource(props.file)}
function download(){if(!prepared.value)return;const a=document.createElement('a');a.href=output.value;a.download=prepared.value.name;a.click()}
watch(()=>props.file,()=>{request++;visionRequest++;flowRequest++;flowBusy.value=false;flowStage.value='';segmentationChoice.value=statusChecking.value||visionConfigured.value&&smartEnabled.value?'auto':'u2net';visionBusy.value=false;visionActive.value=false;visionAdvice.value=null;visionReview.value=null;visionError.value='';busy.value=false;revoke(originalSource.value);originalSource.value=URL.createObjectURL(props.file);reset();void analyze()},{immediate:true})
watch([x,y,width,height,margin,centered,enhance],schedule)
watch(working,value=>emit('busy',value),{immediate:true})
watch(originalSafe,value=>emit('original-safe',value),{immediate:true})
onUnmounted(()=>{disposed=true;version++;request++;visionRequest++;flowRequest++;window.clearTimeout(timer);cancelAnimationFrame(previewFrame);cachedSource=null;revoke(originalSource.value);revoke(source.value);revoke(output.value)})
</script>
<template>
 <section class="image-preparation" :aria-busy="working">
  <div class="tool-section-head"><div><p class="eyebrow">保留主体 · 去除背景</p><h2>整理一张完整的生成参考图</h2></div><span class="tool-badge">1024 × 1024 PNG</span></div>
  <div class="cutout-entry">
   <div><strong>{{removed?'第二步 · 对照原图，检查完整性':'第一步 · 自动去除背景'}}</strong><p>{{visionConfigured&&smartEnabled?'自动识别主体、去除背景并检查完整性，无需分别点击。':'去除背景后，请对照原图检查主体是否完整。'}}</p><small v-if="visionConfigured&&smartEnabled">智能辅助会将图片发送到 DeepSeek 进行识别与复核。</small></div>
   <button type="button" class="library-button primary-action cutout-start" :disabled="working" @click="automaticCutout"><LoaderCircle v-if="flowBusy" class="cutout-spinner" :size="18" /><Scan v-else :size="18" />{{cutoutLabel}}</button>
  </div>
  <ol class="cutout-stages" aria-label="自动抠图流程" v-if="visionConfigured&&smartEnabled">
   <li :class="{active:flowStage==='recognize',done:!!visionAdvice}"><span>1</span>识别主体</li><li :class="{active:flowStage==='cutout',done:removed}"><span>2</span>去除背景</li><li :class="{active:flowStage==='review',done:visionReview?.verdict==='pass'}"><span>3</span>检查完整性</li>
  </ol>
  <div v-if="analyzing" class="reference-assessment" role="status"><LoaderCircle :size="18" /><strong>正在读取图片…</strong></div>
  <div class="prepare-workspace">
   <div class="prepare-comparison">
    <figure><div class="prepare-image-label"><span>01</span> 原始图片 <small>亮框内为保留范围</small></div><div class="prepare-image-stage"><div class="prepare-crop-area" :style="{width:`min(100%, calc(var(--prepare-preview-height) * ${sourceAspect}))`,aspectRatio:sourceAspect}"><img :src="originalSource" alt="未经处理的原图对照" /><span class="prepare-crop-box" :style="cropStyle"></span></div></div><figcaption>对照头发、四肢和配饰，保留完整主体</figcaption></figure>
    <figure><div class="prepare-image-label"><span>02</span> 生成输入 <small>实时构图预览</small></div><div class="prepare-output" :style="previewStyle"><img v-show="!livePreview" v-if="output" :src="output" alt="处理后的参考图预览" /><canvas ref="previewCanvas" v-show="livePreview" width="384" height="384" aria-label="实时裁剪预览"></canvas><span v-if="rendering" class="prepare-status"><LoaderCircle :size="13" class="cutout-spinner" />正在更新</span></div><figcaption><span>{{removed?'透明 PNG · 用于生成 3D':'尚未自动抠图'}}</span><button type="button" class="preview-download" :disabled="!prepared||working||submitting" @click="download"><Download :size="13"/>下载图片</button></figcaption></figure>
   </div>
   <aside class="prepare-adjustments" aria-label="裁剪与构图设置">
    <div class="adjustments-heading"><strong>裁剪与构图</strong><span>拖动即预览</span></div>
    <p class="adjustments-hint">左侧框选保留范围，右侧查看生成效果。</p>
    <div class="prepare-controls"><label>左边界 {{x}}%<input v-model.number="x" type="range" min="0" max="99" :disabled="controlsLocked" /></label><label>上边界 {{y}}%<input v-model.number="y" type="range" min="0" max="99" :disabled="controlsLocked" /></label><label>裁剪宽度 {{Math.min(width,100-x)}}%<input v-model.number="width" type="range" min="1" max="100" :disabled="controlsLocked" /></label><label>裁剪高度 {{Math.min(height,100-y)}}%<input v-model.number="height" type="range" min="1" max="100" :disabled="controlsLocked" /></label><label>主体留白 {{margin}}%<input v-model.number="margin" type="range" min="0" max="24" step="0.5" :disabled="controlsLocked" /></label><label class="tool-check"><input v-model="centered" type="checkbox" :disabled="controlsLocked" />按轮廓整理构图</label><label class="tool-check"><input v-model="enhance" type="checkbox" :disabled="controlsLocked" />轻度锐化已有细节</label></div>
    <div class="prepare-background" role="group" aria-label="预览底色"><span>预览底色</span><button v-for="choice in backgroundChoices" :key="choice.value" type="button" class="library-button quiet" :aria-pressed="background===choice.value" :disabled="controlsLocked||(choice.value!=='preserve'&&!hasAlpha)" @click="background=choice.value">{{choice.label}}</button><small>仅改变预览底色，不改变生成图片。</small></div>
    <button type="button" class="library-button quiet reset-framing" :disabled="controlsLocked" @click="reset"><RotateCcw :size="14" />恢复原图与默认构图</button>
   </aside>
  </div>
  <div v-if="visionReview" class="cutout-result" :class="{'needs-attention':visionReview.verdict!=='pass'}" role="status"><strong>{{visionReview.verdict==='pass'?'检查完成，未发现明显缺失':visionReview.verdict==='fail'?'检查提示：可能有缺失或背景残留':'暂时无法确认完整性，请人工检查'}}</strong><p>{{visionReview.explanation}}</p><p v-if="visionReview.missing_parts.length">缺失：{{visionReview.missing_parts.join('、')}}</p><p v-if="visionReview.background_residue.length">残留：{{visionReview.background_residue.join('、')}}</p><p v-if="visionReview.verdict!=='pass'">可用下方画笔恢复遗漏部件；若检查有误，也可人工确认当前结果。</p></div>
  <div v-else-if="removed&&!working" class="cutout-result" role="status"><strong>{{manualEdits?'修补已保存，请确认完整性':'抠图完成，请检查主体是否完整'}}</strong><p>对照原图确认主体完整后，在底部确认并继续；也可选择 AI 再检查一次。</p><button v-if="visionActive" class="library-button" :disabled="working||!prepared" @click="inspectVision(true)">让 AI 再检查（可选）</button></div>
  <p v-else-if="!working&&!generationSafe" class="tool-hint">当前图片含有复杂背景，请先点击上方「自动抠图」。</p>
  <p v-if="error" class="library-error" role="alert">{{error}}</p><p v-if="visionError" class="library-error" role="alert">{{visionError}}</p><p v-if="renderError" class="library-error" role="alert">{{renderError}}</p>
  <div v-if="removed" class="mask-repair-entry"><div><strong>有部件缺失或背景残留？</strong><p>放大画布，用细画笔恢复或擦除；完成后在此确认图片。</p></div><button class="library-button" :disabled="working" @click="openRepair">打开精细修补</button></div>
  <MaskRepairEditor v-if="editing" :original="originalSource" :mask="source" @cancel="closeRepair" @save="saveRepair" />

  <details class="cutout-advanced">
   <summary>更多设置 <span>分割模型与智能识别结果</span></summary>
   <div class="cutout-settings">
    <label class="cutout-model">分割方式<select v-model="segmentationChoice" class="library-select" aria-label="前景分割方式" :disabled="working"><option value="auto">自动选择（推荐）</option><option value="isnet-anime">动漫人物 · ISNet Anime</option><option value="u2net">建筑 / 物品 / 真人 · U2Net</option></select></label>
    <label v-if="visionConfigured" class="tool-check"><input v-model="smartEnabled" type="checkbox" :disabled="working" @change="changeSmartMode" />智能辅助：自动识别与复核</label>
    <p class="tool-hint">先框选完整主体，再点击上方「{{removed?'重新自动抠图':'自动抠图'}}」；框选范围会实际参与分割，减少工具栏干扰。{{visionConfigured?'关闭智能辅助后，由你手动检查完整性。':'请手动选择合适方式并检查完整性。'}}</p>
    <div v-if="visionAdvice" class="cutout-advice"><strong>识别结果</strong><p>{{visionAdvice.description}}</p><p v-if="visionAdvice.keep_parts.length">应保留：{{visionAdvice.keep_parts.join('、')}}</p><p v-if="visionAdvice.exclude_parts.length">应排除：{{visionAdvice.exclude_parts.join('、')}}</p><ul v-if="visionAdvice.warnings.length" class="reference-warnings"><li v-for="item in visionAdvice.warnings" :key="item">{{item}}</li></ul><button v-if="visionAdvice.bounds" class="library-button quiet" :disabled="working" @click="applyVisionBounds">应用建议保留范围</button></div>

    <ul v-if="warnings.length" class="reference-warnings"><li v-for="item in warnings" :key="item.code">{{item.message}}</li></ul>
    <p class="tool-hint">自动检查可能漏判；放大和锐化不能补回缺失结构。始终对照原图检查完整性。</p>
   </div>
  </details>
  <div class="cutout-confirm">
   <div class="confirmation-copy"><label v-if="removed&&prepared&&visionActive&&visionReview?.verdict!=='pass'" class="manual-review tool-check"><input v-model="manualConfirmed" type="checkbox" :disabled="working" @change="emit('change')" />我已对照原图，确认主体完整</label><strong>{{submitting?'正在上传图片并创建任务…':!generationSafe?'先完成抠图，或选择使用原图':!visionReady?'请对照原图，确认主体完整':'图片准备就绪'}}</strong><p>{{submitting?'请稍候，提交后会自动进入生成与质检。':allowOriginal?'确认后直接开始生成，无需再次确认。':'使用处理结果后，前往生成页选择参数。'}}</p><p v-if="submissionError" class="library-error" role="alert">{{submissionError}}</p></div>
   <div class="confirmation-actions"><button v-if="allowOriginal" type="button" class="library-button quiet original-fallback" :disabled="working||submitting" @click="emit('original')">使用原图直接生成</button><button type="button" class="library-button primary-action" :disabled="!prepared||working||submitting||!generationSafe||!visionReady" @click="prepared&&generationSafe&&visionReady&&emit('apply',prepared,details())"><LoaderCircle v-if="submitting" :size="16" class="cutout-spinner"/><Check v-else :size="16"/>{{submitting?'正在提交…':applyLabel}}</button></div>
  </div>

 </section>
</template>
<style scoped>
.prepare-workspace{--prepare-preview-height:clamp(260px,27vw,370px);display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:22px;align-items:start;margin:20px 0}
.prepare-workspace .prepare-comparison{gap:16px;min-width:0}.prepare-comparison figure{min-width:0}
.prepare-image-label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:#edf5fc;margin-bottom:12px}.prepare-image-label>span{color:#a6c7e0;font-size:10px;letter-spacing:.1em}.prepare-image-label small{font-size:11px;font-weight:400;color:#b9cede;margin-left:auto}
.prepare-image-stage,.prepare-workspace .prepare-output{height:var(--prepare-preview-height);width:100%;max-width:none;max-height:none;aspect-ratio:auto;border:1px solid #bad2e140;border-radius:12px;background-color:#183047;display:flex;align-items:center;justify-content:center;overflow:hidden}
.prepare-workspace .prepare-crop-area{max-width:100%;height:auto;max-height:100%;margin:0}.prepare-workspace .prepare-crop-area img{display:block;width:100%;height:100%;object-fit:contain}
.prepare-workspace .prepare-output>img,.prepare-output>canvas{width:100%;height:100%;object-fit:contain}.prepare-workspace .prepare-status{inset:10px 10px auto auto;display:flex;gap:6px;align-items:center;padding:6px 9px;border-radius:20px;background:#17324be8;font-size:11px;pointer-events:none;color:#e2edf8}
.prepare-adjustments{padding:18px;border:1px solid #b5cfe94a;border-radius:12px;background:#18334ded}.adjustments-heading{display:flex;justify-content:space-between;align-items:center;color:#edf5fc;font-size:14px}.adjustments-heading span{font-size:10px;font-weight:400;color:#bdd7eb;background:#b5cfe916;padding:4px 7px;border-radius:5px}.adjustments-hint{font-size:11px;line-height:1.7;color:#b9cede;margin:9px 0 14px}
.prepare-adjustments .prepare-controls{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;margin:0}.prepare-adjustments .prepare-controls label{font-size:12px;color:#d6e6f3;gap:2px;min-width:0}.prepare-adjustments input[type=range]{margin:0;height:30px;width:100%;cursor:ew-resize;touch-action:pan-y}.prepare-adjustments .tool-check{grid-column:1/-1;display:flex;gap:8px;align-items:center;min-height:27px}.prepare-adjustments input:focus-visible{outline:2px solid #b5cfe9;outline-offset:3px}
.prepare-adjustments .prepare-background{display:flex;flex-wrap:wrap;gap:6px;border-top:1px solid #bad2e130;margin:14px 0 0;padding-top:13px}.prepare-adjustments .prepare-background>span{width:100%;font-size:11px;color:#c1d7e8;margin-bottom:3px}.prepare-adjustments .prepare-background .library-button{padding:6px 9px;min-height:30px;font-size:11px}.prepare-adjustments .prepare-background [aria-pressed=true]{background:#b5cfe92b;border-color:#c5e0f5}.prepare-adjustments .prepare-background small{font-size:10px;line-height:1.7;color:#aac4d9}.reset-framing{margin-top:13px;width:100%;justify-content:center;font-size:11px;min-height:34px}
@media(max-width:1150px){.prepare-workspace{--prepare-preview-height:300px;grid-template-columns:minmax(0,1fr)}.prepare-adjustments .prepare-controls{grid-template-columns:repeat(3,minmax(0,1fr))}.prepare-adjustments .tool-check{grid-column:auto}.prepare-adjustments .prepare-background{align-items:center}.prepare-adjustments .prepare-background>span{width:auto;margin:0 8px 0 0}.reset-framing{width:auto}.prepare-image-stage,.prepare-workspace .prepare-output{height:300px}}
@media(max-width:700px){.prepare-workspace{--prepare-preview-height:230px;gap:14px}.prepare-workspace .prepare-comparison{gap:10px}.prepare-image-label{font-size:12px}.prepare-image-label small{display:none}.prepare-image-stage,.prepare-workspace .prepare-output{height:230px}.prepare-comparison figcaption{font-size:10px;line-height:1.6}.prepare-adjustments{padding:14px}.prepare-adjustments .prepare-controls{grid-template-columns:1fr 1fr}.prepare-adjustments .tool-check{grid-column:1/-1}}

.cutout-entry{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 24px;border:1px solid #b5cfe95c;border-radius:14px;background:#17385388;margin-bottom:16px}
.cutout-entry strong{font-size:17px;color:#f0f6fd}.cutout-entry p{font-size:13px;color:#d1e1ef;line-height:1.8;margin:7px 0}.cutout-entry small{font-size:11px;color:#b8cee0}
.cutout-start{flex-shrink:0;min-width:165px;min-height:48px;justify-content:center;font-size:15px;font-weight:650}
.cutout-stages{display:flex;list-style:none;gap:28px;margin:0 0 25px;padding:0;color:#afc5d8;font-size:12px;flex-wrap:wrap}.cutout-stages li{display:flex;align-items:center;gap:8px}.cutout-stages span{display:grid;place-items:center;width:23px;height:23px;border:1px solid #b6cee34a;border-radius:50%;font-size:11px}.cutout-stages .active{color:#fff;font-weight:650}.cutout-stages .active span{background:#b5cfe9;color:#17314c}.cutout-stages .done span{border-color:#b5cfe9;color:#e8f4ff}
.cutout-result{padding:18px 20px;border-left:3px solid #b5cfe9;background:#18344d70;border-radius:0 10px 10px 0;margin:18px 0;color:#e5f0f9}.cutout-result.needs-attention{border-color:#e4c591;background:#55473535}.cutout-result p,.cutout-settings p{font-size:12px;line-height:1.8;color:#ccdeed;margin:8px 0}.cutout-result .library-button{margin-top:8px}
.cutout-advanced{margin:24px 0;border-block:1px solid #bad2e130}.cutout-advanced summary{cursor:pointer;padding:18px 0;font-size:13px;font-weight:600;color:#e1edf8}.cutout-advanced summary span{font-weight:400;font-size:12px;margin-left:12px;color:#b7cde0}.cutout-settings{padding:2px 0 22px}.cutout-model{display:grid;gap:9px;max-width:380px;color:#d1e1ef;font-size:12px;margin-bottom:16px}.cutout-model select{width:100%}.cutout-advice{margin:20px 0;padding-top:18px;border-top:1px solid #bad2e130;font-size:13px}
.cutout-confirm{position:sticky;bottom:12px;z-index:8;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 22px;margin:26px -8px -8px;border:1px solid #b5d2e96b;border-radius:14px;background:#203c57f7;box-shadow:0 10px 30px #10203940;backdrop-filter:blur(12px)}
.confirmation-copy{min-width:0}.confirmation-copy strong{font-size:14px;color:#edf5fc}.confirmation-copy p{font-size:12px;line-height:1.7;color:#c4d7e8;margin:5px 0 0}.confirmation-actions{display:flex;align-items:center;gap:14px;flex-wrap:wrap;justify-content:flex-end}.confirmation-actions .primary-action{min-height:46px;white-space:normal;text-align:center;justify-content:center}.original-fallback{font-size:12px}.prepare-comparison figcaption{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.preview-download{display:inline-flex;align-items:center;gap:6px;background:none;padding:4px 0;color:#d0e1ef;font-size:11px;cursor:pointer}.preview-download:disabled{opacity:.4;cursor:not-allowed}
.mask-repair-entry{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 20px;margin:18px 0;border:1px solid #bad2e140;border-radius:12px;background:#18344d70}.mask-repair-entry strong{font-size:14px;color:#e5f0f9}.mask-repair-entry p{font-size:12px;color:#caddeb;line-height:1.8;margin:7px 0}.manual-review{padding:0 0 10px;color:#e5f0f9;font-size:13px}
.cutout-spinner{animation:cutout-spin 1s linear infinite}@keyframes cutout-spin{to{transform:rotate(360deg)}}
.cutout-advanced summary:focus-visible{outline:2px solid #b5cfe9;outline-offset:3px}
@media(max-width:700px){.mask-repair-entry{align-items:stretch;flex-direction:column;gap:10px}.mask-repair-entry .library-button{justify-content:center;min-height:42px}.cutout-entry{align-items:stretch;flex-direction:column;gap:12px;padding:18px}.cutout-start{width:100%}.cutout-stages{gap:15px}.cutout-confirm{align-items:stretch;flex-direction:column}.cutout-confirm{bottom:6px;padding:16px;margin-inline:0}.confirmation-actions{width:100%;gap:10px}.confirmation-actions .primary-action{flex:1;min-width:165px}.confirmation-copy strong{font-size:13px}.cutout-advanced summary span{display:block;margin:7px 0 0 16px}}
@media(prefers-reduced-motion:reduce){.cutout-spinner{animation:none}}
</style>
