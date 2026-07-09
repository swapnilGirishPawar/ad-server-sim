import React, { useState } from 'react'
import { Card, Stat, Button, Field, Input, Select, Badge, cls } from './ui.jsx'
import { api } from './api.js'

// A real publisher OpenRTB 2.6 CTV bid request (Samsung Tizen app) — editable, so
// you can paste your own and fire N copies verbatim. This is the "custom" path.
const SAMPLE_ORTB = JSON.stringify({
  id: '15e5c56b5831a92a',
  imp: [{
    id: '1',
    video: {
      mimes: ['video/mp4'], minduration: 3, maxduration: 300, startdelay: 0,
      protocols: [1, 2, 3, 4, 5, 6], w: 1920, h: 1080, linearity: 1, sequence: 1,
      boxingallowed: 1, playbackmethod: [1], api: [1, 2],
    },
    tagid: '351511', bidfloor: 5.775, bidfloorcur: 'USD', clickbrowser: 0, secure: 1,
  }],
  app: {
    id: '9887674', name: 'Philo: Shows, Movies, and Live TV', bundle: 'G22223020133',
    storeurl: 'https://samsung.com/us/appstore/app/G22223020133',
    cat: ['IAB4', 'IAB5', 'IAB2', 'IAB3', 'IAB1'], publisher: { id: '1192' },
    content: {
      genre: 'Adventure', cat: ['IAB1-5'], videoquality: 1, context: 1,
      contentrating: 'TV-MA', livestream: 0, len: 1380, language: 'en',
    },
  },
  device: {
    geo: { lat: 32.9074, lon: -97.4257, type: 2, country: 'USA', region: 'TX', city: 'Fort Worth', zip: '76179' },
    dnt: 0, lmt: 0,
    ua: 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) 76.0.3809.146/6.0 TV Safari/537.36',
    ip: '132.147.164.4', devicetype: 3, make: 'Samsung', model: 'UN70TU6985FXZA',
    os: 'Tizen', osv: '6.0', js: 1, language: 'en', carrier: 'Nextlink Broadband',
    connectiontype: 2, ifa: 'df8ee962-af95-4a77-b0ad-4bbb6ff86c0b', ext: { ifa_type: 'tifa' },
  },
  user: {}, at: 1, tmax: 660, cur: ['USD'], bcat: ['IAB26'],
  source: {
    fd: 1, tid: '85x1CF677D5AED84A08',
    ext: { schain: { complete: 1, ver: '1.0', nodes: [{ asi: 'voisetech.com', sid: '1192', rid: '15e5c56b5831a92a', hp: 1 }] } },
  },
  regs: { coppa: 0, ext: { us_privacy: '1YNN' } },
}, null, 2)

const DEFAULTS = {
  protocol: 'ortb', publisher_id: '1192', tag_id: '351511', count: 5, concurrency: 10,
  ad_format: 'video', app_mode: true, device: 'ctv', country: 'US',
  width: 1920, height: 1080, bidfloor: 5.775,
  us_privacy: '1YNN', gdpr: '', gpp: '', coppa: '',
}

function Textarea(props) {
  return <textarea {...props}
    className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-indigo-500" />
}

function Checkbox({ checked, onChange, label }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
      <input type="checkbox" checked={checked} onChange={onChange}
        className="h-4 w-4 rounded border-slate-600 bg-slate-950 accent-indigo-500" />
      {label}
    </label>
  )
}

const CLASS_TONE = { real: 'PASS', filler: 'WARN', no_fill: 'BLOCKED', error: 'FAIL', empty: 'ERROR' }

