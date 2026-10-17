#!/usr/bin/env node
'use strict';
// Read-only preflight. Never creates an approval or changes evaluation thresholds.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { policyReady } = require('./quality-gate.cjs');
const ROOT = path.resolve(__dirname, '../..');
const sha256 = file => {
  const hash = crypto.createHash('sha256');
  const fd = fs.openSync(file, 'r');
  try {
    const buffer = Buffer.alloc(1024 * 1024);
    let count;
    while ((count = fs.readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count));
  } finally { fs.closeSync(fd); }
  return hash.digest('hex');
};
function validateSplit(split) {
  if (split?.schema_version !== 1 || split.group_key !== 'video_id') throw Error('Split requires version 1 and video_id grouping');
  if (!split.provenance?.source || !split.provenance?.license || !split.provenance?.authorized_use) throw Error('Data provenance and authorized use are required');
  const names = ['train', 'guideline', 'calibration', 'held_out'];
  const groups = {};
  for (const name of names) {
    const videos = split[name];
    if (!Array.isArray(videos) || videos.some(id => typeof id !== 'string' || !id.trim()) || new Set(videos).size !== videos.length) throw Error('Invalid/duplicate video IDs in ' + name);
    groups[name] = new Set(videos);
  }
  if (!groups.calibration.size || !groups.held_out.size) throw Error('Calibration and held-out groups must be nonempty');
  for (const name of ['train', 'guideline', 'calibration']) {
    if ([...groups.held_out].some(id => groups[name].has(id))) throw Error('Held-out video leakage from ' + name);
  }
  if ([...groups.calibration].some(id => groups.train.has(id) || groups.guideline.has(id))) throw Error('Calibration video leakage from train/guideline');
  return Object.fromEntries(names.map(name => [name, groups[name].size]));
}
function verifyInputs({ policyFile, referenceFile, modelFile, splitFile, root = ROOT }) {
  const policy = JSON.parse(fs.readFileSync(policyFile, 'utf8'));
  policyReady(policy, root);
  const reference = sha256(referenceFile), model = sha256(modelFile), split = sha256(splitFile);
  if (reference !== policy.reference_sha256) throw Error('Reference bytes do not match approved checksum');
  if (model !== policy.model_sha256) throw Error('Model bytes do not match approved checksum');
  // Additional provenance for this preflight, without weakening the existing gate schema.
  if (split !== policy.split_sha256) throw Error('Split bytes do not match approved checksum');
  if (!policy.model_provenance?.source || !policy.model_provenance?.license || !policy.model_provenance?.authorized_use) throw Error('Model provenance and authorized use are required');
  const groups = validateSplit(JSON.parse(fs.readFileSync(splitFile, 'utf8')));
  return {
    status: 'inputs_verified',
    policy_sha256: sha256(policyFile), reference_sha256: reference,
    model_sha256: model, split_sha256: split, group_counts: groups,
    reference_version: policy.reference_version, score_version: policy.score_version,
    approved_decision: policy.approved_decision,
    evaluation_status: 'NOT VERIFIED',
  };
}
function cli(args) {
  const keys = ['policy', 'reference', 'model', 'split'];
  const values = {};
  for (const key of keys) {
    const index = args.indexOf('--' + key);
    if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) throw Error('Required input: --' + key);
    values[key + 'File'] = path.resolve(args[index + 1]);
  }
  return verifyInputs(values);
}
module.exports = { sha256, validateSplit, verifyInputs, cli };
if (require.main === module) {
  try { console.log(JSON.stringify(cli(process.argv.slice(2)), null, 2)); }
  catch (_) {
    // File-system/JSON errors may include sensitive paths or data. Keep stdout/stderr public-safe.
    console.error('BLOCKED: evaluation inputs or approval invalid; inspect privately against evaluation-policy-readiness.html');
    process.exitCode = 2;
  }
}
