<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { ArrowUpRight, Bell, BookOpen, Boxes, Compass, ImagePlus, Menu, Moon, MousePointer2, Pause, Play, RotateCcw, Sun, X } from 'lucide-vue-next'
import { createCloudWorld, releaseWorld, worldPlaces, type WorldAction } from '../utils/cloudWorld'

const host=ref<HTMLElement>(),root=ref<HTMLElement>(),status=ref<'loading'|'ready'|'fallback'>('loading')
const selected=ref<WorldAction|null>(null),night=ref(false),moving=ref(true),menu=ref(false),notice=ref(''),wishes=ref(0),pineLoaded=ref(false)
const active=computed(()=>worldPlaces.find(place=>place.id===selected.value))
const placeDescriptions:Record<string,string>={create:'带上一张参考图，在这里开始创造你的 3D 角色、建筑与物品。',assets:'收藏每一次生成的作品，旋转检视、对比版本，下载模型。',knowledge:'翻阅创作资料，为构图、材质和下一次生成寻找线索。',workspace:'回到自己的创作空间，继续项目，查看生成任务。',bell:'轻点铃铛，放飞一盏灵感灯。愿每一个想法，都有成形的那天。'}
const shortcuts=[{name:'图片生成 3D',path:'/generate',icon:ImagePlus},{name:'模型资产',path:'/library',icon:Boxes},{name:'创作知识库',path:'/knowledge',icon:BookOpen},{name:'我的工作台',path:'/workspace',icon:Compass},{name:'参考图处理',path:'/prepare',icon:ImagePlus},{name:'生成任务',path:'/tasks',icon:Compass},{name:'检查与修复',path:'/repair',icon:Boxes},{name:'模型对比',path:'/compare',icon:Boxes},{name:'项目管理',path:'/projects',icon:BookOpen},{name:'生成预设',path:'/presets',icon:Compass},{name:'使用指南',path:'/guide',icon:BookOpen}]
let renderer:THREE.WebGLRenderer|undefined,scene:THREE.Scene|undefined,camera:THREE.PerspectiveCamera|undefined,controls:OrbitControls|undefined
let world:ReturnType<typeof createCloudWorld>|undefined,light:THREE.DirectionalLight|undefined,ambient:THREE.HemisphereLight|undefined,sky:THREE.ShaderMaterial|undefined,sun:THREE.Mesh|undefined
let resize:ResizeObserver|undefined,motion:MediaQueryList|undefined,frame=0,disposed=false,dragging=false,reduced=false,mobile=false,lastTime=0,time=0,effectUntil=0,noticeTimer:number|undefined
let pointerDown:{x:number;y:number}|undefined,focus: {from:THREE.Vector3;to:THREE.Vector3;targetFrom:THREE.Vector3;targetTo:THREE.Vector3;start:number}|undefined
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2(),projected=new THREE.Vector3()
const anchors=new Map<string,HTMLElement>()
function anchorRef(id:string,value:unknown){if(value instanceof HTMLElement)anchors.set(id,value);else anchors.delete(id)}
function message(text:string){notice.value=text;window.clearTimeout(noticeTimer);noticeTimer=window.setTimeout(()=>notice.value='',4300)}
function projectLabels(){
 if(!camera||!host.value)return
 const width=host.value.clientWidth,height=host.value.clientHeight
 for(const place of worldPlaces){
  const element=anchors.get(place.id);if(!element)continue
  projected.copy(place.position).project(camera)
  const x=(projected.x*.5+.5)*width,y=(-projected.y*.5+.5)*height
  const visible=projected.z<1&&x>30&&x<width-30&&y>75&&y<height-95
  element.style.transform=`translate3d(${x}px,${y}px,0) translate(-50%,-100%)`
  element.style.visibility=visible?'visible':'hidden'
 }
}
function draw(){if(renderer&&scene&&camera){renderer.render(scene,camera);projectLabels()}}
function animate(now:number){
 frame=0;if(disposed||document.hidden||!renderer)return
 const delta=Math.min((now-lastTime)/1000,.05);lastTime=now;time+=delta
 if(focus&&camera&&controls){
  const t=Math.min(1,(now-focus.start)/1000),ease=t*t*(3-2*t)
  camera.position.lerpVectors(focus.from,focus.to,ease);controls.target.lerpVectors(focus.targetFrom,focus.targetTo,ease)
  if(t===1)focus=undefined
 }
 const changed=controls?.update(delta)
 world?.tick(time,delta,reduced||!moving.value)
 draw()
 if((moving.value&&!reduced)||dragging||focus||time<effectUntil||changed)frame=requestAnimationFrame(animate)
}
function start(){if(!frame&&!disposed&&!document.hidden){lastTime=performance.now();frame=requestAnimationFrame(animate)}}
function resizeCanvas(){
 if(!renderer||!camera||!host.value)return
 const width=host.value.clientWidth,height=host.value.clientHeight
 renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();draw();start()
}
function homePosition(){return mobile?new THREE.Vector3(24,20,35):new THREE.Vector3(11,8.5,13.5)}
function reset(){
 if(!camera||!controls)return
 selected.value=null;focus={from:camera.position.clone(),to:homePosition(),targetFrom:controls.target.clone(),targetTo:new THREE.Vector3(0,.2,0),start:performance.now()}
 if(reduced){camera.position.copy(focus.to);controls.target.copy(focus.targetTo);focus=undefined;controls.update()}
 start()
}
function select(id:WorldAction){
 if(id==='water')return
 if(id==='bell'){ringBell();return}
 if(id==='reference'){selected.value='create';message('这座古楼来自平台实际生成案例，原始参考图可在造物阁旁查看。');return}
 const place=worldPlaces.find(item=>item.id===id)
 if(!place||!camera||!controls)return
 selected.value=id;menu.value=false
 const offset=camera.position.clone().sub(controls.target).normalize().multiplyScalar(mobile?13:11)
 offset.y=Math.max(offset.y,5)
 focus={from:camera.position.clone(),to:place.target.clone().add(offset),targetFrom:controls.target.clone(),targetTo:place.target.clone(),start:performance.now()}
 if(reduced){camera.position.copy(focus.to);controls.target.copy(focus.targetTo);focus=undefined;controls.update()}
 start()
}
function ringBell(){
 if(!world)return
 wishes.value++;world.releaseLanterns(time);effectUntil=time+15;selected.value='bell';message(`第 ${wishes.value} 次灵感祈愿 · 灯已放飞`);start()
}
function hit(event:PointerEvent){
 if(!camera||!host.value||!world)return null
 const bounds=host.value.getBoundingClientRect();pointer.set((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1)
 raycaster.setFromCamera(pointer,camera)
 for(const result of raycaster.intersectObjects(world.root.children,true)){
  let ancestor:THREE.Object3D|null=result.object,visible=true
  while(ancestor){if(!ancestor.visible){visible=false;break}ancestor=ancestor.parent}
  if(!visible)continue
  let object:THREE.Object3D|null=result.object
  while(object&&object!==world.root){if(object.userData.action)return {id:object.userData.action as WorldAction,point:result.point};object=object.parent}
  // Terrain occludes objects on the far side of the island.
  if(result.object instanceof THREE.Mesh&&!Array.isArray(result.object.material)&&!result.object.material.transparent)return null
 }
 return null
}
function pointerStart(event:PointerEvent){pointerDown={x:event.clientX,y:event.clientY};focus=undefined}
function pointerMove(event:PointerEvent){if(!host.value)return;host.value.style.cursor=!pointerDown&&hit(event)?'pointer':pointerDown?'grabbing':'grab'}
function pointerEnd(event:PointerEvent){
 const initial=pointerDown;pointerDown=undefined
 if(!initial||Math.hypot(event.clientX-initial.x,event.clientY-initial.y)>7)return
 const result=hit(event);if(!result)return
 if(result.id==='water'){world?.ripple(result.point);effectUntil=time+2;message('云水有声，灵感有回应。');start()}else select(result.id)
}
function cancelPointer(){pointerDown=undefined;dragging=false}
function keyboard(event:KeyboardEvent){
 if(!camera||!controls||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key))return
 event.preventDefault();focus=undefined
 if(event.key==='Home'){reset();return}
 const offset=camera.position.clone().sub(controls.target),spherical=new THREE.Spherical().setFromVector3(offset)
 if(event.key==='ArrowLeft')spherical.theta-=.12
 if(event.key==='ArrowRight')spherical.theta+=.12
 if(event.key==='ArrowUp')spherical.phi=Math.max(.5,spherical.phi-.08)
 if(event.key==='ArrowDown')spherical.phi=Math.min(1.35,spherical.phi+.08)
 camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));controls.update();draw();start()
}
function changeLight(){
 if(!scene||!sky||!light||!ambient||!sun)return
 const dark=night.value
 sky.uniforms.top.value.set(dark?'#192e4c':'#9fc7d7');sky.uniforms.bottom.value.set(dark?'#567285':'#e2e9df')
 ;(scene.fog as THREE.Fog).color.set(dark?'#415d73':'#bad3d8')
 light.color.set(dark?'#b5cee9':'#ffedcc');light.intensity=dark?1.5:2.7
 ambient.color.set(dark?'#a9c8df':'#deedf0');ambient.groundColor.set(dark?'#415568':'#778d83');ambient.intensity=dark?1.5:2.6
 ;(sun.material as THREE.MeshBasicMaterial).color.set(dark?'#e1e9e9':'#fff0c7')
 if(renderer)renderer.toneMappingExposure=dark?.9:1.08
 draw();start()
}
function onVisibility(){if(document.hidden){cancelAnimationFrame(frame);frame=0}else start()}
function onMotion(){reduced=!!motion?.matches;if(reduced)moving.value=false;start()}
function contextLost(event:Event){event.preventDefault();status.value='fallback';cancelAnimationFrame(frame);frame=0}
watch(night,changeLight);watch(moving,start)
onMounted(async()=>{
 if(!host.value)return
 mobile=matchMedia('(max-width:760px)').matches;motion=matchMedia('(prefers-reduced-motion: reduce)');reduced=motion.matches;moving.value=!reduced
 try{
  renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'low-power'});renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.15:1.5))
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.08
  renderer.shadowMap.enabled=!mobile;renderer.shadowMap.type=THREE.PCFSoftShadowMap
  renderer.domElement.setAttribute('aria-hidden','true');host.value.append(renderer.domElement)
  renderer.domElement.addEventListener('webglcontextlost',contextLost)
  renderer.domElement.addEventListener('pointerdown',pointerStart);renderer.domElement.addEventListener('pointermove',pointerMove);renderer.domElement.addEventListener('pointerup',pointerEnd);renderer.domElement.addEventListener('pointercancel',cancelPointer)
  scene=new THREE.Scene();scene.fog=new THREE.Fog('#bad3d8',26,76)
  sky=new THREE.ShaderMaterial({side:THREE.BackSide,depthWrite:false,uniforms:{top:{value:new THREE.Color('#9fc7d7')},bottom:{value:new THREE.Color('#e2e9df')}},vertexShader:'varying vec3 v; void main(){v=position;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',fragmentShader:'varying vec3 v;uniform vec3 top;uniform vec3 bottom;void main(){float h=smoothstep(-.15,.7,normalize(v).y);gl_FragColor=vec4(mix(bottom,top,h),1.);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}'})
  const dome=new THREE.Mesh(new THREE.SphereGeometry(200,24,16),sky);scene.add(dome)
  ambient=new THREE.HemisphereLight('#deedf0','#778d83',2.6);scene.add(ambient)
  light=new THREE.DirectionalLight('#ffedcc',2.7);light.position.set(-8,16,10);light.castShadow=!mobile;light.shadow.mapSize.set(1536,1536);light.shadow.camera.left=-12;light.shadow.camera.right=12;light.shadow.camera.top=12;light.shadow.camera.bottom=-12;light.shadow.camera.far=60;light.shadow.bias=-.0008;light.shadow.normalBias=.08;scene.add(light)
  const rim=new THREE.DirectionalLight('#bad9e8',1.2);rim.position.set(12,8,-12);scene.add(rim)
  sun=new THREE.Mesh(new THREE.SphereGeometry(3,24,16),new THREE.MeshBasicMaterial({color:'#fff0c7',fog:false}));sun.position.set(-30,17,-42);scene.add(sun)
  world=createCloudWorld(scene,mobile)
  const assetWorld=world
  void new GLTFLoader().loadAsync(mobile?'/showcase/pine-mobile.glb':'/showcase/pine.glb').then(gltf=>{
   if(disposed){releaseWorld(gltf.scene);return}
   if(assetWorld.installPine(gltf.scene)){pineLoaded.value=true;draw();start()}else releaseWorld(gltf.scene)
  }).catch(()=>{if(!disposed)message('松树素材暂未加载，已保留备用树木。')})
  camera=new THREE.PerspectiveCamera(42,1,.1,300);camera.position.copy(homePosition())
  controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,.2,0);controls.enableDamping=true;controls.dampingFactor=.07;controls.enablePan=false;controls.minDistance=10;controls.maxDistance=mobile?60:34;controls.minPolarAngle=.5;controls.maxPolarAngle=1.35;controls.rotateSpeed=.55;controls.zoomSpeed=.65;controls.update()
  controls.addEventListener('start',()=>{dragging=true;focus=undefined;start()});controls.addEventListener('end',()=>{dragging=false;start()})
  resize=new ResizeObserver(resizeCanvas);resize.observe(host.value);document.addEventListener('visibilitychange',onVisibility);motion.addEventListener('change',onMotion)
  resizeCanvas();start()
  const gltf=await new GLTFLoader().loadAsync(mobile?'/showcase/pavilion-mobile.glb':'/showcase/pavilion.glb')
  if(disposed){releaseWorld(gltf.scene);return}
  const model=gltf.scene,bounds=new THREE.Box3().setFromObject(model),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3()),scale=4.5/Math.max(size.x,size.z)
  model.scale.setScalar(scale);model.position.set(-center.x*scale,.26-bounds.min.y*scale,-.95-center.z*scale);model.userData.action='create'
  model.traverse(node=>{if(node instanceof THREE.Mesh){node.castShadow=true;node.receiveShadow=true;for(const mat of Array.isArray(node.material)?node.material:[node.material])if(mat instanceof THREE.MeshStandardMaterial){mat.roughness=.88;mat.metalness=.03;const rough=mat.roughnessMap,metal=mat.metalnessMap;mat.roughnessMap=null;mat.metalnessMap=null;rough?.dispose();if(metal!==rough)metal?.dispose()}}})
  world.root.add(model)
  // A real image plane inside the 3D scene, rather than a page background.
  const texture=await new THREE.TextureLoader().loadAsync('/showcase/pavilion-reference.webp')
  if(disposed){texture.dispose();return}
  texture.colorSpace=THREE.SRGBColorSpace
  const reference=new THREE.Group();reference.userData.action='reference';reference.position.set(-2.7,2.4,-.5);reference.rotation.y=.35
  const backing=new THREE.Mesh(new THREE.BoxGeometry(1.15,1.03,.06),new THREE.MeshStandardMaterial({color:'#e5e8da',roughness:1}));reference.add(backing)
  const image=new THREE.Mesh(new THREE.PlaneGeometry(1.02,.78),new THREE.MeshBasicMaterial({map:texture,transparent:true,side:THREE.DoubleSide}));image.position.z=.034;reference.add(image);world.root.add(reference)
  status.value='ready';draw();start()
 }catch{if(world&&renderer){status.value='ready';message('古楼展示暂未加载，其他浮岛仍可探索。')}else status.value='fallback'}
})
onBeforeUnmount(()=>{
 disposed=true;cancelAnimationFrame(frame);window.clearTimeout(noticeTimer);resize?.disconnect();controls?.dispose();document.removeEventListener('visibilitychange',onVisibility);motion?.removeEventListener('change',onMotion)
 if(scene)releaseWorld(scene)
 if(renderer){const canvas=renderer.domElement;canvas.removeEventListener('webglcontextlost',contextLost);canvas.removeEventListener('pointerdown',pointerStart);canvas.removeEventListener('pointermove',pointerMove);canvas.removeEventListener('pointerup',pointerEnd);canvas.removeEventListener('pointercancel',cancelPointer);renderer.dispose();canvas.remove()}
 anchors.clear()
})
</script>

