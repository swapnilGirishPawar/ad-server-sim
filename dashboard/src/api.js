const BASE = '/api'

async function j(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status}: ${text}`)
  return text ? JSON.parse(text) : null
}

const q = (runId) => (runId ? `?run_id=${encodeURIComponent(runId)}` : '')

export const api = {
  health: () => j('GET', '/health'),
  config: () => j('GET', '/config'),
  target: () => j('GET', '/target'),
  seed: (b) => j('POST', '/seed', b),
  run: (b) => j('POST', '/run', b),
  scenario: (b) => j('POST', '/scenario', b),
  stop: () => j('POST', '/runs/stop'),
  runs: () => j('GET', '/runs'),
  overview: (r) => j('GET', '/metrics/overview' + q(r)),
  campaigns: (r) => j('GET', '/metrics/campaigns' + q(r)),
  auctions: (r) => j('GET', '/metrics/auctions' + q(r)),
  timeseries: (r) => j('GET', '/metrics/timeseries' + q(r)),
  scenarios: (r) => j('GET', '/metrics/scenarios' + q(r)),
  fill: (r) => j('GET', '/metrics/fill' + q(r)),
  scorecard: (r) => j('GET', '/metrics/scorecard' + q(r)),
  findings: (r) => j('GET', '/metrics/findings' + q(r)),
  reconcile: (r) => j('GET', '/metrics/reconcile' + q(r)),
  supplyChain: () => j('GET', '/supply-chain'),
  report: (r) => j('GET', '/report' + q(r)),
  dsp: () => j('GET', '/dsp'),
  dspConfig: (b) => j('POST', '/dsp/config', b),
  flowOrtb: (b) => j('POST', '/flow/ortb', b),
  publisherRequest: (b) => j('POST', '/publisher-request', b),
}

// Raw mock-DSP control (endpoints live at /dsps/*, NOT under /api - same origin).
// Every DSP - including the original default one, id 'dsp-1' - is reachable
// uniformly at /dsps/{dspId}/... . `dspId` defaults to 'dsp-1' so existing
// no-arg call sites (e.g. panels.jsx's Flow B) keep working unchanged.
async function raw(method, path, body) {
  const res = await fetch(path, {
    method, headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status}: ${text}`)
  return text ? JSON.parse(text) : null
}

export const dspList = () => raw('GET', '/dsps/')
export const dspCreate = (body) => raw('POST', '/dsps/', body || {})
export const dspDelete = (dspId) => raw('DELETE', `/dsps/${encodeURIComponent(dspId)}`)
export const dspGetConfig = (dspId = 'dsp-1') => raw('GET', `/dsps/${encodeURIComponent(dspId)}/config`)

export async function dspSetConfig(patch, dspId = 'dsp-1') {
  return raw('POST', `/dsps/${encodeURIComponent(dspId)}/config`, patch)
}
export async function dspReset(dspId = 'dsp-1') {
  const res = await fetch(`/dsps/${encodeURIComponent(dspId)}/reset`, { method: 'POST' })
  return res.ok ? res.json() : null
}

// Fetch a mock DSP's live VAST creative as raw XML text (for the VAST Player).
// Same origin (served at :8090), so no CORS concerns.
export async function dspGetVast(dspId = 'dsp-1') {
  const res = await fetch(`/dsps/${encodeURIComponent(dspId)}/vast`)
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`)
  return res.text()
}

// The mock DSP lives at /dsps/{dspId}/bid (NOT under /api) - same origin, so
// the browser can call it directly to show that DSP's own raw bid response.
export async function dspBidRaw(dspId = 'dsp-1') {
  const sample = {
    id: 'dashboard-raw-1',
    at: 1,
    tmax: 660,
    cur: ['USD'],
    bcat: ['IAB26'],
    imp: [{
      id: '1',
      tagid: '351511',
      bidfloor: 5.775,
      bidfloorcur: 'USD',
      clickbrowser: 0,
      secure: 1,
      video: {
        mimes: ['video/mp4'],
        minduration: 3,
        maxduration: 300,
        startdelay: 0,
        protocols: [1, 2, 3, 4, 5, 6],
        w: 1920,
        h: 1080,
        linearity: 1,
        sequence: 1,
        boxingallowed: 1,
        playbackmethod: [1],
        api: [1, 2],
      },
    }],
    app: {
      id: '9887674',
      name: 'Philo: Shows, Movies, and Live TV',
      bundle: 'G22223020133',
      storeurl: 'https://samsung.com/us/appstore/app/G22223020133',
      cat: ['IAB4', 'IAB5', 'IAB2', 'IAB3', 'IAB1'],
      publisher: { id: '1192' },
      content: {
        genre: 'Adventure',
        cat: ['IAB1-5'],
        videoquality: 1,
        context: 1,
        contentrating: 'TV-MA',
        livestream: 0,
        len: 1380,
        language: 'en',
      },
    },
    device: {
      geo: { lat: 32.9074, lon: -97.4257, type: 2, country: 'USA', region: 'TX', city: 'Fort Worth', zip: '76179' },
      dnt: 0,
      lmt: 0,
      ua: 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/537.36 (KHTML, like Gecko) 76.0.3809.146/6.0 TV Safari/537.36',
      ip: '132.147.164.4',
      devicetype: 3,
      make: 'Samsung',
      model: 'UN70TU6985FXZA',
      os: 'Tizen',
      osv: '6.0',
      js: 1,
      language: 'en',
      carrier: 'Nextlink Broadband',
      connectiontype: 2,
      ifa: 'df8ee962-af95-4a77-b0ad-4bbb6ff86c0b',
      ext: { ifa_type: 'tifa' },
    },
    user: {},
    source: {
      fd: 1,
      tid: '85x1CF677D5AED84A08',
      ext: {
        schain: {
          complete: 1,
          ver: '1.0',
          nodes: [{ asi: 'voisetech.com', sid: '1192', rid: 'dashboard-raw-1', hp: 1 }],
        },
      },
    },
    regs: { coppa: 0, ext: { us_privacy: '1YNN' } },
  }
  const res = await fetch(`/dsps/${encodeURIComponent(dspId)}/bid`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sample),
  })
  if (res.status === 204) return { _note: 'HTTP 204 - DSP no-bid (no body)' }
  const text = await res.text()
  return text ? JSON.parse(text) : { _note: `HTTP ${res.status}` }
}

export function openWS(onMsg) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/ws`)
  ws.onmessage = (e) => {
    try { onMsg(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  return ws
}
