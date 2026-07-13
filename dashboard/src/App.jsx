import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, openWS } from './api.js'
import { Card, Stat, Button, Field, Input, Select, Badge, cls } from './ui.jsx'
import { Overview, Auctions, CampaignTable, Charts, Scenarios, Scorecard, FillBreakdown, Latency, Findings, FlowB } from './panels.jsx'
import PublisherRequest from './publisher.jsx'
import DspSettings from './dsp_settings.jsx'

const SCENARIO_OPTIONS = [
  ['all', 'All (S1–S15)'], ['S1', 'S1 · Smoke'], ['S2', 'S2 · Normal traffic'],
  ['S3', 'S3 · Real-vs-filler'], ['S4', 'S4 · No-fill semantics'], ['S5', 'S5 · Geo targeting'],
  ['S6', 'S6 · Frequency cap'], ['S7', 'S7 · Budget exhaustion'], ['S8', 'S8 · Schedule'],
  ['S9', 'S9 · Ad pods / VMAP'], ['S10', 'S10 · OpenRTB conformance'], ['S11', 'S11 · Tracking accuracy'],
  ['S12', 'S12 · Privacy (GDPR/GPP)'], ['S13', 'S13 · ads.txt / sellers.json'],
  ['S14', 'S14 · Load / SLO'], ['S15', 'S15 · Resilience'],
]

