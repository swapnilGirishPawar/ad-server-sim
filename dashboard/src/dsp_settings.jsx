import React, { useCallback, useEffect, useState } from 'react'
import { Card, Stat, Button, Field, Input, Select, Badge, cls } from './ui.jsx'
import { dspList, dspCreate, dspDelete, dspSetConfig, dspReset, dspBidRaw } from './api.js'

// OpenRTB No-Bid Reason codes (2.6 §5.24 / List 5.24) - shown when mode = no_bid.
const NBR_CODES = [
  [0, '0 · Unknown / other'], [1, '1 · Technical error'], [2, '2 · Invalid request'],
  [3, '3 · Known web spider'], [4, '4 · Suspected non-human'], [5, '5 · Cloud/DC/proxy IP'],
  [6, '6 · Unsupported device'], [7, '7 · Blocked publisher/site'], [8, '8 · Unmatched user'],
  [9, '9 · Daily reader cap'], [10, '10 · Daily domain cap'],
]

// A starter custom BidResponse template. Macros are substituted by the mock DSP:
// quoted "{{price}}" becomes a JSON number; the rest are string substitutions.
const SAMPLE_CUSTOM = JSON.stringify({
  id: '{{id}}', cur: 'USD',
  seatbid: [{
    seat: '{{seat}}',
    bid: [{
      id: '{{id}}-1', impid: '{{impid}}', price: '{{price}}',
      adm: '<VAST version="4.2"><Ad id="{{crid}}">…</Ad></VAST>',
      nurl: 'https://my-dsp.example/win?price=${AUCTION_PRICE}&cb=[CB]',
      crid: '{{crid}}', adid: '{{crid}}', cid: 'my-campaign-1',
      adomain: ['my-brand.com'], cat: ['IAB1'], mtype: 2, w: 1920, h: 1080, protocol: 7,
    }],
  }],
}, null, 2)

function Textarea(props) {
  return <textarea {...props}
    className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-indigo-500 disabled:opacity-50" />
}

function Checkbox({ checked, onChange, label }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
      <input type="checkbox" checked={!!checked} onChange={onChange}
        className="h-4 w-4 rounded border-slate-600 bg-slate-950 accent-indigo-500" />
      {label}
    </label>
  )
}

const num = (v, d = 0) => { const n = Number(v); return Number.isFinite(n) ? n : d }
const arr = (v) => (Array.isArray(v) ? v : String(v || '').split(',').map((s) => s.trim()).filter(Boolean))

const MODES = [
  ['bid', 'Bid', 'PASS'], ['no_bid', 'No-bid', 'WARN'],
  ['timeout', 'Timeout', 'BLOCKED'], ['error', 'Error', 'FAIL'],
]
const modeTone = (m) => (MODES.find((x) => x[0] === m) || [])[2] || 'ERROR'

// Tabs for switching between the registered mock DSPs, plus "+ Add DSP".
function DspTabs({ dsps, activeId, onSelect, onAdd, onRemove, busy }) {
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')

  const submit = () => { onAdd(name.trim()); setName(''); setAdding(false) }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {dsps.map((d) => (
        <button key={d.id} onClick={() => onSelect(d.id)}
          className={cls('flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition',
            d.id === activeId ? 'border-indigo-500 bg-indigo-600 text-white'
              : 'border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800')}>
          {d.name}
          <Badge verdict={modeTone(d.config?.mode)}>{d.config?.mode}</Badge>
          <span className="text-xs opacity-70">{d.stats?.bids ?? 0} bids</span>
        </button>
      ))}
      {!adding && (
        <Button variant="ghost" onClick={() => setAdding(true)} disabled={busy}>+ Add DSP</Button>
      )}
      {adding && (
        <div className="flex items-center gap-1">
          <Input autoFocus placeholder="DSP name (optional)" value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setAdding(false) }} />
          <Button onClick={submit} disabled={busy}>Create</Button>
          <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
        </div>
      )}
      {activeId !== 'dsp-1' && (
        <Button variant="danger" onClick={onRemove} disabled={busy}>Remove {dsps.find((d) => d.id === activeId)?.name}</Button>
      )}
    </div>
  )
}

