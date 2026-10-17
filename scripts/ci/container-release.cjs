#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { upstreamReady, Blocked } = require('./quality-gate.cjs');
const REPOSITORY = 'toilatrung/label-x';
const COMPONENTS = ['frontend', 'backend'];
const REQUIRED_CI_JOBS = ['bootstrap-windows', 'framework', 'backend', 'detector', 'frontend', 'production-images'];
const image = component => `ghcr.io/toilatrung/labelx-${component}`;

function sourceSha() {
  const sha = process.env.SOURCE_SHA;
  if (!/^[a-f0-9]{40}$/.test(sha || '')) throw new Blocked('A full immutable source SHA is required');
  return sha;
}

function trustedRun(run, sha, workflow) {
  upstreamReady(run, sha, workflow);
  if (run.repository?.full_name !== REPOSITORY || run.head_repository?.full_name !== REPOSITORY) {
    throw new Blocked('Upstream must belong to the source repository, not a fork');
  }
  return run;
}

function requireJobs(jobs, names) {
  for (const name of names) {
    const matches = jobs.filter(job => job.name === name);
    if (matches.length !== 1 || matches[0].status !== 'completed' || matches[0].conclusion !== 'success') {
      throw new Blocked(`Required job did not pass: ${name}`);
    }
  }
}

function publishingContext(eventName, ref, repository, event, sha) {
  if (repository !== REPOSITORY) throw new Blocked('Publishing is restricted to the source repository');
  if (eventName === 'workflow_dispatch' && ref === 'refs/heads/main') return;
  if (eventName !== 'workflow_run') throw new Blocked('Publishing requires main or a trusted main workflow run');
  const trigger = event.workflow_run;
  if (!['.github/workflows/ci.yml', '.github/workflows/phase-testing.yml'].includes(trigger?.path)) {
    throw new Blocked('Unexpected triggering workflow');
  }
  trustedRun(trigger, sha, trigger.path);
}

function checkContext(sha) {
  const event = process.env.GITHUB_EVENT_PATH
    ? JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8')) : {};
  publishingContext(process.env.GITHUB_EVENT_NAME, process.env.GITHUB_REF,
    process.env.GITHUB_REPOSITORY, event, sha);
}

function existingDigest(versions, tag) {
  const matches = versions.filter(version => version.metadata?.container?.tags?.includes(tag));
  if (matches.length > 1) throw new Blocked('A SHA tag refers to multiple package versions');
  if (!matches.length) return '';
  if (!/^sha256:[a-f0-9]{64}$/.test(matches[0].name || '')) throw new Blocked('Invalid package digest');
  return matches[0].name;
}

function output(name, value) {
  if (!process.env.GITHUB_OUTPUT) throw Error('GITHUB_OUTPUT is required');
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
}

