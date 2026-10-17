'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { trustedRun, publishingContext, requireJobs, existingDigest, REQUIRED_CI_JOBS } = require('../container-release.cjs');
const sha = 'a'.repeat(40);
const repository = { full_name: 'toilatrung/label-x' };
const good = { status: 'completed', conclusion: 'success', head_sha: sha, head_branch: 'main',
  path: '.github/workflows/ci.yml', event: 'push', repository, head_repository: repository };

test('only successful trusted main CI at the exact SHA is eligible', () => {
  assert.equal(trustedRun(good, sha, good.path), good);
  for (const changes of [{ event: 'pull_request' }, { head_branch: 'develop' },
    { head_sha: 'b'.repeat(40) }, { status: 'in_progress' }, { conclusion: 'failure' },
    { head_repository: { full_name: 'fork/label-x' } }, { repository: { full_name: 'fork/label-x' } },
    { path: '.github/workflows/other.yml' }]) {
    assert.throws(() => trustedRun({ ...good, ...changes }, sha, good.path));
  }
});

test('manual publication cannot run from develop or a fork', () => {
  assert.doesNotThrow(() => publishingContext('workflow_dispatch', 'refs/heads/main', repository.full_name, {}, sha));
  assert.throws(() => publishingContext('workflow_dispatch', 'refs/heads/develop', repository.full_name, {}, sha));
  assert.throws(() => publishingContext('workflow_dispatch', 'refs/heads/main', 'fork/label-x', {}, sha));
});

test('workflow_run checks source branch even when the default branch is develop', () => {
  assert.doesNotThrow(() => publishingContext('workflow_run', 'refs/heads/develop', repository.full_name,
    { workflow_run: good }, sha));
  assert.throws(() => publishingContext('workflow_run', 'refs/heads/main', repository.full_name,
    { workflow_run: { ...good, head_branch: 'develop' } }, sha));
  assert.throws(() => publishingContext('workflow_run', 'refs/heads/main', repository.full_name,
    { workflow_run: { ...good, path: '.github/workflows/other.yml' } }, sha));
});

test('all required CI jobs including the production image smoke must pass', () => {
  const jobs = REQUIRED_CI_JOBS.map(name => ({ name, status: 'completed', conclusion: 'success' }));
  assert.doesNotThrow(() => requireJobs(jobs, REQUIRED_CI_JOBS));
  for (const conclusion of ['skipped', 'failure', 'cancelled', 'neutral']) {
    assert.throws(() => requireJobs(jobs.map(j => j.name === 'production-images' ? { ...j, conclusion } : j), REQUIRED_CI_JOBS));
  }
  assert.throws(() => requireJobs(jobs.slice(1), REQUIRED_CI_JOBS));
  assert.throws(() => requireJobs([...jobs, jobs[0]], REQUIRED_CI_JOBS));
});

test('existing SHA tags resolve to the original digest and ambiguous metadata fails closed', () => {
  const tag = `sha-${sha}`, digest = 'sha256:' + 'b'.repeat(64);
  const version = { name: digest, metadata: { container: { tags: [tag] } } };
  assert.equal(existingDigest([], tag), '');
  assert.equal(existingDigest([version], tag), digest);
  assert.equal(existingDigest([version], 'sha-' + 'c'.repeat(40)), '');
  assert.throws(() => existingDigest([version, version], tag));
  assert.throws(() => existingDigest([{ ...version, name: 'not-a-digest' }], tag));
});
