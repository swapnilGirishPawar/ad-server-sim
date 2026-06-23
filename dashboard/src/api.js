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
}

export function openWS(onMsg) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/api/ws`)
  ws.onmessage = (e) => {
    try { onMsg(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  return ws
}