<template>
 <main ref="root" class="world-home" :class="{'world-night':night,'world-loaded':status==='ready'}" :data-tree-source="pineLoaded?'pixal3d':'fallback'">
  <div ref="host" class="world-canvas" role="group" aria-label="完整 3D 云山浮岛，拖动环绕，滚轮缩放，点击建筑探索功能；方向键调整视角，Home 复位" tabindex="0" @keydown="keyboard"></div>
  <div class="world-intro"><p>灵境造物 · 云山之境</p><h1>云山之间，<br/>万物成形。</h1><span>一座可以探索的 3D 创作小世界</span></div>
  <div v-if="status==='loading'" class="world-loading" role="status"><span></span>正在唤醒云山…</div>
  <div v-if="status==='fallback'" class="world-fallback" role="status"><h2>云山暂时未能展开</h2><p>当前设备的 3D 渲染不可用，你仍可以直接进入创作。</p><RouterLink to="/generate">开始图片建模<ArrowUpRight :size="16"/></RouterLink></div>
  <div v-show="status==='ready'" class="world-labels" aria-label="浮岛功能入口">
   <button v-for="place in worldPlaces" :key="place.id" :ref="value=>anchorRef(place.id,value)" class="world-place" :class="{'is-selected':selected===place.id,'is-playful':place.id==='bell'}" :data-place="place.id" :aria-label="`探索${place.name}：${place.subtitle}`" :aria-pressed="selected===place.id" @click="select(place.id)"><span class="world-place-dot"></span><span><strong>{{place.name}}</strong><small>{{place.subtitle}}</small></span><Bell v-if="place.id==='bell'" :size="12"/><ArrowUpRight v-else :size="12"/></button>
  </div>
  <Transition name="world-panel"><section v-if="active" class="world-detail" :aria-label="active.name"><button class="world-detail-close" aria-label="关闭地点介绍" @click="selected=null"><X :size="15"/></button><p>{{active.id==='bell'?'云间小趣':'发现一处创作之地'}}</p><h2>{{active.name}}</h2><span>{{placeDescriptions[active.id]}}</span><RouterLink v-if="active.route" :to="active.route" class="world-enter">{{active.subtitle}}<ArrowUpRight :size="16"/></RouterLink><button v-else class="world-enter" @click="ringBell">再放飞一盏灯<Bell :size="15"/></button></section></Transition>
  <div v-if="!active" class="world-guide"><MousePointer2 :size="16"/><div><strong>拖动环绕，点击探索</strong><span>古楼通往创作 · 水池与铃铛藏着小惊喜</span></div></div>
  <div class="world-toolbar" role="group" aria-label="浮岛场景控制"><button aria-label="回到浮岛全景" title="回到全景" @click="reset"><RotateCcw :size="16"/></button><span></span><button :aria-label="night?'切换白昼':'切换夜晚'" :aria-pressed="night" @click="night=!night"><Sun v-if="night" :size="17"/><Moon v-else :size="16"/></button><button :aria-label="moving?'暂停场景动态':'开启场景动态'" :aria-pressed="moving" @click="moving=!moving"><Pause v-if="moving" :size="16"/><Play v-else :size="16"/></button></div>
  <button class="world-menu-toggle" :aria-expanded="menu" aria-controls="world-quick-links" @click="menu=!menu"><X v-if="menu" :size="15"/><Menu v-else :size="15"/><span>功能导航</span></button>
  <nav v-if="menu||status==='fallback'" id="world-quick-links" class="world-quick-links" aria-label="功能快捷导航"><RouterLink v-for="item in shortcuts" :key="item.path" :to="item.path"><component :is="item.icon" :size="15"/>{{item.name}}<ArrowUpRight :size="12"/></RouterLink></nav>
  <Transition name="world-panel"><div v-if="notice" class="world-notice" role="status">{{notice}}</div></Transition>
  <p class="world-credit">云间楼阁 · 平台生成案例 <span>拖动环绕 / 滚轮缩放</span></p>
 </main>
</template>
