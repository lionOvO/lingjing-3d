<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { Pause, Play, RotateCcw, MoveHorizontal, Image, Layers } from 'lucide-vue-next'

const host = ref<HTMLElement>()
const status = ref<'loading'|'ready'|'fallback'>('loading')
const rotating = ref(true), structure = ref(false), referenceOpen = ref(false)
let renderer:THREE.WebGLRenderer|undefined, scene:THREE.Scene|undefined, camera:THREE.PerspectiveCamera|undefined
let controls:OrbitControls|undefined, model:THREE.Object3D|undefined, environment:THREE.WebGLRenderTarget|undefined
let resize:ResizeObserver|undefined, intersection:IntersectionObserver|undefined, motion:MediaQueryList|undefined
let frame=0, disposed=false, inView=true, lastTime=0, sampleFrames=0, sampleStart=0
let reduced=false, mobile=false, interacting=false
const original = new Map<THREE.Mesh,THREE.Material|THREE.Material[]>()
let wire:THREE.MeshBasicMaterial|undefined

function disposeObject(object:THREE.Object3D){
 const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>(),textures=new Set<THREE.Texture>()
 object.traverse(node=>{if(node instanceof THREE.Mesh){geometries.add(node.geometry);for(const material of Array.isArray(node.material)?node.material:[node.material]){materials.add(material);for(const value of Object.values(material))if(value instanceof THREE.Texture)textures.add(value)}}})
 geometries.forEach(value=>value.dispose());materials.forEach(value=>value.dispose());textures.forEach(value=>value.dispose())
}
function draw(){if(renderer&&scene&&camera)renderer.render(scene,camera)}
function animate(time:number){
 frame=0
 if(disposed||!inView||document.hidden||!renderer)return
 const delta=Math.min((time-lastTime)/1000,.05);lastTime=time
 if(controls){controls.autoRotate=rotating.value&&!reduced&&!interacting;controls.update(delta)}
 draw()
 // Reduce drawing resolution once if a sustained low frame rate is observed.
 if(!reduced&&status.value==='ready'&&sampleFrames<90){
  if(!sampleFrames)sampleStart=time
  sampleFrames++
  if(sampleFrames===90&&(time-sampleStart)/90>34){renderer.setPixelRatio(1);renderer.shadowMap.enabled=false;resizeCanvas()}
 }
 if(!reduced||interacting)frame=requestAnimationFrame(animate)
}
function start(){if(!frame&&!disposed&&inView&&!document.hidden){lastTime=performance.now();frame=requestAnimationFrame(animate)}}
function visibility(){if(document.hidden){cancelAnimationFrame(frame);frame=0}else start()}
function resizeCanvas(){
 if(!renderer||!camera||!host.value)return
 const {width,height}=host.value.getBoundingClientRect()
 if(!width||!height)return
 renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();draw();start()
}
function reset(){
 if(!camera||!controls)return
 camera.position.set(5.4,4.1,7.2);controls.target.set(0,1.25,0);controls.update();draw();start()
}
function keyboard(event:KeyboardEvent){
 if(!camera||!controls)return
 if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return
 event.preventDefault()
 if(event.key==='Home'){reset();return}
 const offset=camera.position.clone().sub(controls.target),spherical=new THREE.Spherical().setFromVector3(offset)
 if(event.key==='ArrowLeft')spherical.theta-=.12
 if(event.key==='ArrowRight')spherical.theta+=.12
 if(event.key==='ArrowUp')spherical.phi=Math.max(.5,spherical.phi-.08)
 if(event.key==='ArrowDown')spherical.phi=Math.min(1.5,spherical.phi+.08)
 camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));controls.update();draw();start()
}
function updateMotion(){
 reduced=!!motion?.matches
 if(reduced){rotating.value=false;cancelAnimationFrame(frame);frame=0;draw()}else start()
}
function contextLost(event:Event){event.preventDefault();status.value='fallback';cancelAnimationFrame(frame);frame=0}
watch(structure,value=>{
 if(!model)return
 model.traverse(node=>{if(node instanceof THREE.Mesh)node.material=value?wire!:original.get(node)!})
 draw();start()
})
watch(rotating,start)

