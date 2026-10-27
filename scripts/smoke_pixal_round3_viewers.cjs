const {chromium}=require('%USERPROFILE%/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
const root='D:/灵境造物/tmp/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 const results=[];
 try {
  for(const [html,metrics,onlyLatest] of [
   ['inspect-pixal-pipeline-20261011.html','pixal-round3-viewer-metrics-20261011.json',true],
   ['inspect-pixal-uv-comparison-20261011.html','pixal-uv-comparison-viewer-metrics-20261011.json',false]]){
   const rows=JSON.parse(fs.readFileSync(root+metrics,'utf8'));
   const page=await browser.newPage({viewport:{width:1100,height:900}});
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:18765/tmp/'+html);
   await page.waitForFunction(()=>window.ready||window.error,null,{timeout:60000});
   if(await page.evaluate(()=>window.error))throw Error(await page.evaluate(()=>window.error));
   if(await page.locator('#sample option').count()!==rows.length)throw Error('Sample inventory mismatch');
   let count=0;
   for(let i=0;i<rows.length;i++){
    if(onlyLatest&&!rows[i].label.includes('round3-sparse-resume'))continue;
    const filename=rows[i].model.split(/[\\/]/).pop();
    await page.selectOption('#sample',String(i));
    await page.waitForFunction(name=>window.ready&&document.querySelector('#info').textContent.startsWith(name),filename,{timeout:60000});
    await page.selectOption('#mode','base');await page.locator('[data-axis="angle"]').click();
    await page.selectOption('#mode','original');await page.locator('[data-axis="top"]').click();
    count++;console.log(filename);
   }
   if(errors.length)throw Error(errors.join('\n'));
   if(count!==(onlyLatest?3:12))throw Error('Expected current validation samples missing');
   await page.screenshot({path:root+html.replace('.html','-smoke.png')});
   results.push({page:html,inventory:rows.length,reviewed_current_models:count,material_modes:['base','original'],views:['front','angle','top'],page_errors:errors});
   await page.close();
  }
  fs.writeFileSync(root+'pixal-round3-viewer-smoke-20261012.json',JSON.stringify(results,null,2));
  console.log('PASS current full and fixed-geometry viewers');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
