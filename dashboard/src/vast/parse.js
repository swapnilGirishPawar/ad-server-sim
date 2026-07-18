// Pure, dependency-free VAST parser built on the browser DOMParser.
// Handles VAST 2/3/4 InLine ads and detects Wrappers. No React, no network.
// The single source of truth for turning a VAST XML string into a structured
// object the player and the UI can render.

const lname = (el) => (el.localName || el.tagName || '').toLowerCase()

// Namespace-agnostic, case-insensitive element lookup (VAST is PascalCase, but
// some servers wrap it in a namespace prefix).
function all(root, name) {
  if (!root) return []
  const want = name.toLowerCase()
  return Array.from(root.getElementsByTagName('*')).filter((e) => lname(e) === want)
}
function first(root, name) { return all(root, name)[0] || null }
function text(el) { return el ? (el.textContent || '').trim() : '' }

// "HH:MM:SS(.mmm)" -> seconds. Falls back to a bare number, else 0.
export function durationToSeconds(str) {
  if (!str) return 0
  const m = String(str).trim().match(/^(\d+):(\d{1,2}):(\d{1,2})(?:\.(\d+))?$/)
  if (!m) { const n = Number(str); return Number.isFinite(n) ? n : 0 }
  const [, h, mm, ss, frac] = m
  return (+h) * 3600 + (+mm) * 60 + (+ss) + (frac ? Number('0.' + frac) : 0)
}

// Choose the MediaFile most likely to play in a browser <video>: prefer MP4,
// then the highest bitrate that stays reasonable for local playback.
function pickMediaFile(mediaFiles) {
  if (!mediaFiles.length) return null
  const mp4 = mediaFiles.filter((m) => /mp4/i.test(m.type || '') || /\.mp4($|\?)/i.test(m.url || ''))
  const pool = mp4.length ? mp4 : mediaFiles
  const sorted = [...pool].sort((a, b) => (a.bitrate || 0) - (b.bitrate || 0))
  const capped = sorted.filter((m) => (m.bitrate || 0) <= 2000)
  return capped.length ? capped[capped.length - 1] : sorted[sorted.length - 1]
}

export function parseVast(xmlText) {
  const out = {
    ok: false, raw: xmlText || '', version: null, adType: null,
    adSystem: null, adTitle: null, adId: null, creativeId: null,
    durationStr: null, durationSec: 0,
    mediaFiles: [], mediaFile: null,
    impressions: [], trackingEvents: [], clickThrough: null, clickTracking: [],
    errors: [], wrapperUri: null, parseErrors: [],
  }
  const src = (xmlText || '').trim()
  if (!src) { out.parseErrors.push('No VAST XML provided.'); return out }

  let doc
  try { doc = new DOMParser().parseFromString(src, 'application/xml') }
  catch (e) { out.parseErrors.push('XML parse failed: ' + (e.message || e)); return out }

  const perr = doc.querySelector('parsererror')
  if (perr) { out.parseErrors.push('Malformed XML: ' + (text(perr).split('\n')[0] || 'invalid document')); return out }

  const vast = lname(doc.documentElement) === 'vast' ? doc.documentElement : first(doc, 'VAST')
  if (!vast) { out.parseErrors.push('Root <VAST> element not found.'); return out }
  out.version = vast.getAttribute('version') || null

  const ad = first(vast, 'Ad')
  if (!ad) {
    // An empty <VAST></VAST> is a valid "no ad" response, not a broken document.
    out.parseErrors.push('No <Ad> element (empty VAST / no-fill response).')
    return out
  }
  out.adId = ad.getAttribute('id') || null

  const inline = first(ad, 'InLine')
  const wrapper = first(ad, 'Wrapper')
  const body = inline || wrapper
  out.adType = inline ? 'InLine' : wrapper ? 'Wrapper' : null
  if (!body) { out.parseErrors.push('<Ad> has neither <InLine> nor <Wrapper>.'); return out }

  out.adSystem = text(first(body, 'AdSystem')) || null
  out.adTitle = text(first(body, 'AdTitle')) || null
  out.impressions = all(body, 'Impression')
    .map((e) => ({ id: e.getAttribute('id') || null, url: text(e) })).filter((x) => x.url)
  out.errors = all(body, 'Error').map(text).filter(Boolean)

  if (wrapper) out.wrapperUri = text(first(body, 'VASTAdTagURI')) || null

  out.trackingEvents = all(body, 'Tracking')
    .map((e) => ({ event: e.getAttribute('event') || 'unknown', url: text(e) })).filter((x) => x.url)

  out.clickThrough = text(first(body, 'ClickThrough')) || null
  out.clickTracking = all(body, 'ClickTracking').map(text).filter(Boolean)

  const linear = first(body, 'Linear')
  if (linear) {
    const dur = text(first(linear, 'Duration'))
    out.durationStr = dur || null
    out.durationSec = durationToSeconds(dur)
    const creative = all(body, 'Creative').find((c) => first(c, 'Linear')) || first(body, 'Creative')
    if (creative) out.creativeId = creative.getAttribute('id') || null
    const uaid = text(first(linear, 'UniversalAdId'))
    if (!out.creativeId && uaid) out.creativeId = uaid
    out.mediaFiles = all(linear, 'MediaFile').map((m) => ({
      url: text(m), type: m.getAttribute('type') || '',
      delivery: m.getAttribute('delivery') || '',
      width: Number(m.getAttribute('width')) || null,
      height: Number(m.getAttribute('height')) || null,
      bitrate: Number(m.getAttribute('bitrate')) || null,
    })).filter((m) => m.url)
    out.mediaFile = pickMediaFile(out.mediaFiles)
  }

  if (inline) {
    if (!out.mediaFiles.length) out.parseErrors.push('InLine ad has no <MediaFile> to play.')
    if (!out.impressions.length) out.parseErrors.push('InLine ad has no <Impression> tracker (VAST requires at least one).')
  }
  // "ok" means playable: an InLine with a media file, or a wrapper (which would
  // need resolving, surfaced to the UI as a note rather than a hard failure).
  out.ok = !!out.mediaFile || (out.adType === 'Wrapper' && !!out.wrapperUri)
  return out
}