onMounted(async()=>{
 if(!host.value)return
 motion=matchMedia('(prefers-reduced-motion: reduce)');reduced=motion.matches;rotating.value=!reduced
 mobile=matchMedia('(max-width: 760px)').matches
 try{
  renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'})
  renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.25:1.65));renderer.setClearColor(0x000000,0)
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.15
  renderer.shadowMap.enabled=!mobile;renderer.shadowMap.type=THREE.PCFSoftShadowMap
  renderer.domElement.setAttribute('aria-hidden','true');renderer.domElement.addEventListener('webglcontextlost',contextLost)
  host.value.append(renderer.domElement)
  scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(34,1,.1,100)
  scene.add(new THREE.HemisphereLight(0xddefff,0x697b8a,2.1))
  const key=new THREE.DirectionalLight(0xffebcd,3.2);key.position.set(-3,7,5);key.castShadow=true
  key.shadow.mapSize.set(1024,1024);key.shadow.camera.left=-4;key.shadow.camera.right=4;key.shadow.camera.top=4;key.shadow.camera.bottom=-4;key.shadow.bias=-.0005;key.shadow.normalBias=.035
  scene.add(key)
  const rim=new THREE.DirectionalLight(0xa6d3ed,1.7);rim.position.set(5,4,-5);scene.add(rim)
  const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment()
  environment=pmrem.fromScene(room,.04);scene.environment=environment.texture;pmrem.dispose();room.dispose()
  const platform=new THREE.Mesh(new THREE.CylinderGeometry(2.8,2.68,.23,96),new THREE.MeshStandardMaterial({color:0x6e8589,roughness:.96,metalness:0}))
  platform.position.y=.05;platform.receiveShadow=true;scene.add(platform)
  const rimRing=new THREE.Mesh(new THREE.TorusGeometry(2.76,.012,6,96),new THREE.MeshStandardMaterial({color:0xc6b38a,roughness:.4,metalness:.7}))
  rimRing.rotation.x=Math.PI/2;rimRing.position.y=.171;scene.add(rimRing)
  const lowerRing=new THREE.Mesh(new THREE.CylinderGeometry(2.65,2.55,.08,96),new THREE.MeshStandardMaterial({color:0x607987,roughness:.8}))
  lowerRing.position.y=-.1;scene.add(lowerRing)
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(12,12),new THREE.ShadowMaterial({opacity:.15}))
  floor.rotation.x=-Math.PI/2;floor.position.y=-.18;floor.receiveShadow=true;scene.add(floor)
  controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.075
  controls.enableZoom=false;controls.enablePan=false;controls.autoRotateSpeed=.35;controls.minPolarAngle=.5;controls.maxPolarAngle=1.5
  renderer.domElement.style.touchAction='pan-y'
  controls.addEventListener('start',()=>{interacting=true;start()})
  controls.addEventListener('end',()=>{interacting=false;draw()})
  controls.addEventListener('change',()=>{if(reduced)draw()})
  reset();resize=new ResizeObserver(resizeCanvas);resize.observe(host.value)
  intersection=new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;if(inView)start();else{cancelAnimationFrame(frame);frame=0}},{threshold:.05});intersection.observe(host.value)
  document.addEventListener('visibilitychange',visibility);motion.addEventListener('change',updateMotion)
  const gltf=await new GLTFLoader().loadAsync(mobile?'/showcase/pavilion-mobile.glb':'/showcase/pavilion.glb')
  if(disposed){disposeObject(gltf.scene);return}
  model=gltf.scene
  const bounds=new THREE.Box3().setFromObject(model),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3())
  const scale=4.25/Math.max(size.x,size.z)
  model.scale.setScalar(scale);model.position.set(-center.x*scale,.175-bounds.min.y*scale,-center.z*scale)
  model.traverse(node=>{if(node instanceof THREE.Mesh){node.castShadow=true;node.receiveShadow=true;original.set(node,node.material);for(const material of Array.isArray(node.material)?node.material:[node.material])if(material instanceof THREE.MeshStandardMaterial){material.roughness=.86;material.metalness=.04;material.roughnessMap=null;material.metalnessMap=null;material.envMapIntensity=.5}}})
  wire=new THREE.MeshBasicMaterial({color:0xcfe4e9,wireframe:true,transparent:true,opacity:.7})
  scene.add(model);status.value='ready';resizeCanvas();start()
 }catch{status.value='fallback';cancelAnimationFrame(frame);frame=0}
})
onBeforeUnmount(()=>{
 disposed=true;cancelAnimationFrame(frame);resize?.disconnect();intersection?.disconnect()
 document.removeEventListener('visibilitychange',visibility);motion?.removeEventListener('change',updateMotion)
 controls?.dispose()
 if(model)model.traverse(node=>{if(node instanceof THREE.Mesh&&original.has(node))node.material=original.get(node)!})
 if(scene)disposeObject(scene);original.clear();wire?.dispose();environment?.dispose()
 renderer?.domElement.removeEventListener('webglcontextlost',contextLost);renderer?.dispose();renderer?.domElement.remove()
})
</script>

