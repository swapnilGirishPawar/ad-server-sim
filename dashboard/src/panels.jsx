import React from 'react'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import { Card, Stat, Badge } from './ui.jsx'

const fmtTime = (ms) => {
  const d = new Date(ms)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
const pct = (x) => `${(x * 100).toFixed(2)}%`
const money = (x) => (x == null ? '—' : `$${Number(x).toFixed(2)}`)

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
              <div className="font-semibold text-slate-100">Scenario {r.scenario} — {r.title}</div>
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

const TT = { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12, color: '#e2e8f0' }
const Empty = () => <div className="py-8 text-center text-sm text-slate-600">No data yet — seed and run traffic.</div>
