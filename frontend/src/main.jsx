import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { request } from './api.js';
import './style.css';

const number = (value, digits = 0) => Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: digits });
const label = (value) => value?.replaceAll('_', ' ') || 'OFFLINE';
const time = (value) => value ? new Date(value).toLocaleTimeString('en-GB') : '—';
const isOnline = (live) => live && Date.now() - Date.parse(live.timestamp) < 60000;
const sections = [['overview', '◫', 'Overview'], ['vehicles', '▤', 'Live vehicles'], ['alerts', '⚑', 'Active alerts'], ['analytics', '▥', 'Analytics'], ['infrastructure', '◇', 'Infrastructure']];
const names = { summary: 'Fleet statistics', vehicles: 'Vehicles', alerts: 'Alerts', idling: 'Idling insights', events: 'Telemetry activity', metrics: 'Metrics', routing: 'Routing', health: 'System health' };

function Brand() {
  return <a className="brand" href="#overview" aria-label="ValeoSense overview"><span className="brand-icon" aria-hidden="true">v↗</span><span>ValeoSense<small>CONNECTED INTELLIGENCE</small></span></a>;
}
function Empty({ failed, loading, children }) {
  return <div className={`empty ${failed ? 'unavailable' : ''}`}><span aria-hidden="true">{failed ? '↯' : loading ? '◌' : '↗'}</span><p>{failed ? 'Data unavailable. Reconnecting automatically.' : loading ? 'Connecting to your fleet…' : children}</p></div>;
}
function PanelHeading({ title, subtitle, children }) {
  return <div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div>{children}</div>;
}
function History({ vehicle, apiKey, close }) {
  const dialog = useRef(null);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const opener = document.activeElement;
    const modal = dialog.current;
    modal.showModal();
    return () => { modal.close(); opener?.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setHistory(null); setError('');
    request(`/api/v1/vehicles/${vehicle}/history?limit=12`, apiKey, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setHistory(data); })
      .catch(error => { if (!controller.signal.aborted) setError(error.message); });
    return () => controller.abort();
  }, [vehicle, apiKey, attempt]);
  return <dialog ref={dialog} className="modal panel" aria-label="Vehicle history" onCancel={close} onClick={e => { if (e.target === dialog.current) close(); }}>
    <PanelHeading title={`${vehicle} · History`} subtitle="Most recent 12 events · last 24 hours"><button onClick={close} aria-label="Close history">✕</button></PanelHeading>
    {error ? <div className="error" role="alert"><p>History unavailable: {error}</p><button onClick={() => setAttempt(n => n + 1)}>Retry history ↻</button></div> : history ? <>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Historical telemetry"><table><thead><tr><th>Time</th><th>Speed</th><th>Scenario</th></tr></thead><tbody>{history.data.map((row, i) => <tr key={i}><td>{time(row.timestamp)}</td><td>{number(row.speed_kmh, 1)} km/h</td><td>{label(row.event_type)}</td></tr>)}</tbody></table></div>
      {!history.data.length && <Empty>No events recorded in the last 24 hours.</Empty>}
      {history.execution && <p className="panel-note">{history.execution.route} · {history.execution.engine} · {history.execution.latency_ms} ms</p>}
    </> : <Empty loading/>}
  </dialog>;
}

