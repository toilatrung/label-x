#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const ROOT=path.resolve(__dirname,'../..');
const PLAN=path.join(ROOT,'docs/09-testing/test-matrix.json');
class Blocked extends Error {}
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const load=p=>JSON.parse(fs.readFileSync(p,'utf8'));
function inside(root,p){const r=path.resolve(root),q=path.resolve(root,p);if(q!==r&&!q.startsWith(r+path.sep))throw new Error('Path outside workspace');return q;}
function validatePlan(plan,root=ROOT){
 if(plan.schema_version!==1||!Array.isArray(plan.phases)||!Array.isArray(plan.cases))throw Error('Invalid plan schema');
 const phases=new Map(),ids=new Set();
 for(const p of plan.phases){if(!/^[a-z][a-z0-9_]+$/.test(p.id)||phases.has(p.id)||!Array.isArray(p.dependencies)||typeof p.required_for_mvp!=='boolean'||!p.source)throw Error('Invalid/duplicate phase');phases.set(p.id,p);}
 const visited=new Set(),stack=new Set();function visit(id){if(stack.has(id))throw Error('Cyclic phase dependencies');if(visited.has(id))return;if(!phases.has(id))throw Error('Unknown phase dependency');stack.add(id);for(const d of phases.get(id).dependencies)visit(d);stack.delete(id);visited.add(id);}for(const id of phases.keys())visit(id);
 for(const c of plan.cases){if(!/^[A-Z]+-\d+$/.test(c.id)||ids.has(c.id)||!phases.has(c.phase)||!c.expected||!c.fixtures||!Array.isArray(c.requirements)||c.requirements.length===0||!['planned','implemented'].includes(c.implementation))throw Error('Invalid/duplicate case');ids.add(c.id);if(c.implementation==='implemented')validateBinding(c,root);else if(c.test_nodeid!==null||c.runner!=='unbound')throw Error('Planned case cannot claim a binding');}
 for(const id of phases.keys())if(!plan.cases.some(c=>c.phase===id))throw Error('Phase without cases');
 return {phases:phases.size,cases:ids.size,implemented:plan.cases.filter(c=>c.implementation==='implemented').length};
}
function validateBinding(c,root){
 if(c.runner!=='pytest'||typeof c.test_nodeid!=='string'||!c.test_nodeid.includes('::'))throw new Blocked('Unbound/unsupported test runner: '+c.id);
 const [p,...parts]=c.test_nodeid.split('::');if(!p.endsWith('.py')||parts.some(x=>!/^\w+(?:\[[^\r\n]+\])?$/.test(x)))throw Error('Unsafe pytest node ID');
 const base=path.join(root,'src/backend'),file=inside(base,p);
 if(!fs.existsSync(file))throw new Blocked('Test file missing: '+c.id);
 const actual=fs.realpathSync(file),realBase=fs.realpathSync(base);if(!actual.startsWith(realBase+path.sep))throw Error('Test symlink escapes backend');
 return c.test_nodeid;
}
function junitSummary(xml){
 // Strict reader for pytest-produced JUnit, not a general XML parser.
 if(typeof xml!=='string'||/<!DOCTYPE|<!ENTITY/.test(xml)||!/<testsuite\b/.test(xml)||!/<\/testsuite>/.test(xml))throw Error('Invalid pytest JUnit');
 const count=(xml.match(/<testcase\b/g)||[]).length;
 const suites=[...xml.matchAll(/<testsuite\b([^>]*)>/g)];let declared=0;
 for(const s of suites){const attrs=Object.fromEntries([...s[1].matchAll(/(tests|failures|errors|skipped)=["'](\d+)["']/g)].map(m=>[m[1],Number(m[2])]));if(!['tests','failures','errors','skipped'].every(k=>Number.isSafeInteger(attrs[k])))throw Error('JUnit counters missing');declared+=attrs.tests;if(attrs.failures||attrs.errors||attrs.skipped)throw new Blocked('Failed/error/skipped mandatory tests');}
 if(!count||declared!==count||/<(?:failure|error|skipped)\b/.test(xml))throw new Blocked('Zero/inconsistent/skipped JUnit tests');
 return {tests:count,failures:0,errors:0,skipped:0};
}
function selected(plan,id,root=ROOT){
 const phase=plan.phases.find(p=>p.id===id);if(!phase)throw Error('Unknown phase: '+id);
 const cases=plan.cases.filter(c=>c.phase===id);if(cases.some(c=>c.implementation!=='implemented'))throw new Blocked('Tests not implemented: '+cases.filter(c=>c.implementation!=='implemented').map(c=>c.id).join(', '));
 const nodes=cases.map(c=>validateBinding(c,root));if(new Set(nodes).size!==nodes.length)throw Error('Each mandatory case needs a distinct executable test');
 return {phase,cases,nodes};
}
function policyReady(policy,root=ROOT){
 const numeric=['minimum_reference_errors','minimum_errors_per_group','minimum_recall_at_20','minimum_effort_reduction','residual_non_inferiority_margin','false_positive_non_inferiority_margin'];
 if(policy?.status!=='approved'||!policy.reference_version||!policy.score_version||!numeric.every(k=>Number.isFinite(policy[k])&&policy[k]>=0)||!['reference_sha256','model_sha256'].every(k=>/^[a-f0-9]{64}$/.test(policy[k]||'')))throw new Blocked('Approved numeric evaluation policy/reference/model not supplied');
 if(!Number.isInteger(policy.minimum_reference_errors)||policy.minimum_reference_errors<1||!Number.isInteger(policy.minimum_errors_per_group)||policy.minimum_errors_per_group<1||numeric.slice(2).some(k=>policy[k]>1))throw new Blocked('Invalid evaluation thresholds');
 if(typeof policy.approved_decision!=='string'||!/^\.agent\/governance\/decisions\/[^/]+\.html$/.test(policy.approved_decision))throw new Blocked('Approval record missing');
 const recordPath=inside(root,policy.approved_decision);if(!fs.existsSync(recordPath))throw new Blocked('Approved evaluation decision file missing');
 const record=fs.readFileSync(recordPath,'utf8');
 if(!/\*\*Status\*\*:\s*`accepted`/.test(record)||!/\*\*Decision Type\*\*:\s*`(?:evaluation|acceptance|testing)`/.test(record))throw new Blocked('Evaluation policy lacks accepted governance evidence');
 return true;
}
function receiptReady(plan,id,dir,sha,root=ROOT){
 const {cases}=selected(plan,id,root),receiptPath=path.join(dir,'phase-'+id+'.json');if(!fs.existsSync(receiptPath))throw new Blocked('Dependency evidence missing: '+id);const receipt=load(receiptPath);
 if(receipt.status!=='passed'||receipt.phase!==id||receipt.source_sha!==sha||receipt.plan_sha256!==hash(JSON.stringify(plan)))throw new Blocked('Stale/mismatched/not-passed phase evidence: '+id);
 const want=cases.map(c=>c.id).sort(),got=[...(receipt.case_ids||[])].sort();if(JSON.stringify(want)!==JSON.stringify(got))throw new Blocked('Missing mandatory case evidence: '+id);
 const junitPath=path.join(dir,'junit-'+id+'.xml');if(!fs.existsSync(junitPath))throw new Blocked('JUnit evidence missing: '+id);const xml=fs.readFileSync(junitPath,'utf8');if(hash(xml)!==receipt.junit_sha256)throw new Blocked('JUnit checksum mismatch: '+id);
 const summary=junitSummary(xml);if(summary.tests<cases.length)throw new Blocked('Too few executed cases: '+id);
 return receipt;
}
function suiteReady(plan,dir,sha,root=ROOT){
 if(!/^[a-f0-9]{40}$/.test(sha))throw new Blocked('Release requires a real immutable Git SHA');
 validatePlan(plan,root);for(const p of plan.phases.filter(p=>p.required_for_mvp))receiptReady(plan,p.id,dir,sha,root);return true;
}
function upstreamReady(run,sha,workflow){
 if(!/^[a-f0-9]{40}$/.test(sha)||run.status!=='completed'||run.conclusion!=='success'||run.head_sha!==sha||run.head_branch!=='main'||run.path!==workflow||!['push','workflow_dispatch'].includes(run.event))throw new Blocked('Upstream run must be successful trusted main, matching SHA and workflow');return true;
}
function deployReady(environment,enabled,root=ROOT){
 if(!['staging','production'].includes(environment)||enabled!=='true')throw new Blocked('CD is not configured/enabled');
 for(const p of ['scripts/deploy/'+environment+'.sh','scripts/deploy/rollback.sh','scripts/deploy/smoke.sh'])if(!fs.existsSync(inside(root,p)))throw new Blocked('Deployment target hook missing: '+p);
 return true;
}
function environmentReady(config,name){
 const approval=config?.protection_rules?.find(r=>r.type==='required_reviewers');
 if(config?.name!==name||!['staging','production','labelx-evaluation'].includes(name)||!approval||!Array.isArray(approval.reviewers)||approval.reviewers.length===0||approval.prevent_self_review!==true)throw new Blocked('Environment requires reviewers and prevent_self_review');
 const policy=config.deployment_branch_policy;if(!policy||(policy.protected_branches!==true&&policy.custom_branch_policies!==true))throw new Blocked('Environment needs restricted deployment branches');return true;
}
function stagingReady(receipt,run,sha,ciRunId,testRunId){
 if(run?.status!=='completed'||run.conclusion!=='success'||run.head_branch!=='main'||run.path!=='.github/workflows/cd.yml'||run.event!=='workflow_dispatch'||receipt?.environment!=='staging'||receipt.status!=='passed'||receipt.source_sha!==sha||String(receipt.staging_run_id)!==String(run.id)||String(receipt.ci_run_id)!==String(ciRunId)||String(receipt.test_run_id)!==String(testRunId))throw new Blocked('Production requires successful staging of exactly the same artifact/test runs');return true;
}
function sourceSha(){if(/^[a-f0-9]{40}$/.test(process.env.GITHUB_SHA||''))return process.env.GITHUB_SHA;const r=spawnSync('git',['rev-parse','HEAD'],{cwd:ROOT,encoding:'utf8',stdio:['ignore','pipe','ignore']});return r.status===0?r.stdout.trim():'local-unversioned';}
function runPhase(plan,id,dir,root=ROOT){
 const sha=sourceSha(),receipt={schema_version:1,phase:id,source_sha:sha,plan_sha256:hash(JSON.stringify(plan)),status:'blocked',case_ids:[],test_summary:null};fs.mkdirSync(dir,{recursive:true});
 try{
  validatePlan(plan,root);const {phase,cases,nodes}=selected(plan,id,root);
  for(const dep of phase.dependencies)receiptReady(plan,dep,dir,sha,root);
  if(cases.some(c=>c.level==='evaluation')){if(!process.env.LABELX_EVALUATION_POLICY)throw new Blocked('Evaluation requires an approved policy');const policyPath=inside(root,process.env.LABELX_EVALUATION_POLICY);if(!fs.existsSync(policyPath))throw new Blocked('Evaluation policy file missing');const policy=load(policyPath);policyReady(policy,root);receipt.evaluation_policy_sha256=hash(JSON.stringify(policy));receipt.reference_version=policy.reference_version;receipt.reference_sha256=policy.reference_sha256;receipt.model_sha256=policy.model_sha256;receipt.score_version=policy.score_version;}
  const junit=path.join(dir,'junit-'+id+'.xml');
  const result=spawnSync('uv',['run','--frozen','python','-m','pytest',...nodes,'-q','--junitxml='+junit,'--strict-markers'],{cwd:path.join(root,'src/backend'),encoding:'utf8',stdio:['ignore','pipe','pipe'],shell:false});
  const privateDir=inside(root,'.ci-artifacts/private');fs.mkdirSync(privateDir,{recursive:true});
  fs.writeFileSync(path.join(privateDir,id+'.log'),String(result.stdout||'')+'\n'+String(result.stderr||''));
  if(result.error)throw result.error;if(result.status!==0)throw Error('pytest failed, exit '+result.status);
  const xml=fs.readFileSync(junit,'utf8'),summary=junitSummary(xml);if(summary.tests<cases.length)throw new Blocked('Insufficient executed tests');
  Object.assign(receipt,{status:'passed',case_ids:cases.map(c=>c.id),test_summary:summary,junit_sha256:hash(xml)});
 }catch(e){receipt.reason=e.message;if(!(e instanceof Blocked))receipt.status='failed';}
 fs.writeFileSync(path.join(dir,'phase-'+id+'.json'),JSON.stringify(receipt,null,2)+'\n');console.log(receipt.status.toUpperCase()+': '+id+(receipt.reason?' — '+receipt.reason:''));return receipt.status==='passed'?0:receipt.status==='blocked'?2:1;
}
function cli(args){const command=args.shift(),plan=load(PLAN),get=k=>{const i=args.indexOf(k);return i<0?undefined:args[i+1]};const dir=inside(ROOT,get('--evidence-dir')||'.ci-artifacts/phases');
 if(command==='validate-plan'){console.log(JSON.stringify(validatePlan(plan)));return 0;}
 if(command==='run'){const id=get('--phase');return runPhase(plan,id,dir);}
 if(command==='run-mvp'){for(const p of plan.phases.filter(p=>p.required_for_mvp)){const status=runPhase(plan,p.id,dir);if(status)return status;}return 0;}
 if(command==='verify-suite'){suiteReady(plan,dir,get('--sha'));console.log('MVP_TEST_EVIDENCE_PASS');return 0;}
 if(command==='verify-upstream'){upstreamReady(load(inside(ROOT,get('--file'))),get('--sha'),get('--workflow'));console.log('UPSTREAM_PASS');return 0;}
 if(command==='verify-environment'){environmentReady(load(inside(ROOT,get('--file'))),get('--environment'));console.log('ENVIRONMENT_PROTECTION_PASS');return 0;}
 if(command==='verify-staging'){stagingReady(load(inside(ROOT,get('--receipt'))),load(inside(ROOT,get('--run'))),get('--sha'),get('--ci-run-id'),get('--test-run-id'));console.log('STAGING_PROMOTION_PASS');return 0;}
 if(command==='deploy-preflight'){deployReady(get('--environment'),process.env.LABELX_CD_ENABLED);console.log('DEPLOY_PREFLIGHT_PASS');return 0;}
 throw Error('Commands: validate-plan, run --phase ID, run-mvp, verify-suite --sha SHA, verify-upstream --file JSON --sha SHA --workflow PATH, deploy-preflight --environment staging|production');
}
module.exports={Blocked,inside,hash,validatePlan,validateBinding,junitSummary,selected,policyReady,receiptReady,suiteReady,upstreamReady,deployReady,environmentReady,stagingReady,runPhase};
if(require.main===module){try{process.exitCode=cli(process.argv.slice(2));}catch(e){console.error((e instanceof Blocked?'BLOCKED: ':'FAILED: ')+e.message);process.exitCode=e instanceof Blocked?2:1;}}
