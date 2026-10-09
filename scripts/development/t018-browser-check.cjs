/* Browser acceptance against real local Django; never intercepts API routes.
 * Requires Playwright and private JSON credentials for the local QA accounts.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.LABELX_PLAYWRIGHT_MODULE || 'playwright');
const credentials = JSON.parse(fs.readFileSync(process.env.LABELX_BROWSER_CREDENTIALS, 'utf8'));
const output = process.env.LABELX_EVIDENCE_DIR || path.resolve(__dirname, '../../docs/design/evidence/T-018');
fs.mkdirSync(output, { recursive: true });
if (process.env.LABELX_BROWSER_LIBS) process.env.LD_LIBRARY_PATH = process.env.LABELX_BROWSER_LIBS;
(async () => {
  const browser = await chromium.launch({ headless: true, env: { ...process.env,
    LD_LIBRARY_PATH: process.env.LABELX_BROWSER_LIBS || process.env.LD_LIBRARY_PATH || '' } });
  const context = await browser.newContext({ viewport: { width: 1345, height: 1077 } });
  const page = await context.newPage();
  const api = []; const pageErrors = []; const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.port === '8000' && url.pathname.startsWith('/api/')) api.push({ path: url.pathname, query: url.search, status: response.status() });
  });
  async function login(username) {
    await page.goto('http://localhost:3000/login');
    await page.getByLabel('Tên đăng nhập').fill(username);
    await page.getByLabel('Mật khẩu', { exact: true }).fill(credentials[username]);
    await page.getByRole('button', { name: /Đăng nhập vào LabelX/ }).click();
    await page.waitForURL('http://localhost:3000/');
  }
  await login('t018_reviewer');
  await page.goto('http://localhost:3000/configuration/guidelines');
  await page.getByText('VEH-01', { exact: true }).waitFor();
  assert.equal(await page.getByTestId('guideline-version').textContent(), 'v1');
  await page.getByRole('button', { name: 'Configuration', exact: true }).click();
  assert.equal(await page.getByRole('menuitem', { name: 'Models & Guidelines' }).getAttribute('href'), '/configuration/guidelines');
  assert.equal(await page.getByRole('menuitem', { name: 'Workflow & Permissions' }).count(), 0);
  await page.screenshot({ path: path.join(output, 'reviewer-dropdown.png'), fullPage: true });
  await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('menu').count(), 0);
  assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), 'Configuration');
  await page.getByLabel('Rule ID', { exact: true }).fill('VEH-03');
  await page.getByLabel('Guideline version').fill('v1');
  const detail = page.waitForResponse(r => r.url().includes(':8000/api/guidelines/rules/VEH-03/') && r.status() === 200);
  await page.getByRole('button', { name: 'Lọc', exact: true }).click();
  assert.equal((await (await detail).json()).rule_id, 'VEH-03');
  await page.locator('tbody tr').filter({ hasText: 'VEH-03' }).waitFor();
  await page.screenshot({ path: path.join(output, 'reviewer-exact-rule.png'), fullPage: true });
  await page.getByRole('button', { name: 'Xoá bộ lọc' }).click();
  await page.getByLabel('Nhóm lỗi').selectOption('E2');
  await page.getByLabel('Tên lớp').fill('truck');
  const filtered = page.waitForResponse(r => r.url().includes(':8000/api/guidelines/rules/?') && new URL(r.url()).searchParams.get('class_name') === 'truck');
  await page.getByRole('button', { name: 'Lọc', exact: true }).click();
  assert.equal((await filtered).status(), 200);
  await page.locator('section[aria-busy="false"]').waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'Mobile page overflow');
  await page.screenshot({ path: path.join(output, 'reviewer-mobile.png'), fullPage: true });
  await page.getByLabel('Rule ID', { exact: true }).fill('MISSING');
  const missing = page.waitForResponse(r => r.url().includes(':8000/api/guidelines/rules/MISSING/'));
  await page.getByRole('button', { name: 'Lọc', exact: true }).click();
  assert.equal((await missing).status(), 404);
  await page.getByRole('alert').filter({ hasText: 'Không tìm thấy tài nguyên' }).waitFor();
  assert.equal(await page.getByText('VEH-03', { exact: true }).count(), 0);
  await page.locator('.lx-user--btn').click();
  await page.getByRole('menuitem', { name: 'Đăng xuất' }).click();
  await page.waitForURL('http://localhost:3000/login');
  await login('t018_annotator');
  const readsBefore = api.filter(r => r.path.startsWith('/api/guidelines/')).length;
  await page.goto('http://localhost:3000/configuration/guidelines');
  await page.getByText('403 - Quyền truy cập bị từ chối').waitFor();
  assert.equal(api.filter(r => r.path.startsWith('/api/guidelines/')).length, readsBefore);
  const forbidden = await context.request.get('http://localhost:8000/api/guidelines/rules/');
  assert.equal(forbidden.status(), 403);
  assert.equal((await forbidden.json()).code, 'FORBIDDEN');
  await page.screenshot({ path: path.join(output, 'annotator-forbidden.png'), fullPage: true });
  assert.deepEqual(pageErrors, []);
  const evidence = { status: 'passed', auth: 'real Django session + CSRF', backend: 'http://localhost:8000',
    viewports: ['1345x1077', '390x844'], checks: ['Reviewer login', 'real rule list', 'rule ID/version detail', 'family/class filter',
      'dropdown permissions', 'Escape focus', 'mobile overflow', '404 without stale rule', 'Annotator frontend/API 403'], api, pageErrors, consoleErrors };
  fs.writeFileSync(path.join(output, 'browser-evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
  await browser.close();
  console.log(JSON.stringify({ status: evidence.status, checks: evidence.checks.length, pageErrors: pageErrors.length }));
})().catch(e => { console.error(e); process.exitCode = 1; });
