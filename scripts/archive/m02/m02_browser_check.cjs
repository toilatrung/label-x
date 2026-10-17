/* M-02 browser evidence trên API thật (không chặn/giả request). Playwright + users.json riêng tư.
 * env: LABELX_PLAYWRIGHT_MODULE, LABELX_BROWSER_CREDENTIALS (users.json {role: pw}), LABELX_EVIDENCE_DIR */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.LABELX_PLAYWRIGHT_MODULE || 'playwright');
const pw = JSON.parse(fs.readFileSync(process.env.LABELX_BROWSER_CREDENTIALS, 'utf8'));
const out = process.env.LABELX_EVIDENCE_DIR; fs.mkdirSync(out, { recursive: true });
const ROLES = ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin', 'product_owner', 'data_model_owner'];
(async () => {
  const browser = await chromium.launch({ headless: true });
  const result = { roles: {}, api: [], errors: [] };
  for (const role of ROLES) {
    const ctx = await browser.newContext({ viewport: { width: 1345, height: 900 } });
    const page = await ctx.newPage();
    page.on('pageerror', e => result.errors.push(`${role}: ${e.message}`));
    page.on('response', r => { const u = new URL(r.url()); if (u.port === '8000' && u.pathname.startsWith('/api/')) result.api.push({ role, path: u.pathname, status: r.status() }); });
    await page.goto('http://localhost:3000/login', { timeout: 180000 });
    await page.getByLabel('Tên đăng nhập').fill(`e2e_${role}`);
    await page.getByLabel('Mật khẩu', { exact: true }).fill(pw[role]);
    await page.getByRole('button', { name: /Đăng nhập vào LabelX/ }).click();
    await page.waitForURL('http://localhost:3000/', { timeout: 180000 });
    const nav = await page.locator('header a, header button, nav a, nav button').allInnerTexts();
    result.roles[role] = { topbar: [...new Set(nav.map(s => s.trim()).filter(Boolean))] };
    await page.screenshot({ path: path.join(out, `topbar-${role}.png`) });
    for (const route of ['/analysis/snapshots', '/analysis/config', '/analysis/history']) {
      const resp = await page.goto('http://localhost:3000' + route, { timeout: 180000 });
      await page.waitForTimeout(3000);
      const body = (await page.locator('main, body').first().innerText()).slice(0, 300).replace(/\s+/g, ' ');
      result.roles[role][route] = { forbidden: /không có quyền|forbidden|Forbidden|403/i.test(body), text: body };
      if (role === 'qa_lead' || role === 'annotator') await page.screenshot({ path: path.join(out, `${role}${route.replace(/\//g, '-')}.png`), fullPage: true });
    }
    await ctx.close();
  }
  fs.writeFileSync(path.join(out, 'browser-result.json'), JSON.stringify(result, null, 1));
  await browser.close();
  console.log('done', result.errors.length, 'pageerrors');
})().catch(e => { console.error(e); process.exit(1); });
