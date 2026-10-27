const {chromium}=require('%USERPROFILE%/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 const rows=[];
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18765/tmp/pixal-model-gallery-20261019.html');
  for(const index of [0,1,2,3]){
   await page.locator('#model').selectOption(String(index));
   await page.waitForFunction(index=>window.error||(window.ready&&window.viewerState.index===index),index,{timeout:120000});
   const state=await page.evaluate(()=>({ready:window.ready,error:window.error,...window.viewerState}));
   if(!state.ready||state.error||errors.length)throw Error(JSON.stringify({state,errors}));
   const path='D:/灵境造物/tmp/pixal-gallery-model-'+index+'-20261019.png';
   await page.screenshot({path});
   rows.push({...state,screenshot:path});
   if(index===0){
    const canvas=page.locator('canvas'),box=await canvas.boundingBox();
    const before=await canvas.screenshot();
    await page.mouse.move(box.x+box.width*.45,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5,{steps:12});await page.mouse.up();
    const after=await canvas.screenshot();
    if(before.equals(after))throw Error('Dragging did not alter the view');
    rows[0].orbit_drag_changes_render=true;
    await page.locator('button[data-axis="front"]').click();
    await page.locator('#mode').selectOption('base');
    if(await page.evaluate(()=>window.viewerState.mode)!=='base')throw Error('Display switch failed');
    rows[0].base_color_switch_works=true;
    await page.locator('#mode').selectOption('original');
   }
  }
 }finally{await browser.close();}
 const target='D:/灵境造物/tmp/pixal-model-gallery-review-20261019.json';
 if(fs.existsSync(target))throw Error('Preserve previous inspection evidence');
 fs.writeFileSync(target,JSON.stringify({completed:true,rows},null,2));console.log(JSON.stringify(rows));
})().catch(e=>{console.error(e);process.exit(1)});