function App() {
  const [key, setKey] = useState(sessionStorage.getItem('valeosense-key') || '');
  const [draft, setDraft] = useState('');
  const [state, setState] = useState({});
  const [errors, setErrors] = useState({});
  const [updated, setUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const [section, setSection] = useState(window.location.hash.slice(1) || 'overview');

  useEffect(() => {
    const onHash = () => setSection(window.location.hash.slice(1) || 'overview');
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    if (!key) return;
    let active = true;
    const timers = new Map();
    const controller = new AbortController();
    const endpoints = {
      summary: '/api/v1/fleet/summary', vehicles: `/api/v1/vehicles?limit=12&offset=${offset}`,
      alerts: '/api/v1/alerts?limit=12', idling: '/api/v1/analytics/idling',
      events: '/api/v1/analytics/events', metrics: '/api/v1/system/metrics',
      routing: '/api/v1/system/routing', health: '/health',
    };
    setLoading(true);
    setState({});
    setErrors({});
    setUpdated(null);
    // Independent polling keeps live panels responsive even when analytics is slow.
    async function poll(name, path) {
      try {
        const result = await request(path, key, { signal: controller.signal });
        if (!active) return;
        setState(previous => ({ ...previous, [name]: result }));
        setErrors(previous => { const next = { ...previous }; delete next[name]; return next; });
        if (name === 'summary') setUpdated(new Date());
      } catch (error) {
        if (!active) return;
        setErrors(previous => ({ ...previous, [name]: error }));
        // Failed panels must not keep displaying an old snapshot as live data.
        setState(previous => { const next = { ...previous }; delete next[name]; return next; });
        if (name === 'summary') setUpdated(null);
      } finally {
        if (active) {
          if (name === 'summary') setLoading(false);
          timers.set(name, setTimeout(() => poll(name, path), 3000));
        }
      }
    }
    Object.entries(endpoints).forEach(([name, path]) => poll(name, path));
    return () => { active = false; controller.abort(); timers.forEach(timer => clearTimeout(timer)); };
  }, [key, offset, attempt]);

  const disconnect = () => {
    sessionStorage.removeItem('valeosense-key');
    setKey(''); setDraft(''); setState({}); setErrors({}); setUpdated(null); setSelected(null); setOffset(0);
  };
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
  const failed = Object.keys(errors);
  const unauthorized = Object.values(errors).some(error => error.status === 401);
  const total = state.vehicles?.pagination?.total ?? 0;
  const vehicles = state.vehicles?.data || [];
  const degraded = state.health?.status === 'degraded';
  const emptyProps = name => ({ failed: !!errors[name], loading: !state[name] && !errors[name] });

  if (!key) return <div className="login-layout"><div className="login-story"><Brand/><div><span className="sticker">LESS NOISE. MORE SIGNAL.</span><h1>Your fleet.<br/>In full <em>focus.</em></h1><p>A front-row seat to every vehicle, every alert, and every signal that matters.</p><div className="login-art" aria-hidden="true"><span>↗</span><div>LIVE SIGNALS<br/><b>ALL IN ONE PLACE.</b></div></div></div><small>FLEET OPERATIONS / VALEOSENSE</small></div><main className="login"><span className="eyebrow">LET’S GET YOU CONNECTED</span><h2>Take the wheel.</h2><p>Connect to your local fleet workspace.</p><form onSubmit={e => { e.preventDefault(); const value = draft.trim(); if (value) { sessionStorage.setItem('valeosense-key', value); setKey(value); } }}><label htmlFor="api-key">Local demo API key</label><input id="api-key" type="password" value={draft} onChange={e => setDraft(e.target.value)} required autoComplete="off" placeholder="Enter your API key"/><button className="primary-button">Open fleet overview <span>↗</span></button></form><small>Use API_KEY from your local .env. The key stays in this browser session.</small><div className="login-note"><span className="dot"/>Synthetic fleet demo · Real telemetry pipeline</div></main></div>;

  return <div className="app">
    <a className="skip-link" href="#overview">Skip to dashboard</a>
    <aside><Brand/><div className="nav-label">YOUR WORKSPACE <span>01</span></div><nav aria-label="Main navigation">{sections.map(([id, icon, title]) => <a key={id} href={`#${id}`} className={section === id ? 'selected' : ''} aria-current={section === id ? 'location' : undefined} title={title}><span className="nav-icon" aria-hidden="true">{icon}</span><span>{title}</span><span className="nav-arrow" aria-hidden="true">↗</span></a>)}</nav><div className="sidebar-note"><span className="sidebar-spark" aria-hidden="true">✳</span><strong>Big fleet.<br/>Clear picture.</strong><p>Every signal has a story.<br/>Stay ahead of yours.</p></div><div className="sidebar-bottom"><span className="dot"/> Synthetic fleet demo<p>{summary ? `${number(summary.registered_vehicles)} registered vehicles` : 'Local workspace'}</p><button className="text-button" onClick={disconnect}>Disconnect <span>↗</span></button></div></aside>
    <main id="overview"><header><div className="breadcrumb">Workspace <span>/</span> <b>Fleet overview</b></div><div className="header-right"><span className={`status-pill ${freshProcessor ? '' : 'muted'}`}><i className="dot"/>{freshProcessor ? 'Stream connected' : 'Awaiting stream'}</span><span className="avatar">VS</span></div></header>
      <div className="content"><div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line"/> FLEET OPERATIONS / OVERVIEW</div><h1>Every signal.<br className="mobile-break"/> A clearer picture<span className="heading-period">.</span></h1><p>Your fleet, at a glance. Stay in motion. Stay in control.</p></div><div className="refresh"><button onClick={() => setAttempt(n => n + 1)} disabled={loading}>↻ {loading ? 'Connecting…' : 'Refresh data'}</button><small>Auto-refresh 3s · {updated ? `Updated ${time(updated)}` : 'Awaiting fleet data'}</small></div></div>
        {(failed.length > 0 || degraded) && <div className="error" role="alert"><span className="error-icon" aria-hidden="true">!</span><div><strong>{unauthorized ? 'Let’s reconnect your workspace.' : 'A few signals are out of reach.'}</strong><p>{unauthorized ? 'Your API key was not accepted. Update it to reconnect.' : failed.length ? [...new Set(Object.values(errors).map(error => error.message))].join(' ') : 'Some data services are unavailable. Reconnecting automatically.'}</p><small>{failed.map(name => names[name]).join(' · ')}{degraded ? ` · Unavailable services: ${Object.entries(state.health.services).filter(([, status]) => status !== 'ok').map(([name]) => name).join(', ')}` : ''}</small></div><button onClick={unauthorized ? disconnect : () => setAttempt(n => n + 1)}>{unauthorized ? 'Update API key' : 'Retry now ↻'}</button></div>}
        <section className="cards" aria-label="Fleet statistics">{[
          ['Registered vehicles', summary?.registered_vehicles, 'Synthetic master registry', '◈', 'cream'],
          ['Online vehicles', summary?.online_vehicles, 'Telemetry within 60 seconds', '↗', 'lime'],
          ['Events / second', summary?.events_per_sec, 'Measured consumer rate', 'ϟ', 'lavender'],
          ['Active alerts', summary?.active_alerts, 'Current detected incidents', '⚑', 'coral'],
          ['Currently idling', summary?.currently_idling, 'Engine on · speed ≤ 0.5 km/h', '◷', 'cream'],
          ['Estimated idling waste', state.idling ? `₹${number(waste, 1)}` : undefined, '7 days · top 20 · ICE estimate', '₹', 'yellow'],
        ].map(([name, value, sub, icon, color], i) => <article className={`stat ${color}`} key={name}><div className="stat-label">{name}<span aria-hidden="true">{icon}</span></div><strong>{value === undefined ? '—' : typeof value === 'string' ? value : number(value)}</strong><div className="stat-bottom"><small>{sub}</small><span aria-hidden="true">0{i + 1}</span></div></article>)}</section>
        <div className="section-label"><span>01 / ON THE GROUND</span><span>YOUR FLEET, RIGHT NOW ↘</span></div>
        <div className="main-grid"><section className="panel vehicle-panel" id="vehicles"><PanelHeading title={<>Live vehicle feed <span className={`tiny-dot ${freshProcessor ? '' : 'gray'}`}/></>} subtitle="The latest from your connected fleet"><span className="badge">{state.vehicles ? number(total) : '—'} VEHICLES</span></PanelHeading>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Live vehicle readings"><table><thead><tr><th>Vehicle / Fleet</th><th>Speed</th><th>Energy</th><th>Status</th><th>Last seen</th></tr></thead><tbody>{vehicles.map(vehicle => { const live = vehicle.live; const online = isOnline(live); const energy = live?.fuel_pct ?? live?.soc_pct; return <tr key={vehicle.vehicle_id}><td><button className="vehicle-id" onClick={() => setSelected(vehicle.vehicle_id)}>{vehicle.vehicle_id} <span aria-hidden="true">↗</span></button><small>{vehicle.fleet_id} · {vehicle.oem} {vehicle.model}</small></td><td><b>{live ? number(live.speed_kmh, 1) : '—'}</b> <small className="inline">km/h</small></td><td><span>{energy == null ? '—' : `${number(energy)}%`}</span><small>{vehicle.fuel_type === 'EV' ? 'Battery SOC' : 'Fuel level'}</small></td><td><span className={`tag ${online ? (live.status || '').toLowerCase() : 'offline'}`}><i/>{online ? label(live.status) : 'OFFLINE'}</span></td><td className="mono">{time(live?.timestamp)}</td></tr>; })}</tbody></table></div>
          {!vehicles.length && <Empty {...emptyProps('vehicles')}>No vehicle metadata yet. Seed your fleet to get started.</Empty>}
          <div className="table-footer"><span>Showing <b>{vehicles.length ? `${number(offset + 1)}–${number(offset + vehicles.length)}` : '0'}</b> of {state.vehicles ? number(total) : '—'}</span><div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 12))}>← Previous</button><button disabled={!state.vehicles || offset + 12 >= total} onClick={() => setOffset(offset + 12)}>Next →</button></div></div></section>
          <section className="panel alerts-panel" id="alerts"><PanelHeading title="Attention needed" subtitle="Small signals. Big priorities."><span className="alert-count">{summary?.active_alerts ?? '—'}</span></PanelHeading><div className="alert-list">{(state.alerts?.data || []).slice(0, 7).map(alert => <article className="alert" key={alert.alert_id}><div className={`alert-symbol ${alert.type === 'IDLING_ALERT' ? 'amber' : ''}`} aria-hidden="true">{alert.type === 'ENGINE_FAULT' ? '⚙' : '!'}</div><div><h3>{label(alert.type)}</h3><p><button onClick={() => setSelected(alert.vehicle_id)}>{alert.vehicle_id}</button> <span>· {alert.fleet_id}</span></p><small>{alert.type === 'IDLING_ALERT' ? `${number(alert.duration_seconds)}s idling · ₹${number(alert.estimated_cost, 2)} estimated` : alert.detail}</small></div><time>{time(alert.timestamp)}</time></article>)}</div>{!state.alerts?.data?.length && <Empty {...emptyProps('alerts')}>All clear for now. Active detections will appear here.</Empty>}<div className="panel-note"><span aria-hidden="true">↳</span> Detected from telemetry, not scenario labels.</div></section></div>
        <div className="section-label"><span>02 / THE BIGGER PICTURE</span><span>TURN SIGNALS INTO INSIGHT ↘</span></div>
        <div className="analytics-grid" id="analytics"><section className="panel"><PanelHeading title="Telemetry activity" subtitle="Events per minute · latest 240 time/type groups"><span className="badge lavender">LAST 24H</span></PanelHeading><div className="chart" aria-label="Events per minute">{chart.length ? chart.map(([minute, n]) => <div className="bar-column" key={minute} title={`${minute}: ${n} events`}><span>{number(n)}</span><div style={{ height: `${Math.max(3, n / max * 125)}px` }}/><small>{time(minute).slice(0, 5)}</small></div>) : <Empty {...emptyProps('events')}>Your activity takes shape after the first processor batch.</Empty>}</div><div className="legend">{Object.entries(distribution).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([name, n]) => <span key={name}><i/>{label(name)} <b>{number(n)}</b></span>)}</div></section>
          <section className="panel"><PanelHeading title="Idling insights" subtitle="Top vehicles · last 7 days"><span className="badge yellow">ICE + EV</span></PanelHeading>{idle.slice(0, 5).map((row, i) => <div className="idle-row" key={row.vehicle_id}><span className="rank">0{i + 1}</span><div><button className="vehicle-id" onClick={() => setSelected(row.vehicle_id)}>{row.vehicle_id}</button><small>{row.fleet_id}</small></div><span>{number(row.duration_seconds / 60, 1)} <small className="inline">min</small></span><b>₹{number(row.estimated_cost, 2)}</b></div>)}{!idle.length && <Empty {...emptyProps('idling')}>Less idle time. More road time. Continuous idle readings appear here.</Empty>}<div className="panel-note">Estimate: {state.idling?.assumptions?.idle_fuel_lph ?? '—'} L/h at ₹{state.idling?.assumptions?.fuel_price_per_litre ?? '—'}/L. EV fuel cost excluded.</div></section></div>
        <section className="infrastructure" id="infrastructure"><div><div className="eyebrow">03 / UNDER THE HOOD</div><h2>The right store.<br/>For every signal<span>↗</span></h2><p>Live state stays responsive while analytics does the heavy lifting.</p><div className="route-chips"><span>LIVE <b>Redis</b></span><span>METADATA <b>PostgreSQL</b></span><span>ANALYTICS <b>{route?.analytics_configured_route === 'queryflux' ? 'QueryFlux → ClickHouse' : route?.analytics_configured_route === 'direct' ? 'ClickHouse direct' : 'Unavailable'}</b></span></div><div className="query-counters" aria-label="Query counters"><span>Live queries <b>{metrics ? number(metrics.api.live_queries) : '—'}</b></span><span>Metadata queries <b>{metrics ? number(metrics.api.metadata_queries) : '—'}</b></span><span>Analytics queries <b>{metrics ? number(metrics.analytics_requests) : '—'}</b></span></div></div><div className="query-card"><div className="query-title"><span>ANALYTICAL QUERY</span><span aria-hidden="true">↗</span></div><strong>7-day fleet idling</strong><div><span>Route</span><b>{execution?.route ?? 'Not yet verified'}</b></div><div><span>Engine</span><b>{execution?.engine ?? '—'}</b></div><div><span>Latency</span><b>{execution ? `${execution.latency_ms} ms` : '—'}</b></div><small>Response metadata · Available in debug mode</small></div></section>
        <section className="health-strip"><strong><i className={`dot ${state.health?.status === 'ok' ? '' : 'gray'}`}/>System health</strong><span>Data services <b>{state.health?.status ?? 'unavailable'}</b></span><span>Consumer lag <b>{freshProcessor && processor.consumer_lag != null ? number(processor.consumer_lag) : '—'}</b></span><span>Duplicates ignored <b>{freshProcessor ? number(processor.duplicates_ignored) : '—'}</b></span><span>Processor errors <b>{freshProcessor ? number(processor.processor_errors) : '—'}</b></span><span>QueryFlux requests <b>{metrics ? number(metrics.queryflux_requests) : '—'}</b></span></section>
        <footer><strong>ValeoSense<span>↗</span></strong><span>EVERY SIGNAL COUNTS.</span><span>Synthetic telemetry · Hackathon prototype</span></footer>
      </div>
    </main>
    {selected && <History key={selected} vehicle={selected} apiKey={key} close={() => setSelected(null)}/>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
