'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const {spawnSync} = require('node:child_process');
const {initEnv, preflight} = require('../environment.cjs');
const root = path.resolve(__dirname, '../../..');
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'labelx-bootstrap-'));
  for (const rel of ['src/backend/.env.example', 'src/backend/pyproject.toml', 'src/backend/uv.lock', 'src/frontend/.env.example', 'src/frontend/package-lock.json', 'infrastructure/docker-compose.dev.yml']) {
    fs.mkdirSync(path.dirname(path.join(dir, rel)), {recursive: true});
    fs.copyFileSync(path.join(root, rel), path.join(dir, rel));
  }
  t.after(() => {
    const real = fs.realpathSync(dir);
    assert(real.startsWith(fs.realpathSync(os.tmpdir()) + path.sep));
    assert(path.basename(real).startsWith('labelx-bootstrap-'));
    fs.rmSync(real, {recursive: true, force: true});
  });
  return dir;
}
test('new environment uses random secrets; rerun preserves both files and lockfiles', t => {
  const dir = fixture(t), lock = fs.readFileSync(path.join(dir, 'src/backend/uv.lock'));
  initEnv(dir);
  const backend = fs.readFileSync(path.join(dir, 'src/backend/.env'), 'utf8');
  assert.match(backend, /^DJANGO_SECRET_KEY=dev-only-[a-f0-9]{64}$/m);
  const front = fs.readFileSync(path.join(dir, 'src/frontend/.env.local'), 'utf8');
  initEnv(dir);
  assert.equal(fs.readFileSync(path.join(dir, 'src/backend/.env'), 'utf8'), backend);
  assert.equal(fs.readFileSync(path.join(dir, 'src/frontend/.env.local'), 'utf8'), front);
  assert.deepEqual(fs.readFileSync(path.join(dir, 'src/backend/uv.lock')), lock);
  preflight(dir, 'win32', {});
  const other = fixture(t); initEnv(other);
  assert.notEqual(fs.readFileSync(path.join(other, 'src/backend/.env'), 'utf8'), backend);
});
test('never migrates an external database or logs its credentials', t => {
  const dir = fixture(t); initEnv(dir);
  const file = path.join(dir, 'src/backend/.env');
  fs.appendFileSync(file, '\nDATABASE_URL=postgres://private:secret@production/real\n');
  assert.throws(() => preflight(dir, 'win32', {}), e => e.message.includes('DATABASE_URL') && !e.message.includes('secret'));
});
test('process environment overriding local DB is rejected too', t => {
  const dir = fixture(t); initEnv(dir);
  assert.throws(() => preflight(dir, 'linux', {DATABASE_URL: 'postgres://prod'}), /DATABASE_URL/);
});
test('placeholder existing secret is preserved and rejected', t => {
  const dir = fixture(t);
  fs.copyFileSync(path.join(dir, 'src/backend/.env.example'), path.join(dir, 'src/backend/.env'));
  initEnv(dir);
  assert.throws(() => preflight(dir, 'linux', {}), /DJANGO_SECRET_KEY/);
  assert.match(fs.readFileSync(path.join(dir, 'src/backend/.env'), 'utf8'), /DJANGO_SECRET_KEY=change-me/);
});
test('mixed OS virtualenv and active external environment stop before installation', t => {
  const dir = fixture(t);
  fs.mkdirSync(path.join(dir, 'src/backend/.venv/bin'), {recursive: true});
  fs.writeFileSync(path.join(dir, 'src/backend/.venv/bin/python'), '');
  assert.throws(() => preflight(dir, 'win32', {}), /another OS/);
  assert.throws(() => preflight(dir, 'linux', {UV_PROJECT_ENVIRONMENT: '/external'}), /UV_PROJECT_ENVIRONMENT/);
});
test('custom Compose and remote Docker overrides stop local setup', t => {
  const dir = fixture(t);
  for (const key of ['COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'DOCKER_CONTEXT', 'DOCKER_HOST']) {
    assert.throws(() => preflight(dir, 'linux', {[key]: 'custom'}), /overrides/);
  }
});
test('frontend external API is preserved and rejected', t => {
  const dir = fixture(t); initEnv(dir);
  fs.appendFileSync(path.join(dir, 'src/frontend/.env.local'), '\nNEXT_PUBLIC_API_BASE_URL=https://external/api\n');
  assert.throws(() => preflight(dir, 'linux', {}), /Frontend API/);
});
test('Windows Plan runs without global tools and never claims setup success', {skip: process.platform !== 'win32'}, () => {
  const result = spawnSync('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'scripts/init-develop-environment.ps1'), '-Mode', 'Plan'], {encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /PLAN ONLY/);
  assert.doesNotMatch(result.stdout, /SETUP PASSED/);
});
test('Windows native command failure propagates nonzero exit', {skip: process.platform !== 'win32'}, () => {
  const script = fs.readFileSync(path.join(root, 'scripts/init-develop-environment.ps1'), 'utf8');
  const helper = script.slice(script.indexOf('function Invoke-Checked'), script.indexOf('function Refresh-ToolPath'));
  const result = spawnSync('powershell.exe', ['-NoProfile', '-Command', `$ErrorActionPreference='Stop'; ${helper}; Invoke-Checked '${process.execPath.replaceAll("'", "''")}' @('-e', 'process.exit(7)')`], {encoding: 'utf8'});
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /exit 7/);
});
