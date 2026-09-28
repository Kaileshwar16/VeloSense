export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

// Keep credentials and requests on the dashboard origin (Vite/nginx proxy).
export async function request(path, key, { signal, timeout = 35000 } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
  try {
    const response = await fetch(path, {
      headers: { 'X-API-Key': key }, signal: controller.signal,
    });
    if (response.status === 401) throw new ApiError('Your API key was not accepted. Update it to reconnect.', 401);
    if (response.status === 502 || response.status === 504) {
      throw new ApiError('The dashboard cannot reach the API. Check that the backend is running.', response.status);
    }
    const isJson = response.headers.get('content-type')?.includes('application/json');
    if (!isJson) throw new ApiError('The API did not return data. Check the backend and dashboard proxy.', response.status);
    const body = await response.json();
    // A degraded health response still tells us which services are unavailable.
    if (path === '/health' && response.status === 503 && body.services) return body;
    if (!response.ok) throw new ApiError(body.error?.message || `Request failed (HTTP ${response.status}).`, response.status);
    return body;
  } catch (error) {
    if (signal?.aborted) throw error;
    if (timedOut) throw new ApiError('The API took too long to respond. Retrying automatically.');
    if (error instanceof ApiError) throw error;
    throw new ApiError('Cannot connect to the API. Check your connection and that the local services are running.');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}