<template>
 <div class="creation-stage" :class="{'is-ready':status==='ready','is-fallback':status==='fallback','reference-open':referenceOpen}">
  <div class="stage-orbit" aria-hidden="true"></div>
  <div class="stage-halo" aria-hidden="true"></div>
  <div ref="host" class="creation-canvas" role="group" aria-label="古楼 3D 展台，可拖动旋转，也可用方向键调整视角" tabindex="0" @keydown="keyboard"></div>
  <div v-if="status!=='ready'" class="stage-poster"><img src="/showcase/pavilion-reference.webp" alt="三层飞檐古楼展示"/><span v-if="status==='loading'" role="status">正在布置造物台…</span><span v-else role="status">静态展示 · 当前设备暂未启用 3D</span></div>
  <button class="stage-reference" :aria-expanded="referenceOpen" aria-label="查看古楼原始参考图" @click="referenceOpen=!referenceOpen"><span class="reference-eyebrow"><i></i>原始参考图</span><img src="/showcase/pavilion-reference.webp" alt="生成这座古楼所用的参考图"/><span class="reference-bottom">一张图 · 立体的开始 <Image :size="12"/></span></button>
  <div class="stage-annotation" aria-hidden="true"><span></span>三重飞檐，虚实之间。</div>
  <div class="stage-name"><span class="stage-seal" aria-hidden="true">造<br/>物</span><div><span class="stage-collection">云山藏品 · 建筑</span><strong>云间楼阁</strong><small>平台生成示例 · 已为网页展示优化</small></div></div>
  <div class="stage-bottom">
   <span class="stage-drag-hint"><MoveHorizontal :size="14"/>拖动旋转，探索另一面</span>
   <div class="stage-controls" role="group" aria-label="展台控制">
    <button :disabled="status!=='ready'" :aria-pressed="structure" aria-label="切换模型结构视图" @click="structure=!structure"><Layers :size="15"/><span>{{structure?'看纹理':'看结构'}}</span></button>
    <button :disabled="status!=='ready'" :aria-pressed="rotating" :aria-label="rotating?'暂停自动旋转':'开启自动旋转'" @click="rotating=!rotating"><Pause v-if="rotating" :size="14"/><Play v-else :size="14"/></button>
    <button :disabled="status!=='ready'" aria-label="重置展台视角" @click="reset"><RotateCcw :size="14"/></button>
   </div>
  </div>
 </div>
</template>

