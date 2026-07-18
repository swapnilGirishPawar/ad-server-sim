import React, { useEffect, useRef, useState } from 'react'
import { Card, Button, Select, Textarea, Checkbox, Stat } from './ui.jsx'
import { dspList, dspGetVast } from './api.js'
import { parseVast } from './vast/parse.js'
import { QUARTILE_AT, STEP_LABEL, fireBeacon } from './vast/tracking.js'
import { SAMPLE_VAST } from './vast/sample.js'
import { TrackingDiagram, EventsTable, ParsedInfoCard, ErrorPanel } from './vast/components.jsx'

const initialDiag = () => ({
  request: { state: 'fired', sub: 'loaded' },
  impression: { state: 'pending' }, start: { state: 'pending' },
  firstQuartile: { state: 'pending' }, midpoint: { state: 'pending' },
  thirdQuartile: { state: 'pending' }, complete: { state: 'pending' },
  click: { state: 'pending' }, error: { state: 'pending' },
})

// Props: seed = { xml, meta, key } handed over from the Publisher Ad Request tab.
export default function VastPlayer({ seed }) {
  const [xml, setXml] = useState(SAMPLE_VAST)
  const [parsed, setParsed] = useState(null)
  const [source, setSource] = useState(null)
  const [log, setLog] = useState([])
  const [diag, setDiag] = useState(initialDiag())
  const [dsps, setDsps] = useState([])
  const [dspId, setDspId] = useState('dsp-1')
  const [fireReal, setFireReal] = useState(true)
  const [muted, setMuted] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const videoRef = useRef(null)
  const firedRef = useRef(new Set())
  const startRef = useRef(null)
  const fireRealRef = useRef(fireReal)
  const mutedRef = useRef(muted)
  useEffect(() => { fireRealRef.current = fireReal }, [fireReal])
  useEffect(() => { mutedRef.current = muted }, [muted])

  const ts = () => (startRef.current == null ? '0.000' : ((performance.now() - startRef.current) / 1000).toFixed(3))
  const addLog = (e) => setLog((l) => [...l, { ts: ts(), ...e }])
  const trackUrls = (name) => (parsed ? parsed.trackingEvents.filter((e) => e.event === name).map((e) => e.url) : [])

  function load(xmlText, meta) {
    const p = parseVast(xmlText)
    firedRef.current = new Set()
    startRef.current = performance.now()
    setParsed(p); setSource(meta || null); setDiag(initialDiag()); setErr(null)
    setLog([{ ts: '0.000', event: 'request', label: 'Ad Request', status: 'info', note: p.ok ? 'VAST loaded' : 'parse issues' }])
  }

  // Reload the media element to the start whenever a new VAST is parsed, and
  // attempt playback (muted autoplay is allowed; unmuted may be blocked).
  useEffect(() => {
    const v = videoRef.current
    if (!v || !parsed?.mediaFile) return
    try { v.muted = mutedRef.current; v.load(); v.play().catch(() => {}) } catch { /* ignore */ }
  }, [parsed])

  // Load the built-in sample on mount, or the seed handed over from Publisher.
  useEffect(() => {
    if (seed?.xml) { setXml(seed.xml); load(seed.xml, seed.meta) }
    else { load(SAMPLE_VAST, { label: 'Built-in sample' }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.key])

  useEffect(() => { dspList().then(setDsps).catch(() => { /* sim may be starting */ }) }, [])

  function fireStep(step, urls, label) {
    if (!fireRealRef.current) {
      setDiag((d) => ({ ...d, [step]: { state: 'reached', sub: urls.length ? `${urls.length} px (off)` : 'no tracker' } }))
      addLog({ event: step, label, status: 'reached', note: 'firing off' }); return
    }
    if (!urls.length) {
      setDiag((d) => ({ ...d, [step]: { state: 'reached', sub: 'no tracker' } }))
      addLog({ event: step, label, status: 'reached' }); return
    }
    setDiag((d) => ({ ...d, [step]: { state: 'fired', sub: `${urls.length} px` } }))
    Promise.all(urls.map((u) => fireBeacon(u))).then((res) => {
      addLog({ event: step, label, status: 'fired', ok: res.some((r) => r.ok), url: res[0]?.url })
    })
  }

  // ---- video lifecycle ----
  const onPlay = () => {
    if (firedRef.current.has('started') || !parsed) return
    firedRef.current.add('started'); firedRef.current.add('start')
    fireStep('impression', parsed.impressions.map((i) => i.url), 'Impression')
    fireStep('start', trackUrls('start'), 'Start')
  }
  const onTimeUpdate = (ev) => {
    const v = ev.currentTarget
    const dur = v.duration || parsed?.durationSec || 0
    if (!dur) return
    const frac = v.currentTime / dur
    for (const q of ['firstQuartile', 'midpoint', 'thirdQuartile']) {
      if (frac >= QUARTILE_AT[q] && !firedRef.current.has(q)) {
        firedRef.current.add(q); fireStep(q, trackUrls(q), STEP_LABEL[q])
      }
    }
  }
  const onEnded = () => {
    if (firedRef.current.has('complete')) return
    firedRef.current.add('complete'); fireStep('complete', trackUrls('complete'), 'Ad Complete')
  }
  const onError = () => {
    const urls = parsed?.errors || []
    setDiag((d) => ({ ...d, error: { state: 'error', sub: urls.length ? `${urls.length} px` : 'playback failed' } }))
    if (fireRealRef.current) urls.forEach((u) => fireBeacon(u))
    addLog({ event: 'error', label: 'Ad Error', status: 'error', note: 'playback failed' })
  }
  const doClick = () => {
    if (!parsed) return
    fireStep('click', parsed.clickTracking, 'Click')
  }

  const loadFromDsp = async () => {
    setErr(null); setBusy(true)
    try {
      const text = await dspGetVast(dspId)
      setXml(text)
      load(text, { label: `Mock DSP creative (${dspId})`, endpoint: `/dsps/${dspId}/vast` })
    } catch (e) { setErr(`Could not load DSP creative: ${String(e.message || e)}`) }
    finally { setBusy(false) }
  }

  const mediaUrl = parsed?.mediaFile?.url || null

  return (
    <div className="space-y-4">
      {err && <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{err}</div>}

      <Card title="What this does">
        <p className="text-sm text-slate-400">
          Paste or load a <span className="text-slate-200">VAST tag</span>, watch it play, and see the impression,
          quartile, click and error trackers fire in real time. Pull the live creative from any mock DSP, or open the
          winning ad straight from the <span className="text-slate-200">Publisher Ad Request</span> tab. When
          "Fire real tracking pixels" is on, the beacons hit the ad server and mock DSP, so the events show up on the
          Dashboard through the normal tracking pipeline.
        </p>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card title="VAST source">
          <Textarea rows={12} value={xml} spellCheck={false} onChange={(e) => setXml(e.target.value)} />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button onClick={() => load(xml)} disabled={busy}>Load &amp; Play</Button>
            <Button variant="ghost" onClick={() => load(xml, source)} disabled={busy}>Reset</Button>
            <Button variant="ghost" onClick={() => { setXml(SAMPLE_VAST); load(SAMPLE_VAST, { label: 'Built-in sample' }) }} disabled={busy}>Load sample</Button>
            <Button variant="ghost" onClick={() => { setXml(''); setParsed(null); setLog([]); setDiag(initialDiag()) }} disabled={busy}>Clear</Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <div className="w-44">
              <Select value={dspId} onChange={(e) => setDspId(e.target.value)}>
                {dsps.length
                  ? dsps.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.id})</option>)
                  : <option value="dsp-1">dsp-1</option>}
              </Select>
            </div>
            <Button variant="ghost" onClick={loadFromDsp} disabled={busy}>Load from DSP</Button>
            <Checkbox checked={fireReal} onChange={(e) => setFireReal(e.target.checked)} label="Fire real tracking pixels" />
            <Checkbox checked={muted} onChange={(e) => setMuted(e.target.checked)} label="Muted (autoplay)" />
          </div>
          {source && (
            <p className="mt-2 text-xs text-slate-500">
              Source: {source.label}{source.endpoint ? ` · ${source.endpoint}` : ''}{source.status ? ` · HTTP ${source.status}` : ''}
            </p>
          )}
        </Card>

        <Card title="Player">
          {mediaUrl ? (
            <video ref={videoRef} src={mediaUrl} controls playsInline
              className="aspect-video w-full rounded-lg bg-black"
              onPlay={onPlay} onTimeUpdate={onTimeUpdate} onEnded={onEnded} onError={onError} />
          ) : (
            <div className="flex aspect-video w-full items-center justify-center rounded-lg border border-line bg-ink-900 px-4 text-center text-sm text-slate-500">
              {parsed?.adType === 'Wrapper'
                ? 'Wrapper VAST detected. Resolve the tag URI (see Parsed VAST) to play the wrapped creative.'
                : 'No playable media. Load a VAST that contains a MediaFile.'}
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button onClick={doClick} disabled={!parsed || (!parsed.clickThrough && !parsed.clickTracking.length)}>Simulate click</Button>
            {parsed?.clickThrough && (
              <a href={parsed.clickThrough} target="_blank" rel="noreferrer" className="break-all text-xs text-indigo-300 hover:underline">
                {parsed.clickThrough}
              </a>
            )}
          </div>
        </Card>
      </div>

      {parsed && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Impression px" value={parsed.impressions.length} tone={parsed.impressions.length ? 'good' : 'warn'} />
          <Stat label="Tracking events" value={parsed.trackingEvents.length} />
          <Stat label="Media files" value={parsed.mediaFiles.length} tone={parsed.mediaFiles.length ? 'good' : 'bad'} />
          <Stat label="Duration" value={parsed.durationStr || 'n/a'} />
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        <TrackingDiagram states={diag} />
        <EventsTable log={log} />
      </div>

      {parsed && <ParsedInfoCard parsed={parsed} />}
      {parsed && <ErrorPanel parsed={parsed} />}
    </div>
  )
}
