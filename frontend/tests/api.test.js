import { test } from 'node:test';
import assert from 'node:assert/strict';
import { request } from '../src/api.js';

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

test('request failures explain authentication, proxy, and network errors', async t => {
  for (const [response, expected] of [
    [json({}, 401), /API key was not accepted/],
    [new Response('Bad gateway', { status: 502 }), /cannot reach the API/],
    [new Response('<html>SPA fallback</html>'), /dashboard proxy/],
    [json({ error: { message: 'A required data service is unavailable' } }, 503), /required data service/],
  ]) {
    t.mock.method(globalThis, 'fetch', async () => response);
    await assert.rejects(request('/api/v1/vehicles', 'test-key'), expected);
    t.mock.restoreAll();
  }
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(request('/api/v1/vehicles', 'test-key'), /Cannot connect to the API/);
});

test('degraded health retains service diagnostics', async t => {
  const body = { status: 'degraded', services: { redis: 'unavailable' } };
  t.mock.method(globalThis, 'fetch', async () => json(body, 503));
  assert.deepEqual(await request('/health', 'test-key'), body);
});

test('hung requests time out and caller cancellation is preserved', async t => {
  t.mock.method(globalThis, 'fetch', async (_, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  await assert.rejects(request('/api/v1/vehicles', 'test-key', { timeout: 10 }), /took too long/);
  const controller = new AbortController();
  const pending = request('/api/v1/vehicles', 'test-key', { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
});
