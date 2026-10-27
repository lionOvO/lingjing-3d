import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import ts from 'typescript'
const source=fs.readFileSync(new URL('../src/utils/referencePreparation.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {fitReference,sharpenReference,paintForeground}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'))

test('repair restores fine source details and erasure never alters remaining RGB',()=>{
 const original=new Uint8ClampedArray(30*40*4),mask=new Uint8ClampedArray(original.length)
 for(let i=0;i<original.length;i+=4)original.set([213,134,47,255],i)
 const before=new Uint8ClampedArray(original)
 paintForeground(mask,original,30,40,{x:15,y:2},{x:15,y:35},1,true)
 for(let y=2;y<35;y++)assert.deepEqual(Array.from(mask.slice((y*30+15)*4,(y*30+15)*4+4)),[213,134,47,255])
 assert.equal(mask[3],0)
 const rgb=mask.slice((20*30+15)*4,(20*30+15)*4+3)
 paintForeground(mask,original,30,40,{x:15,y:20},{x:15,y:20},2,false)
 assert.equal(mask[(20*30+15)*4+3],0)
 assert.deepEqual(mask.slice((20*30+15)*4,(20*30+15)*4+3),rgb)
 assert.deepEqual(original,before)
})

test('one-pixel brush restores exactly one column at fractional pointer positions',()=>{
 const original=new Uint8ClampedArray(20*20*4).fill(255),mask=new Uint8ClampedArray(original.length)
 paintForeground(mask,original,20,20,{x:7.13,y:2.19},{x:7.89,y:16.88},.5,true)
 for(let y=0;y<20;y++)for(let x=0;x<20;x++)assert.equal(mask[(y*20+x)*4+3],x===7&&y>=2&&y<=16?255:0,`pixel ${x},${y}`)
})
test('square brush reaches corners while circular brush preserves them',()=>{
 const original=new Uint8ClampedArray(12*12*4).fill(255)
 const circle=new Uint8ClampedArray(original.length),square=new Uint8ClampedArray(original.length)
 for(const [pixels,shape] of [[circle,'circle'],[square,'square']])paintForeground(pixels,original,12,12,{x:6,y:6},{x:6,y:6},3,true,shape)
 assert.equal(circle[(3*12+3)*4+3],0)
 assert.equal(square[(3*12+3)*4+3],255)
 assert.ok(square.filter((v,i)=>i%4===3&&v).length>circle.filter((v,i)=>i%4===3&&v).length)
 assert.equal(square[3],0)
})
test('brush interpolation covers fast movements and clips at image edges',()=>{
 const original=new Uint8ClampedArray(25*20*4).fill(255),pixels=new Uint8ClampedArray(original.length)
 paintForeground(pixels,original,25,20,{x:-5,y:8.5},{x:40,y:8.5},.5,true,'square')
 for(let x=0;x<25;x++)assert.equal(pixels[(8*25+x)*4+3],255)
 assert.equal(pixels.length,25*20*4)
})

test('full-body input retains aspect ratio, vertical space and symmetric margin',()=>{
 const result=fitReference({left:20,top:10,right:220,bottom:810},8)
 assert.equal(result.height,1024*.84)
 assert.equal(result.width/result.height,.25)
 assert.equal(result.y,(1024-result.height)/2)
 assert.equal(result.x,(1024-result.width)/2)
})
test('no valid foreground cannot produce a prepared image',()=>{
 assert.throws(()=>fitReference({left:20,top:0,right:10,bottom:80},8))
})
test('sharpening leaves smooth colours and alpha edges unchanged',()=>{
 const pixels=new Uint8ClampedArray(5*5*4)
 for(let i=0;i<pixels.length;i+=4)pixels.set([110,120,130,255],i)
 assert.deepEqual(sharpenReference(pixels,5,5),pixels)
 pixels.set([200,200,200,0],(2*5+2)*4)
 assert.deepEqual(sharpenReference(pixels,5,5),pixels)
})
test('optional sharpening has bounded colour change and never mutates input',()=>{
 const pixels=new Uint8ClampedArray(5*5*4)
 for(let i=0;i<pixels.length;i+=4)pixels.set([100,100,100,255],i)
 pixels.set([180,120,80,255],(2*5+2)*4)
 const before=new Uint8ClampedArray(pixels),result=sharpenReference(pixels,5,5)
 assert.deepEqual(pixels,before)
 assert.notDeepEqual(result,pixels)
 for(let i=0;i<pixels.length;i++)assert.ok(i%4===3?result[i]===pixels[i]:Math.abs(result[i]-pixels[i])<=8)
})
