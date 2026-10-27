// Isolated UI fixture server. It never forwards requests to the real backend,
// calls an AI service, or queues a GPU task. Run from frontend/ with Node.
import {createServer} from 'vite'
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs'
import {resolve} from 'node:path'
const directory=resolve('../tmp/preprocess-ux-20261022')
mkdirSync(directory,{recursive:true})
const records={uploads:[],tasks:[],projects:[]}
const user={id:1,username:'交互测试',email:'qa@example.test'}
let task=null
const server=await createServer({server:{host:'127.0.0.1',port:5174,strictPort:true,proxy:{}},plugins:[{
 name:'isolated-preparation-qa',configureServer(server){
  server.config.server.proxy=undefined
  server.httpServer.on('upgrade',(req,socket)=>{if(req.url.startsWith('/api/'))socket.destroy()})
  server.middlewares.use(async(req,res,next)=>{
  const path=(req.url||'').split('?')[0]
  if(path.startsWith('/__qa/')){const file=path.endsWith('mask.png')?'mask.png':'source.png';res.setHeader('Content-Type','image/png');res.end(readFileSync(resolve(directory,file)));return}
  if(!path.startsWith('/api/')){next();return}
  const chunks=[];for await(const chunk of req)chunks.push(chunk)
  const body=Buffer.concat(chunks),json=()=>JSON.parse(body.toString()||'{}')
  const send=(data,status=200)=>{res.statusCode=status;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data))}
  const png=(file)=>{res.setHeader('Content-Type','image/png');res.end(readFileSync(resolve(directory,file)))}
  const persist=()=>writeFileSync(resolve(directory,'browser-requests.json'),JSON.stringify(records,null,2))
  if(path==='/api/v1/auth/login'){send({access_token:'isolated-qa-token',token_type:'bearer'});return}
  if(path==='/api/v1/auth/me'){send(user);return}
  if(path==='/api/v1/generation/capabilities'){send({available_modes:['fast','balanced','high_quality'],pbr_required:false,texture_resolutions:['512','1024'],default_seed:109020838});return}
  if(path==='/api/v1/studio/images/vision-status'){send({configured:true});return}
  if(path==='/api/v1/studio/images/analyze-reference'){send({version:1,width:512,height:1536,background_kind:'complex',background_color:'#808080',subject_bounds:null,warnings:[]});return}
  if(path==='/api/v1/studio/images/import-url'){png('source.png');return}
  if(path==='/api/v1/studio/images/remove-background'){res.setHeader('X-Foreground-Model','u2net');png('mask.png');return}
  if(path==='/api/v1/studio/images/vision-preparation'){
   const review=body.includes(Buffer.from('name="candidate"'))
   send(review?{verdict:'fail',missing_parts:['杆顶（测试提示）'],background_residue:[],explanation:'测试复核：请人工对照顶部细节。',confidence:.8,model:'qa'}:{subject_type:'object',description:'细长装饰杆，用于验证小画笔和缩放。',bounds:null,keep_parts:['顶端','杆身','底座'],exclude_parts:[],warnings:[],confidence:.9,recommended_model:'u2net',model:'qa'});return
  }
  if(path==='/api/v1/uploads'){
   const start=body.indexOf(Buffer.from([137,80,78,71,13,10,26,10])),end=body.indexOf(Buffer.from([73,69,78,68]),start)+8
   const index=records.uploads.length
   if(start>=0&&end>start)writeFileSync(resolve(directory,`upload-${index}.png`),body.subarray(start,end))
   records.uploads.push({index,filename:body.toString('latin1',0,Math.max(0,start)).match(/filename="([^"]+)"/)?.[1]});persist()
   await new Promise(r=>setTimeout(r,200));send({url:`http://127.0.0.1:5174/__qa/source.png?upload=${index}`,object_name:`qa-${index}.png`});return
  }
  if(path==='/api/v1/projects'&&req.method==='POST'){records.projects.push(json());persist();send({id:9001,...json()});return}
  if(path==='/api/v1/tasks'&&req.method==='POST'){
   records.tasks.push(json());persist()
   if(records.tasks.length===1){send({detail:'测试：模拟提交失败，请重新点击确认。'},400);return}
   task={id:9001,project_id:9001,task_type:'object_model',status:'pending',output_format:'glb',retry_count:0,created_at:new Date().toISOString(),...json()};send(task);return
  }
  if(path==='/api/v1/tasks/9001'){send(task);return}
  if(path==='/api/v1/agents/workflow/9001'){send({task_id:9001,status:'pending',state:{}});return}
  if(path.startsWith('/api/v1/projects/')){send({id:9001,name:'隔离交互测试'});return}
  if(path.endsWith('/progress')){res.statusCode=404;res.end();return}
  send([])
 })}
}]})
await server.listen()
console.log('Isolated UI QA: http://127.0.0.1:5174/generate (fixture login: qa / qa)')
