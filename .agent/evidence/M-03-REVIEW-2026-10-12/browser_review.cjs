const fs=require('node:fs');
const {chromium}=require('/tmp/labelx-m03-browser/node_modules/playwright');
const root='/tmp/labelx-m03-browser-evidence'; fs.mkdirSync(root,{recursive:true});
const base='http://localhost:3303';
const roles=['reviewer','qalead','superadmin','annotator','qc_admin','product_owner','data_model_owner'];
(async()=>{
 const browser=await chromium.launch({headless:true});
 const rows=[];
 for(const role of roles){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.setDefaultTimeout(10000);
  const calls=[];page.on('response',r=>{if(r.url().includes('/api/'))calls.push({url:r.url(),status:r.status()})});
  await page.goto(base+'/login');await page.locator('#username').fill('t046_'+role);
  await page.locator('#password').fill('isolated-review-browser-2026');await page.locator('button[type=submit]').click();await page.waitForURL(base+'/');
  for(const path of ['/review','/review/workspace?frame_id=1','/escalations','/rework']){
   const response=await page.goto(base+path);await page.waitForTimeout(500);
   const body=await page.locator('body').innerText();
   const name=role+'-'+path.replace(/[^a-z0-9]+/gi,'-');
   await page.screenshot({path:root+'/'+name+'.png',fullPage:true});
   rows.push({role,path,httpStatus:response.status(),text:body,annotations:await page.locator('#snapshot-annotations-layer rect').count(),calls:[...calls]});
   console.log(role,path,response.status(),body.includes('403')?'403 guard':body.slice(-110).replace(/\n/g,' '));
  }
  await context.close();
 }
 fs.writeFileSync(root+'/role-matrix.json',JSON.stringify({sha:'0662c1a73d5b80c1c4ca727f439c93f4f55abe73',fixture:true,rows},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
