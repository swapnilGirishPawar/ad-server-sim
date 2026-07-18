import React, { useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { Card, Stat, Badge, Button, Select, Field } from './ui.jsx'
import { api, dspBidRaw } from './api.js'

const fmtTime = (ms) => {
  const d = new Date(ms)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const pct = (x) => `${(x * 100).toFixed(2)}%`
const money = (x) => (x == null ? '-' : `$${Number(x).toFixed(2)}`)

const AXIS = { stroke: '#64748b', fontSize: 11 }
const GRID = '#1e293b'

export function Overview({ o }) {
  if (!o) return null
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <Stat label="Requests" value={o.total_requests} />
      <Stat label="Responses" value={o.total_responses} />
      <Stat label="Impressions" value={o.total_impressions} />
      <Stat label="Clicks" value={o.total_clicks} />
      <Stat label="Fill Rate" value={pct(o.fill_rate)} sub="real campaign fills" tone="good" />
      <Stat label="CTR" value={pct(o.ctr)} tone="warn" />
    </div>
  )
}

export function Auctions({ a }) {
  if (!a) return null
  const data = (a.win_distribution || []).map((w) => ({
    name: (w.campaign || '(none)').replace(/^Scenario /, '').slice(0, 22), wins: w.wins,
  }))
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      <Stat label="Avg Latency" value={`${a.avg_latency_ms} ms`} />
      <Stat label="P95 Latency" value={`${a.p95_latency_ms} ms`} tone="warn" />
      <Stat label="Requests / sec" value={a.requests_per_second} />
      <Card title="Win Distribution" className="lg:col-span-3">
        {data.length === 0 ? <Empty /> : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="name" tick={AXIS} angle={-12} textAnchor="end" height={50} interval={0} />
              <YAxis tick={AXIS} allowDecimals={false} />
              <Tooltip contentStyle={TT} />
              <Bar dataKey="wins" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  )
}

export function CampaignTable({ rows }) {
  return (
    <Card title="Campaign Metrics">
      {(!rows || rows.length === 0) ? <Empty /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr className="border-b border-slate-800">
                <th className="py-2 pr-3">Campaign</th>
                <th className="py-2 pr-3 text-right">Impr.</th>
                <th className="py-2 pr-3 text-right">Clicks</th>
                <th className="py-2 pr-3 text-right">CTR</th>
                <th className="py-2 pr-3 text-right">Spend</th>
                <th className="py-2 pr-3 text-right">Budget</th>
                <th className="py-2 text-right">Remaining</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-slate-800/50">
                  <td className="py-2 pr-3">{r.campaign}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{r.impressions}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{r.clicks}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.ctr)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{money(r.spend)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{money(r.budget)}</td>
                  <td className="py-2 text-right tabular-nums">{money(r.remaining_budget)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function Charts({ ts }) {
  const data = (ts || []).map((d) => ({ ...d, label: fmtTime(d.t) }))
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <Card title="Requests / Impressions / Clicks over time">
        {data.length === 0 ? <Empty /> : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: -10 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} minTickGap={40} />
              <YAxis tick={AXIS} allowDecimals={false} />
              <Tooltip contentStyle={TT} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="requests" stroke="#38bdf8" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="impressions" stroke="#34d399" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="clicks" stroke="#f472b6" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
      <Card title="Campaign spend over time (modelled)">
        {data.length === 0 ? <Empty /> : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: -10 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} minTickGap={40} />
              <YAxis tick={AXIS} />
              <Tooltip contentStyle={TT} />
              <Area type="monotone" dataKey="spend" stroke="#a78bfa" fill="#7c3aed33" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  )
}

export function Scenarios({ rows }) {
  if (!rows || rows.length === 0) return <Card title="Scenario Results"><Empty /></Card>
  return (
    <Card title="Scenario Results (standard expectations vs server behaviour)">
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-slate-100">Scenario {r.scenario} - {r.title}</div>
              <Badge verdict={r.verdict} />
            </div>
            <div className="mt-2 grid gap-1 text-sm">
              <div><span className="text-slate-500">Expected: </span><span className="text-slate-300">{r.expected}</span></div>
              <div><span className="text-slate-500">Actual: </span><span className="text-slate-300">{r.actual}</span></div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

const GRADE_TONE = { PASS: 'good', WARN: 'warn', FAIL: 'bad', INFO: undefined }

export function Scorecard({ sc }) {
  if (!sc || !sc.overall) return null
  const o = sc.overall
  return (
    <Card title="Conformance Scorecard (IAB standards)"
      right={<Badge verdict={o.grade === 'PASS' ? 'PASS' : o.grade === 'FAIL' ? 'FAIL' : 'WARN'}>{o.grade}</Badge>}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Checks" value={o.checks} />
        <Stat label="Pass" value={o.pass} tone="good" />
        <Stat label="Fail" value={o.fail} tone="bad" />
        <Stat label="Warn" value={o.warn} tone="warn" />
        <Stat label="Info" value={o.info} />
      </div>
      {sc.standards && sc.standards.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr className="border-b border-slate-800">
                <th className="py-2 pr-3">Standard</th><th className="py-2 pr-3">Grade</th>
                <th className="py-2 pr-3 text-right">Pass</th><th className="py-2 pr-3 text-right">Fail</th>
                <th className="py-2 pr-3 text-right">Warn</th><th className="py-2 text-right">Info</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {sc.standards.map((s, i) => (
                <tr key={i} className="border-b border-slate-800/50">
                  <td className="py-2 pr-3">{s.standard}</td>
                  <td className="py-2 pr-3"><Badge verdict={s.grade === 'PASS' ? 'PASS' : s.grade === 'FAIL' ? 'FAIL' : 'WARN'}>{s.grade}</Badge></td>
                  <td className="py-2 pr-3 text-right tabular-nums">{s.pass}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-rose-300">{s.fail}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-amber-300">{s.warn}</td>
                  <td className="py-2 text-right tabular-nums text-slate-400">{s.info}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function FillBreakdown({ fb }) {
  if (!fb || !fb.total) return null
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Stat label="Real fills" value={fb.real} sub={pct(fb.real_fill_rate)} tone="good" />
      <Stat label="Filler" value={fb.filler} sub={pct(fb.filler_rate)} tone="warn" />
      <Stat label="No-fill" value={fb.no_fill} />
      <Stat label="Errors" value={fb.error} tone={fb.error ? 'bad' : undefined} />
    </div>
  )
}

export function Latency({ a }) {
  if (!a) return null
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <Stat label="p50 latency" value={`${a.p50_latency_ms ?? 0} ms`} />
      <Stat label="p95 latency" value={`${a.p95_latency_ms ?? 0} ms`} tone="warn" />
      <Stat label="p99 latency" value={`${a.p99_latency_ms ?? 0} ms`} tone="warn" />
      <Stat label="Req / sec" value={a.requests_per_second} />
      <Stat label="Error rate" value={pct(a.error_rate || 0)} tone={a.error_rate ? 'bad' : 'good'} />
    </div>
  )
}

export function Findings({ data }) {
  const rows = (data && data.findings) || []
  const fails = rows.filter((f) => f.severity === 'fail' || f.severity === 'warn')
  if (fails.length === 0) return null
  return (
    <Card title={`Conformance findings (${fails.length} fail/warn)`}>
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr className="border-b border-slate-800">
              <th className="py-2 pr-3">Sev</th><th className="py-2 pr-3">Standard</th>
              <th className="py-2 pr-3">Spec</th><th className="py-2">Observed</th>
            </tr>
          </thead>
          <tbody className="text-slate-200">
            {fails.slice(0, 200).map((f, i) => (
              <tr key={i} className="border-b border-slate-800/50 align-top">
                <td className="py-2 pr-3"><Badge verdict={f.severity === 'fail' ? 'FAIL' : 'WARN'}>{f.severity}</Badge></td>
                <td className="py-2 pr-3 whitespace-nowrap">{f.standard}</td>
                <td className="py-2 pr-3 whitespace-nowrap text-slate-400">{f.spec_section}</td>
                <td className="py-2 text-slate-300">{f.observed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export function FlowB() {
  const [mode, setMode] = useState('bid')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [raw, setRaw] = useState(null)
  const [err, setErr] = useState(null)

  const run = async () => {
    setErr(null); setRaw(null); setBusy(true)
    try { setRes(await api.flowOrtb({ dsp_mode: mode })) }
    catch (e) { setErr(String(e.message || e)) }
    finally { setBusy(false) }
  }
  const showRaw = async () => {
    setErr(null)
    try { await api.dspConfig({ mode }); setRaw(await dspBidRaw()) }
    catch (e) { setErr(String(e.message || e)) }
  }

  const ad = res && res.ad_server
  const won = ad && ad.won
  return (
    <Card title="Flow B · OpenRTB Auction (Mock DSP)"
      right={<span className="text-xs text-slate-500">ad server ⇄ mock DSP, end-to-end</span>}>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="DSP behaviour">
          <Select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="bid">bid (buy)</option>
            <option value="no_bid">no_bid (refuse)</option>
            <option value="timeout">timeout</option>
            <option value="error">error (500)</option>
          </Select>
        </Field>
        <Button onClick={run} disabled={busy}>{busy ? 'Running auction…' : 'Run auction'}</Button>
        <Button variant="ghost" onClick={showRaw} disabled={busy}>Show raw DSP bid</Button>
        <span className="text-xs text-slate-500">First run can take ~30s (ad-server cold start).</span>
      </div>

      {err && <div className="mt-3 rounded-lg border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{err}</div>}

      {res && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-400">DSP decision</div>
              <div className="mt-1">
                <Badge verdict={res.dsp?.decision?.decision === 'bid' ? 'PASS' : 'WARN'}>
                  {res.dsp?.decision?.decision === 'bid' ? 'BID' : 'NO-BID'}
                </Badge>
              </div>
              <div className="mt-1 text-xs text-slate-500">called by ad server: {String(res.dsp?.called_by_ad_server)}</div>
            </div>
            <Stat label="Ad server outcome" value={won ? 'WON' : 'NO WINNER'} tone={won ? 'good' : 'warn'}
              sub={`HTTP ${ad.status}`} />
            <Stat label="Clearing price" value={ad.price != null ? `$${ad.price}` : '-'}
              sub={ad.winner_seat ? `seat: ${ad.winner_seat}` : ''} />
            <Stat label="Auction latency" value={`${ad.latency_ms} ms`}
              sub={ad.conformant ? 'spec-conformant ✓' : 'conformance fail'} tone={ad.conformant ? 'good' : 'bad'} />
          </div>

          <div className="grid gap-2 text-sm md:grid-cols-2">
            <Flag ok={ad.adm_has_vast} label="VAST creative returned (adm)" />
            <Flag ok={ad.dsp_nurl_chained} label="DSP win-notice chained (dsp_nurl)" />
          </div>
          {ad.error && <div className="text-sm text-rose-300">Ad server error: {ad.error} - try again (cold start / raise timeout).</div>}
          {ad.fail_findings?.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 text-xs text-rose-300">
              {ad.fail_findings.map((f, i) => <li key={i}>{f.spec_section}: {f.observed}</li>)}
            </ul>
          )}
          <details className="text-xs">
            <summary className="cursor-pointer text-slate-400">Ad server response (raw)</summary>
            <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-slate-300">{JSON.stringify(res.raw_response, null, 2)}</pre>
          </details>
        </div>
      )}

      {raw && (
        <details className="mt-3 text-xs" open>
          <summary className="cursor-pointer text-slate-400">Mock DSP raw bid response (direct from /dsp/bid)</summary>
          <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-slate-300">{JSON.stringify(raw, null, 2)}</pre>
        </details>
      )}
    </Card>
  )
}

function Flag({ ok, label }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
      <span className={ok ? 'text-emerald-400' : 'text-slate-600'}>{ok ? '✓' : '○'}</span>
      <span className="text-slate-300">{label}</span>
    </div>
  )
}

const TT = { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12, color: '#e2e8f0' }
const Empty = () => <div className="py-8 text-center text-sm text-slate-600">No data yet - seed and run traffic.</div>