export default function DspSettings() {
  const [dsps, setDsps] = useState([])           // all registered mock DSPs (summaries)
  const [activeId, setActiveId] = useState('dsp-1')
  const [cfg, setCfg] = useState(null)          // editable mirror of the active DSP's config
  const [stats, setStats] = useState(null)
  const [endpoint, setEndpoint] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [customText, setCustomText] = useState(SAMPLE_CUSTOM)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [saved, setSaved] = useState('')
  const [testResp, setTestResp] = useState(null)

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))

  const applyEntry = (entry) => {
    setActiveId(entry.id)
    setCfg(entry.config); setStats(entry.stats); setEndpoint(entry.endpoint_url || '')
    if (entry.config && entry.config.custom_response) {
      setUseCustom(true); setCustomText(JSON.stringify(entry.config.custom_response, null, 2))
    } else {
      setUseCustom(false)
    }
    setTestResp(null)
  }

  // Reload the full DSP list and (re)select a DSP by id - preferId, else the
  // currently active one if it still exists, else the first registered DSP.
  const load = useCallback(async (preferId) => {
    setErr(null)
    try {
      const list = await dspList()
      setDsps(list)
      const wantId = preferId || activeId
      const entry = list.find((d) => d.id === wantId) || list[0]
      if (entry) applyEntry(entry)
    } catch (e) { setErr(String(e.message || e)) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const selectDsp = (id) => {
    const entry = dsps.find((d) => d.id === id)
    if (entry) applyEntry(entry)
    else load(id)
  }

  function buildPatch() {
    const c = cfg
    const patch = {
      mode: c.mode,
      bid_rate: num(c.bid_rate, 1), emit_nbr: !!c.emit_nbr, nbr_code: num(c.nbr_code, 0),
      timeout_ms: num(c.timeout_ms, 2000), verbose: !!c.verbose,
      price: num(c.price, 0), bid_margin: num(c.bid_margin, 1), max_cpm: num(c.max_cpm, 0),
      jitter: num(c.jitter, 0), respect_floor: !!c.respect_floor, currency: c.currency || 'USD',
      seat: c.seat, crid: c.crid, campaign_id: c.campaign_id, adomain: arr(c.adomain), cat: arr(c.cat),
      video_url: c.video_url, video_w: num(c.video_w, 640), video_h: num(c.video_h, 360),
      video_bitrate: num(c.video_bitrate, 463), video_duration: c.video_duration,
      advertiser_name: c.advertiser_name, landing_url: c.landing_url, track_base: c.track_base,
      nurl_template: c.nurl_template, burl_template: c.burl_template,
      lurl_template: c.lurl_template, iurl: c.iurl,
    }
    if (useCustom) {
      let parsed
      try { parsed = JSON.parse(customText) }
      catch (e) { throw new Error('Custom response JSON is invalid: ' + e.message) }
      patch.custom_response = parsed
    } else {
      patch.custom_response = null
    }
    return patch
  }

  const flash = (m) => { setSaved(m); setTimeout(() => setSaved(''), 2500) }

  const saveAll = async () => {
    setErr(null); setBusy(true)
    try { await dspSetConfig(buildPatch(), activeId); await load(activeId); flash('Settings saved ✓') }
    catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
  }
  // Mode buttons apply instantly (the common demo toggle).
  const applyMode = async (m) => {
    setErr(null); set('mode', m)
    try { await dspSetConfig({ mode: m }, activeId); flash(`Mode → ${m}`); await load(activeId) }
    catch (e) { setErr(String(e.message || e)) }
  }
  const doReset = async () => {
    setErr(null)
    try { setStats(await dspReset(activeId)); setTestResp(null); flash('Stats reset'); load(activeId) }
    catch (e) { setErr(String(e.message || e)) }
  }
  const doTest = async () => {
    setErr(null); setBusy(true)
    try { setTestResp(await dspBidRaw(activeId)); await load(activeId) }
    catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
  }
  const doAdd = async (name) => {
    setErr(null); setBusy(true)
    try { const entry = await dspCreate({ name: name || undefined }); await load(entry.id); flash(`${entry.name} added ✓`) }
    catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
  }
  const doRemove = async () => {
    if (activeId === 'dsp-1') return
    setErr(null); setBusy(true)
    try { await dspDelete(activeId); await load() }
    catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
  }

  if (!cfg) {
    return <div className="text-sm text-slate-400">{err ? <span className="text-rose-300">{err}</span> : 'Loading DSP settings…'}</div>
  }

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{err}</div>}

      <Card title="Fake DSPs (the pretend buyers)">
        <p className="text-sm text-slate-400">
          Configure one or more mock demand partners so your ad server's auction has multiple bidders to
          compete against. Add a DSP here, copy its endpoint, and register it as a new demand partner on the
          real ad server - then a single publisher request can be won by any of them.
        </p>
        <div className="mt-3">
          <DspTabs dsps={dsps} activeId={activeId} onSelect={selectDsp} onAdd={doAdd} onRemove={doRemove} busy={busy} />
        </div>
      </Card>

      <Card title={`${dsps.find((d) => d.id === activeId)?.name || 'DSP'} - behaviour`}
        right={saved && <span className="text-xs text-emerald-400">{saved}</span>}>
        <p className="text-sm text-slate-400">
          Control how this mock demand partner responds when your ad server asks it to bid. Changes here
          take effect on the <b>next</b> request - no restart. Endpoint: <code className="text-indigo-300">{endpoint}</code>
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-500">Behaviour:</span>
          {MODES.map(([m, label, tone]) => (
            <button key={m} onClick={() => applyMode(m)}
              className={cls('rounded-lg border px-3 py-1.5 text-sm font-medium transition',
                cfg.mode === m ? 'border-indigo-500 bg-indigo-600 text-white'
                  : 'border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800')}>
              {label}
            </button>
          ))}
          <span className="ml-auto"><Badge verdict={modeTone(cfg.mode)}>{cfg.mode}</Badge></span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button onClick={saveAll} disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</Button>
          <Button variant="ghost" onClick={doTest} disabled={busy}>Send test bid</Button>
          <Button variant="ghost" onClick={doReset} disabled={busy}>Reset stats</Button>
          <Button variant="ghost" onClick={() => load(activeId)} disabled={busy}>Refresh</Button>
        </div>
      </Card>

      {/* Live stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
          <Stat label="Requests" value={stats.requests} />
          <Stat label="Bids" value={stats.bids} tone="good" />
          <Stat label="No-bids" value={stats.no_bids} tone="warn" />
          <Stat label="Timeouts" value={stats.timeouts} tone={stats.timeouts ? 'bad' : undefined} />
          <Stat label="Errors" value={stats.errors} tone={stats.errors ? 'bad' : undefined} />
          <Stat label="Total bid $" value={`$${Number(stats.total_bid_value || 0).toFixed(2)}`} />
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {/* Behaviour detail */}
        <Card title="Behaviour">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Bid rate (0–1)"><Input type="number" step="0.05" min="0" max="1" value={cfg.bid_rate} onChange={(e) => set('bid_rate', e.target.value)} /></Field>
            <Field label="Timeout delay (ms)"><Input type="number" value={cfg.timeout_ms} onChange={(e) => set('timeout_ms', e.target.value)} /></Field>
            <Field label="No-bid reason (nbr)">
              <Select value={cfg.nbr_code} onChange={(e) => set('nbr_code', e.target.value)}>
                {NBR_CODES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <div className="flex flex-col justify-end gap-2 pb-1">
              <Checkbox checked={cfg.emit_nbr} onChange={(e) => set('emit_nbr', e.target.checked)} label="No-bid as 200 + nbr (else bare 204)" />
              <Checkbox checked={cfg.verbose} onChange={(e) => set('verbose', e.target.checked)} label="Verbose logging (terminal)" />
            </div>
          </div>
        </Card>

        {/* Pricing */}
        <Card title="Pricing (how much it bids)">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Base price (CPM)"><Input type="number" step="0.5" value={cfg.price} onChange={(e) => set('price', e.target.value)} /></Field>
            <Field label="Bid margin (× floor)"><Input type="number" step="0.05" value={cfg.bid_margin} onChange={(e) => set('bid_margin', e.target.value)} /></Field>
            <Field label="Max CPM (ceiling)"><Input type="number" step="1" value={cfg.max_cpm} onChange={(e) => set('max_cpm', e.target.value)} /></Field>
            <Field label="Price jitter (±, 0–1)"><Input type="number" step="0.05" min="0" max="1" value={cfg.jitter} onChange={(e) => set('jitter', e.target.value)} /></Field>
            <Field label="Currency"><Input value={cfg.currency} onChange={(e) => set('currency', e.target.value)} /></Field>
            <div className="flex items-end pb-1"><Checkbox checked={cfg.respect_floor} onChange={(e) => set('respect_floor', e.target.checked)} label="Respect floor (no-bid below floor)" /></div>
          </div>
        </Card>

        {/* Bid identity */}
        <Card title="Who's bidding (labels on the bid)">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Seat"><Input value={cfg.seat} onChange={(e) => set('seat', e.target.value)} /></Field>
            <Field label="Creative id (crid)"><Input value={cfg.crid} onChange={(e) => set('crid', e.target.value)} /></Field>
            <Field label="Campaign id (cid)"><Input value={cfg.campaign_id} onChange={(e) => set('campaign_id', e.target.value)} /></Field>
            <Field label="Advertiser domain(s)"><Input value={arr(cfg.adomain).join(', ')} onChange={(e) => set('adomain', e.target.value)} /></Field>
            <Field label="Category (cat)"><Input value={arr(cfg.cat).join(', ')} onChange={(e) => set('cat', e.target.value)} /></Field>
          </div>
        </Card>

        {/* Creative */}
        <Card title="The creative (the ad returned)">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Advertiser name"><Input value={cfg.advertiser_name} onChange={(e) => set('advertiser_name', e.target.value)} /></Field>
            <Field label="Landing URL (clickthrough)"><Input value={cfg.landing_url} onChange={(e) => set('landing_url', e.target.value)} /></Field>
            <Field label="Video URL (MP4)"><Input value={cfg.video_url} onChange={(e) => set('video_url', e.target.value)} /></Field>
            <Field label="Duration (HH:MM:SS)"><Input value={cfg.video_duration} onChange={(e) => set('video_duration', e.target.value)} /></Field>
            <Field label="Width"><Input type="number" value={cfg.video_w} onChange={(e) => set('video_w', e.target.value)} /></Field>
            <Field label="Height"><Input type="number" value={cfg.video_h} onChange={(e) => set('video_h', e.target.value)} /></Field>
            <Field label="Bitrate (kbps)"><Input type="number" value={cfg.video_bitrate} onChange={(e) => set('video_bitrate', e.target.value)} /></Field>
            <Field label="Tracking base URL"><Input value={cfg.track_base} onChange={(e) => set('track_base', e.target.value)} /></Field>
          </div>
        </Card>
      </div>

      {/* Response URLs */}
      <Card title="Response notice URLs">
        <p className="mb-2 text-xs text-slate-500">
          The URLs the exchange pings on win / billing / loss. <code>[CB]</code> = cache-buster nonce;
          <code>{'${AUCTION_PRICE}'}</code> etc. are OpenRTB macros the exchange fills in.
        </p>
        <div className="grid gap-3">
          <Field label="Win notice (nurl)"><Input value={cfg.nurl_template} onChange={(e) => set('nurl_template', e.target.value)} /></Field>
          <Field label="Billing (burl)"><Input value={cfg.burl_template} onChange={(e) => set('burl_template', e.target.value)} /></Field>
          <Field label="Loss (lurl)"><Input value={cfg.lurl_template} onChange={(e) => set('lurl_template', e.target.value)} /></Field>
          <Field label="Preview image (iurl)"><Input value={cfg.iurl} onChange={(e) => set('iurl', e.target.value)} /></Field>
        </div>
      </Card>

      {/* Advanced: full custom response */}
      <Card title="Advanced · edit the full bid response"
        right={<Checkbox checked={useCustom} onChange={(e) => setUseCustom(e.target.checked)} label="Use custom response" />}>
        <p className="mb-2 text-xs text-slate-500">
          When on, the DSP returns this exact JSON (in Bid mode) instead of the auto-built bid. Macros:
          <code className="mx-1">{'{{price}}'}</code><code className="mx-1">{'{{impid}}'}</code>
          <code className="mx-1">{'{{id}}'}</code><code className="mx-1">{'{{crid}}'}</code>
          <code className="mx-1">{'{{seat}}'}</code><code className="mx-1">{'{{cur}}'}</code>
          - a quoted <code>"{'{{price}}'}"</code> becomes a number. Remember to click <b>Save settings</b>.
        </p>
        <Textarea rows={14} value={customText} disabled={!useCustom} onChange={(e) => setCustomText(e.target.value)} />
      </Card>

      {/* Test bid result */}
      {testResp && (
        <Card title="Test bid - what the DSP returned">
          <pre className="max-h-96 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(testResp, null, 2)}</pre>
        </Card>
      )}
    </div>
  )
}