export default function PublisherRequest() {
  const [form, setForm] = useState(DEFAULTS)
  const [useCustom, setUseCustom] = useState(false)
  const [customJson, setCustomJson] = useState(SAMPLE_ORTB)
  const [randomizeId, setRandomizeId] = useState(true)
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [preview, setPreview] = useState(null)
  const [result, setResult] = useState(null)

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const isOrtb = form.protocol === 'ortb'

  function buildBody(previewOnly) {
    const b = {
      publisher_id: form.publisher_id, tag_id: form.tag_id,
      count: Number(form.count) || 1, concurrency: Number(form.concurrency) || 10,
      protocol: form.protocol, ad_format: form.ad_format, app_mode: !!form.app_mode,
      device: form.device, country: form.country,
      width: Number(form.width) || 1920, height: Number(form.height) || 1080,
      bidfloor: Number(form.bidfloor) || 0, preview_only: !!previewOnly,
    }
    if (form.us_privacy) b.us_privacy = form.us_privacy
    if (form.gdpr !== '') b.gdpr = Number(form.gdpr)
    if (form.gpp) b.gpp = form.gpp
    if (form.coppa !== '') b.coppa = Number(form.coppa)
    if (isOrtb && useCustom) {
      let parsed
      try { parsed = JSON.parse(customJson) }
      catch (e) { throw new Error('Custom OpenRTB JSON is invalid: ' + e.message) }
      b.custom_request = parsed
      b.randomize_id = randomizeId
    }
    return b
  }

  const guard = async (fn) => {
    setErr(null); setBusy(true)
    try { await fn() } catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
  }
  const doPreview = () => guard(async () => {
    setResult(null); const r = await api.publisherRequest(buildBody(true)); setPreview(r.sample_request)
  })
  const doSend = () => guard(async () => {
    setPreview(null); const r = await api.publisherRequest(buildBody(false)); setResult(r)
  })

  const s = result?.summary
  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{err}</div>}

      <Card title="What this does">
        <p className="text-sm text-slate-400">
          Send <span className="text-slate-200">publisher ad requests</span> to your ad server
          (<code className="text-indigo-300">:8001</code>) for a specific publisher + ad unit, and see exactly what comes back.
          Two IAB request types:
        </p>
        <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <span className="font-semibold text-emerald-300">VAST tag</span> — an HTTP <b>GET</b> to
            <code className="mx-1 text-slate-300">/api/v/{'{tag_id}'}</code>; returns <b>VAST XML</b> (the video ad). What a player/simple publisher sends.
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <span className="font-semibold text-sky-300">OpenRTB bid request</span> — an HTTP <b>POST</b> of a JSON
            BidRequest to <code className="mx-1 text-slate-300">/api/b/{'{tag_id}'}</code>; returns a JSON BidResponse or a <b>204</b> no-bid. What an SSP/programmatic supply sends (your sample).
          </div>
        </div>
      </Card>

      <Card title="Compose request">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-4">
          <Field label="Request type (IAB standard)">
            <Select value={form.protocol} onChange={(e) => set('protocol', e.target.value)}>
              <option value="ortb">OpenRTB bid request (POST)</option>
              <option value="vast">VAST tag (GET)</option>
            </Select>
          </Field>
          <Field label="Publisher ID"><Input value={form.publisher_id} onChange={(e) => set('publisher_id', e.target.value)} /></Field>
          <Field label="Ad unit / Tag ID"><Input value={form.tag_id} onChange={(e) => set('tag_id', e.target.value)} /></Field>
          <Field label="Number of requests"><Input type="number" min="1" max="500" value={form.count} onChange={(e) => set('count', e.target.value)} /></Field>

          {isOrtb && (
            <Field label="Ad format (imp type)">
              <Select value={form.ad_format} onChange={(e) => set('ad_format', e.target.value)}>
                <option value="video">Video (VAST-in-oRTB)</option>
                <option value="banner">Banner / display</option>
                <option value="native">Native</option>
                <option value="audio">Audio (DAAST)</option>
              </Select>
            </Field>
          )}
          <Field label="Device">
            <Select value={form.device} onChange={(e) => set('device', e.target.value)}>
              <option value="ctv">CTV / smart TV</option>
              <option value="mobile">Mobile</option>
              <option value="tablet">Tablet</option>
              <option value="desktop">Desktop</option>
            </Select>
          </Field>
          <Field label="Country"><Input value={form.country} onChange={(e) => set('country', e.target.value)} /></Field>
          <Field label="Concurrency"><Input type="number" min="1" max="50" value={form.concurrency} onChange={(e) => set('concurrency', e.target.value)} /></Field>

          {isOrtb && <Field label="Bid floor (CPM)"><Input type="number" step="0.001" value={form.bidfloor} onChange={(e) => set('bidfloor', e.target.value)} /></Field>}
          <Field label="Width"><Input type="number" value={form.width} onChange={(e) => set('width', e.target.value)} /></Field>
          <Field label="Height"><Input type="number" value={form.height} onChange={(e) => set('height', e.target.value)} /></Field>
          {isOrtb && (
            <div className="flex items-end pb-1">
              <Checkbox checked={form.app_mode} onChange={(e) => set('app_mode', e.target.checked)} label="App inventory (else Site/web)" />
            </div>
          )}
        </div>

        <button className="mt-3 text-xs text-slate-400 hover:text-slate-200" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? '▾' : '▸'} Advanced — privacy{isOrtb ? ' + paste custom OpenRTB JSON' : ''}
        </button>
        {advanced && (
          <div className="mt-2 space-y-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
            <div className="grid gap-3 md:grid-cols-4">
              <Field label="us_privacy (CCPA)"><Input value={form.us_privacy} onChange={(e) => set('us_privacy', e.target.value)} placeholder="1YNN" /></Field>
              <Field label="gdpr (0/1)"><Input value={form.gdpr} onChange={(e) => set('gdpr', e.target.value)} placeholder="unset" /></Field>
              <Field label="gpp string"><Input value={form.gpp} onChange={(e) => set('gpp', e.target.value)} placeholder="unset" /></Field>
              <Field label="coppa (0/1)"><Input value={form.coppa} onChange={(e) => set('coppa', e.target.value)} placeholder="unset" /></Field>
            </div>
            {isOrtb && (
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <Checkbox checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)}
                    label="Send this exact OpenRTB body (verbatim) instead of the builder" />
                  {useCustom && <Checkbox checked={randomizeId} onChange={(e) => setRandomizeId(e.target.checked)} label="Randomize id per request" />}
                </div>
                <Textarea rows={10} value={customJson} onChange={(e) => setCustomJson(e.target.value)} disabled={!useCustom} />
                <p className="mt-1 text-xs text-slate-500">Paste a real publisher request here. Only used when the checkbox above is on.</p>
              </div>
            )}
          </div>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button onClick={doSend} disabled={busy}>{busy ? 'Sending…' : `Send ${form.count} request${Number(form.count) === 1 ? '' : 's'}`}</Button>
          <Button variant="ghost" onClick={doPreview} disabled={busy}>Preview request</Button>
          <span className="text-xs text-slate-500">Requests go via the simulator backend to avoid CORS. First OpenRTB call can be slow (ad-server cold start).</span>
        </div>
      </Card>

      {preview && (
        <Card title="Request preview (not sent)" right={<Badge verdict="BLOCKED">{preview.method}</Badge>}>
          <div className="text-xs text-slate-400">Endpoint</div>
          <div className="mb-2 break-all font-mono text-sm text-indigo-300">{preview.url}</div>
          <pre className="max-h-96 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(preview.body ?? preview.params, null, 2)}</pre>
        </Card>
      )}

      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
            <Stat label="Sent" value={s.count} />
            <Stat label="Filled" value={s.filled} tone="good" sub={`${(s.fill_rate * 100).toFixed(1)}%`} />
            <Stat label="No-fill" value={s.no_fill} tone="warn" />
            <Stat label="Errors" value={s.errors} tone={s.errors ? 'bad' : undefined} />
            <Stat label="Conformant" value={s.conformant} tone={s.non_conformant ? 'warn' : 'good'} sub={s.non_conformant ? `${s.non_conformant} not` : 'all ✓'} />
            <Stat label="Avg latency" value={`${s.avg_latency_ms} ms`} />
            <Stat label="p95 latency" value={`${s.p95_latency_ms} ms`} tone="warn" />
            <Stat label="Elapsed" value={`${(s.elapsed_ms / 1000).toFixed(1)} s`} />
          </div>

          <Card title="Sample request sent" right={<Badge verdict="BLOCKED">{result.sample_request.method}</Badge>}>
            <div className="mb-2 break-all font-mono text-sm text-indigo-300">{result.endpoint}</div>
            <pre className="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(result.sample_request.body ?? result.sample_request.params, null, 2)}</pre>
          </Card>

          {result.sample_response && (
            <Card title="Sample response from ad server"
              right={<Badge verdict={result.sample_response.findings?.some((f) => f.severity === 'fail') ? 'FAIL' : 'PASS'}>
                HTTP {result.sample_response.status_code}
              </Badge>}>
              {result.sample_response.findings?.filter((f) => f.severity === 'fail' || f.severity === 'warn').length > 0 && (
                <ul className="mb-2 list-disc space-y-1 pl-5 text-xs">
                  {result.sample_response.findings.filter((f) => f.severity === 'fail' || f.severity === 'warn').slice(0, 30).map((f, i) => (
                    <li key={i} className={f.severity === 'fail' ? 'text-rose-300' : 'text-amber-300'}>
                      <span className="uppercase">[{f.severity}]</span> {f.spec_section}: {f.observed}
                    </li>
                  ))}
                </ul>
              )}
              <pre className="max-h-80 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">{result.sample_response.raw || '(empty body)'}</pre>
            </Card>
          )}

          <Card title={`Per-request results (${result.results.length})`}>
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-slate-900 text-xs uppercase text-slate-500">
                  <tr className="border-b border-slate-800">
                    <th className="py-2 pr-3">#</th><th className="py-2 pr-3">HTTP</th>
                    <th className="py-2 pr-3">Filled</th><th className="py-2 pr-3">Class</th>
                    <th className="py-2 pr-3 text-right">Price</th><th className="py-2 pr-3 text-right">Latency</th>
                    <th className="py-2 pr-3">Conformant</th><th className="py-2">Note</th>
                  </tr>
                </thead>
                <tbody className="text-slate-200">
                  {result.results.slice(0, 200).map((r) => (
                    <tr key={r.i} className="border-b border-slate-800/50">
                      <td className="py-1.5 pr-3 tabular-nums text-slate-500">{r.i}</td>
                      <td className={cls('py-1.5 pr-3 tabular-nums', r.status_code >= 500 || r.status_code === 0 ? 'text-rose-300' : 'text-slate-300')}>{r.status_code || 'ERR'}</td>
                      <td className="py-1.5 pr-3">{r.filled ? <span className="text-emerald-400">yes</span> : <span className="text-slate-500">no</span>}</td>
                      <td className="py-1.5 pr-3"><Badge verdict={CLASS_TONE[r.classification] || 'ERROR'}>{r.classification}</Badge></td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{r.price != null ? `$${Number(r.price).toFixed(2)}` : '—'}</td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">{r.latency_ms} ms</td>
                      <td className="py-1.5 pr-3">{r.conformant ? <span className="text-emerald-400">✓</span> : <span className="text-rose-300">✗ {r.fail_count}</span>}</td>
                      <td className="py-1.5 text-slate-500">{r.no_fill_reason || r.campaign || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.results.length > 200 && <p className="py-2 text-center text-xs text-slate-500">Showing first 200 of {result.results.length}.</p>}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
