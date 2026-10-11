/* Browser/API acceptance for T-039 against real Next.js + Django + PostgreSQL.
 * No API interception, mocked response, or checked-in credential is allowed.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.LABELX_PLAYWRIGHT_MODULE || 'playwright-core');

const credentialsPath = process.env.LABELX_BROWSER_CREDENTIALS;
const sharedPassword = process.env.LABELX_T039_PASSWORD;
assert(credentialsPath || sharedPassword, 'LABELX_BROWSER_CREDENTIALS or LABELX_T039_PASSWORD is required');
const credentials = credentialsPath
  ? JSON.parse(fs.readFileSync(credentialsPath, 'utf8'))
  : Object.fromEntries([
      't039_qalead', 't039_superadmin', 't039_reviewer', 't039_annotator',
      't039_unmapped_qa', 't039_self_qa', 't039_outscope_qa', 't039_alias_qa',
    ].map(username => [username, sharedPassword]));
const output = process.env.LABELX_EVIDENCE_DIR || path.resolve(__dirname, '../../src/frontend/evidence/t039');
const executablePath = process.env.LABELX_BROWSER_EXECUTABLE;
assert(executablePath, 'LABELX_BROWSER_EXECUTABLE is required');
fs.mkdirSync(output, { recursive: true });

const FRONTEND = 'http://localhost:3000';
const BACKEND = 'http://localhost:8000';
const results = [];
const api = [];
const pageErrors = [];
const consoleErrors = [];

function record(name, details = {}) {
  results.push({ name, status: 'passed', ...details });
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath });

  async function session(username, viewport = { width: 1440, height: 1000 }) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    page.on('pageerror', error => pageErrors.push({ username, message: error.message }));
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push({ username, message: message.text() });
    });
    page.on('response', response => {
      const url = new URL(response.url());
      if (url.origin === BACKEND && url.pathname.startsWith('/api/')) {
        api.push({ username, method: response.request().method(), path: url.pathname, query: url.search, status: response.status() });
      }
    });
    await page.goto(`${FRONTEND}/login`);
    await page.getByLabel('Tên đăng nhập').fill(username);
    await page.getByLabel('Mật khẩu', { exact: true }).fill(credentials[username]);
    await page.getByRole('button', { name: /Đăng nhập vào LabelX/ }).click();
    await page.waitForURL(`${FRONTEND}/`);
    return { context, page };
  }

  async function csrfPost(page, pathname, body) {
    return page.evaluate(async ({ backend, pathname, body }) => {
      await fetch(`${backend}/api/auth/csrf/`, { credentials: 'include' });
      const csrf = document.cookie.split('; ').find(value => value.startsWith('csrftoken='))?.split('=')[1];
      const response = await fetch(`${backend}${pathname}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf || '', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      return { status: response.status, payload: await response.json() };
    }, { backend: BACKEND, pathname, body });
  }

  // QA Lead: real list response, full evidence, reusable case lookup, cursor, and write.
  {
    const { context, page } = await session('t039_qalead');
    const firstPageResponse = page.waitForResponse(r => r.url().startsWith(`${BACKEND}/api/escalations/`) && r.status() === 200);
    await page.goto(`${FRONTEND}/escalations`);
    const firstPage = await (await firstPageResponse).json();
    assert.equal(firstPage.results.length, 50);
    assert(firstPage.next, 'first page must expose a cursor');
    assert.equal(await page.getByRole('link', { name: 'Escalations', exact: true }).getAttribute('href'), '/escalations');
    const primaryRow = page.getByRole('row').filter({ hasText: '#1' }).first();
    await primaryRow.getByRole('button', { name: 'Mở phân xử' }).click();
    await page.getByRole('region', { name: 'Bằng chứng issue 1' }).getByText('reference_match').waitFor();
    await page.getByRole('region', { name: 'Quyết định reviewer của issue 1' }).getByText('Primary browser escalation').waitFor();
    await page.getByRole('table', { name: 'Kết quả Decision Case' }).getByText('Historical case for reusable lookup').waitFor();
    await page.screenshot({ path: path.join(output, 'qa-lead-evidence-and-case.png'), fullPage: true });
    record('QA Lead sees escalation evidence, reviewer decision, and reusable Decision Case lookup');

    const secondResponse = page.waitForResponse(r => new URL(r.url()).searchParams.has('cursor') && r.status() === 200);
    await page.getByRole('button', { name: 'Trang sau' }).click();
    assert.equal((await (await secondResponse).json()).results.length, 1);
    await page.getByText('Trang 2', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(output, 'qa-lead-cursor-page-2.png'), fullPage: true });
    record('Cursor pagination reaches second page', { first_page_count: 50, second_page_count: 1 });

    await page.getByRole('button', { name: 'Trang trước' }).click();
    await page.getByText('Trang 1', { exact: true }).waitFor();
    await page.getByRole('row').filter({ hasText: '#1' }).first().getByRole('button', { name: 'Mở phân xử' }).click();
    await page.getByLabel('Thiếu guideline').check();
    await page.getByLabel('Lý do *').fill('Browser verified guideline gap mapping');
    const adjudication = page.waitForResponse(r => r.url().endsWith('/api/issues/1/adjudications/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Lưu kết luận phân xử' }).click();
    const adjudicationResponse = await adjudication;
    assert.equal(adjudicationResponse.status(), 201);
    assert.equal((await adjudicationResponse.json()).outcome, 'guideline_missing');
    await page.getByText(/Đã lưu Decision Case/).waitFor();
    record('QA Lead adjudication uses real CSRF, idempotency key, and guideline_gap compatibility seam');
    await context.close();
  }

  // Same-account client guard.
  {
    const { context, page } = await session('t039_self_qa');
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByRole('row').filter({ hasText: '#2' }).first().getByRole('button', { name: 'Mở phân xử' }).click();
    await page.getByRole('alert').filter({ hasText: 'không được tự phân xử' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Lưu kết luận phân xử' }).isDisabled(), true);
    await page.screenshot({ path: path.join(output, 'same-account-client-guard.png'), fullPage: true });
    record('Same-account escalator is blocked in the UI');
    await context.close();
  }

  // Natural-person alias: UI cannot infer it, backend must reject it.
  {
    const { context, page } = await session('t039_alias_qa');
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByRole('row').filter({ hasText: '#3' }).first().getByRole('button', { name: 'Mở phân xử' }).click();
    await page.getByLabel('Lý do *').fill('Attempt from reviewer employee alias');
    const rejected = page.waitForResponse(r => r.url().endsWith('/api/issues/3/adjudications/') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Lưu kết luận phân xử' }).click();
    assert.equal((await rejected).status(), 403);
    await page.getByRole('alert').filter({ hasText: 'SAME_REQUESTER_APPROVER' }).waitFor();
    await page.screenshot({ path: path.join(output, 'same-natural-person-api-rejection.png'), fullPage: true });
    record('Backend rejects an alias sharing the escalator EmployeeIdentity');
    await context.close();
  }

  // Super Admin override is mandatory in the form.
  {
    const { context, page } = await session('t039_superadmin');
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByRole('row').filter({ hasText: '#1' }).first().getByRole('button', { name: 'Mở phân xử' }).click();
    await page.getByLabel('Lý do *').fill('Super Admin browser validation');
    const writesBefore = api.filter(item => item.username === 't039_superadmin' && item.method === 'POST' && item.path.includes('/adjudications/')).length;
    assert.equal(await page.getByLabel('Lý do override *').getAttribute('required'), '');
    await page.getByRole('button', { name: 'Lưu kết luận phân xử' }).click();
    await page.waitForTimeout(300);
    assert.equal(api.filter(item => item.username === 't039_superadmin' && item.method === 'POST' && item.path.includes('/adjudications/')).length, writesBefore);
    await page.screenshot({ path: path.join(output, 'super-admin-override-required.png'), fullPage: true });
    record('Super Admin override reason is required before submission');
    await context.close();
  }

  // Reviewer and Annotator never mount the protected workspace or call its list API.
  for (const username of ['t039_reviewer', 't039_annotator']) {
    const before = api.filter(item => item.username === username && item.path === '/api/escalations/').length;
    const { context, page } = await session(username);
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByText('403 - Quyền truy cập bị từ chối').waitFor();
    const after = api.filter(item => item.username === username && item.path === '/api/escalations/').length;
    assert.equal(after, before);
    const direct = await context.request.get(`${BACKEND}/api/escalations/`);
    assert.equal(direct.status(), 403);
    record(`${username} is denied by frontend guard and backend API`);
    await context.close();
  }

  // Missing verified identity is blocked before protected data is fetched.
  {
    const { context, page } = await session('t039_unmapped_qa');
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByText('IDENTITY_MAPPING_MISSING', { exact: true }).waitFor();
    assert.equal(api.filter(item => item.username === 't039_unmapped_qa' && item.path === '/api/escalations/').length, 0);
    record('Unmapped QA Lead fails closed before escalation data fetch');
    await context.close();
  }

  // A valid QA role in dataset 99 sees no dataset 42 list rows and cannot mutate them.
  {
    const { context, page } = await session('t039_outscope_qa');
    await page.goto(`${FRONTEND}/escalations`);
    await page.getByText('Không có issue nào đang chờ phân xử.').waitFor();
    const direct = await csrfPost(page, '/api/issues/1/adjudications/', {
      outcome: 'confirm', rule_id: 'RULE-01', reason: 'Out-of-scope attempt',
    });
    assert.equal(direct.status, 403);
    assert.equal(direct.payload.code, 'OUT_OF_SCOPE');
    record('Dataset scope filters reads and rejects cross-dataset adjudication');
    await context.close();
  }

  assert.deepEqual(pageErrors, []);
  const expectedConsoleErrors = consoleErrors.filter(item => item.message.includes('status of 403'));
  const unexpectedConsoleErrors = consoleErrors.filter(item => !item.message.includes('status of 403'));
  assert.deepEqual(unexpectedConsoleErrors, []);
  const evidence = {
    status: 'passed',
    generated_at: new Date().toISOString(),
    auth: 'real Django session + CSRF cookie/header',
    data: 'isolated PostgreSQL database labelx_t039_browser',
    frontend: FRONTEND,
    backend: BACKEND,
    browser: path.basename(executablePath),
    checks: results,
    api,
    pageErrors,
    expectedConsoleErrors,
    consoleErrors: unexpectedConsoleErrors,
  };
  fs.writeFileSync(path.join(output, 'browser-api-evidence.json'), `${JSON.stringify(evidence, null, 2)}\n`);
  await browser.close();
  console.log(JSON.stringify({ status: evidence.status, checks: results.length, apiCalls: api.length, pageErrors: 0 }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
