"""Mock DSP — a controllable OpenRTB bidder the ad server (SUT) fans out to.

WHAT A REAL DSP DOES (and what this mock emulates), per the IAB OpenRTB 2.5/2.6 spec:
  1. The exchange/ad server sends a `BidRequest` (POST JSON) with one or more `imp`
     objects (video/banner/native/audio), each carrying a `bidfloor` + `bidfloorcur`,
     plus `site`/`app`, `device` (geo/devicetype/ifa), `user`, `regs` (privacy), `source`
     (schain), and — for private deals — `imp.pmp.deals`.
  2. The DSP evaluates each impression against its campaigns/targeting/budget and its
     internal valuation, then EITHER:
       • bids: returns 200 with `seatbid[].bid[]` — each bid has `impid`, `price`,
         `adm`/`nurl`, `crid`, `adomain`, `cat`, `mtype`, `w`/`h`, optional `dealid`; OR
       • no-bids: returns bare **HTTP 204**, or `200 {id, nbr}` with a No-Bid Reason code.
  3. On win the exchange calls the bid's `nurl` (win notice) and later `burl` (billing);
     both may contain the `${AUCTION_PRICE}` clearing-price macro (+ `${AUCTION_ID}` /
     `${AUCTION_IMP_ID}` / cache-buster). Loss is signalled via `lurl`.

Refs: IAB OpenRTB 2.6 §4.2 (BidResponse/SeatBid/Bid), §5.24 (No-Bid Reason Codes),
Macros §4.4. See README → "Mock DSP".

This mock is mounted inside the simulator at `/dsp` (so the SUT posts to
`http://<sim>/dsp/bid`) and can also run standalone (`python -m app.dsp.router`).
Every bid request and the bid/no-bid decision are logged to the backend terminal.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("adsim.dsp")

# OpenRTB No-Bid Reason Codes (§5.24 / OpenRTB 2.5 List 5.24 values 0..10).
NBR = {
    0: "Unknown / other", 1: "Technical error", 2: "Invalid request",
    3: "Known web spider", 4: "Suspected non-human traffic",
    5: "Cloud/data-center/proxy IP", 6: "Unsupported device",
    7: "Blocked publisher/site", 8: "Unmatched user",
    9: "Daily reader cap met", 10: "Daily domain cap met",
}
_MTYPE = {"banner": 1, "video": 2, "audio": 3, "native": 4}
# OpenRTB 2.5 List 5.8 (bid.protocol for video/audio markup): 7 = VAST 4.0.
_VIDEO_PROTOCOL = 7

# Runtime-controllable behaviour (patched via POST /api/dsp/config or /dsp/config).
CONFIG: Dict[str, Any] = {
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
}

STATS: Dict[str, Any] = {
    "requests": 0, "bids": 0, "no_bids": 0, "timeouts": 0, "errors": 0,
    "total_bid_value": 0.0, "last_request": None, "last_response": None,
}

router = APIRouter()


# ----------------------------------------------------------------- creatives
def _vast_adm(crid: str, w: int, h: int) -> str:
    """A spec-valid VAST 4.2 InLine creative for a video bid (adm)."""
    return (
        '<VAST version="4.2"><Ad id="' + crid + '"><InLine>'
        '<AdSystem version="1.0">VoiseFakeDSP</AdSystem><AdTitle>Fake DSP Creative</AdTitle>'
        '<Impression><![CDATA[https://fakedsp-advertiser.com/imp?cb=[CACHEBUSTING]]]></Impression>'
        '<Creatives><Creative id="' + crid + '"><Linear><Duration>00:00:15</Duration>'
        '<TrackingEvents>'
        '<Tracking event="start"><![CDATA[https://fakedsp-advertiser.com/e?ev=start]]></Tracking>'
        '<Tracking event="firstQuartile"><![CDATA[https://fakedsp-advertiser.com/e?ev=q1]]></Tracking>'
        '<Tracking event="midpoint"><![CDATA[https://fakedsp-advertiser.com/e?ev=mid]]></Tracking>'
        '<Tracking event="thirdQuartile"><![CDATA[https://fakedsp-advertiser.com/e?ev=q3]]></Tracking>'
        '<Tracking event="complete"><![CDATA[https://fakedsp-advertiser.com/e?ev=complete]]></Tracking>'
        '</TrackingEvents>'
        '<VideoClicks><ClickThrough><![CDATA[https://fakedsp-advertiser.com/lp]]></ClickThrough></VideoClicks>'
        f'<MediaFiles><MediaFile delivery="progressive" type="video/mp4" width="{w}" height="{h}" '
        'bitrate="800"><![CDATA[https://fakedsp-advertiser.com/creative.mp4]]></MediaFile></MediaFiles>'
        '</Linear></Creative></Creatives></InLine></Ad></VAST>'
    )


def _banner_adm(w: int, h: int) -> str:
    return (f'<a href="https://fakedsp-advertiser.com/lp"><img src="https://fakedsp-advertiser.com/'
            f'banner_{w}x{h}.png" width="{w}" height="{h}"/></a>'
            '<img src="https://fakedsp-advertiser.com/imp?cb=[CACHEBUSTING]" width="0" height="0"/>')


def _imp_format(imp: Dict[str, Any]) -> Tuple[str, int, int]:
    """Return (kind, w, h) for an imp: video | banner | native | audio."""
    if "video" in imp:
        v = imp["video"] or {}
        return "video", int(v.get("w", 640)), int(v.get("h", 480))
    if "banner" in imp:
        b = imp["banner"] or {}
        if b.get("format"):
            f0 = b["format"][0] or {}
            return "banner", int(f0.get("w", 300)), int(f0.get("h", 250))
        return "banner", int(b.get("w", 300)), int(b.get("h", 250))
    if "native" in imp:
        return "native", 0, 0
    if "audio" in imp:
        return "audio", 0, 0
    return "banner", 0, 0


# ----------------------------------------------------------------- valuation
def _value_imp(imp: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[Optional[float], str]:
    """Return (bid_price, reason). bid_price is None => no-bid on this imp."""
    floor = float(imp.get("bidfloor") or 0.0)
    base = float(cfg["price"])
    valuation = min(float(cfg["max_cpm"]), max(base, floor * float(cfg["bid_margin"])))
    jitter = 1.0 + random.uniform(-float(cfg["jitter"]), float(cfg["jitter"]))
    price = round(valuation * jitter, 4)
    if cfg["respect_floor"] and price < floor:
        return None, f"valuation {price} below floor {floor}"
    if price <= 0:
        return None, "zero valuation"
    return price, f"valued at {price} (floor {floor})"


def _deal_for(imp: Dict[str, Any]) -> Optional[str]:
    """If the imp carries a private-marketplace deal we recognise, echo its id."""
    pmp = imp.get("pmp") or {}
    for d in pmp.get("deals", []) or []:
        if d.get("id"):
            return d["id"]        # a real DSP would match against booked deals
    return None


def _build_bid(req_id: str, imp: Dict[str, Any], price: float, cfg: Dict[str, Any]) -> Dict[str, Any]:
    kind, w, h = _imp_format(imp)
    crid = str(cfg["crid"])
    adm = _vast_adm(crid, w or 640, h or 480) if kind in ("video", "audio") else _banner_adm(w or 300, h or 250)
    # Notice URLs use ONLY OpenRTB §4.4 macros (${...}); the exchange never
    # substitutes VAST [CACHEBUSTING] here. Cache-busting is a DSP-generated
    # nonce; the VAST [CACHEBUSTING] macro lives inside the adm (correct there).
    cb = random.randint(10_000_000, 99_999_999)
    nurl = (f"https://fakedsp-advertiser.com/win?price=${{AUCTION_PRICE}}"
            f"&aid=${{AUCTION_ID}}&impid=${{AUCTION_IMP_ID}}&seat=${{AUCTION_SEAT_ID}}&cb={cb}")
    bid = {
        "id": f"{req_id}-{imp.get('id', '1')}",
        "impid": str(imp.get("id", "1")),
        "price": price,
        "adm": adm,
        "nurl": nurl,
        "burl": f"https://fakedsp-advertiser.com/billing?price=${{AUCTION_PRICE}}&cb={cb}",
        "lurl": "https://fakedsp-advertiser.com/loss?reason=${AUCTION_LOSS}",
        "adid": crid,
        "cid": "fake-dsp-campaign-1",
        "crid": crid,
        # iurl: non-cache-busted preview image for ad-quality/safety checks (§4.2.3).
        "iurl": "https://fakedsp-advertiser.com/preview.png",
        "adomain": list(cfg["adomain"]),
        "cat": list(cfg["cat"]),
        "mtype": _MTYPE.get(kind, 1),   # OpenRTB 2.6 markup type (dual-compat)
        "w": w,
        "h": h,
    }
    # Video/audio: advertise the markup protocol per OpenRTB 2.5 §4.2.3 (List 5.8).
    if kind in ("video", "audio"):
        bid["protocol"] = _VIDEO_PROTOCOL
    deal = _deal_for(imp)
    if deal:
        bid["dealid"] = deal
    return bid


# ----------------------------------------------------------------- logging
def _summarize_request(body: Dict[str, Any]) -> Dict[str, Any]:
    imps = body.get("imp") or []
    dev = body.get("device") or {}
    inv = "app" if body.get("app") else "site"
    inv_obj = body.get(inv) or {}
    fmts = []
    for imp in imps:
        kind, w, h = _imp_format(imp)
        fmts.append(f"{kind} {w}x{h} floor={float(imp.get('bidfloor') or 0):.2f}")
    regs_ext = (body.get("regs") or {}).get("ext") or {}
    return {
        "id": body.get("id"), "imp_count": len(imps), "formats": fmts,
        "inventory": f"{inv} {inv_obj.get('domain') or inv_obj.get('bundle') or inv_obj.get('id', '?')}",
        "device": f"type={dev.get('devicetype')} geo={(dev.get('geo') or {}).get('country', '?')} ifa={dev.get('ifa', '-')}",
        "privacy": f"gdpr={regs_ext.get('gdpr', '-')} usp={regs_ext.get('us_privacy', '-')} gpp={'y' if regs_ext.get('gpp') else '-'}",
        "schain": "y" if ((body.get("source") or {}).get("ext") or {}).get("schain") else "-",
    }


def _log_decision(req: Dict[str, Any], decision: Dict[str, Any]) -> None:
    if not CONFIG.get("verbose"):
        return
    bar = "=" * 66
    sep = "-" * 66
    lines = [
        "",
        bar,
        "  MOCK DSP  <--  OpenRTB bid request",
        sep,
        f"  request id : {req['id']}",
        f"  imps       : {req['imp_count']}  [{'; '.join(req['formats'])}]",
        f"  inventory  : {req['inventory']}",
        f"  device     : {req['device']}",
        f"  privacy    : {req['privacy']}   schain={req['schain']}",
        sep,
    ]
    if decision["type"] == "bid":
        lines.append(f"  DECISION   : BID   seat={decision['seat']}  cur={decision['cur']}")
        for b in decision["bids"]:
            lines.append(f"    bid impid={b['impid']}  ${b['price']} {decision['cur']}  "
                         f"mtype={b['mtype']}  crid={b['crid']}  adomain={b['adomain']}"
                         + (f"  dealid={b['dealid']}" if b.get('dealid') else ""))
        lines.append(f"    nurl     : {decision['bids'][0]['nurl']}")
    elif decision["type"] == "no_bid":
        nbr = decision.get("nbr")
        nbr_txt = f"nbr={nbr} ({NBR.get(nbr, '?')})" if nbr is not None else "HTTP 204 (no body)"
        lines.append(f"  DECISION   : NO-BID   {nbr_txt}   reason=\"{decision.get('reason', '')}\"")
    else:
        lines.append(f"  DECISION   : {decision['type'].upper()}   {decision.get('reason', '')}")
    lines.append(bar)
    logger.info("\n".join(lines))


# ----------------------------------------------------------------- endpoints
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
    STATS.update(requests=0, bids=0, no_bids=0, timeouts=0, errors=0,
                 total_bid_value=0.0, last_request=None, last_response=None)
    return STATS


def _no_bid_response(req_id: str, reason: str, nbr: int = 0) -> Response:
    STATS["no_bids"] += 1
    if CONFIG.get("emit_nbr"):
        # §7.1 canonical "no-bid with reason": {id, seatbid:[], nbr}.
        body = {"id": req_id, "seatbid": [], "nbr": nbr, "cur": CONFIG["currency"]}
        STATS["last_response"] = {"decision": "no_bid", "nbr": nbr, "reason": reason}
        return Response(status_code=200, content=json.dumps(body), media_type="application/json")
    STATS["last_response"] = {"decision": "no_bid", "http": 204, "reason": reason}
    return Response(status_code=204)


@router.api_route("/bid", methods=["POST"])
@router.api_route("/bid/{tag_id}", methods=["POST"])
async def dsp_bid(request: Request, tag_id: str = "") -> Response:
    STATS["requests"] += 1
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        # §2.1: a malformed/corrupt payload should return HTTP 400 with no content.
        STATS["errors"] += 1
        logger.info("MOCK DSP  <--  malformed bid request -> HTTP 400")
        return Response(status_code=400)
    if not isinstance(body, dict):
        STATS["errors"] += 1
        return Response(status_code=400)
    req_id = str(body.get("id", "unknown"))
    summary = _summarize_request(body)
    STATS["last_request"] = summary

    mode = CONFIG["mode"]
    if mode == "timeout":
        STATS["timeouts"] += 1
        _log_decision(summary, {"type": "timeout", "reason": f"sleeping {CONFIG['timeout_ms']}ms"})
        await asyncio.sleep(max(0.0, float(CONFIG["timeout_ms"]) / 1000.0))
        return _no_bid_response(req_id, "timeout", nbr=1)
    if mode == "error":
        STATS["errors"] += 1
        _log_decision(summary, {"type": "error", "reason": "forced 500"})
        return Response(status_code=500, content='{"error":"fake dsp forced error"}',
                        media_type="application/json")
    if mode == "no_bid":
        _log_decision(summary, {"type": "no_bid", "nbr": 0, "reason": "configured mode=no_bid"})
        return _no_bid_response(req_id, "configured mode=no_bid", nbr=0)
    if random.random() > float(CONFIG["bid_rate"]):
        _log_decision(summary, {"type": "no_bid", "nbr": 0, "reason": "lost internal bid throttle (bid_rate)"})
        return _no_bid_response(req_id, "bid_rate throttle", nbr=0)

    imps = body.get("imp") or []
    if not imps:
        _log_decision(summary, {"type": "no_bid", "nbr": 2, "reason": "no imp in request"})
        return _no_bid_response(req_id, "no imp", nbr=2)

    bids: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for imp in imps:
        price, reason = _value_imp(imp, CONFIG)
        if price is None:
            skipped.append(reason)
            continue
        bids.append(_build_bid(req_id, imp, price, CONFIG))

    if not bids:
        _log_decision(summary, {"type": "no_bid", "nbr": 0,
                                "reason": "; ".join(skipped) or "no eligible imp"})
        return _no_bid_response(req_id, "; ".join(skipped) or "no eligible imp", nbr=0)

    payload = {
        "id": req_id,
        "bidid": f"{req_id}-resp",
        "cur": CONFIG["currency"],
        "seatbid": [{"seat": CONFIG["seat"], "group": 0, "bid": bids}],
    }
    STATS["bids"] += 1
    STATS["total_bid_value"] = round(STATS["total_bid_value"] + sum(b["price"] for b in bids), 4)
    STATS["last_response"] = {"decision": "bid", "seat": CONFIG["seat"],
                              "prices": [b["price"] for b in bids]}
    _log_decision(summary, {"type": "bid", "seat": CONFIG["seat"], "cur": CONFIG["currency"], "bids": bids})
    return Response(status_code=200, content=json.dumps(payload), media_type="application/json")


def create_dsp_app():
    """Standalone ASGI app (run the DSP as its own process)."""
    from fastapi import FastAPI
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title="Voise Mock DSP", version="1.0.0")
    app.include_router(router, prefix="/dsp")
    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    logger.info("Starting standalone Mock DSP on :8095 (POST /dsp/bid)")
    uvicorn.run(create_dsp_app(), host="0.0.0.0", port=8095)
