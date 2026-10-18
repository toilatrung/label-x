// Run from repository root; uses an existing authenticated storage state, never a password.
// LABELX_PLAYWRIGHT_MODULE and LABELX_BROWSER_EXECUTABLE select installed browser tooling.
// node scripts/frontend/capture-issue-focus.cjs before|after
const {chromium}=require(process.env.LABELX_PLAYWRIGHT_MODULE || 'playwright-core');
const fs=require('fs');const assert=require('node:assert/strict');
(async()=>{
 if(!['before','after'].includes(process.argv[2])) throw new Error('Usage: capture-issue-focus.cjs before|after');
 const after=process.argv[2]==='after';
 const dir='src/frontend/evidence/issue-focus';
 const b=await chromium.launch({headless:true,executablePath:process.env.LABELX_BROWSER_EXECUTABLE});
 const c=await b.newContext({storageState:process.env.LABELX_CAPTURE_AUTH || '.cache/issue-focus/auth.json',viewport:{width:1440,height:1040},recordVideo:{dir:'.cache/issue-focus/video-'+(after?'after':'before'),size:{width:1440,height:1040}}});
 const p=await c.newPage();
 try {
 const live=await c.request.get('https://label-x.williamtrinh.online/api/frames/4/workspace/'); assert.equal(live.status(),200); const raw=await live.json();
 if(!fs.existsSync('.cache/issue-focus/frame.jpg')){
   const r=await c.request.get(raw.frame.image_url);assert.equal(r.status(),200);fs.writeFileSync('.cache/issue-focus/frame.jpg',await r.body());
 }
 if(after){
   const payload=JSON.parse(fs.readFileSync(dir+'/after-payload.json'));payload.frame.image_url='/captured-snapshot.jpg';
   await p.route('**/captured-snapshot.jpg',r=>r.fulfill({contentType:'image/jpeg',body:fs.readFileSync('.cache/issue-focus/frame.jpg')}));
   await p.route('**/api/**',async r=>{
     const request=r.request();const path=new URL(request.url()).pathname;
     if(path==='/api/frames/4/workspace/') return r.fulfill({json:payload});
     if(request.method()!=='GET') return r.fulfill({status:204});
     const response=await c.request.get('https://label-x.williamtrinh.online'+path+new URL(request.url()).search);
     return r.fulfill({status:response.status(),contentType:'application/json',body:await response.body()});
   });
 }
 await p.goto((after?(process.env.LABELX_REPLAY_ORIGIN || 'http://localhost:3012'):'https://label-x.williamtrinh.online')+'/review/workspace?frame_id=4');
 await p.getByRole('button',{name:'Issue tiếp ›',exact:true}).waitFor();
 await p.waitForTimeout(2000);
 if(after){assert.equal(await p.locator('[data-testid=issue-focus-image]').count(),1);assert.equal(await p.locator('[data-annotation-id] rect[stroke="#f2c14e"]').count(),2);}
 await p.screenshot({path:dir+'/'+(after?'after':'before')+'-issue-57.png'});
 await p.getByRole('button',{name:'Issue tiếp ›',exact:true}).click();await p.waitForTimeout(1200);
 if(after){assert.equal(await p.locator('[data-annotation-id="shape:9091"] rect[stroke="#f2c14e"]').count(),1);assert.equal(await p.locator('[data-annotation-id="shape:9090"] rect[stroke="#f2c14e"]').count(),0);}
 await p.screenshot({path:dir+'/'+(after?'after':'before')+'-issue-58.png'});
 await p.getByRole('button',{name:'Frame Review',exact:true}).click();await p.waitForTimeout(1200);
 if(after) assert.equal(await p.locator('[data-testid=issue-focus-image]').count(),0);
 await p.screenshot({path:dir+'/'+(after?'after':'before')+'-frame-review.png'});
 await p.getByRole('button',{name:'Issue Review',exact:true}).click();await p.waitForTimeout(1200);
 if(after) assert.equal(await p.locator('[data-testid=issue-focus-image]').count(),1);
 await p.getByRole('button',{name:'‹ Issue trước',exact:true}).first().click();await p.waitForTimeout(1200);
 if(after) {
   await p.setViewportSize({width:390,height:844});
   await p.screenshot({path:dir+'/after-mobile-390.png',fullPage:true});
 }
 const video=p.video();await c.close();await video.saveAs(dir+'/'+(after?'after-local-replay':'before-production')+'.webm');await b.close();
 console.log('PASS '+(after?'after local replay':'before production')+' issue 57 → 58 → Frame Review → Issue Review → 57');
 } finally { await c.close(); await b.close(); }
})();
