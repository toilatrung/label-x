'use strict';
const fs = require('node:fs'), path = require('node:path');
const root = fs.realpathSync(path.resolve(__dirname, '../..'));
// Fixed allowlist, resolved against this repository. Refuse symlink/junction escapes.
for (const relative of ['src/backend/.venv', 'src/frontend/node_modules', 'src/frontend/.next']) {
  const target = path.resolve(root, relative);
  if (!fs.existsSync(target)) continue;
  const real = fs.realpathSync(target);
  if (!real.startsWith(root + path.sep) || real !== target || fs.lstatSync(target).isSymbolicLink()) {
    throw Error(`Refusing cleanup outside the expected project directory: ${relative}`);
  }
  fs.rmSync(target, {recursive: true, force: true});
  console.log(`Removed ${relative}`);
}
