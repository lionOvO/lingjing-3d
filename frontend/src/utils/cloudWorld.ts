import * as THREE from 'three'

export type WorldAction='create'|'assets'|'knowledge'|'workspace'|'bell'|'water'|'reference'
export type WorldPlace={id:WorldAction;name:string;subtitle:string;position:THREE.Vector3;target:THREE.Vector3;route?:string}
export const worldPlaces:WorldPlace[]=[
 {id:'create',name:'造物阁',subtitle:'图片生成 3D',position:new THREE.Vector3(0,4,-1),target:new THREE.Vector3(0,1.6,-1),route:'/generate'},
 {id:'assets',name:'藏品台',subtitle:'我的模型资产',position:new THREE.Vector3(6.1,2.5,1.1),target:new THREE.Vector3(6.1,.7,1.1),route:'/library'},
 {id:'knowledge',name:'知物亭',subtitle:'创作知识库',position:new THREE.Vector3(-5.6,2.9,-1.7),target:new THREE.Vector3(-5.6,.8,-1.7),route:'/knowledge'},
 {id:'workspace',name:'云间书案',subtitle:'进入工作台',position:new THREE.Vector3(-2.4,2.3,4.5),target:new THREE.Vector3(-2.4,.7,4.5),route:'/workspace'},
 {id:'bell',name:'祈愿铃',subtitle:'点一下，放飞灵感',position:new THREE.Vector3(2.8,.6,4.4),target:new THREE.Vector3(2.8,.8,3.8)},
]

function random(seed:number){let state=seed>>>0;return()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296}}
const material=(color:THREE.ColorRepresentation,roughness=.9)=>new THREE.MeshStandardMaterial({color,roughness,metalness:.02})
function mesh(geometry:THREE.BufferGeometry,mat:THREE.Material,x=0,y=0,z=0){const result=new THREE.Mesh(geometry,mat);result.position.set(x,y,z);result.castShadow=true;result.receiveShadow=true;return result}
function box(w:number,h:number,d:number,mat:THREE.Material,x=0,y=0,z=0){return mesh(new THREE.BoxGeometry(w,h,d),mat,x,y,z)}

export function islandGeometry(radius:number,depth:number,seed:number,segments=34){
 const rng=random(seed),positions:number[]=[],colors:number[]=[],indices:number[]=[]
 const top=new THREE.Color('#a7b7a0'),side=new THREE.Color('#799391'),bottom=new THREE.Color('#506d79')
 positions.push(0,.2,0);colors.push(top.r,top.g,top.b)
 const rings=[{r:1,y:0},{r:1.04,y:-depth*.22},{r:.64,y:-depth*.72},{r:.12,y:-depth}]
 for(let ring=0;ring<rings.length;ring++)for(let i=0;i<segments;i++){
  const angle=i/segments*Math.PI*2,rough=.9+rng()*.18,r=rings[ring].r*radius*rough
  positions.push(Math.cos(angle)*r,rings[ring].y+(rng()-.5)*depth*.12,Math.sin(angle)*r)
  const color=ring===0?top.clone():side.clone().lerp(bottom,ring/3);color.multiplyScalar(.87+rng()*.2);colors.push(color.r,color.g,color.b)
 }
 for(let i=0;i<segments;i++)indices.push(0,1+(i+1)%segments,1+i)
 for(let ring=0;ring<rings.length-1;ring++)for(let i=0;i<segments;i++){
  const a=1+ring*segments+i,b=1+ring*segments+(i+1)%segments,c=a+segments,d=b+segments
  indices.push(a,b,c,b,d,c)
 }
 const tip=positions.length/3;positions.push(0,-depth*1.08,0);colors.push(bottom.r,bottom.g,bottom.b)
 for(let i=0;i<segments;i++)indices.push(1+(rings.length-1)*segments+i,1+(rings.length-1)*segments+(i+1)%segments,tip)
 const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));g.setIndex(indices);g.computeVertexNormals();return g.toNonIndexed()
}

