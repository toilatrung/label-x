'use strict';
// CR-120: only the two application image identities and their receipt may change.
const fs = require('node:fs');
const { requireJobs, REQUIRED_CI_JOBS } = require('./container-release.cjs');
const ROOT = 'infrastructure/k8s/labelx/';
const FILES = [ROOT + 'kustomization.yaml', ROOT + 'release.json'];
const REPOSITORY = 'toilatrung/label-x';
const SHA = /^[a-f0-9]{40}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;

function validateReceipt(receipt) {
  if (!SHA.test(receipt.source_sha || '') || !/^\d+$/.test(String(receipt.ci_run_id || '')) ||
      receipt.deployment_policy !== 'CR-120' || receipt.mvp_acceptance !== 'unverified') {
    throw Error('Invalid deployment receipt; deployment is not MVP acceptance');
  }
  for (const component of ['backend', 'frontend']) {
    const entry = receipt.images?.[component];
    const repository = `ghcr.io/toilatrung/labelx-${component}`;
    if (entry?.repository !== repository || !DIGEST.test(entry.digest || '') ||
        entry.reference !== `${repository}@${entry.digest}` || entry.tag !== `sha-${receipt.source_sha}`) {
      throw Error('Image receipt has an unexpected repository, SHA or digest');
    }
  }
  return receipt;
}

function render(current, receipt) {
  validateReceipt(receipt);
  const updated = structuredClone(current);
  updated.images = ['backend', 'frontend'].map(component => ({
    name: `labelx-${component}`, newName: receipt.images[component].repository,
    digest: receipt.images[component].digest,
  }));
  const release = updated.configMapGenerator.find(item => item.name === 'labelx-release');
  if (!release) throw Error('Release identity ConfigMap missing');
  release.literals = [`SOURCE_SHA=${receipt.source_sha}`, 'MVP_EVIDENCE=unverified', 'DEPLOYMENT_POLICY=CR-120'];
  return updated;
}

function digestOnly(before, after, receipt, changedFiles) {
  try {
    if (!changedFiles.length || changedFiles.some(file => !FILES.includes(file))) return false;
    return JSON.stringify(render(before, receipt)) === JSON.stringify(after);
  } catch { return false; }
}

async function api(path, method = 'GET', body) {
  if (!process.env.GH_TOKEN) throw Error('LABELX_GITOPS_TOKEN is required for protected-main digest PRs');
  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}${path}`, {
    method, headers: { Authorization: `Bearer ${process.env.GH_TOKEN}`,
      Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw Error(`GitHub ${method} ${path}: ${response.status}`);
  return response.status === 204 ? null : response.json();
}

async function update() {
  const receipt = validateReceipt(JSON.parse(fs.readFileSync('.ci-artifacts/images/image-digests.json', 'utf8')));
  if (receipt.source_sha !== process.env.SOURCE_SHA) throw Error('Receipt does not belong to the tested source SHA');
  const ref = await api('/git/ref/heads/main');
  if (ref.object.sha !== receipt.source_sha) throw Error('Main advanced; let the newer successful CI publish its own images');
  const commit = await api(`/git/commits/${receipt.source_sha}`);
  const content = await api(`/contents/${FILES[0]}?ref=${receipt.source_sha}`);
  const current = JSON.parse(Buffer.from(content.content, 'base64').toString('utf8'));
  const updated = render(current, receipt);
  if (!digestOnly(current, updated, receipt, FILES)) throw Error('Update exceeds the CR-120 digest-only exception');
  const tree = await api('/git/trees', 'POST', { base_tree: commit.tree.sha, tree: [
    { path: FILES[0], mode: '100644', type: 'blob', content: JSON.stringify(updated, null, 2) + '\n' },
    { path: FILES[1], mode: '100644', type: 'blob', content: JSON.stringify(receipt, null, 2) + '\n' },
  ] });
  const next = await api('/git/commits', 'POST', {
    message: `deploy(labelx): pin images from ${receipt.source_sha}`, tree: tree.sha, parents: [receipt.source_sha],
  });
  const branch = `gitops/images-${receipt.source_sha}-${process.env.GITHUB_RUN_ID}`;
  await api('/git/refs', 'POST', { ref: `refs/heads/${branch}`, sha: next.sha });
  const pr = await api('/pulls', 'POST', {
    title: `deploy(labelx): ${receipt.source_sha.slice(0, 12)}`, head: branch, base: 'main',
    body: `CR-120 authorizes automatic merge of this digest-only PR after all six CI jobs pass.\n\n` +
      `Source: ${receipt.source_sha}\nCI run: ${receipt.ci_run_id}\nImage smoke/publish: ${receipt.publish_run_id}\n` +
      `MVP acceptance: UNVERIFIED. MVP issues remain open.\n\n` +
      Object.values(receipt.images).map(entry => `- \`${entry.reference}\``).join('\n'),
  });
  console.log(`Digest PR: ${pr.html_url}`);
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `Digest PR: ${pr.html_url}\nMVP acceptance: UNVERIFIED.\n`);
  // Use a normal PR and all existing required checks; no ruleset bypass or direct push.
  for (let attempt = 0; attempt < 120; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 30000));
    const currentMain = await api('/git/ref/heads/main');
    if (currentMain.object.sha !== receipt.source_sha) throw Error('Main advanced while testing the digest PR; merge cancelled');
    const state = await api(`/pulls/${pr.number}`);
    if (state.state !== 'open' || state.head.sha !== next.sha) throw Error('Digest PR was closed or modified; merge cancelled');
    const checks = await api(`/commits/${next.sha}/check-runs?per_page=100`);
    const ours = checks.check_runs.filter(check => check.app?.slug === 'github-actions' && REQUIRED_CI_JOBS.includes(check.name));
    if (ours.some(check => check.status === 'completed' && check.conclusion !== 'success')) throw Error('Digest PR CI failed');
    try { requireJobs(ours, REQUIRED_CI_JOBS); } catch { continue; }
    const files = await api(`/pulls/${pr.number}/files?per_page=100`);
    if (files.length !== 2 || files.some(file => !FILES.includes(file.filename))) throw Error('Digest PR scope changed');
    const merged = await api(`/pulls/${pr.number}/merge`, 'PUT', {
      sha: next.sha, merge_method: 'merge', commit_title: `deploy(labelx): images from ${receipt.source_sha}`,
    });
    if (!merged.merged) throw Error('Protected digest PR could not be merged');
    console.log(`GitOps revision: ${merged.sha}; Argo CD will sync automatically`);
    return;
  }
  throw Error('Digest PR CI timed out; PR stays open for inspection');
}

module.exports = { validateReceipt, render, digestOnly, FILES };
if (require.main === module) update().catch(error => { console.error(error.message); process.exitCode = 1; });
