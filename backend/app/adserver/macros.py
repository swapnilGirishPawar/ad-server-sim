"""VAST/VAST-tracking macro substitution.

IAB VAST macros are square-bracketed tokens the player MUST replace before
firing a URL (VAST 4.x §6 "Macros"). A simulator that fires the raw tag without
substituting them is not behaving like a real player — and the server can't
correlate cachebusting/playhead — so we substitute the standard set here.

We handle both literal brackets (`[CACHEBUSTING]`) and percent-encoded brackets
(`%5BCACHEBUSTING%5D`), since servers often emit the encoded form inside query
strings.

Supported (others pass through unchanged and are reported so the caller can warn):
  [CACHEBUSTING]      random 8-digit int (VAST §6, dedupe/cache-bust)
  [TIMESTAMP]         ISO-8601 UTC of the fire moment
  [CONTENTPLAYHEAD]   HH:MM:SS playhead position (quartile-aware)
  [ADPLAYHEAD]        alias of CONTENTPLAYHEAD for the ad timeline
  [ERRORCODE]         VAST error code (only meaningful on <Error> pixels)
  [CACHEBUSTER]       common non-standard alias of CACHEBUSTING
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import quote

# Matches [TOKEN] or %5BTOKEN%5D (case-insensitive on the encoding markers).
_MACRO_RE = re.compile(r"\[([A-Z0-9_]+)\]|%5B([A-Za-z0-9_]+)%5D", re.IGNORECASE)


def _value(name: str, *, errorcode: Optional[int], playhead: str, ts_iso: str, ts_ms: int) -> Optional[str]:
    name = name.upper()
    if name in ("CACHEBUSTING", "CACHEBUSTER"):
        return str(random.randint(10_000_000, 99_999_999))
    if name == "TIMESTAMP":
        return ts_iso
    if name in ("CONTENTPLAYHEAD", "ADPLAYHEAD", "MEDIAPLAYHEAD"):
        return playhead
    if name == "ERRORCODE":
        return str(errorcode if errorcode is not None else 0)
    return None  # unknown macro -> leave in place, report it


def substitute(url: str, *, errorcode: Optional[int] = None, playhead: str = "00:00:00",
               now_ms: Optional[int] = None) -> Tuple[str, List[str], List[str]]:
    """Return (substituted_url, replaced_macros, unresolved_macros).

    Values destined for a query string are percent-encoded. `playhead` should be
    the HH:MM:SS position appropriate to the event being fired (e.g. midpoint).
    """
    if not url or "[" not in url and "%5B" not in url and "%5b" not in url:
        return url, [], []
    ts_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    ts_iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
    replaced: List[str] = []
    unresolved: List[str] = []

    def _repl(m: re.Match) -> str:
        token = m.group(1) or m.group(2)
        val = _value(token, errorcode=errorcode, playhead=playhead, ts_iso=ts_iso, ts_ms=ts_ms)
        if val is None:
            unresolved.append(token.upper())
            return m.group(0)
        replaced.append(token.upper())
        return quote(val, safe="")

    return _MACRO_RE.sub(_repl, url), replaced, unresolved


# Quartile -> representative content playhead (assumes a 30s creative; only the
# ordering/relative value matters for correlating quartile fires).
QUARTILE_PLAYHEAD = {
    "start": "00:00:00",
    "firstQuartile": "00:00:07",
    "midpoint": "00:00:15",
    "thirdQuartile": "00:00:22",
    "complete": "00:00:30",
}
