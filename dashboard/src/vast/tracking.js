// Tracking-event ordering, macro substitution, and fire-and-forget beacons.
// Beacons are plain image requests (exactly how a real VAST player fires pixels),
// so they are never blocked by CORS and need no readable response.

// Progress fraction at which each standard linear quartile event fires.
export const QUARTILE_AT = {
  start: 0, firstQuartile: 0.25, midpoint: 0.5, thirdQuartile: 0.75, complete: 1,
}

// The lifecycle steps shown in the timeline / diagram, in order. "request" and
// "impression" bracket the quartiles; "click" is user-driven.
export const LIFECYCLE = [
  'request', 'impression', 'start', 'firstQuartile', 'midpoint',
  'thirdQuartile', 'complete', 'click',
]

// Human labels for the steps above.
export const STEP_LABEL = {
  request: 'Ad Request', impression: 'Impression', start: 'Start',
  firstQuartile: '25% Complete', midpoint: '50% Complete',
  thirdQuartile: '75% Complete', complete: 'Ad Complete', click: 'Click',
}

// Replace the common VAST / OpenRTB macros a player is expected to fill in.
export function substituteMacros(url) {
  if (!url) return url
  const cb = String(Math.floor(Math.random() * 1e10))
  const ts = new Date().toISOString()
  return url
    .replace(/\[CACHEBUSTING\]/g, cb)
    .replace(/\[CB\]/g, cb)
    .replace(/\[TIMESTAMP\]/g, encodeURIComponent(ts))
    .replace(/\[ERRORCODE\]/g, '900')
    .replace(/\[CONTENTPLAYHEAD\]/g, '00:00:00.000')
    .replace(/\$\{AUCTION_PRICE\}/g, '0')
}

// Fire a single pixel. Resolves { ok, url }; never rejects. Note: onload only
// succeeds for image-like responses (the mock DSP returns a 1x1 gif); an ad
// server that answers a pixel with 204/JSON will report ok=false even though the
// hit landed, so treat ok as a best-effort hint, not proof.
export function fireBeacon(rawUrl, timeoutMs = 5000) {
  const url = substituteMacros(rawUrl)
  return new Promise((resolve) => {
    let done = false
    const finish = (ok) => { if (done) return; done = true; resolve({ ok, url }) }
    try {
      const img = new Image()
      img.onload = () => finish(true)
      img.onerror = () => finish(false)
      img.src = url
      setTimeout(() => finish(false), timeoutMs)
    } catch { finish(false) }
  })
}
