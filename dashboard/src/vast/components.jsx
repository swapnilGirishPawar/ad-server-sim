import React from 'react'
import { Card, Badge, cls } from '../ui.jsx'
import { STEP_LABEL } from './tracking.js'

// Colour per step state, reusing the app's verdict palette conventions.
const STATE_CLS = {
  pending: 'border-line bg-panel text-slate-500',
  fired: 'border-emerald-600/40 bg-emerald-500/15 text-emerald-200',
  reached: 'border-sky-600/40 bg-sky-500/15 text-sky-200',
  error: 'border-rose-600/40 bg-rose-500/15 text-rose-200',
}

function Node({ label, state, sub }) {
  return (
    <div className={cls('rounded-lg border px-3 py-2 text-center text-xs font-semibold transition', STATE_CLS[state] || STATE_CLS.pending)}>
      {label}
      {sub && <div className="mt-0.5 text-[10px] font-normal opacity-80">{sub}</div>}
    </div>
  )
}

// SpringServe-style lifecycle diagram. `states` maps each step name to
// { state, sub }. The linear path runs top to bottom; click/error sit aside.
export function TrackingDiagram({ states }) {
  const main = ['request', 'impression', 'start', 'firstQuartile', 'midpoint', 'thirdQuartile', 'complete']
  const st = (k) => states[k] || { state: 'pending' }
  return (
    <Card title="Lifecycle diagram">
      <div className="flex gap-6">
        <div className="flex flex-1 flex-col items-stretch gap-0">
          {main.map((k, i) => (
            <div key={k} className="flex flex-col items-center">
              <div className="w-full max-w-[220px]"><Node label={STEP_LABEL[k]} state={st(k).state} sub={st(k).sub} /></div>
              {i < main.length - 1 && <div className={cls('h-4 w-px', st(main[i + 1]).state === 'pending' ? 'bg-line' : 'bg-emerald-600/40')} />}
            </div>
          ))}
        </div>
        <div className="flex w-28 flex-col justify-center gap-3">
          <Node label={STEP_LABEL.click} state={st('click').state} sub={st('click').sub} />
          <Node label="Ad Error" state={st('error').state} sub={st('error').sub} />
        </div>
      </div>
    </Card>
  )
}

// Time-ordered event log, like SpringServe's Events panel.
export function EventsTable({ log }) {
  return (
    <Card title="Events">
      {!log.length ? (
        <p className="text-xs text-slate-500">No events yet. Load a VAST and press play.</p>
      ) : (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-panel text-xs uppercase text-slate-500">
              <tr className="border-b border-line"><th className="py-2 pr-3">Time</th><th className="py-2 pr-3">Event</th><th className="py-2">Status</th></tr>
            </thead>
            <tbody className="text-slate-200">
              {log.map((e, i) => (
                <tr key={i} className="border-b border-line/50 align-top">
                  <td className="py-1.5 pr-3 whitespace-nowrap tabular-nums text-slate-400">{e.ts}</td>
                  <td className="py-1.5 pr-3 whitespace-nowrap">{e.label || e.event}</td>
                  <td className="py-1.5">
                    {e.status === 'fired'
                      ? <span className={e.ok ? 'text-emerald-400' : 'text-amber-400'}>{e.ok ? '✓ sent' : '○ sent (no ack)'}</span>
                      : e.status === 'error' ? <span className="text-rose-300">✗ error</span>
                      : e.status === 'reached' ? <span className="text-sky-300">reached (no tracker)</span>
                      : <span className="text-slate-500">{e.note || '-'}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function Row({ label, value }) {
  if (value == null || value === '') return null
  return (
    <div className="flex justify-between gap-3 border-b border-line/40 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-200 break-all">{value}</span>
    </div>
  )
}

export function ParsedInfoCard({ parsed }) {
  const mf = parsed.mediaFile
  return (
    <Card title="Parsed VAST" right={parsed.adType && <Badge verdict={parsed.adType === 'InLine' ? 'PASS' : 'BLOCKED'}>{parsed.adType}</Badge>}>
      <div className="grid gap-x-6 md:grid-cols-2">
        <div>
          <Row label="VAST version" value={parsed.version} />
          <Row label="Ad system" value={parsed.adSystem} />
          <Row label="Ad title" value={parsed.adTitle} />
          <Row label="Ad id" value={parsed.adId} />
          <Row label="Creative id" value={parsed.creativeId} />
          <Row label="Duration" value={parsed.durationStr ? `${parsed.durationStr} (${parsed.durationSec}s)` : null} />
        </div>
        <div>
          <Row label="Media file" value={mf ? `${mf.width || '?'}x${mf.height || '?'} ${mf.type || ''}` : 'none'} />
          <Row label="Bitrate" value={mf?.bitrate ? `${mf.bitrate} kbps` : null} />
          <Row label="Impression pixels" value={parsed.impressions.length} />
          <Row label="Tracking events" value={parsed.trackingEvents.length} />
          <Row label="Click trackers" value={parsed.clickTracking.length} />
          <Row label="Clickthrough" value={parsed.clickThrough} />
        </div>
      </div>
      {parsed.mediaFiles.length > 1 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">All media files ({parsed.mediaFiles.length})</div>
          <div className="max-h-40 space-y-1 overflow-auto">
            {parsed.mediaFiles.map((m, i) => (
              <div key={i} className="rounded-md border border-line bg-ink-900 px-2 py-1 text-xs text-slate-400">
                <span className={cls(m === mf && 'text-emerald-300')}>{m === mf ? '✓ ' : ''}{m.type || 'video'} · {m.width || '?'}x{m.height || '?'} · {m.bitrate || '?'} kbps</span>
                <div className="break-all text-slate-600">{m.url}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

export function ErrorPanel({ parsed }) {
  const hasParseErr = parsed.parseErrors.length > 0
  if (!hasParseErr && !parsed.errors.length) return null
  return (
    <Card title="Errors" right={<Badge verdict={hasParseErr ? 'FAIL' : 'WARN'}>{hasParseErr ? 'invalid' : 'error tags'}</Badge>}>
      {hasParseErr && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-rose-300">
          {parsed.parseErrors.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
      )}
      {parsed.errors.length > 0 && (
        <div className={cls(hasParseErr && 'mt-3')}>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">VAST &lt;Error&gt; URLs (fired on playback failure)</div>
          <ul className="space-y-1 text-xs text-slate-400">
            {parsed.errors.map((u, i) => <li key={i} className="break-all">{u}</li>)}
          </ul>
        </div>
      )}
    </Card>
  )
}
