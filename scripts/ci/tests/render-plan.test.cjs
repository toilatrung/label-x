'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {render}=require('../render-plan.cjs');
const root=path.resolve(__dirname,'../../..'),plan=JSON.parse(fs.readFileSync(path.join(root,'docs/09-testing/test-matrix.json'),'utf8'));
test('HTML contains every phase/case without loading external resources',()=>{const html=render(plan);assert.equal((html.match(/data-phase=/g)||[]).length,62);for(const p of plan.phases)assert(html.includes('<td>'+p.id+'</td>'));assert(!/<(?:script|link|img)[^>]+(?:src|href)=/i.test(html));assert(html.includes('@page{size:A4 landscape'));});
test('three filters compose and empty matches stay empty',()=>{
 const html=render(plan),script=html.match(/<script>([\s\S]*?)<\/script>/)[1],ids={},handlers={};
 const rows=plan.cases.map(c=>({dataset:{phase:c.phase,state:c.implementation,level:c.level},hidden:false}));
 const el=id=>ids[id]||(ids[id]={value:'',textContent:'',addEventListener:(name,cb)=>handlers[id+':'+name]=cb});
 vm.runInNewContext(script,{document:{getElementById:el,querySelectorAll:()=>rows},window:{print(){}}});
 el('state').value='implemented';handlers['state:change']();assert.equal(rows.filter(r=>!r.hidden).length,1);
 el('phase').value='p0_snapshot';handlers['phase:change']();assert.equal(rows.filter(r=>!r.hidden).length,0);
 el('state').value='planned';el('level').value='contract';handlers['level:change']();assert.equal(rows.filter(r=>!r.hidden).length,2);
 el('phase').value='';el('state').value='';el('level').value='';handlers['phase:change']();assert.equal(rows.filter(r=>!r.hidden).length,62);
});
