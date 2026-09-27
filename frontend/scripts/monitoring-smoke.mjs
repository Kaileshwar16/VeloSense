import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const env = await readFile(new URL('../../.env', import.meta.url), 'utf8');
const value = name => env.split('\n').find(line => line.startsWith(`${name}=`))?.slice(name.length + 1).trim();
const password = process.env.GRAFANA_ADMIN_PASSWORD || value('GRAFANA_ADMIN_PASSWORD') || value('API_KEY');
const url = process.env.GRAFANA_URL || 'http://127.0.0.1:3001';
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
const errors = [];
const queries = [];
page.on('pageerror', error => errors.push(error.message));
page.on('response', response => {
  if (response.url().includes('/api/ds/query')) queries.push(response);
});
try {
  const login = await page.request.post(`${url}/login`, { data: { user: 'admin', password } });
  assert.equal(login.status(), 200, 'Grafana login failed');
  await page.goto(`${url}/d/valeosense-overview?from=now-15m&to=now`, { waitUntil: 'networkidle' });
  await page.getByText('Metrics API reachable', { exact: true }).waitFor();
  await page.getByText('Pipeline throughput', { exact: true }).waitFor();
  assert.ok(queries.length > 0, 'dashboard did not query its datasource');
  for (const response of queries) {
    assert.equal(response.status(), 200, 'Grafana datasource query failed');
    const body = await response.json();
    for (const result of Object.values(body.results || {})) {
      assert.ok(!result.error, result.error || 'datasource error');
    }
  }
  assert.deepEqual(errors, [], 'browser JavaScript errors');
  // Grafana virtualizes panels; full-page resizing can unmount the visible grid.
  await page.screenshot({ path: '../artifacts/grafana-dashboard.png' });
  const evidence = { verified_at: new Date().toISOString(), browser: await browser.version(),
    checks: ['Grafana login', 'provisioned dashboard rendered', 'real datasource queries without errors', 'no JavaScript errors', 'actual browser screenshot'], passed: true };
  await writeFile('../artifacts/grafana-browser-smoke.json', JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await browser.close();
}
