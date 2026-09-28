import { test, expect } from '@playwright/test';

const fixture = pathname => {
  if (pathname === '/health') return { status: 'ok', services: { redis: 'ok', postgres: 'ok', clickhouse: 'ok' } };
  if (pathname.endsWith('/summary')) return { data: { registered_vehicles: 100000, online_vehicles: 1000, events_per_sec: 982, active_alerts: 3, currently_idling: 47 } };
  if (pathname.endsWith('/metrics')) return { data: { api: { live_queries: 123, metadata_queries: 23 }, analytics_requests: 42, queryflux_requests: 0, processor: { updated_at: Date.now() / 1000, consumer_lag: 2, duplicates_ignored: 0, processor_errors: 0 } } };
  if (pathname.endsWith('/routing')) return { data: { analytics_configured_route: 'direct' } };
  if (pathname.endsWith('/idling')) return { data: Array.from({ length: 5 }, (_, i) => ({ vehicle_id: `V00000${i + 1}`, fleet_id: 'F001', duration_seconds: 3600 - i * 450, estimated_cost: 80 - i * 10 })), assumptions: { idle_fuel_lph: 0.8, fuel_price_per_litre: 100 }, execution: { route: 'direct', engine: 'clickhouse', latency_ms: 12 } };
  if (pathname.endsWith('/events')) return { data: Array.from({ length: 12 }, (_, i) => ({ minute: new Date(Date.now() - (12 - i) * 60000).toISOString(), event_type: 'NORMAL', events: 320 + i * 31 })) };
  if (pathname.endsWith('/alerts')) return { data: ['ENGINE_FAULT', 'IDLING_ALERT', 'SPEEDING'].map((type, i) => ({ alert_id: `a${i}`, vehicle_id: `V00000${i + 1}`, fleet_id: 'F001', type, duration_seconds: 140, estimated_cost: 3.1, detail: 'Threshold exceeded', timestamp: new Date().toISOString() })) };
  if (pathname.endsWith('/history')) return { data: [{ timestamp: new Date().toISOString(), speed_kmh: 42, event_type: 'NORMAL' }] };
  return { data: [] };
};

async function setup(page, override = async () => false) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route(/\/(api\/v1\/|health)/, async route => {
    const url = new URL(route.request().url());
    if (await override(route, url)) return;
    let body = fixture(url.pathname);
    if (url.pathname === '/api/v1/vehicles') {
      const offset = Number(url.searchParams.get('offset'));
      body = { data: Array.from({ length: 12 }, (_, i) => ({ vehicle_id: `V${String(offset + i + 1).padStart(6, '0')}`, fleet_id: 'F001', oem: 'Tata', model: 'Nexon', fuel_type: 'ICE', live: { timestamp: new Date().toISOString(), speed_kmh: 40 + i, fuel_pct: 70 - i, status: i % 3 ? 'MOVING' : 'IDLING' } })), pagination: { total: 100000, offset, limit: 12 } };
    }
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.getByLabel('Local demo API key').fill('test-key');
  await page.getByRole('button', { name: 'Open fleet overview' }).click();
  return errors;
}

test('desktop and mobile dashboard, pagination, keyboard history, and navigation', async ({ page }, testInfo) => {
  const errors = await setup(page);
  await expect(page.locator('.stat').first()).toContainText('1,00,000');
  await expect(page.locator('.error')).toHaveCount(0);
  const vehicle = page.getByRole('button', { name: 'V000001', exact: false }).first();
  await vehicle.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('.modal tbody')).toContainText('42 km/h');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(vehicle).toBeFocused();
  await page.getByRole('button', { name: 'Next →', exact: true }).click();
  await expect(page.locator('#vehicles tbody')).toContainText('V000013');
  await page.getByRole('button', { name: '← Previous', exact: true }).click();
  await expect(page.locator('#vehicles tbody')).toContainText('V000001');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath('dashboard-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath('dashboard-mobile.png'), fullPage: true });
  await page.getByRole('link', { name: 'Analytics', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Analytics', exact: true })).toHaveAttribute('aria-current', 'location');
  await page.getByRole('button', { name: 'Disconnect' }).click();
  await expect(page.getByLabel('Local demo API key')).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('network outage clears failed data and retry recovers without reloading', async ({ page }) => {
  let offline = false;
  await setup(page, async (route, url) => {
    if (offline && url.pathname === '/api/v1/vehicles') { await route.abort('failed'); return true; }
  });
  await expect(page.locator('#vehicles tbody')).toContainText('V000001');
  offline = true;
  await expect(page.getByRole('alert')).toContainText('Cannot connect to the API', { timeout: 10000 });
  await expect(page.locator('#vehicles tbody tr')).toHaveCount(0);
  await expect(page.locator('#vehicles')).toContainText('Data unavailable');
  await expect(page.locator('.stat').first()).toContainText('1,00,000');
  offline = false;
  await page.getByRole('button', { name: 'Retry now' }).click();
  await expect(page.locator('#vehicles tbody')).toContainText('V000001');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('bad credentials can be replaced and do not look like empty fleet data', async ({ page }) => {
  await setup(page, async (route, url) => {
    if (url.pathname.startsWith('/api/')) { await route.fulfill({ status: 401, json: { error: { message: 'Invalid key' } } }); return true; }
  });
  await expect(page.getByRole('alert')).toContainText('API key was not accepted');
  await expect(page.locator('.stat').first().locator('strong')).toHaveText('—');
  await page.getByRole('button', { name: 'Update API key' }).click();
  await expect(page.getByLabel('Local demo API key')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('valeosense-key'))).toBeNull();
});

test('slow analytics does not block live data and degraded health names the service', async ({ page }) => {
  let release;
  const blocked = new Promise(resolve => { release = resolve; });
  try {
    await setup(page, async (route, url) => {
      if (url.pathname.endsWith('/events')) { await blocked; await route.fulfill({ json: { data: [] } }); return true; }
      if (url.pathname === '/health') { await route.fulfill({ status: 503, json: { status: 'degraded', services: { redis: 'ok', postgres: 'ok', clickhouse: 'unavailable' } } }); return true; }
    });
    await expect(page.locator('.stat').first()).toContainText('1,00,000');
    await expect(page.locator('#vehicles tbody')).toContainText('V000001');
    await expect(page.getByRole('alert')).toContainText('Unavailable services: clickhouse');
    await expect(page.locator('.health-strip')).toContainText('degraded');
  } finally { release(); }
});
