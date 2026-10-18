/* Local visual regression fixture based on QC#6. No production data or writes. */
const { chromium } = require(process.env.LABELX_PLAYWRIGHT_MODULE || 'playwright-core');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const mode = process.argv[2] || 'after';
const output = path.resolve('src/frontend/evidence/ranking-evidence');
const order = [0, 4, 2, 9, 1, 3, 5, 6, 7, 8];
const frames = order.map((number, index) => {
  const counts = number === 0 ? { E3: 2 } : number === 4 ? { E3: 1 } : {};
  const baseline = number === 2 ? 0.13 : number === 9 ? 0.12 : 0.1;
  const score = baseline + (counts.E3 || 0) * 0.5;
  return { frame_id: number + 100, frame_key: { cvat_task_id: 13, frame_number: number },
    rank: index + 1, score, baseline_score: baseline, score_version: 'score_v0',
    queue: 'risk', source: 'risk', review_state: 'unreviewed',
    missing_evidence: mode === 'after', issue_counts: counts,
    explanation: { score_version: 'score_v0', baseline_score: baseline,
      contributions: Array.from({ length: counts.E3 || 0 }, (_, cluster) => ({
        family: 'E3', candidate_hash: `fixture-${number}-${cluster}`,
        anchor_count: 2, n_i: 1, q_i: 0.5, contribution: 0.5,
      })) },
    lease_holder_user_id: null, thumbnail_url: null,
    priority: mode === 'before' ? (index < 4 ? 'high' : index < 7 ? 'medium' : 'low')
      : counts.E3 ? 'suspected' : 'unassessed' };
});
const run = { id: 6, snapshot_id: 4, config_version_id: 1, seed: 6,
  status: 'completed', is_final: false, origin_run_id: null, score_version: 'score_v0',
  model_artifact: null, created_by: 4, created_at: '2026-10-18T00:00:00Z',
  finished_at: '2026-10-18T00:01:00Z', engines: [
    ...['schema', 'geometry', 'duplicate'].map(engine => ({ engine, status: 'checked', reason: null, failed_units: 0 })),
    { engine: 'detector', status: 'not_checked', reason: 'disabled', failed_units: 0 },
  ] };
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.LABELX_BROWSER_EXECUTABLE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
  try {
    for (const width of [1440, 390]) {
      const page = await browser.newPage({ viewport: { width, height: 1100 } });
      await page.route('**/api/**', async route => {
        const url = new URL(route.request().url());
        let body;
        if (url.pathname === '/api/auth/session/') body = {
          user: { id: 4, username: 'visual-fixture', display_name: 'Dữ liệu mô phỏng QC#6' },
          roles: [{ role: 'reviewer', dataset_id: 1 }], identity_mapping: { status: 'mapped', cvat_user_id: 104 } };
        else if (url.pathname === '/api/runs/6/') body = run;
        else if (url.pathname.endsWith('/ranking/')) {
          const priority = url.searchParams.get('priority');
          body = { next: null, previous: null, source: 'risk', content_hash: 'fixture', ranking_hash: 'fixture',
            priority_counts: mode === 'before' ? { high: 4, medium: 3, low: 3 }
              : { suspected: 2, unassessed: 8, no_suspicions: 0 },
            results: frames.filter(frame => !priority || frame.priority === priority) };
        } else if (url.pathname.includes('/api/queues/')) body = { name: 'risk', run_id: 6, total: 10,
          counts: { unreviewed: 10, in_review: 0, incomplete: 0, reviewed: 0, awaiting_followup: 0, completed: 0 } };
        else if (url.pathname.includes('cvat') || url.pathname.includes('/datasets/')) body = [];
        else body = { results: [], next: null, previous: null };
        await route.fulfill({ json: body });
      });
      await page.goto('http://localhost:3106/review?run=6');
      await page.getByRole('heading', { name: 'Task #13 • Frame #9', exact: true }).waitFor();
      assert.equal(await page.getByRole('listitem').count(), 10);
      if (mode === 'after') {
        const baseline = page.getByRole('listitem').filter({ hasText: 'Task #13 • Frame #2' });
        assert.match(await baseline.innerText(), /Chưa đánh giá đầy đủ/);
        assert.doesNotMatch(await baseline.innerText(), /Ưu tiên cao|0 issue/);
        await page.getByText(/detector: NOT CHECKED — disabled/).waitFor();
      }
      await page.screenshot({ path: path.join(output, `${mode}-${width}.png`), fullPage: true });
      if (mode === 'after') {
        await page.getByLabel('Nhóm review theo bằng chứng').selectOption('unassessed');
        await page.getByRole('heading', { name: 'Task #13 • Frame #0', exact: true }).waitFor({ state: 'detached' });
        assert.equal(await page.getByRole('listitem').count(), 8);
      }
      await page.close();
    }
    fs.writeFileSync(path.join(output, `${mode}-fixture.json`), JSON.stringify({ run, frames }, null, 2));
    console.log(`${mode}: screenshots 1440/390, ten frames, evidence labels and filter assertions passed`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
