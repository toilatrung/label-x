#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {hash,junitSummary,inside}=require('./quality-gate.cjs');
const ROOT=path.resolve(__dirname,'../..');
function redacted(receipt,xml){
 const publicReceipt={schema_version:receipt.schema_version,phase:receipt.phase,source_sha:receipt.source_sha,plan_sha256:receipt.plan_sha256,status:receipt.status,case_ids:receipt.case_ids||[],test_summary:receipt.test_summary,evidence_export:'redacted-test-summary'};
 for(const k of ['evaluation_policy_sha256','reference_version','reference_sha256','model_sha256','score_version'])if(receipt[k]!==undefined)publicReceipt[k]=receipt[k];
 if(receipt.status!=='passed'){publicReceipt.reason=receipt.status==='blocked'?'Required tests or approved inputs unavailable':'Tests failed; inspect restricted runner logs';return {receipt:publicReceipt,xml:null};}
 if(hash(xml)!==receipt.junit_sha256)throw Error('Raw JUnit checksum mismatch');
 const summary=junitSummary(xml);
 const out='<testsuites><testsuite tests="'+summary.tests+'" failures="0" errors="0" skipped="0">'+Array.from({length:summary.tests},(_,i)=>'<testcase name="redacted-test-'+(i+1)+'" />').join('')+'</testsuite></testsuites>';
 Object.assign(publicReceipt,{test_summary:summary,raw_junit_sha256:receipt.junit_sha256,junit_sha256:hash(out)});
 return {receipt:publicReceipt,xml:out};
}
function exportEvidence(root=ROOT){const dir=inside(root,'.ci-artifacts/phases'),out=inside(root,'.ci-artifacts/phase-public');fs.mkdirSync(out,{recursive:true});let n=0;
 for(const filename of fs.existsSync(dir)?fs.readdirSync(dir):[]){if(!/^phase-[a-z0-9_]+\.json$/.test(filename))continue;const receipt=JSON.parse(fs.readFileSync(path.join(dir,filename),'utf8'));if(!/^[a-z][a-z0-9_]+$/.test(receipt.phase))throw Error('Invalid phase');const raw=receipt.status==='passed'?fs.readFileSync(path.join(dir,'junit-'+receipt.phase+'.xml'),'utf8'):null;const data=redacted(receipt,raw);fs.writeFileSync(path.join(out,filename),JSON.stringify(data.receipt,null,2)+'\n');if(data.xml)fs.writeFileSync(path.join(out,'junit-'+receipt.phase+'.xml'),data.xml);n++;}
 if(!n)fs.writeFileSync(path.join(out,'not-run.json'),JSON.stringify({status:'not-run',reason:'No phase test receipts'})+'\n');console.log('Redacted receipts: '+n);return n;
}
module.exports={redacted,exportEvidence};if(require.main===module)exportEvidence();
