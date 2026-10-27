const {chromium}=require('%USERPROFILE%/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const reportTag=process.env.PIXAL_RENDER_REPORT_TAG||'round5';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 const rows=[];
 try{
  for(const model of process.argv.slice(2))for(const mode of ['original','base'])for(const axis of ['+z','angle','+y']){
   const path='D:/灵境造物/tmp/'+reportTag+'-'+model.replace('.glb','')+'_'+mode+'_'+axis.replace('+','plus')+'.png';
   if(fs.existsSync(path))throw Error('Preserve previous render: '+path);
   const page=await browser.newPage({viewport:{width:900,height:900}});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:18765/tmp/texture-audit-neural-20261012.html?'+new URLSearchParams({model,mode,axis}));
   await page.waitForFunction(()=>window.ready||window.error,null,{timeout:120000});
   const error=await page.evaluate(()=>window.error);
   if(error||errors.length)throw Error(error||errors.join('\n'));
   await page.screenshot({path});
   rows.push({model,mode,axis,path,info:await page.locator('#info').innerText()});
   console.log(path);await page.close();
  }
 }finally{await browser.close();}
 const report='D:/灵境造物/tmp/pixal-'+reportTag+'-renders-20261019.json';
 if(fs.existsSync(report))throw Error('Preserve previous render report');
 fs.writeFileSync(report,JSON.stringify(rows,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
