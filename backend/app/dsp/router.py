"""Fake DSP — a controllable OpenRTB bidder endpoint (build prompt §4.4).

The SUT's auction (`POST /api/b/{tag_id}`) fans out to demand partners by their
`endpoint_url`. With no real DSP it always no-bids, so OpenRTB conformance (S10)
and any auction/economic behaviour can't be exercised. This module is a tiny DSP
the simulator seeds as a demand partner so the SUT has something to win.

It is mounted inside the simulator app at `/dsp` (so its URL is e.g.
`http://localhost:8090/dsp/bid`) AND can run standalone (`python -m app.dsp.router`).

Behaviour is controllable at runtime via `POST /dsp/config`:
  mode         : "bid" | "no_bid" | "timeout" | "error"
  price        : winning CPM to return (default 6.50)
  bid_rate     : probability of bidding when mode="bid" (default 1.0)
  timeout_ms   : sleep before responding when mode="timeout" (default 2000)
  seat/adomain/crid/cat : creative metadata echoed in the bid
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict

from fastapi import APIRouter, Request, Response

# Module-level mutable config (single fake DSP instance per process).
CONFIG: Dict[str, Any] = {
    "mode": "bid",
    "price": 6.50,
    "bid_rate": 1.0,
    "timeout_ms": 2000,
    "seat": "voise-fake-dsp",
    "adomain": ["fakedsp-advertiser.com"],
    "crid": "fake-dsp-creative-1",
    "cat": ["IAB1"],
}

STATS: Dict[str, int] = {"requests": 0, "bids": 0, "no_bids": 0, "timeouts": 0, "errors": 0}

router = APIRouter()


def _vast_adm(price: float, crid: str) -> str:
    """A minimal but spec-valid VAST 4.2 InLine the SUT can return as bid.adm."""
    return (
        '<VAST version="4.2"><Ad id="' + crid + '"><InLine>'
        '<AdSystem version="1.0">VoiseFakeDSP</AdSystem>'
        '<AdTitle>Fake DSP Creative</AdTitle>'
        '<Impression><![CDATA[https://fakedsp-advertiser.com/imp?cb=[CACHEBUSTING]]]></Impression>'
        '<Creatives><Creative id="' + crid + '"><Linear>'
        '<Duration>00:00:15</Duration>'
        '<TrackingEvents>'
        '<Tracking event="start"><![CDATA[https://fakedsp-advertiser.com/e?ev=start]]></Tracking>'
        '<Tracking event="firstQuartile"><![CDATA[https://fakedsp-advertiser.com/e?ev=q1]]></Tracking>'
        '<Tracking event="midpoint"><![CDATA[https://fakedsp-advertiser.com/e?ev=mid]]></Tracking>'
        '<Tracking event="thirdQuartile"><![CDATA[https://fakedsp-advertiser.com/e?ev=q3]]></Tracking>'
        '<Tracking event="complete"><![CDATA[https://fakedsp-advertiser.com/e?ev=complete]]></Tracking>'
        '</TrackingEvents>'
        '<VideoClicks><ClickThrough><![CDATA[https://fakedsp-advertiser.com/lp]]></ClickThrough></VideoClicks>'
        '<MediaFiles><MediaFile delivery="progressive" type="video/mp4" width="640" height="480" '
        'bitrate="800"><![CDATA[https://fakedsp-advertiser.com/creative.mp4]]></MediaFile></MediaFiles>'
        '</Linear></Creative></Creatives></InLine></Ad></VAST>'
    )


@router.get("/health")
async def dsp_health() -> Dict[str, Any]:
    return {"ok": True, "config": CONFIG, "stats": STATS}


@router.get("/config")
async def dsp_get_config() -> Dict[str, Any]:
    return CONFIG


@router.post("/config")
async def dsp_set_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in (patch or {}).items():
        if k in CONFIG:
            CONFIG[k] = v
    return CONFIG


@router.post("/reset")
async def dsp_reset() -> Dict[str, Any]:
    for k in STATS:
        STATS[k] = 0
    return STATS


@router.api_route("/bid", methods=["POST"])
@router.api_route("/bid/{tag_id}", methods=["POST"])
async def dsp_bid(request: Request, tag_id: str = "") -> Response:
    STATS["requests"] += 1
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    mode = CONFIG["mode"]
    if mode == "timeout":
        STATS["timeouts"] += 1
        await asyncio.sleep(max(0.0, float(CONFIG["timeout_ms"]) / 1000.0))
        # respond after the delay; the SUT will likely have abandoned us.
    if mode == "error":
        STATS["errors"] += 1
        return Response(status_code=500, content='{"error":"fake dsp forced error"}',
                        media_type="application/json")
    if mode == "no_bid" or (mode == "bid" and random.random() > float(CONFIG["bid_rate"])):
        STATS["no_bids"] += 1
        return Response(status_code=204)

    imps = body.get("imp") or [{}]
    impid = (imps[0] or {}).get("id", "1")
    req_id = body.get("id", "unknown")
    price = float(CONFIG["price"])
    crid = str(CONFIG["crid"])
    bid = {
        "id": f"{req_id}-bid-1",
        "impid": impid,
        "price": price,
        "adm": _vast_adm(price, crid),
        "nurl": f"https://fakedsp-advertiser.com/win?price=${{AUCTION_PRICE}}&cb=[CACHEBUSTING]",
        "burl": "https://fakedsp-advertiser.com/billing?cb=[CACHEBUSTING]",
        "crid": crid,
        "adomain": list(CONFIG["adomain"]),
        "cat": list(CONFIG["cat"]),
        "w": (imps[0].get("video", {}) or imps[0].get("banner", {}) or {}).get("w", 640),
        "h": (imps[0].get("video", {}) or imps[0].get("banner", {}) or {}).get("h", 480),
    }
    STATS["bids"] += 1
    import json
    payload = {"id": req_id, "seatbid": [{"seat": CONFIG["seat"], "bid": [bid]}], "cur": "USD"}
    return Response(status_code=200, content=json.dumps(payload), media_type="application/json")


def create_dsp_app():
    """Standalone ASGI app (for running the DSP as its own process)."""
    from fastapi import FastAPI
    app = FastAPI(title="Voise Fake DSP", version="1.0.0")
    app.include_router(router, prefix="/dsp")
    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run(create_dsp_app(), host="0.0.0.0", port=8095)