export default function App() {
  const [view, setView] = useState('dashboard')  // 'dashboard' | 'publisher'
  const [health, setHealth] = useState(null)
  const [runs, setRuns] = useState([])
  const [runId, setRunId] = useState('')        // '' = all runs
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState(null)
  const [err, setErr] = useState(null)
  const [metrics, setMetrics] = useState({ overview: null, campaigns: [], auctions: null, ts: [], scenarios: [], scorecard: null, fill: null, findings: null })
  const [target, setTarget] = useState(null)

  const [seed, setSeed] = useState({ publishers: 3, ad_units_per_publisher: 3, demand_partners: 3, advertisers: 3, campaigns: 6, cpm_min: 5, cpm_max: 150 })
  const [run, setRun] = useState({ protocols: 'vast', total_requests: 300, requests_per_second: 50, concurrency: 10, impression_rate: 0.9, ctr: 0.03 })
  const [scen, setScen] = useState('all')
  const wsRef = useRef(null)

  const loadRuns = useCallback(async () => { try { setRuns(await api.runs()) } catch (e) { /* */ } }, [])

  const loadMetrics = useCallback(async (rid) => {
    try {
      const [overview, campaigns, auctions, ts, scenarios, scorecard, fill, findings] = await Promise.all([
        api.overview(rid), api.campaigns(rid), api.auctions(rid), api.timeseries(rid), api.scenarios(''),
        api.scorecard(rid).catch(() => null), api.fill(rid).catch(() => null), api.findings(rid).catch(() => null),
      ])
      setMetrics({ overview, campaigns, auctions, ts, scenarios, scorecard, fill, findings })
    } catch (e) { setErr(String(e.message || e)) }
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }))
    api.target().then(setTarget).catch(() => setTarget(null))
    loadRuns(); loadMetrics('')
    const ws = openWS((msg) => {
      if (msg.type === 'progress') { setLive(msg.stats); setBusy(true) }
      else if (msg.type === 'started') { setBusy(true); setLive(null) }
      else if (msg.type === 'done') { setBusy(false); setLive(msg.summary); setRunId(msg.run_id); loadRuns(); loadMetrics(msg.run_id) }
      else if (msg.type === 'scenario_done') { setBusy(false); loadRuns(); loadMetrics('') }
      else if (msg.type === 'error') { setBusy(false); setErr(msg.error) }
    })
    wsRef.current = ws
    return () => ws.close()
  }, [loadRuns, loadMetrics])

  const guard = async (fn) => {
    setErr(null)
    try { await fn() } catch (e) { setErr(String(e.message || e)) }
  }

  const doSeed = () => guard(async () => { setBusy(true); const s = await api.seed(numify(seed)); setBusy(false); await loadRuns(); await loadMetrics(runId); setLive({ seed: s.counts, findings: s.findings }) })
  const doRun = () => guard(async () => {
    const body = numify(run); body.protocols = run.protocols.split(',').map((x) => x.trim())
    await api.run(body)
  })
  const doScenario = () => guard(async () => { await api.scenario({ scenario: scen }) })
  const doStop = () => guard(() => api.stop())

  return (
    <div className="min-h-full text-slate-200">
      <header className="border-b border-slate-800 bg-slate-950/80 px-6 py-3 sticky top-0 z-10 backdrop-blur">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-white">Ad Server Simulator</h1>
            <p className="text-xs text-slate-500">Standard traffic / impression / click / scenario harness · honest conformance reporting</p>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className={cls('inline-flex items-center gap-1.5', health?.ad_server_reachable ? 'text-emerald-400' : 'text-rose-400')}>
              <span className={cls('h-2 w-2 rounded-full', health?.ad_server_reachable ? 'bg-emerald-400' : 'bg-rose-400')} />
              {health?.ad_server_url || 'ad server'}
            </span>
            {health?.auth_role && <span className="text-slate-500">role: {health.auth_role}</span>}
            {target?.discovery && (
              <span className={cls(target.discovery.openapi_ok ? 'text-slate-400' : 'text-amber-400')}>
                {target.discovery.openapi_ok ? `discovered ${target.discovery.path_count} routes` : 'discovery: default routes'}
              </span>
            )}
            {busy && <span className="text-amber-400 animate-pulse">● running…</span>}
          </div>
        </div>
        <nav className="mt-2 flex gap-1">
          {[['dashboard', 'Dashboard'], ['publisher', 'Publisher Ad Request'], ['dsp', 'DSP Settings']].map(([v, label]) => (
            <button key={v} onClick={() => setView(v)}
              className={cls('rounded-md px-3 py-1 text-sm font-medium transition',
                view === v ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200')}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 p-6">
        {view === 'publisher' ? <PublisherRequest /> : view === 'dsp' ? <DspSettings /> : (
        <>
        {err && <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{String(err)}</div>}

        {/* Controls */}
        <div className="grid gap-3 lg:grid-cols-3">
          <Card title="1 · Seed data">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Campaigns"><Input type="number" value={seed.campaigns} onChange={(e) => setSeed({ ...seed, campaigns: e.target.value })} /></Field>
              <Field label="Publishers"><Input type="number" value={seed.publishers} onChange={(e) => setSeed({ ...seed, publishers: e.target.value })} /></Field>
              <Field label="CPM min"><Input type="number" value={seed.cpm_min} onChange={(e) => setSeed({ ...seed, cpm_min: e.target.value })} /></Field>
              <Field label="CPM max"><Input type="number" value={seed.cpm_max} onChange={(e) => setSeed({ ...seed, cpm_max: e.target.value })} /></Field>
            </div>
            <div className="mt-3"><Button onClick={doSeed} disabled={busy}>Seed ecosystem</Button></div>
          </Card>

          <Card title="2 · Generate traffic">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Protocols"><Select value={run.protocols} onChange={(e) => setRun({ ...run, protocols: e.target.value })}>
                <option value="vast">VAST</option><option value="ortb">OpenRTB</option><option value="vast,ortb">VAST + OpenRTB</option>
              </Select></Field>
              <Field label="Total requests"><Input type="number" value={run.total_requests} onChange={(e) => setRun({ ...run, total_requests: e.target.value })} /></Field>
              <Field label="Requests / sec"><Input type="number" value={run.requests_per_second} onChange={(e) => setRun({ ...run, requests_per_second: e.target.value })} /></Field>
              <Field label="Concurrency"><Input type="number" value={run.concurrency} onChange={(e) => setRun({ ...run, concurrency: e.target.value })} /></Field>
              <Field label="Impression rate"><Input type="number" step="0.05" value={run.impression_rate} onChange={(e) => setRun({ ...run, impression_rate: e.target.value })} /></Field>
              <Field label="CTR"><Input type="number" step="0.01" value={run.ctr} onChange={(e) => setRun({ ...run, ctr: e.target.value })} /></Field>
            </div>
            <div className="mt-3 flex gap-2"><Button onClick={doRun} disabled={busy}>Run traffic</Button><Button onClick={doStop} variant="danger" disabled={!busy}>Stop</Button></div>
          </Card>

          <Card title="3 · Conformance scenarios (S1–S15)">
            <Field label="Scenario"><Select value={scen} onChange={(e) => setScen(e.target.value)}>
              {SCENARIO_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select></Field>
            <p className="mt-2 text-xs text-slate-500">Each asserts the IAB standard and reports PASS / GAP / BLOCKED / FAIL with evidence. "All" runs S1–S15 (1–2 min).</p>
            <div className="mt-3 flex gap-2">
              <Button onClick={doScenario} disabled={busy}>Run scenario</Button>
              <Button variant="ghost" onClick={() => window.open('/api/report/markdown', '_blank')}>GAP report</Button>
              <Button variant="ghost" onClick={() => window.open('/api/report/gaps.json', '_blank')}>gaps.json</Button>
            </div>
          </Card>
        </div>

        {/* Flow B — OpenRTB auction against the mock DSP (one click) */}
        <FlowB />

        {/* Live progress */}
        {live && (
          <Card title="Live run">
            <div className="grid grid-cols-3 gap-3 md:grid-cols-6">
              {['requests', 'fills', 'impressions', 'clicks', 'wins', 'errors'].map((k) => (
                <Stat key={k} label={k} value={live[k] ?? (live.seed ? '—' : 0)} />
              ))}
            </div>
            {live.findings && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-300/90">{live.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>}
          </Card>
        )}

        {/* Run filter */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-400">View:</span>
          <Select value={runId} onChange={(e) => { setRunId(e.target.value); loadMetrics(e.target.value) }}>
            <option value="">All runs (aggregate)</option>
            {runs.map((r) => <option key={r.id} value={r.id}>{r.kind} · {r.label} · {r.id.slice(0, 12)}</option>)}
          </Select>
          <Button variant="ghost" onClick={() => loadMetrics(runId)}>Refresh</Button>
        </div>

        <Scorecard sc={metrics.scorecard} />
        <Overview o={metrics.overview} />
        <FillBreakdown fb={metrics.fill} />
        <Latency a={metrics.auctions} />
        <Charts ts={metrics.ts} />
        <div className="grid gap-3 lg:grid-cols-2">
          <CampaignTable rows={metrics.campaigns} />
          <Auctions a={metrics.auctions} />
        </div>
        <Findings data={metrics.findings} />
        <Scenarios rows={metrics.scenarios} />

        <footer className="pt-4 text-center text-xs text-slate-600">
          Ad Server Simulator · the simulator is the source of truth; GAP/FAIL verdicts indicate ad-server gaps, not simulator errors.
        </footer>
        </>
        )}
      </main>
    </div>
  )
}

function numify(obj) {
  const out = {}
  for (const [k, v] of Object.entries(obj)) {
    if (k === 'protocols') { out[k] = v; continue }
    const n = Number(v)
    out[k] = Number.isFinite(n) && v !== '' ? n : v
  }
  return out
}
