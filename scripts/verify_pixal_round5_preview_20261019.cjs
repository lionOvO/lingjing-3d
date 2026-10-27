const {chromium}=require('%USERPROFILE%/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const target='D:/灵境造物/tmp/pixal-round5-preview-verified-20261019.json';
 if(fs.existsSync(target))throw Error('Preserve previous preview evidence');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 const rows=[];
 try{
  const page=await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18765/tmp/inspect-pixal-round5-20261019.html');
  for(const trial of [
   {model:'PixalFullPipeline_Person_round5-final-chain-person-20261019_00001_.glb',mode:'original',axis:'+z'},
   {model:'PixalFullPipeline_Person_round5-naf-global-person-20261019_00001_.glb',mode:'base',axis:'+y'}
  ]){
   await page.evaluate(trial=>{for(const key of ['model','mode','axis'])document.querySelector('#'+key).value=trial[key];update();},trial);
   await page.waitForFunction(trial=>{const w=document.querySelector('#view').contentWindow;return w&&new URL(w.location.href).searchParams.get('model')===trial.model&&(w.ready||w.error);},trial,{timeout:120000});
   const state=await page.evaluate(()=>{const w=document.querySelector('#view').contentWindow;return {url:w.location.href,ready:w.ready,error:w.error,info:w.document.querySelector('#info').textContent};});
   if(!state.ready||state.error||errors.length)throw Error(JSON.stringify({state,errors}));
   rows.push({trial,state});
  }
 }finally{await browser.close();}
 fs.writeFileSync(target,JSON.stringify({completed:true,rows},null,2));
 console.log(target);
})().catch(e=>{console.error(e);process.exit(1)});