async function api(path, missing = false) {
  if (!process.env.GH_TOKEN) throw Error('GH_TOKEN is required');
  const response = await fetch(`https://api.github.com${path}`, {
    headers: { Authorization: `Bearer ${process.env.GH_TOKEN}`, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28' },
    signal: AbortSignal.timeout(30000),
  });
  if (missing && response.status === 404) return null;
  if (!response.ok) throw Error(`GitHub API returned ${response.status} for ${path}`);
  return response.json();
}

async function pages(path, key) {
  const result = [];
  for (let page = 1; ; page++) {
    const data = await api(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`);
    const items = key ? data[key] : data;
    if (!Array.isArray(items)) throw Error('Invalid GitHub API list response');
    result.push(...items);
    if (items.length < 100) return result;
  }
}

async function discover() {
  const sha = sourceSha();
  checkContext(sha);
  const selected = [];
  for (const workflow of ['ci.yml', 'phase-testing.yml']) {
    const data = await api(`/repos/${REPOSITORY}/actions/workflows/${workflow}/runs?branch=main&head_sha=${sha}&per_page=100`);
    const run = [...data.workflow_runs].sort((a, b) => b.id - a.id)[0];
    if (!run || run.status !== 'completed' || run.conclusion !== 'success') {
      output('available', 'false');
      const message = `Images not published: waiting for successful ${workflow} at ${sha}.\n`;
      if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, message);
      if (process.env.GITHUB_EVENT_NAME === 'workflow_dispatch') throw new Blocked(message.trim());
      return;
    }
    trustedRun(run, sha, `.github/workflows/${workflow}`);
    const jobs = await pages(`/repos/${REPOSITORY}/actions/runs/${run.id}/jobs?filter=latest`, 'jobs');
    requireJobs(jobs, workflow === 'ci.yml' ? REQUIRED_CI_JOBS : ['phase']);
    selected.push(run);
  }
  output('ci_run_id', selected[0].id);
  output('test_run_id', selected[1].id);
  output('available', 'true');
}

async function resolveExisting() {
  const tag = `sha-${sourceSha()}`;
  for (const component of COMPONENTS) {
    const path = `/users/toilatrung/packages/container/labelx-${component}/versions`;
    const first = await api(`${path}?per_page=100&page=1`, true);
    const versions = first === null ? [] : first;
    if (!Array.isArray(versions)) throw Error('Invalid package versions response');
    if (versions.length === 100) {
      for (let page = 2; ; page++) {
        const next = await api(`${path}?per_page=100&page=${page}`);
        versions.push(...next);
        if (next.length < 100) break;
      }
    }
    output(`${component}_digest`, existingDigest(versions, tag));
  }
}

function publish() {
  const sha = sourceSha();
  checkContext(sha);
  if (!/^\d+$/.test(process.env.CI_RUN_ID || '') || !/^\d+$/.test(process.env.TEST_RUN_ID || '')) {
    throw new Blocked('Publishing requires verified CI/test run identities on main');
  }
  const receipt = { source_sha: sha, ci_run_id: process.env.CI_RUN_ID, test_run_id: process.env.TEST_RUN_ID,
    publish_run_id: process.env.GITHUB_RUN_ID, images: {} };
  for (const component of COMPONENTS) {
    const repository = image(component);
    const tag = `sha-${sha}`;
    const previous = process.env[`${component.toUpperCase()}_DIGEST`] || '';
    if (!previous) execFileSync('docker', ['push', `${repository}:${tag}`], { stdio: 'inherit' });
    const info = JSON.parse(execFileSync('docker', ['image', 'inspect', `${repository}:${tag}`], { encoding: 'utf8' }))[0];
    const reference = info.RepoDigests.find(value => value.startsWith(`${repository}@sha256:`));
    const digest = reference?.split('@')[1];
    if (!/^sha256:[a-f0-9]{64}$/.test(digest || '') || (previous && previous !== digest)) {
      throw new Blocked('Published digest is missing or changed for an existing SHA tag');
    }
    receipt.images[component] = { repository, tag, digest, reference };
    output(`${component}_digest`, digest);
  }
  fs.mkdirSync('.ci-artifacts/images', { recursive: true });
  fs.writeFileSync('.ci-artifacts/images/image-digests.json', JSON.stringify(receipt, null, 2) + '\n');
  if (process.env.GITHUB_STEP_SUMMARY) {
    const rows = COMPONENTS.map(c => `| ${c} | \`${receipt.images[c].repository}:${receipt.images[c].tag}\` | \`${receipt.images[c].digest}\` |`);
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n| Image | SHA tag | Digest |\n|---|---|---|\n${rows.join('\n')}\n\nPublication is not staging/production promotion; cd.yml gates still apply.\n`);
  }
}

module.exports = { trustedRun, publishingContext, requireJobs, existingDigest, REQUIRED_CI_JOBS };
if (require.main === module) {
  const commands = { discover, existing: resolveExisting, publish };
  Promise.resolve().then(() => {
    if (!commands[process.argv[2]]) throw Error('Commands: discover, existing, publish');
    return commands[process.argv[2]]();
  }).catch(error => { console.error(error.message); process.exitCode = error instanceof Blocked ? 2 : 1; });
}
