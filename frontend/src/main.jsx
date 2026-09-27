import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const number = (value, digits = 0) => Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: digits });
const label = (value) => value?.replaceAll('_', ' ') || 'OFFLINE';
const time = (value) => value ? new Date(value).toLocaleTimeString('en-GB') : '—';
const isOnline = (live) => live && Date.now() - Date.parse(live.timestamp) < 60000;

function App() {
  const [key, setKey] = useState(sessionStorage.getItem('valeosense-key') || '');
  const [draft, setDraft] = useState('');
  const [state, setState] = useState({});
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState(null);
  const [historyError, setHistoryError] = useState('');
  const refresh = useRef(0);
  useEffect(() => {
    if (!key) return;
    let active = true;
    let timer;
    const controller = new AbortController();
    async function poll() {
      const generation = ++refresh.current;
      const endpoints = {
        summary: '/api/v1/fleet/summary', vehicles: `/api/v1/vehicles?limit=12&offset=${offset}`,
        alerts: '/api/v1/alerts?limit=12', idling: '/api/v1/analytics/idling',
        events: '/api/v1/analytics/events', faults: '/api/v1/analytics/faults',
        metrics: '/api/v1/system/metrics', routing: '/api/v1/system/routing', health: '/health',
      };
      const results = await Promise.allSettled(Object.entries(endpoints).map(async ([name, path]) => {
        const response = await fetch(path, { headers: { 'X-API-Key': key }, signal: controller.signal });
        if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
        return [name, await response.json()];
      }));
      if (!active || generation !== refresh.current) return;
      const failures = results.filter(r => r.status === 'rejected');
      setError(failures.map(r => r.reason.message).join(' · '));
      // Each refresh is a new snapshot. Failed panels cannot retain apparently live old values.
      setState(Object.fromEntries(results.filter(r => r.status === 'fulfilled').map(r => r.value)));
      setUpdated(new Date());
      timer = setTimeout(poll, 3000);
    }
    poll();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [key, offset]);

  useEffect(() => {
    if (!selected || !key) return;
    const controller = new AbortController();
    setHistory(null); setHistoryError('');
    fetch(`/api/v1/vehicles/${selected}/history?limit=12`, { headers: { 'X-API-Key': key }, signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(setHistory).catch(e => { if (e.name !== 'AbortError') setHistoryError(e.message); });
    return () => controller.abort();
  }, [selected, key]);

  const summary = state.summary?.data;
  const metrics = state.metrics?.data;
  const processor = metrics?.processor;
  const freshProcessor = processor && Date.now() / 1000 - processor.updated_at < 5;
  const route = state.routing?.data;
  const idle = state.idling?.data || [];
  const waste = idle.reduce((sum, row) => sum + Number(row.estimated_cost), 0);
  const distribution = {};
  const timeline = {};
  (state.events?.data || []).forEach(row => {
    distribution[row.event_type] = (distribution[row.event_type] || 0) + Number(row.events);
    timeline[row.minute] = (timeline[row.minute] || 0) + Number(row.events);
  });
  const chart = Object.entries(timeline).sort(([a], [b]) => a.localeCompare(b)).slice(-20);
  const max = Math.max(...chart.map(([, n]) => n), 1);
  const execution = state.idling?.execution;
  if (!key) return <main className="login"><div className="brand-icon">v<span>›</span></div><h1>ValeoSense</h1><p>Real-time intelligence for massive connected-vehicle streams.</p><form onSubmit={e => { e.preventDefault(); sessionStorage.setItem('valeosense-key', draft); setKey(draft); }}><label htmlFor="api-key">Local demo API key</label><input id="api-key" type="password" value={draft} onChange={e => setDraft(e.target.value)} required autoComplete="off"/><button>Open fleet overview <span>→</span></button></form><small>Use API_KEY from your local .env. The key stays in this browser session.</small></main>;
  return <div className="app">
    <aside><a className="brand" href="#overview"><div className="brand-icon">v<span>›</span></div><div>ValeoSense<small>CONNECTED INTELLIGENCE</small></div></a><div className="nav-label">WORKSPACE</div><nav><a className="selected" href="#overview">◫ <span>Fleet overview</span></a><a href="#vehicles">▤ <span>Live vehicles</span></a><a href="#alerts">⚑ <span>Active alerts</span></a><a href="#analytics">▥ <span>Analytics</span></a><a href="#infrastructure">◇ <span>Infrastructure</span></a></nav><div className="sidebar-bottom"><span className="dot"></span> Synthetic fleet demo<p>100K registry · Seed 42</p><button className="text-button" onClick={() => { sessionStorage.removeItem('valeosense-key'); setKey(''); setState({}); }}>Disconnect</button></div></aside>
    <main id="overview"><header><div className="breadcrumb">Workspace <span>/</span> Fleet overview</div><div className="header-right"><span className={`status-pill ${freshProcessor ? '' : 'muted'}`}><i className="dot"/>{freshProcessor ? 'Stream connected' : 'Awaiting stream'}</span><span className="avatar">VS</span></div></header>
    <div className="content"><div className="page-heading"><div><div className="eyebrow">FLEET OPERATIONS</div><h1>Every signal. A clearer picture.</h1><p>Real-time connected-vehicle intelligence across your fleet.</p></div><div className="refresh">↻ Polling every 3 seconds<small>Last refresh {time(updated)}</small></div></div>
    {error && <div className="error" role="alert">Some data is unavailable. {error}</div>}
    <section className="cards" aria-label="Fleet statistics">{[
      ['Registered vehicles', summary?.registered_vehicles, 'Synthetic master registry', '◈'],
      ['Online vehicles', summary?.online_vehicles, 'Telemetry within 60 seconds', '⌁'],
      ['Events / second', summary?.events_per_sec, 'Measured consumer rate', '↗'],
      ['Active alerts', summary?.active_alerts, 'Current detected incidents', '⚑'],
      ['Currently idling', summary?.currently_idling, 'Engine on · speed ≤ 0.5 km/h', '◷'],
      ['Estimated idling waste', state.idling ? `₹${number(waste, 1)}` : undefined, '7 days · top 20 · ICE estimate', '₹'],
    ].map(([name, value, sub, icon], i) => <article className={`stat ${i === 5 ? 'accent' : ''}`} key={name}><div className="stat-label">{name}<span>{icon}</span></div><strong>{value === undefined ? '—' : typeof value === 'string' ? value : number(value)}</strong><small>{sub}</small></article>)}</section>
    <div className="main-grid"><section className="panel vehicle-panel" id="vehicles"><div className="panel-heading"><div><h2>Live vehicle feed <span className="tiny-dot"/></h2><p>Latest readings, separated from historical storage</p></div><span className="badge">{state.vehicles?.pagination?.total ? number(state.vehicles.pagination.total) : '—'} vehicles</span></div><div className="table-scroll"><table><thead><tr><th>Vehicle / Fleet</th><th>Speed</th><th>Energy</th><th>Status</th><th>Last seen</th></tr></thead><tbody>{(state.vehicles?.data || []).map(vehicle => { const live = vehicle.live; const online = isOnline(live); const energy = live?.fuel_pct ?? live?.soc_pct; return <tr key={vehicle.vehicle_id} onClick={() => setSelected(vehicle.vehicle_id)}><td><button className="vehicle-id">{vehicle.vehicle_id}</button><small>{vehicle.fleet_id} · {vehicle.oem} {vehicle.model}</small></td><td>{live ? number(live.speed_kmh, 1) : '—'} <small className="inline">km/h</small></td><td><span>{energy == null ? '—' : `${number(energy)}%`}</span><small>{vehicle.fuel_type === 'EV' ? 'Battery SOC' : 'Fuel level'}</small></td><td><span className={`tag ${online ? live.status.toLowerCase() : 'offline'}`}>{online ? label(live.status) : 'OFFLINE'}</span></td><td className="mono">{time(live?.timestamp)}</td></tr>; })}</tbody></table></div>{!state.vehicles?.data?.length && <div className="empty">Waiting for vehicle metadata.</div>}<div className="table-footer"><span>Showing {offset + 1}–{Math.min(offset + 12, state.vehicles?.pagination?.total || 0)}</span><div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 12))}>← Previous</button><button disabled={offset + 12 >= (state.vehicles?.pagination?.total || 0)} onClick={() => setOffset(offset + 12)}>Next →</button></div></div></section>
    <section className="panel alerts-panel" id="alerts"><div className="panel-heading"><div><h2>Attention needed</h2><p>Active vehicle alerts</p></div><span className="alert-count">{summary?.active_alerts ?? '—'}</span></div><div className="alert-list">{(state.alerts?.data || []).slice(0, 7).map(alert => <article className="alert" key={alert.alert_id}><div className={`alert-symbol ${alert.type === 'IDLING_ALERT' ? 'amber' : ''}`}>{alert.type === 'ENGINE_FAULT' ? '⚙' : '!'}</div><div><h3>{label(alert.type)}</h3><p><button onClick={() => setSelected(alert.vehicle_id)}>{alert.vehicle_id}</button> <span>· {alert.fleet_id}</span></p><small>{alert.type === 'IDLING_ALERT' ? `${number(alert.duration_seconds)}s idling · ₹${number(alert.estimated_cost, 2)} estimated` : alert.detail}</small></div><time>{time(alert.timestamp)}</time></article>)}</div>{!state.alerts?.data?.length && <div className="empty">No active alerts. Start the demo stream to see detections.</div>}<div className="panel-note">Detections use telemetry values, not scenario labels.</div></section></div>
    <div className="analytics-grid" id="analytics"><section className="panel"><div className="panel-heading"><div><h2>Telemetry activity</h2><p>Events per minute · latest 240 time/type groups</p></div><span className="badge">LAST 24H</span></div><div className="chart" aria-label="Events per minute">{chart.length ? chart.map(([minute, n]) => <div className="bar-column" key={minute} title={`${minute}: ${n} events`}><span>{number(n)}</span><div style={{ height: `${Math.max(3, n / max * 125)}px` }}/><small>{time(minute).slice(0, 5)}</small></div>) : <div className="empty">Historical readings appear after the first processor batch.</div>}</div><div className="legend">{Object.entries(distribution).sort((a,b) => b[1]-a[1]).slice(0, 5).map(([name, n]) => <span key={name}><i/>{label(name)} <b>{number(n)}</b></span>)}</div></section>
    <section className="panel"><div className="panel-heading"><div><h2>Idling insights</h2><p>Top vehicles · last 7 days</p></div><span className="badge">ICE + EV</span></div>{idle.slice(0, 5).map((row, i) => <div className="idle-row" key={row.vehicle_id}><span className="rank">0{i + 1}</span><div><strong>{row.vehicle_id}</strong><small>{row.fleet_id}</small></div><span>{number(row.duration_seconds / 60, 1)} <small className="inline">min</small></span><b>₹{number(row.estimated_cost, 2)}</b></div>)}{!idle.length && <div className="empty">Continuous idle readings will appear here.</div>}<div className="panel-note">Estimate assumes {state.idling?.assumptions?.idle_fuel_lph ?? '—'} L/h and ₹{state.idling?.assumptions?.fuel_price_per_litre ?? '—'}/L. EV fuel cost excluded.</div></section></div>
    <section className="infrastructure" id="infrastructure"><div><div className="eyebrow">WORKLOAD SEPARATION</div><h2>The right store for every signal.</h2><p>Live state stays responsive while analytical queries run separately.</p><div className="route-chips"><span>LIVE <b>Redis</b></span><span>METADATA <b>PostgreSQL</b></span><span>ANALYTICS <b>{route?.analytics_configured_route === 'queryflux' ? 'QueryFlux → ClickHouse' : route?.analytics_configured_route === 'direct' ? 'ClickHouse direct' : 'Unavailable'}</b></span></div><div className="route-chips" aria-label="Query counters"><span>Live queries <b>{metrics ? number(metrics.api.live_queries) : '—'}</b></span><span>Metadata queries <b>{metrics ? number(metrics.api.metadata_queries) : '—'}</b></span><span>Analytics queries <b>{metrics ? number(metrics.analytics_requests) : '—'}</b></span></div></div><div className="query-card"><div className="query-title"><span>ANALYTICAL QUERY</span><span className="dot"/></div><strong>7-day fleet idling</strong><div><span>Route</span><b>{execution?.route ?? 'Not yet verified'}</b></div><div><span>Engine</span><b>{execution?.engine ?? '—'}</b></div><div><span>Latency</span><b>{execution ? `${execution.latency_ms} ms` : '—'}</b></div><small>Last successful response · debug metadata</small></div></section>
    <section className="health-strip"><strong>System health</strong><span><i className={`dot ${state.health?.status === 'ok' ? '' : 'gray'}`}/>Data services {state.health?.status ?? 'unavailable'}</span><span>Consumer lag <b>{freshProcessor && processor.consumer_lag != null ? number(processor.consumer_lag) : '—'}</b></span><span>Duplicates ignored <b>{freshProcessor ? number(processor.duplicates_ignored) : '—'}</b></span><span>Processor errors <b>{freshProcessor ? number(processor.processor_errors) : '—'}</b></span><span>QueryFlux requests <b>{metrics ? number(metrics.queryflux_requests) : '—'}</b></span></section><footer>ValeoSense <span>Real-time intelligence for massive connected-vehicle streams.</span><span>Synthetic telemetry · Hackathon prototype</span></footer>
    </div></main>{selected && <div className="modal-backdrop" onClick={() => setSelected(null)}><section className="modal panel" role="dialog" aria-modal="true" aria-label="Vehicle history" onClick={e => e.stopPropagation()}><div className="panel-heading"><div><h2>{selected} · History</h2><p>Most recent 12 events · last 24 hours</p></div><button onClick={() => setSelected(null)} aria-label="Close history">✕</button></div>{historyError && <div className="error">History unavailable: {historyError}</div>}{history ? <><div className="table-scroll"><table><thead><tr><th>Time</th><th>Speed</th><th>Scenario</th></tr></thead><tbody>{history.data.map((row, i) => <tr key={i}><td>{time(row.timestamp)}</td><td>{number(row.speed_kmh, 1)} km/h</td><td>{label(row.event_type)}</td></tr>)}</tbody></table></div><p className="panel-note">{history.execution?.route} · {history.execution?.engine} · {history.execution?.latency_ms}ms</p></> : !historyError && <div className="empty">Loading history…</div>}</section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
