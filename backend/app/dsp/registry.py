"""Registry of independently-configurable mock DSPs.

`dsp-1` is the original single fake DSP (see `app.dsp.router`), kept reachable at
its historical fixed paths (`/dsp/bid`, `/dsp/config`, ...) for backward
compatibility. Any additional DSP created here (via the dashboard's DSP Settings
tab, or `POST /dsps`) gets its own isolated config/stats and is reachable at
`/dsps/{dsp_id}/bid` (see `app.dsp.multi`), so multiple mock bidders can compete
in the same real-ad-server auction — point a second demand partner's
endpoint_url at the new DSP's URL to test a multi-DSP auction end-to-end.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Optional

from fastapi import HTTPException

# The original single-DSP config shape (unchanged from the historical `CONFIG`
# dict) — `dsp-1` is seeded from this literal so its defaults (seat, crid, ...)
# stay byte-for-byte identical to before this file existed.
_DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "bid",            # bid | no_bid | timeout | error
    "price": 6.50,            # base CPM the DSP is willing to pay
    "bid_rate": 1.0,          # probability of bidding when eligible (win-rate sim)
    "timeout_ms": 2000,       # delay before responding when mode="timeout"
    "seat": "voise-fake-dsp",
    "adomain": ["fakedsp-advertiser.com"],
    "crid": "fake-dsp-creative-1",
    "cat": ["IAB1"],
    # --- valuation / floor handling ---
    "currency": "USD",
    "bid_margin": 1.20,       # bid at least floor * margin (so we clear the floor)
    "max_cpm": 25.0,          # valuation ceiling
    "jitter": 0.10,           # +/- price randomisation to look realistic
    "respect_floor": True,    # if our valuation < bidfloor -> no-bid on that imp
    "emit_nbr": True,         # no-bid as 200 {nbr} (True) or bare 204 (False)
    "verbose": True,          # log every request + response to the terminal
    # --- creative / tracking (a REAL, watchable ad) ---
    "video_url": "https://samplefile.com/samples/download/video/mp4/mp4_15s_sample_file_868KB.mp4",
    "video_w": 640,
    "video_h": 360,
    "video_bitrate": 463,
    "video_duration": "00:00:15",
    "advertiser_name": "Voise Fake Advertiser",
    "landing_url": "https://voisetech.com/",
    "track_base": "http://localhost:8090",
    # --- response identity + notice URLs ---
    "campaign_id": "fake-dsp-campaign-1",
    "iurl": "https://fakedsp-advertiser.com/preview.png",
    "nurl_template": ("https://fakedsp-advertiser.com/win?price=${AUCTION_PRICE}"
                      "&aid=${AUCTION_ID}&impid=${AUCTION_IMP_ID}&seat=${AUCTION_SEAT_ID}&cb=[CB]"),
    "burl_template": "https://fakedsp-advertiser.com/billing?price=${AUCTION_PRICE}&cb=[CB]",
    "lurl_template": "https://fakedsp-advertiser.com/loss?reason=${AUCTION_LOSS}",
    "nbr_code": 0,
    # --- Advanced: full custom BidResponse template override ---
    "custom_response": None,
}


def _default_config() -> Dict[str, Any]:
    return copy.deepcopy(_DEFAULT_CONFIG)


def _default_stats() -> Dict[str, Any]:
    return {
        "requests": 0, "bids": 0, "no_bids": 0, "timeouts": 0, "errors": 0,
        "total_bid_value": 0.0, "last_request": None, "last_response": None,
        "tracked": {}, "last_tracked": None,
    }


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "dsp"


def _next_letter_name() -> str:
    n = len(DSPS)
    return f"DSP {chr(65 + n)}" if n < 26 else f"DSP {n + 1}"


# id -> {"id", "name", "config", "stats"}
DSPS: Dict[str, Dict[str, Any]] = {}


def _register(dsp_id: str, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    entry = {"id": dsp_id, "name": name, "config": config, "stats": _default_stats()}
    DSPS[dsp_id] = entry
    return entry


# Seed the original default DSP — unmodified template, fixed id, so `router.py`'s
# CONFIG/STATS (and everything importing them) keep behaving exactly as before.
_register("dsp-1", "DSP A", _default_config())


def create_dsp(name: Optional[str] = None, dsp_id: Optional[str] = None) -> Dict[str, Any]:
    """Register a new, independently-configurable mock DSP and return its entry."""
    name = (name or "").strip() or _next_letter_name()
    base_id = _slugify(dsp_id or name)
    candidate, i = base_id, 1
    while candidate in DSPS:
        i += 1
        candidate = f"{base_id}-{i}"
    cfg = _default_config()
    # Distinguish this DSP's bids from dsp-1 (and from each other) out of the box.
    cfg["seat"] = f"voise-fake-dsp-{candidate}"
    cfg["crid"] = f"fake-dsp-creative-{candidate}"
    cfg["campaign_id"] = f"fake-dsp-campaign-{candidate}"
    return _register(candidate, name, cfg)


def delete_dsp(dsp_id: str) -> None:
    if dsp_id == "dsp-1":
        raise HTTPException(status_code=400, detail="Cannot remove the default DSP (dsp-1)")
    if dsp_id not in DSPS:
        raise HTTPException(status_code=404, detail=f"Unknown dsp_id '{dsp_id}'")
    del DSPS[dsp_id]


def get_dsp(dsp_id: str) -> Dict[str, Any]:
    entry = DSPS.get(dsp_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown dsp_id '{dsp_id}'")
    return entry
