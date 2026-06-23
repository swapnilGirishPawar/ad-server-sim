"""Tracking-URL normalisation + canonical builders.

The ad server embeds tracking URLs that (a) use a production host and (b) omit
the `/api` prefix (e.g. `https://voiseadserver.com/track/impression?...`). To
make events actually record against the local server we rewrite scheme/host and
optionally re-add `/api`. Every rewrite is reported so the underlying URL bug
stays visible rather than being silently masked.
"""
from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlencode, urlsplit, urlunsplit

from app.config import Settings


def normalize_url(url: str, settings: Settings) -> Tuple[str, bool, Optional[str]]:
    """Return (normalized_url, was_rewritten, note)."""
    base = urlsplit(settings.ad_server_url)
    u = urlsplit(url)
    rewritten = False
    notes = []

    scheme = base.scheme
    netloc = base.netloc
    path = u.path

    if u.netloc and (u.scheme, u.netloc) != (base.scheme, base.netloc):
        rewritten = True
        notes.append(f"host {u.scheme}://{u.netloc} -> {base.scheme}://{base.netloc}")
    elif not u.netloc:
        # relative URL -> attach to configured base
        rewritten = True
        notes.append("relative URL anchored to base")

    if settings.tracking_prefix_fix and path.startswith("/track/"):
        path = "/api" + path
        rewritten = True
        notes.append("prefix /track -> /api/track")

    new_url = urlunsplit((scheme, netloc, path, u.query, u.fragment))
    return new_url, rewritten, ("; ".join(notes) if notes else None)


# --- Canonical tracking URL builders (used when we drive events ourselves) ----

def _q(base: str, path: str, params: dict) -> str:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    return f"{base}{path}?{urlencode(clean)}"


def impression_url(settings: Settings, aid: str, sid: str, trace_id: str, cpm: Optional[float] = None) -> str:
    return _q(settings.api_base, "/track/impression",
              {"aid": aid, "sid": sid, "trace_id": trace_id, "type": "sim", "cpm": cpm})


def click_url(settings: Settings, aid: str, sid: str, redirect: str, trace_id: str,
              li: Optional[str] = None, partner: Optional[str] = None) -> str:
    return _q(settings.api_base, "/track/click",
              {"aid": aid, "sid": sid, "redirect": redirect, "trace_id": trace_id,
               "li": li, "partner": partner})


def win_url(settings: Settings, price: float, aid: str, pub: str, trace_id: str,
            bid: Optional[str] = None, li: Optional[str] = None, partner: Optional[str] = None) -> str:
    return _q(settings.api_base, "/track/win",
              {"price": price, "aid": aid, "pub": pub, "trace_id": trace_id,
               "bid": bid, "li": li, "partner": partner})


def event_url(settings: Settings, e: str, aid: str, sid: str) -> str:
    return _q(settings.api_base, "/track/event", {"e": e, "aid": aid, "sid": sid})
