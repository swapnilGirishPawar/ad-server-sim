import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, openWS } from './api.js'
import { Card, Stat, Button, Field, Input, Select, Badge, cls } from './ui.jsx'
import { Overview, Auctions, CampaignTable, Charts, Scenarios } from './panels.jsx'

export default function App() {
  const [health, setHealth] = useState(null)
  const [runs, setRuns] = useState([])
  const [runId, setRunId] = useState('')        // '' = all runs
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState(null)
  const [err, setErr] = useState(null)
  const [metrics, setMetrics] = useState({ overview: null, campaigns: [], auctions: null, ts: [], scenarios: [] })

  const [seed, setSeed] = useState({ publishers: 3, ad_units_per_publisher: 3, demand_partners: 3, advertisers: 3, campaigns: 6, cpm_min: 5, cpm_max: 150 })
  const [run, setRun] = useState({ protocols: 'vast', total_requests: 300, requests_per_second: 50, concurrency: 10, impression_rate: 0.9, ctr: 0.03 })
  const [scen, setScen] = useState('all')
  const wsRef = useRef(null)

  const loadRuns = useCallback(async () => { try { setRuns(await api.runs()) } catch (e) { /* */ } }, [])

  const loadMetrics = useCallback(async (rid) => {
    try {
      const [overview, campaigns, auctions, ts, scenarios] = await Promise.all([
        api.overview(rid), api.campaigns(rid), api.auctions(rid), api.timeseries(rid), api.scenarios(''),
      ])
      setMetrics({ overview, campaigns, auctions, ts, scenarios })
    } catch (e) { setErr(String(e.message || e)) }
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }))
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
            {busy && <span className="text-amber-400 animate-pulse">● running…</span>}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 p-6">
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

          <Card title="3 · Business scenarios">
            <Field label="Scenario"><Select value={scen} onChange={(e) => setScen(e.target.value)}>
              <option value="all">All (A–D)</option>
              <option value="A">A · Budget exhaustion</option>
              <option value="B">B · Country targeting</option>
              <option value="C">C · Bid competition</option>
              <option value="D">D · Frequency cap</option>
            </Select></Field>
            <p className="mt-2 text-xs text-slate-500">Each asserts the standard expected behaviour and reports PASS / GAP / FAIL with evidence.</p>
            <div className="mt-3"><Button onClick={doScenario} disabled={busy}>Run scenario</Button></div>
          </Card>
        </div>

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

        <Overview o={metrics.overview} />
        <Charts ts={metrics.ts} />
        <div className="grid gap-3 lg:grid-cols-2">
          <CampaignTable rows={metrics.campaigns} />
          <Auctions a={metrics.auctions} />
        </div>
        <Scenarios rows={metrics.scenarios} />

        <footer className="pt-4 text-center text-xs text-slate-600">
          Ad Server Simulator · the simulator is the source of truth; GAP/FAIL verdicts indicate ad-server gaps, not simulator errors.
        </footer>
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
