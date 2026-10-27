// Local UI fixtures: no request is forwarded to the user's database or GPU.
import {createServer} from 'vite'
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs'
import {resolve} from 'node:path'
const directory=resolve('../tmp/viewer-actions-20261022')
mkdirSync(directory,{recursive:true})
const records=[]
const persist=()=>writeFileSync(resolve(directory,'browser-requests.json'),JSON.stringify(records,null,2))
const assets=Array.from({length:7},(_,i)=>({id:9007-i,project_id:9001,name:`检视测试模型 ${9007-i}`,project_name:'隔离测试项目',tags:[],project_type:'object_model',format:'glb',created_at:'2026-10-22T01:00:00',quality_score:.6,preview_available:true,parameters:{},metadata:{face_count:503689,vertex_count:306665,file_size_mb:14.46,has_pbr:true}}))
const deleted=new Set()
const model=readFileSync(resolve('../tmp/high-quality-integration/web-task-33.glb'))
const server=await createServer({server:{host:'127.0.0.1',port:5175,strictPort:true,proxy:{}},plugins:[{
 name:'isolated-asset-qa',configureServer(server){
  server.config.server.proxy=undefined
  server.httpServer.on('upgrade',(req,socket)=>{if(req.url.startsWith('/api/'))socket.destroy()})
  server.middlewares.use(async(req,res,next)=>{
   const url=new URL(req.url,'http://localhost'),path=url.pathname
   if(!path.startsWith('/api/'))return next()
   const chunks=[];for await(const chunk of req)chunks.push(chunk)
   const send=(data,status=200)=>{res.statusCode=status;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data))}
   if(path==='/api/v1/auth/login')return send({access_token:'isolated-qa-token',token_type:'bearer'})
   if(path==='/api/v1/auth/me')return send({id:1,username:'隔离交互测试',email:'qa@example.test'})
   if(path==='/api/v1/studio/assets')return send(assets.filter(item=>deleted.has(item.id)===(url.searchParams.get('deleted')==='true')))
   const match=path.match(/^\/api\/v1\/studio\/assets\/(\d+)(\/restore|\/file)?$/)
   if(match){
    const id=Number(match[1])
    if(match[2]==='/file'){res.setHeader('Content-Type','model/gltf-binary');return res.end(model)}
    if(req.method==='DELETE'){deleted.add(id);records.push({action:'trash',id});persist();return send({id,deleted:true})}
    if(match[2]==='/restore'){deleted.delete(id);records.push({action:'restore',id});persist();return send({id,deleted:false})}
   }
   const task=path.match(/^\/api\/v1\/tasks\/(\d+)$/)
   if(task)return send({id:Number(task[1]),project_id:9001,task_type:'object_model',status:'completed',output_format:'glb',output_model_url:'/api/v1/models/9007/content',retry_count:0,created_at:'2026-10-22T01:00:00',quality_score:.6})
   if(path.match(/\/models\/\d+\/content$/)){res.setHeader('Content-Type','model/gltf-binary');return res.end(model)}
   if(path.match(/\/models\/\d+\/download$/)){records.push({action:'download'});persist();return send({download_url:'/api/v1/models/9007/content'})}
   if(path.match(/\/models\/\d+\/preview$/))return send({download_url:'/api/v1/models/9007/content'})
   if(path.match(/\/models\/\d+$/))return send({face_count:503689,vertex_count:306665,file_size_mb:14.46,has_pbr:true})
   if(path.startsWith('/api/v1/agents/workflow/'))return send({task_id:9007,status:'completed',state:{}})
   if(path.startsWith('/api/v1/projects/'))return send({id:9001,name:'隔离测试项目'})
   return send([])
  })
 }
}]})
await server.listen()
console.log('Isolated assets/viewer QA: http://127.0.0.1:5175/library (qa / qa)')
