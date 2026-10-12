const fs=require('node:fs');const {chromium}=require('/tmp/labelx-m03-browser/node_modules/playwright');
(async()=>{
const b=await chromium.launch({headless:true});const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(10000);
const calls=[];p.on('response',r=>{if(r.url().includes('/api/'))calls.push({url:r.url(),status:r.status()})});
await p.goto('http://localhost:3303/login');await p.locator('#username').fill('t046_reviewer');await p.locator('#password').fill('isolated-review-browser-2026');await p.locator('button[type=submit]').click();await p.waitForURL('http://localhost:3303/');
await p.goto('http://localhost:3303/review?run=1');
await p.waitForTimeout(1000);
await p.screenshot({path:'/tmp/labelx-m03-browser-evidence/reviewer-before-claim.png',fullPage:true});
console.log('BEFORE',await p.locator('body').innerText());
await p.locator('.lx-toolbar button.lx-btn--primary').click();
await p.getByRole('button',{name:'Vào kiểm tra frame (Workspace)',exact:true}).click();
await p.waitForTimeout(1500);
const text=await p.locator('body').innerText();console.log('AFTER',text);
await p.screenshot({path:'/tmp/labelx-m03-browser-evidence/reviewer-claimed-workspace.png',fullPage:true});
const decision=p.locator('button').filter({hasText:/^Lưu quyết định$/});
const result={fixture:true,test_policy:true,text,calls,workspaceMounted:await p.locator('.lx-stage__view').count()>0,decisionDisabled:await decision.count()>0?await decision.isDisabled():null};
fs.writeFileSync('/tmp/labelx-m03-browser-evidence/reviewer-handoff.json',JSON.stringify(result,null,2));await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
