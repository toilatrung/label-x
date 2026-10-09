const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..');
const context={console, URLSearchParams, location:{search:'?frame=005678'},window:{},sessionStorage:{getItem:()=>null,setItem:()=>{}},document:{addEventListener:()=>{}},Map,fetch:()=>{throw Error('Unexpected fetch')}};
context.window.location=context.location;vm.createContext(context);vm.runInContext(fs.readFileSync(root+'/screens/review-data.js','utf8'),context);
let runtime=fs.readFileSync(root+'/screens/support.js','utf8').replace(/\}\)\(\);\s*$/, 'window.test={definition,expand};})();');
vm.runInContext(runtime,context);
const results=[];
for(const filename of fs.readdirSync(root+'/screens').filter(n=>n.endsWith('.dc.html'))){
 const source=fs.readFileSync(root+'/screens/'+filename,'utf8');const def=context.window.test.definition(source);
 const component=new def.Class();component.props=Object.fromEntries(Object.entries(def.props).filter(([k])=>k!=='$preview').map(([k,v])=>[k,v.default]));
 // Start with defaults; then exercise all tabs returned by each screen's own logic.
 let vals=component.renderVals();const ownTabs=vals.tabs?.filter(t=>typeof t.pick==='function') || [];
 const render=()=>{const handlers=[];const out=context.window.test.expand(def.template,component.renderVals(),handlers);if(/{{|<sc-(for|if)/.test(out))throw Error(filename+': unresolved template');for(const h of handlers)if(typeof h.callback!=='function')throw Error(filename+': missing callback');return out;};
 const out=render();component.draw=async()=>{};
 for(const tab of ownTabs){tab.pick();render();}
 if(filename==='ReviewQueues.dc.html'){
  component.state={search:'005678',priority:'Tất cả',alert:'Tất cả'};const filtered=render();if(!filtered.includes('Ảnh 002')||filtered.includes('<h2 class="lx-h2"><a href="ReviewWorkspace.dc.html?frame=001234"'))throw Error('Search mismatch');
  component.state={search:'missing'};if(!render().includes('Không có ảnh khớp bộ lọc'))throw Error('Empty mismatch');
 }
 if(filename==='ReviewWorkspace.dc.html') {
  for(const text of ['Issue Review','Frame Review','QC-00128','VEH-03','CASE-021','CASE-034','CASE-040','Loại lỗi đã xác nhận','Mức độ','Lưu và chuyển issue tiếp','Mô hình thị giác'])if(!out.includes(text))throw Error('Missing original Workspace content: '+text);
  component.renderVals().setFrame();const frameView=render();if(!frameView.includes('Nhấn vào một object để tạo issue mới.')||!frameView.includes('opacity="1"'))throw Error('Frame mode mismatch');
  component.renderVals().setIssue();const issueView=render();if(!issueView.includes('Đường liền: annotation hiện tại')||!issueView.includes('opacity="0.3"'))throw Error('Issue mode mismatch');
 }
 results.push({filename,tabs:ownTabs.length});
}
console.log(JSON.stringify({screens:results.length,tabStates:results.reduce((sum,x)=>sum+x.tabs,0),status:'passed'},null,2));
