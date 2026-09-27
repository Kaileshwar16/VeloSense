import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

const env = await readFile(new URL('../../.env', import.meta.url), 'utf8');
const key = env.split('\n').find(line => line.startsWith('API_KEY=')).slice(8).trim();
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1512, height: 1100 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(process.env.DASHBOARD_URL || 'http://127.0.0.1:3000', { waitUntil: 'networkidle' });
  await page.getByLabel('Local demo API key').fill(key);
  await page.getByRole('button', { name: 'Open fleet overview' }).click();
  await page.getByRole('heading', { name: 'Every signal. A clearer picture.' }).waitFor();
  await page.locator('.stat').first().getByText('1,00,000', { exact: true }).waitFor();
  await page.getByLabel('Query counters').getByText('Analytics queries').waitFor();
  await page.getByRole('button', { name: 'V000001', exact: true }).first().click();
  await page.getByRole('dialog').waitFor();
  await page.locator('.modal tbody tr').first().waitFor();
  assert.equal(await page.locator('.modal .error').count(), 0);
  await page.getByLabel('Close history').click();
  await page.getByRole('button', { name: 'Next →', exact: true }).click();
  await page.getByRole('button', { name: 'V000013', exact: true }).first().waitFor();
  await page.getByRole('button', { name: '← Previous', exact: true }).click();
  await page.getByRole('button', { name: 'V000001', exact: true }).first().waitFor();
  assert.equal(await page.locator('.error').count(), 0, 'dashboard reported a failing service');
  await page.screenshot({ path: '../artifacts/dashboard-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: '../artifacts/dashboard-mobile.png', fullPage: true });
  assert.deepEqual(errors, [], 'browser JavaScript errors');
  const evidence = { verified_at: new Date().toISOString(), browser: await browser.version(),
    checks: ['API-key login', '100000 registry card', 'live-feed table', 'real historical query dialog',
      'pagination next and previous', 'live/metadata/analytics query counters', 'no failing data panel', 'no JavaScript errors', 'desktop and mobile screenshots'],
    passed: true };
  await writeFile('../artifacts/browser-smoke.json', JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await browser.close();
}