<style scoped>
.creation-stage{position:relative;height:610px;isolation:isolate;min-width:0}.creation-canvas{opacity:0;transform:translateY(12px);transition:opacity 1s ease,transform 1s ease;position:absolute;inset:0;z-index:2;outline:none;cursor:grab}.is-ready .creation-canvas{opacity:1;transform:none}.creation-canvas:active{cursor:grabbing}.creation-canvas:focus-visible{outline:1px solid #c4dce8;outline-offset:-8px;border-radius:24px}.creation-canvas :deep(canvas){display:block;width:100%;height:100%}
.stage-halo{position:absolute;inset:20% 3% 10%;z-index:0;background:radial-gradient(ellipse,#bcd6df30,transparent 65%);filter:blur(18px)}.stage-orbit{position:absolute;width:80%;height:19%;left:12%;bottom:18%;border:1px solid #c4dbe224;border-radius:50%;transform:rotate(-9deg);z-index:0}.stage-orbit:after{content:'';position:absolute;inset:15px -25px;border:1px solid #c4dbe215;border-radius:50%}
.stage-poster{position:absolute;inset:14% 10% 23%;z-index:3;display:flex;align-items:center;justify-content:center;flex-direction:column;pointer-events:none}.stage-poster img{width:90%;max-height:100%;object-fit:contain;filter:drop-shadow(0 25px 20px #0a263c60)}.stage-poster span{font-size:11px;color:#d4e4ec;position:absolute;bottom:-22px}.is-fallback .creation-canvas{visibility:hidden}
.stage-reference{position:absolute;top:12%;left:-2%;z-index:4;width:152px;min-height:173px;background:#d8e6e8ed;color:#294653;box-shadow:0 14px 40px #122c3f30;border:1px solid #e9f2f08c;border-radius:4px;padding:12px 12px 9px;text-align:left;transform:perspective(700px) rotateY(14deg) rotateZ(-7deg) translate(calc(var(--mx,0) * -5px),calc(var(--my,0) * -3px));transition:transform .4s ease,width .4s ease,box-shadow .4s ease;cursor:zoom-in}.stage-reference:hover,.stage-reference:focus-visible{transform:rotate(-2deg) translateY(-5px);box-shadow:0 20px 45px #122c3f60;outline:2px solid #d8e7ec;outline-offset:4px}.stage-reference img{display:block;width:100%;height:107px;object-fit:contain;margin:9px 0 12px}.reference-eyebrow{display:flex;align-items:center;gap:6px;font-size:9px;letter-spacing:.1em}.reference-eyebrow i{height:4px;width:4px;border-radius:50%;background:#8b754c}.reference-bottom{display:flex;align-items:center;justify-content:space-between;font-size:8px;color:#586f7c}.reference-open .stage-reference{width:260px;transform:rotate(0);z-index:6;cursor:zoom-out}.reference-open .stage-reference img{height:190px}
.stage-annotation{position:absolute;top:28%;right:0;display:flex;align-items:center;gap:8px;font-size:10px;letter-spacing:.15em;color:#d1e1e7;z-index:3;pointer-events:none}.stage-annotation span{width:27px;border-top:1px solid #c9dbe06b}.stage-name{position:absolute;top:7%;right:3%;display:flex;gap:13px;align-items:center;z-index:3;pointer-events:none}.stage-seal{border:1px solid #c6b38c9c;color:#e1cc9e;font:15px/1.25 'Noto Serif SC',SimSun,serif;padding:7px 6px;box-shadow:inset 0 0 0 3px #c6b38c0d}.stage-name>div{display:flex;flex-direction:column;gap:7px}.stage-collection{font-size:9px;letter-spacing:.17em;color:#bfd0db}.stage-name strong{font:500 25px 'Noto Serif SC',SimSun,serif;color:#f0f4ed;letter-spacing:.13em}.stage-name small{font-size:9px;color:#b9cdd9}
.stage-bottom{position:absolute;bottom:5px;left:10%;right:0;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:12px}.stage-drag-hint{display:flex;align-items:center;gap:8px;font-size:10px;color:#cfdee4;letter-spacing:.06em}.stage-controls{display:flex;align-items:center;padding:4px;border-radius:25px;border:1px solid #cfdee42e;background:#173a50a6;backdrop-filter:blur(10px)}.stage-controls button{display:flex;align-items:center;justify-content:center;gap:6px;min-width:33px;height:31px;padding:0 9px;color:#d6e4e9;border-radius:20px;background:transparent;cursor:pointer;font-size:10px}.stage-controls button:hover,.stage-controls button[aria-pressed=true]{background:#c4dbe419}.stage-controls button:focus-visible{outline:2px solid #d8e7ec}.stage-controls button:disabled{opacity:.4;cursor:default}
@media(max-width:1100px){.creation-stage{height:540px}.stage-reference{left:0;width:130px;min-height:150px}.stage-reference img{height:85px}.stage-annotation{top:27%;font-size:9px}.stage-bottom{left:0}.stage-name{right:0}}
@media(max-width:760px){.creation-stage{height:440px;margin-top:8px}.stage-reference{top:7%;width:111px;min-height:130px;padding:9px}.stage-reference img{height:70px;margin:7px 0}.reference-bottom{font-size:7px}.stage-annotation{display:none}.stage-name{top:10%;right:2%}.stage-name strong{font-size:21px}.stage-name small{font-size:8px}.stage-seal{font-size:12px}.stage-bottom{gap:6px}.stage-drag-hint{font-size:9px;gap:5px}.stage-controls button{min-width:28px;padding:0 7px}.reference-open .stage-reference{width:205px}.reference-open .stage-reference img{height:140px}}
@media(prefers-reduced-motion:reduce){.creation-canvas{transition:none;transform:none}.stage-reference{transition:none;transform:rotate(-4deg)}}
</style>
