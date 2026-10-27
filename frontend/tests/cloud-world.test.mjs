import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
import * as THREE from 'three'
const source=fs.readFileSync(new URL('../src/utils/cloudWorld.ts',import.meta.url),'utf8').replace("from 'three'",`from '${import.meta.resolve('three')}'`)
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {islandGeometry,createCloudWorld,releaseWorld,worldPlaces}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'))

test('floating terrain has finite geometry and a raycastable upward facing top',()=>{
 const geometry=islandGeometry(5,4,2026),positions=geometry.getAttribute('position')
 assert.ok(positions.count>200)
 assert.ok([...positions.array].every(Number.isFinite))
 geometry.computeBoundingBox()
 assert.ok(geometry.boundingBox.min.y < -4)
 const terrain=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial())
 const ray=new THREE.Raycaster(new THREE.Vector3(.1,10,.1),new THREE.Vector3(0,-1,0))
 const hit=ray.intersectObject(terrain)[0]
 assert.ok(hit&&hit.point.y>-.1&&hit.point.y<.5)
 releaseWorld(terrain)
})
test('every destination is unique, finite and routes to an existing creation feature',()=>{
 assert.equal(new Set(worldPlaces.map(p=>p.id)).size,worldPlaces.length)
 for(const place of worldPlaces){assert.ok([...place.position.toArray(),...place.target.toArray()].every(Number.isFinite));if(place.id!=='bell')assert.match(place.route,/^\/(generate|library|knowledge|workspace)$/)}
})
test('lanterns respond to a wish, expire, and ripple geometry is removed after its animation',()=>{
 const scene=new THREE.Scene(),world=createCloudWorld(scene,true)
 let before=0;world.root.traverse(node=>{if(node instanceof THREE.Mesh)before++})
 world.releaseLanterns(5);world.tick(8,1,false)
 const lanterns=world.root.children.filter(node=>node.type==='Group'&&node.children.some(c=>c.material?.emissiveIntensity===.5))
 assert.equal(lanterns.length,12);assert.ok(lanterns.every(node=>node.visible&&node.position.y>1.2))
 world.tick(21,.1,false);assert.ok(lanterns.every(node=>!node.visible))
 const pondChildren=world.pond.children.length
 world.root.updateMatrixWorld(true)
 world.ripple(world.pond.localToWorld(new THREE.Vector3(0,.09,0)))
 assert.equal(world.pond.children.length,pondChildren+1)
 world.tick(22,1.5,true)
 assert.equal(world.pond.children.length,pondChildren)
 world.tick(23,.01,true)
 world.root.traverse(node=>assert.ok(node.position.toArray().every(Number.isFinite)))
 releaseWorld(scene)
})
test('shared geometry, materials and textures are each released once, including sprites',()=>{
 const root=new THREE.Group(),geometry=new THREE.BoxGeometry(),texture=new THREE.Texture(),material=new THREE.MeshBasicMaterial({map:texture})
 root.add(new THREE.Mesh(geometry,material),new THREE.Mesh(geometry,material),new THREE.Sprite(new THREE.SpriteMaterial({map:texture})))
 let g=0,m=0,t=0;geometry.addEventListener('dispose',()=>g++);material.addEventListener('dispose',()=>m++);texture.addEventListener('dispose',()=>t++)
 releaseWorld(root);assert.deepEqual([g,m,t],[1,1,1])
})

test('wind moves trees and clouds, stays bounded and freezes without a pause jump',()=>{
 const scene=new THREE.Scene(),world=createCloudWorld(scene,true)
 world.tick(1,.05,false)
 const before=world.trees.map(tree=>tree.rotation.z),cloud=world.clouds[0].position.clone()
 for(let i=0;i<40;i++)world.tick(i,.05,false)
 assert.ok(world.trees.some((tree,i)=>Math.abs(tree.rotation.z-before[i])>.01))
 assert.ok(world.clouds[0].position.distanceTo(cloud)>.1)
 const paused=world.clouds[0].position.clone(),sway=world.trees[0].rotation.z
 world.tick(900,.05,true)
 assert.deepEqual(world.clouds[0].position.toArray(),paused.toArray())
 assert.equal(world.trees[0].rotation.z,sway)
 world.tick(901,.01,false)
 assert.ok(world.clouds[0].position.distanceTo(paused)<.01)
 for(let i=0;i<1000;i++)world.tick(i,.05,false)
 for(const cloud of world.clouds)assert.ok(cloud.position.distanceTo(cloud.userData.origin)<2.2)
 releaseWorld(scene)
})

test('generated trees share geometry, hide placeholders and release shadow resources once',()=>{
 const scene=new THREE.Scene(),world=createCloudWorld(scene,true),source=new THREE.Group()
 const geo=new THREE.CylinderGeometry(.1,.2,2,12),mat=new THREE.MeshStandardMaterial(),mesh=new THREE.Mesh(geo,mat)
 mesh.position.y=1;source.add(mesh)
 assert.equal(world.installPine(source),true);assert.equal(world.installPine(source),false)
 assert.equal(world.trees.length,7)
 const models=world.trees.map(tree=>tree.children.find(child=>child.name==='Pixal3D 生成松树'))
 assert.ok(models.every(model=>model&&model.visible))
 assert.ok(world.trees.every(tree=>tree.children.slice(0,4).every(child=>!child.visible)))
 const meshes=models.map(model=>model.children[0])
 assert.ok(meshes.every(mesh=>mesh.geometry===geo&&mesh.customDepthMaterial===meshes[0].customDepthMaterial))
 let g=0,d=0;geo.addEventListener('dispose',()=>g++);meshes[0].customDepthMaterial.addEventListener('dispose',()=>d++)
 releaseWorld(scene);assert.equal(g,1);assert.equal(d,1)
})

