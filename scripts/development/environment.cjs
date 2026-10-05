'use strict';
// Shared local checks. Never log environment values or overwrite existing secrets.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ROOT = path.resolve(__dirname, '../..');
function values(text) {
  const result = {};
  for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/);
    if (match) result[match[1]] = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
  }
  return result;
}
function initEnv(root = ROOT) {
  for (const [folder, name] of [['backend', '.env'], ['frontend', '.env.local']]) {
    const target = path.join(root, 'src', folder, name);
    if (fs.existsSync(target)) { console.log(`Keep src/${folder}/${name}`); continue; }
    let text = fs.readFileSync(path.join(root, 'src', folder, '.env.example'), 'utf8');
    if (folder === 'backend') {
      if (!/^DJANGO_SECRET_KEY=.*$/m.test(text)) throw Error('Template lacks DJANGO_SECRET_KEY');
      text = text.replace(/^DJANGO_SECRET_KEY=.*$/m, `DJANGO_SECRET_KEY=dev-only-${crypto.randomBytes(32).toString('hex')}`);
    }
    fs.writeFileSync(target, text, {flag: 'wx', mode: 0o600});
    console.log(`Created src/${folder}/${name}`);
  }
}
function preflight(root = ROOT, platform = process.platform, environment = process.env) {
  const backend = path.join(root, 'src/backend');
  for (const file of ['src/backend/uv.lock', 'src/backend/pyproject.toml', 'src/frontend/package-lock.json', 'infrastructure/docker-compose.dev.yml']) {
    if (!fs.existsSync(path.join(root, file))) throw Error(`Missing ${file}`);
  }
  const venv = path.join(backend, '.venv');
  if (fs.existsSync(venv) && !fs.existsSync(path.join(venv, platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'))) {
    throw Error('Existing .venv belongs to another OS or is incomplete. Rename it to .venv.backup, then retry. Use separate Windows/WSL checkouts.');
  }
  if (environment.UV_PROJECT_ENVIRONMENT || environment.VIRTUAL_ENV) {
    throw Error('Deactivate the active virtual environment and unset UV_PROJECT_ENVIRONMENT before local setup.');
  }
  const file = path.join(backend, '.env');
  if (fs.existsSync(file)) {
    const current = values(fs.readFileSync(file, 'utf8'));
    const defaults = values(fs.readFileSync(path.join(backend, '.env.example'), 'utf8'));
    if (!current.DJANGO_SECRET_KEY || current.DJANGO_SECRET_KEY === 'change-me') {
      throw Error('Existing backend .env needs a real DJANGO_SECRET_KEY; it was preserved.');
    }
    // Avoid running migrations against an unrelated database. Setup supports bundled local Compose only.
    for (const key of Object.keys(defaults).filter(k => /^(DATABASE_URL|CELERY_|OBJECT_STORAGE_)/.test(k))) {
      if ((environment[key] ?? current[key]) !== defaults[key]) throw Error(`${key} differs from bundled local Compose. Review manually; setup stopped without changing it.`);
    }
  }
  const frontendFile = path.join(root, 'src/frontend/.env.local');
  if (fs.existsSync(frontendFile)) {
    const current = values(fs.readFileSync(frontendFile, 'utf8'));
    if (current.NEXT_PUBLIC_API_BASE_URL !== 'http://localhost:8000/api') {
      throw Error('Frontend API URL differs from bundled local setup. Review it manually; the file was preserved.');
    }
  }
  if (environment.COMPOSE_FILE || environment.COMPOSE_PROJECT_NAME || environment.DOCKER_HOST || environment.DOCKER_CONTEXT) {
    throw Error('Unset custom Compose/Docker environment overrides before bundled local setup.');
  }
}
function main(command) {
  if (command === 'env') initEnv();
  else if (command === 'preflight') preflight();
  else throw Error('Use: node scripts/development/environment.cjs env|preflight');
}
module.exports = {values, initEnv, preflight};
if (require.main === module) {
  try { main(process.argv[2]); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