export function releaseWorld(root:THREE.Object3D){
 const geometries=new Set<THREE.BufferGeometry>(),materials=new Set<THREE.Material>(),textures=new Set<THREE.Texture>()
 root.traverse(node=>{
  if(node instanceof THREE.Mesh||node instanceof THREE.Sprite){
   if(node instanceof THREE.Mesh)geometries.add(node.geometry)
   const owned=Array.isArray(node.material)?[...node.material]:[node.material]
   if(node instanceof THREE.Mesh&&node.customDepthMaterial)owned.push(node.customDepthMaterial)
   for(const mat of owned){materials.add(mat);for(const value of Object.values(mat))if(value instanceof THREE.Texture)textures.add(value)}
  }
 })
 geometries.forEach(value=>value.dispose());materials.forEach(value=>value.dispose());textures.forEach(value=>value.dispose())
}

export function createCloudWorld(scene:THREE.Scene,mobile:boolean){
 const root=new THREE.Group();root.name='云山浮岛';scene.add(root)
 const rng=random(20261026),stone=material('#b8c3b3'),wood=material('#795f4b'),gold=material('#c9a877',.5),jade=material('#5f897c'),dark=material('#375954'),ivory=material('#e5e8d7')
 const islandMat=new THREE.MeshStandardMaterial({vertexColors:true,flatShading:true,roughness:1})
 const main=mesh(islandGeometry(5.1,4.3,3),islandMat);main.scale.z=1.04;root.add(main)
 const lawn=mesh(new THREE.CylinderGeometry(4.6,4.75,.15,48),material('#91a998'),0,-.03,0);root.add(lawn)
 const plaza=mesh(new THREE.CylinderGeometry(2.8,2.9,.12,64),stone,0,.17,-.95);root.add(plaza)
 const plazaRim=mesh(new THREE.TorusGeometry(2.77,.025,5,80),gold,0,.24,-.95);plazaRim.rotation.x=Math.PI/2;root.add(plazaRim)
 const steps=new THREE.Group()
 for(let i=0;i<6;i++)steps.add(box(1.4,.09,1.4-i*.13,stone,0,.06+i*.055,2.6-i*.15))
 root.add(steps)
 const sideIslands=[{x:6.1,z:1.1,r:1.75,seed:5},{x:-5.6,z:-1.7,r:1.9,seed:6},{x:-2.4,z:4.5,r:1.7,seed:7}]
 for(const item of sideIslands){const part=mesh(islandGeometry(item.r,2.4,item.seed,23),islandMat,item.x,.05,item.z);root.add(part);root.add(mesh(new THREE.CylinderGeometry(item.r*.88,item.r*.91,.14,32),stone,item.x,.12,item.z))}
 function bridge(from:THREE.Vector3,to:THREE.Vector3){
  const mid=from.clone().add(to).multiplyScalar(.5),distance=from.distanceTo(to),group=new THREE.Group();group.position.copy(mid);group.rotation.y=-Math.atan2(to.z-from.z,to.x-from.x)
  for(let i=0;i<12;i++){const u=i/11,x=(u-.5)*distance,y=.23+Math.sin(u*Math.PI)*.3;group.add(box(distance/12*.92,.09,.72,wood,x,y,0));if(i%2===0)for(const side of [-1,1])group.add(box(.045,.45,.045,wood,x,y+.25,side*.37))}
  root.add(group)
 }
 bridge(new THREE.Vector3(4.05,0,.7),new THREE.Vector3(5.1,0,1.05));bridge(new THREE.Vector3(-4.05,0,-1.4),new THREE.Vector3(-4.7,0,-1.7));bridge(new THREE.Vector3(-1.7,0,3.9),new THREE.Vector3(-2.2,0,4.3))
 const trees:THREE.Group[]=[]
 function pine(x:number,z:number,scale=1){
  const group=new THREE.Group();group.position.set(x,.12,z);group.scale.setScalar(scale)
  group.add(mesh(new THREE.CylinderGeometry(.07,.13,1.7,7),wood,0,.85,0))
  const greens=['#466e63','#648776','#79947e']
  for(let i=0;i<3;i++){const canopy=mesh(new THREE.SphereGeometry(.85-i*.16,9,6),material(greens[i]),i===1?.16:-.08,1.1+i*.45,0);canopy.scale.y=.43;group.add(canopy)}
  group.name='场景松树';group.userData.phase=trees.length*1.9;root.add(group);trees.push(group)
 }
 for(const [x,z,s] of [[-3.6,-2.5,1.3],[-2.4,-3.9,1.1],[2.8,-3,1.4],[3.6,-1.7,.9],[-3.8,.8,.75],[.7,3.9,.7],[-6.4,-2.1,.65]])pine(x,z,s)
 const windTime={value:0}
 let pineInstalled=false
 function installPine(source:THREE.Object3D){
  if(pineInstalled)return false
  const bounds=new THREE.Box3().setFromObject(source),size=bounds.getSize(new THREE.Vector3()),center=bounds.getCenter(new THREE.Vector3())
  if(!Number.isFinite(size.y)||size.y<=0)return false
  const scale=2.5/Math.max(size.y,size.x*.9,size.z*.9)
  const foliageMaterials=new Map<string,THREE.Material>(),depthMaterials=new Map<THREE.BufferGeometry,THREE.MeshDepthMaterial>()
  // Each tree shares the same generated geometry and texture. Wind bends the crown,
  // keeping the root fixed, and applies identically to its shadow pass.
  function wind(mat:THREE.Material,geometry:THREE.BufferGeometry){
   geometry.computeBoundingBox();const min=geometry.boundingBox!.min.y,height=Math.max(.001,geometry.boundingBox!.max.y-min)
   mat.onBeforeCompile=shader=>{
    shader.uniforms.pineTime=windTime
    shader.vertexShader='uniform float pineTime;\n'+shader.vertexShader.replace('#include <begin_vertex>',`#include <begin_vertex>\nfloat crown=smoothstep(0.12,1.0,(position.y-(${min.toFixed(7)}))/${height.toFixed(7)});\ntransformed.x+=sin(pineTime*1.15+position.y*2.0)*crown*${(height*.035).toFixed(7)};\ntransformed.z+=sin(pineTime*.85+position.y*1.7)*crown*${(height*.02).toFixed(7)};`)
   }
   mat.customProgramCacheKey=()=>`pine-wind-v1-${min}-${height}`
  }
  for(let i=0;i<trees.length;i++){
   const slot=trees[i];for(const child of slot.children)child.visible=false
   const tree=source.clone(true);tree.name='Pixal3D 生成松树';tree.scale.setScalar(scale);tree.position.set(-center.x*scale,-bounds.min.y*scale,-center.z*scale);tree.rotation.y=i*1.73
   tree.traverse(node=>{if(node instanceof THREE.Mesh){
    node.castShadow=true;node.receiveShadow=true
    // Decorative foliage has no click action; skip its dense mesh during hover picking.
    node.raycast=()=>{}
    const convert=(original:THREE.Material)=>{const key=original.uuid+node.geometry.uuid;let mat=foliageMaterials.get(key);if(!mat){mat=original.clone();if(mat instanceof THREE.MeshStandardMaterial){mat.roughness=.95;mat.metalness=0;mat.metalnessMap=null;mat.roughnessMap=null}wind(mat,node.geometry);foliageMaterials.set(key,mat)}return mat}
    node.material=Array.isArray(node.material)?node.material.map(convert):convert(node.material)
    let depth=depthMaterials.get(node.geometry);if(!depth){depth=new THREE.MeshDepthMaterial({depthPacking:THREE.RGBADepthPacking});wind(depth,node.geometry);depthMaterials.set(node.geometry,depth)}node.customDepthMaterial=depth
   }})
   slot.add(tree)
  }
  // Retain ownership of the loaded source for cleanup without drawing it again.
  source.visible=false;root.add(source);pineInstalled=true;return true
 }
 for(let i=0;i<24;i++){const a=rng()*Math.PI*2,r=3.1+rng()*1.4;const rock=mesh(new THREE.DodecahedronGeometry(.15+rng()*.24,0),stone,Math.cos(a)*r,.1,Math.sin(a)*r);rock.scale.y=.7;root.add(rock)}
 const pond=new THREE.Group();pond.position.set(2.2,.13,2.35);pond.rotation.y=-.4;root.add(pond)
 const pondEdge=mesh(new THREE.CylinderGeometry(1.45,1.55,.14,48),stone);pondEdge.scale.z=.64;pond.add(pondEdge)
 const waterMaterial=new THREE.MeshPhysicalMaterial({color:'#659caa',roughness:.28,metalness:.2,transparent:true,opacity:.9,clearcoat:1})
 const water=mesh(new THREE.CircleGeometry(1.38,48),waterMaterial,0,.08,0);water.rotation.x=-Math.PI/2;water.scale.y=.64;water.userData.action='water';pond.add(water)
 const fish:THREE.Group[]=[]
 for(let i=0;i<4;i++){const koi=new THREE.Group();const body=mesh(new THREE.SphereGeometry(.13,10,6),material(i%2?'#e9d4a5':'#d58c61'),0,0,0);body.scale.set(.6,.4,1.8);koi.add(body);const tail=mesh(new THREE.ConeGeometry(.11,.18,3),ivory,0,0,-.25);tail.rotation.x=Math.PI/2;koi.add(tail);pond.add(koi);fish.push(koi)}
 const asset=new THREE.Group();asset.position.set(6.1,.2,1.1);asset.userData.action='assets';root.add(asset)
 asset.add(mesh(new THREE.CylinderGeometry(.8,.91,.2,32),wood,0,.1,0));asset.add(mesh(new THREE.TorusGeometry(.73,.018,5,48),gold,0,.22,0));asset.children[1].rotation.x=Math.PI/2
 const sculpture=mesh(new THREE.IcosahedronGeometry(.62,1),material('#a5c9c5',.35),0,1.2,0);sculpture.rotation.z=.25;asset.add(sculpture)
 const satellite=mesh(new THREE.TorusGeometry(.95,.022,6,64),gold,0,1.2,0);satellite.rotation.x=.8;asset.add(satellite)
 const bookPlace=new THREE.Group();bookPlace.position.set(-5.6,.2,-1.7);bookPlace.userData.action='knowledge';root.add(bookPlace)
 for(const x of [-.68,.68])bookPlace.add(box(.1,1.55,.1,wood,x,.78,0))
 bookPlace.add(box(1.8,.12,.8,wood,0,1.55,0));const roof=mesh(new THREE.ConeGeometry(1.2,.55,4),jade,0,1.86,0);roof.rotation.y=Math.PI/4;roof.scale.z=.65;bookPlace.add(roof)
 bookPlace.add(box(1.2,.14,.6,wood,0,.75,0))
 for(let i=0;i<6;i++){const book=box(.13,.38,.4,material(['#c2b58b','#76999a','#aa8271'][i%3]),-.45+i*.18,1,0);book.rotation.z=(i-2.5)*.06;bookPlace.add(book)}
 const desk=new THREE.Group();desk.position.set(-2.4,.25,4.5);desk.rotation.y=.3;desk.userData.action='workspace';root.add(desk)
 desk.add(box(1.6,.13,.9,wood,0,.68,0));for(const x of [-.64,.64])for(const z of [-.3,.3])desk.add(box(.09,.65,.09,wood,x,.32,z))
 const scroll=box(1,.035,.58,ivory,0,.78,0);scroll.rotation.y=-.15;desk.add(scroll)
 for(const x of [-.52,.52]){const roller=mesh(new THREE.CylinderGeometry(.06,.06,.66,10),gold,x,.8,0);roller.rotation.x=Math.PI/2;desk.add(roller)}
 desk.add(mesh(new THREE.CylinderGeometry(.12,.1,.2,12),dark,.5,.83,.25))
 const bellStand=new THREE.Group();bellStand.position.set(2.8,.28,3.8);root.add(bellStand)
 for(const x of [-.42,.42])bellStand.add(mesh(new THREE.CylinderGeometry(.045,.06,1.7,8),wood,x,.85,0))
 bellStand.add(box(1.1,.1,.15,wood,0,1.7,0));const bell=new THREE.Group();bell.position.y=1.34;bell.userData.action='bell';bellStand.add(bell)
 bell.add(mesh(new THREE.CylinderGeometry(.14,.24,.38,18,1,true),gold,0,-.15,0));bell.add(mesh(new THREE.SphereGeometry(.14,12,6),gold));bell.add(box(.025,.45,.025,wood,0,-.46,0));bell.add(box(.13,.27,.015,ivory,0,-.67,0))
 const lanterns:THREE.Group[]=[]
 const glow=new THREE.MeshStandardMaterial({color:'#f4d59a',emissive:'#c99851',emissiveIntensity:.5,roughness:.7})
 for(let i=0;i<12;i++){const lantern=new THREE.Group();lantern.add(box(.2,.3,.2,glow));lantern.add(box(.24,.025,.24,wood,0,.16,0));lantern.add(box(.24,.025,.24,wood,0,-.16,0));lantern.visible=false;root.add(lantern);lanterns.push(lantern)}
 const clouds:THREE.Group[]=[];const cloudMaterial=new THREE.MeshLambertMaterial({color:'#edf2ef',transparent:true,opacity:.55,depthWrite:false})
 cloudMaterial.onBeforeCompile=shader=>{
  shader.uniforms.cloudTime=windTime
  shader.vertexShader='varying vec3 cloudLocal;\n'+shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\ncloudLocal=position;')
  shader.fragmentShader='varying vec3 cloudLocal;\nuniform float cloudTime;\n'+shader.fragmentShader.replace('#include <normal_fragment_maps>',`#include <normal_fragment_maps>\nfloat feather=smoothstep(0.04,0.8,abs(dot(normalize(normal),normalize(vViewPosition))));\nfloat billow=0.8+0.2*sin(cloudLocal.x*5.0+cloudTime*0.32)*sin(cloudLocal.z*4.0-cloudTime*0.24);\ndiffuseColor.a*=feather*billow;`)
 }
 cloudMaterial.customProgramCacheKey=()=> 'soft-cloud-v1'
 const cloudGeometry=new THREE.SphereGeometry(1,mobile?14:20,12)
 for(let i=0;i<(mobile?14:23);i++){const group=new THREE.Group(),angle=i/(mobile?14:23)*Math.PI*2;group.position.set(Math.cos(angle)*(10+rng()*10),-1.8+rng()*1.5,Math.sin(angle)*(10+rng()*10));for(let j=0;j<5;j++){const puff=mesh(cloudGeometry,cloudMaterial,(j-2)*.65,rng()*.5,(rng()-.5)*.9);puff.scale.set(1.1+rng()*.7,.55+rng()*.6,.85+rng()*.5);puff.castShadow=false;puff.receiveShadow=false;group.add(puff)}group.userData.origin=group.position.clone();root.add(group);clouds.push(group)}
 // Mountains are actual geometry around the entire island, so orbiting reveals a new horizon.
 for(let i=0;i<23;i++){const angle=i/23*Math.PI*2,radius=34+rng()*13;const mountain=mesh(islandGeometry(5+rng()*5,8+rng()*13,100+i,15),material(i%2?'#87aab3':'#7397a4'),Math.cos(angle)*radius,-6,Math.sin(angle)*radius);mountain.rotation.x=Math.PI;mountain.scale.y=.8;root.add(mountain)}
 for(let i=0;i<5;i++){const a=i/5*Math.PI*2+.4;root.add(mesh(islandGeometry(1.3+rng(),3.5,240+i,15),islandMat,Math.cos(a)*15,-1.5+rng()*4,Math.sin(a)*15))}
 const ripples:{mesh:THREE.Mesh;age:number}[]=[]
 let bellTime=-10,lanternTime=-10,ambientTime=0
 function ripple(point:THREE.Vector3){const local=pond.worldToLocal(point.clone());const ring=mesh(new THREE.RingGeometry(.19,.215,40),new THREE.MeshBasicMaterial({color:'#e3f1e8',transparent:true,opacity:.9,side:THREE.DoubleSide,depthWrite:false}),local.x,.095,local.z);ring.rotation.x=-Math.PI/2;pond.add(ring);ripples.push({mesh:ring,age:0})}
 function releaseLanterns(time:number){bellTime=time;lanternTime=time;lanterns.forEach((lantern,i)=>{lantern.visible=true;lantern.position.set(2.8+Math.sin(i*2.4)*.5,1.2,3.8+Math.cos(i*2.4)*.5)})}
 function tick(time:number,delta:number,calm:boolean){
  if(!calm)ambientTime+=delta
  windTime.value=ambientTime
  sculpture.rotation.y=ambientTime*.35;sculpture.position.y=1.2+Math.sin(ambientTime*1.1)*.12
  for(let i=0;i<trees.length;i++){trees[i].rotation.z=Math.sin(ambientTime*.95+i*1.9)*.023;trees[i].rotation.x=Math.sin(ambientTime*.7+i*1.3)*.012}
  for(let i=0;i<clouds.length;i++){const origin=clouds[i].userData.origin as THREE.Vector3;clouds[i].position.x=origin.x+Math.sin(ambientTime*.18+i*.9)*1.8;clouds[i].position.z=origin.z+Math.cos(ambientTime*.15+i*.9)*1.1;clouds[i].position.y=origin.y+Math.sin(ambientTime*.3+i)*.16;for(let j=0;j<clouds[i].children.length;j++){clouds[i].children[j].position.y=Math.sin(ambientTime*.45+i+j)*.12}}
  for(let i=0;i<fish.length;i++){const a=ambientTime*.33+i*Math.PI*.5;fish[i].position.set(Math.cos(a)*(.7+i*.08),.04,Math.sin(a)*(.38+i*.035));fish[i].rotation.y=-a}
  bell.rotation.z=Math.exp(-Math.max(0,time-bellTime)*1.4)*Math.sin((time-bellTime)*14)*.6
  for(let i=0;i<lanterns.length;i++)if(lanterns[i].visible){const age=time-lanternTime-i*.15;lanterns[i].position.set(2.8+Math.sin(i*2.4)*(.5+Math.max(0,age)*.22),1.2+Math.max(0,age)*.85,3.8+Math.cos(i*2.4)*(.5+Math.max(0,age)*.2));lanterns[i].rotation.y=time*.3+i;if(age>13)lanterns[i].visible=false}
  for(let i=ripples.length-1;i>=0;i--){const item=ripples[i];item.age+=delta;item.mesh.scale.setScalar(1+item.age*2.6);(item.mesh.material as THREE.MeshBasicMaterial).opacity=Math.max(0,.85-item.age*.6);if(item.age>1.4){item.mesh.removeFromParent();item.mesh.geometry.dispose();(item.mesh.material as THREE.Material).dispose();ripples.splice(i,1)}}
 }
 return {root,tick,ripple,releaseLanterns,installPine,trees,clouds,pond,main,asset,bookPlace,desk,bellStand}
}
