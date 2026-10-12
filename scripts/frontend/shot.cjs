// Chụp mọi route M-FE01 ở 1440 và 390 cho một vai trò. Chạy bởi screenshot.sh (không chạy trực tiếp).
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const [pwdir, base, role, outDir, ...routes] = process.argv.slice(2);
const { chromium } = require(require.resolve('playwright', { paths: [pwdir] }));

const SIZES = [[1440, 900], [390, 844]];
const slug = (r) => (r === '/' ? 'home' : r.replace(/^\//, '').replace(/\//g, '_'));

(async () => {
  const browser = await chromium.launch();
  fs.mkdirSync(outDir, { recursive: true });
  let bad = 0;
  console.log('route'.padEnd(36), 'kích thước'.padEnd(10), 'h1'.padEnd(34), 'cuộn ngang', 'notice', 'ảnh');
  for (const [w, h] of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded' });
    await page.fill('#username', role);
    await page.fill('#password', 'password123');
    await page.click('button[type=submit]');
    await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30000 });
    for (const route of routes) {
      const file = path.join(outDir, `${slug(route)}-${w}.png`);
      try {
        await page.goto(base + route, { waitUntil: 'networkidle', timeout: 60000 });
        await page.waitForTimeout(700);
        const h1 = (await page.locator('h1').first().innerText({ timeout: 3000 }).catch(() => '(không có h1)')).replace(/\s+/g, ' ').slice(0, 32);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        const notices = await page.locator('.lx-notice').count();
        await page.screenshot({ path: file, fullPage: true });
        if (overflow) bad++;
        console.log(route.padEnd(36), `${w}px`.padEnd(10), h1.padEnd(34), (overflow ? 'CÓ' : 'không').padEnd(10), String(notices).padEnd(6), path.relative(process.cwd(), file));
      } catch (e) {
        bad++;
        console.log(route.padEnd(36), `${w}px`.padEnd(10), 'LỖI:', String(e.message).split('\n')[0]);
      }
    }
    await ctx.close();
  }
  await browser.close();
  console.log(bad ? `\nCó ${bad} trường hợp lỗi hoặc cuộn ngang.` : '\nXong, không có lỗi hoặc cuộn ngang.');
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
