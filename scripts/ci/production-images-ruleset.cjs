'use strict';
// Issue #401: prepare/read back the exact ruleset change. This tool never writes GitHub settings.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const REPO = 'toilatrung/label-x';
const ID = 25297568;
const ENDPOINT = `repos/${REPO}/rulesets/${ID}`;
const CHECK = { context: 'production-images', integration_id: 15368 };
const ORIGINAL = ['framework', 'backend', 'frontend', 'detector', 'bootstrap-windows'];

function payload(snapshot) {
  const { name, target, enforcement, conditions, rules, bypass_actors = [] } = snapshot;
  return structuredClone({ name, target, enforcement, conditions, rules, bypass_actors });
}

function proposed(snapshot) {
  assert.equal(snapshot.id, ID);
  assert.equal(snapshot.source, REPO);
  const result = payload(snapshot);
  assert.equal(result.enforcement, 'active');
  assert.equal(result.target, 'branch');
  assert.deepEqual(result.conditions.ref_name, {
    exclude: [], include: ['refs/heads/main', 'refs/heads/develop'],
  });
  const status = result.rules.filter(r => r.type === 'required_status_checks');
  assert.equal(status.length, 1);
  assert.equal(status[0].parameters.strict_required_status_checks_policy, true);
  assert.deepEqual(status[0].parameters.required_status_checks,
    ORIGINAL.map(context => ({ context, integration_id: CHECK.integration_id })));
  status[0].parameters.required_status_checks.push({ ...CHECK });
  return result;
}

function verify(before, after) {
  assert.equal(after.id, ID);
  assert.equal(after.source, REPO);
  assert.deepEqual(payload(after), proposed(before), 'Unexpected ruleset change; inspect snapshots before recovery');
}

function api(endpoint) {
  return JSON.parse(execFileSync('gh', ['api', endpoint], { encoding: 'utf8', shell: false }));
}

function save(dir, file, value) {
  fs.writeFileSync(path.join(dir, file), JSON.stringify(value, null, 2) + '\n', { flag: 'wx' });
}

function main([mode, dir]) {
  assert.ok(dir && ['prepare', 'preflight', 'verify'].includes(mode),
    'Usage: node scripts/ci/production-images-ruleset.cjs prepare|preflight|verify <evidence-directory>');
  if (mode === 'prepare') {
    // A fresh directory prevents overwriting the original evidence on reruns.
    fs.mkdirSync(dir, { recursive: false });
    const before = api(ENDPOINT);
    save(dir, 'ruleset.before.json', before);
    save(dir, 'ruleset.proposed.json', proposed(before));
    save(dir, 'ruleset.rollback.json', payload(before));
    for (const branch of ['main', 'develop']) {
      save(dir, `${branch}.rules.before.json`, api(`repos/${REPO}/rules/branches/${branch}`));
    }
    const sha = api(`repos/${REPO}/branches/main`).commit.sha;
    save(dir, 'main.check-runs.json', api(`repos/${REPO}/commits/${sha}/check-runs?per_page=100`));
    save(dir, 'main.ci-runs.json', api(`repos/${REPO}/actions/workflows/ci.yml/runs?branch=main&head_sha=${sha}&per_page=100`));
    save(dir, 'manifest.json', { captured_at: new Date().toISOString(), main_sha: sha,
      ruleset_url: `https://github.com/${REPO}/rules/${ID}`, endpoint: ENDPOINT,
      state: 'prepared; administrator review and application pending' });
  } else {
    const before = JSON.parse(fs.readFileSync(path.join(dir, 'ruleset.before.json'), 'utf8'));
    const live = api(ENDPOINT);
    if (mode === 'preflight') {
      assert.deepEqual(payload(live), payload(before), 'Ruleset drift: prepare and review a new snapshot');
      assert.deepEqual(JSON.parse(fs.readFileSync(path.join(dir, 'ruleset.proposed.json'), 'utf8')), proposed(before));
      console.log('Preflight passed. Administrator must apply immediately after review; GitHub PUT is not atomic with this GET.');
    } else {
      save(dir, 'ruleset.after.json', live);
      verify(before, live);
      for (const branch of ['main', 'develop']) {
        const old = JSON.parse(fs.readFileSync(path.join(dir, `${branch}.rules.before.json`), 'utf8'));
        const current = api(`repos/${REPO}/rules/branches/${branch}`);
        save(dir, `${branch}.rules.after.json`, current);
        const expected = structuredClone(old);
        const status = expected.filter(r => r.ruleset_id === ID && r.type === 'required_status_checks');
        assert.equal(status.length, 1);
        status[0].parameters.required_status_checks.push(CHECK);
        assert.deepEqual(current, expected, `Unexpected effective protection change on ${branch}`);
      }
      console.log('Verified: exactly production-images/15368 added; all other effective protections unchanged.');
    }
  }
}

module.exports = { payload, proposed, verify };
if (require.main === module) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
