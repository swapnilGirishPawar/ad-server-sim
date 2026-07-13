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
    # --- creative / tracking (a REAL, watchable ad) ---
    # A public sample MP4 so the ad actually plays in any VAST viewer. Small
    # 15s/868KB sample clip (lighter than the old ones for faster load in tests).
    # Override at runtime via POST /dsp/config if you prefer another.
    "video_url": "https://samplefile.com/samples/download/video/mp4/mp4_15s_sample_file_868KB.mp4",
    "video_w": 640,
    "video_h": 360,
    "video_bitrate": 463,
    "video_duration": "00:00:15",
    "advertiser_name": "Voise Fake Advertiser",
    "landing_url": "https://voisetech.com/",
    # Base URL where THIS mock DSP is reachable, used to build Impression/tracking
    # pixels that can actually be recorded (GET /dsp/track). Fired server-side by
    # the simulator; set to a public/tunnel URL if you want a browser player to hit it.
    "track_base": "http://localhost:8090",
    # --- response identity + notice URLs (previously hardcoded in _build_bid) ---
    # `[CB]` in a template is replaced with a fresh cache-buster nonce per bid.
    # `${AUCTION_*}` are OpenRTB §4.4 macros the EXCHANGE substitutes on win — kept literal.
    "campaign_id": "fake-dsp-campaign-1",
    "iurl": "https://fakedsp-advertiser.com/preview.png",
    "nurl_template": ("https://fakedsp-advertiser.com/win?price=${AUCTION_PRICE}"
                      "&aid=${AUCTION_ID}&impid=${AUCTION_IMP_ID}&seat=${AUCTION_SEAT_ID}&cb=[CB]"),
    "burl_template": "https://fakedsp-advertiser.com/billing?price=${AUCTION_PRICE}&cb=[CB]",
    "lurl_template": "https://fakedsp-advertiser.com/loss?reason=${AUCTION_LOSS}",
    # OpenRTB No-Bid Reason code returned when mode="no_bid" (0..10, see NBR above).
    "nbr_code": 0,
    # --- Advanced: full custom BidResponse template. When set to a non-empty object,
    #     the DSP returns THIS (in bid mode) instead of the auto-built bid, substituting
    #     the macros {{price}} {{impid}} {{id}} {{crid}} {{seat}} {{cur}}. A quoted
    #     "{{price}}" becomes a JSON number. null/empty => normal auto-built bid. ---
    "custom_response": None,
}

STATS: Dict[str, Any] = {
    "requests": 0, "bids": 0, "no_bids": 0, "timeouts": 0, "errors": 0,
    "total_bid_value": 0.0, "last_request": None, "last_response": None,
    # Impression/quartile/click pixels this advertiser has RECEIVED (via /dsp/track).
    "tracked": {}, "last_tracked": None,
}

# 1x1 transparent GIF returned by the /dsp/track pixel.
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01"
    b"\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)

router = APIRouter()


# ----------------------------------------------------------------- creatives
def _track_px(event: str, crid: str) -> str:
    """A CDATA-wrapped, reachable tracking pixel URL for this advertiser's /dsp/track sink."""
    base = str(CONFIG["track_base"]).rstrip("/")
    return f"<![CDATA[{base}/dsp/track?ev={event}&crid={crid}&cb=[CACHEBUSTING]]]>"


def _vast_adm(crid: str, w: int, h: int) -> str:
    """A spec-valid, PLAYABLE VAST 4.2 InLine creative (adm).

    Uses a real public MP4 (CONFIG['video_url']) so the ad plays in any VAST
    viewer, and points every Impression/quartile/click pixel at this mock DSP's
    reachable /dsp/track sink so the hits can actually be recorded and counted.
    """
    cfg = CONFIG
    vw, vh = int(cfg["video_w"]), int(cfg["video_h"])
    base = str(cfg["track_base"]).rstrip("/")
    return (
        '<VAST version="4.2"><Ad id="' + crid + '"><InLine>'
        '<AdSystem version="1.0">VoiseFakeDSP</AdSystem>'
        '<AdTitle>' + str(cfg["advertiser_name"]) + '</AdTitle>'
        '<Impression id="fakedsp">' + _track_px("impression", crid) + '</Impression>'
        f'<Error><![CDATA[{base}/dsp/track?ev=error&crid={crid}&code=[ERRORCODE]]]></Error>'
        '<Creatives><Creative id="' + crid + '" sequence="1">'
        '<UniversalAdId idRegistry="fakedsp.com">' + crid + '</UniversalAdId>'
        '<Linear><Duration>' + str(cfg["video_duration"]) + '</Duration>'
        '<TrackingEvents>'
        '<Tracking event="start">' + _track_px("start", crid) + '</Tracking>'
        '<Tracking event="firstQuartile">' + _track_px("firstQuartile", crid) + '</Tracking>'
        '<Tracking event="midpoint">' + _track_px("midpoint", crid) + '</Tracking>'
        '<Tracking event="thirdQuartile">' + _track_px("thirdQuartile", crid) + '</Tracking>'
        '<Tracking event="complete">' + _track_px("complete", crid) + '</Tracking>'
        '</TrackingEvents>'
        '<VideoClicks>'
        '<ClickThrough id="fakedsp"><![CDATA[' + str(cfg["landing_url"]) + ']]></ClickThrough>'
        '<ClickTracking>' + _track_px("click", crid) + '</ClickTracking>'
        '</VideoClicks>'
        '<MediaFiles>'
        f'<MediaFile delivery="progressive" type="video/mp4" width="{vw}" height="{vh}" '
        f'bitrate="{int(cfg["video_bitrate"])}" scalable="true" maintainAspectRatio="true">'
        '<![CDATA[' + str(cfg["video_url"]) + ']]></MediaFile>'
        '</MediaFiles>'
        '</Linear></Creative></Creatives></InLine></Ad></VAST>'
    )


def _banner_adm(w: int, h: int) -> str:
    base = str(CONFIG["track_base"]).rstrip("/")
    lp = str(CONFIG["landing_url"])
    return (
        f'<a href="{lp}" target="_blank" rel="noopener"><img '
        f'src="https://dummyimage.com/{w}x{h}/2b6cb0/ffffff.png&text=Voise+Fake+Ad" '
        f'width="{w}" height="{h}" border="0" alt="Voise Fake Ad"/></a>'
        f'<img src="{base}/dsp/track?ev=impression&cb=[CACHEBUSTING]" '
        f'width="1" height="1" style="display:none" alt=""/>'
    )


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
    # Notice URLs come from the (configurable) templates. `[CB]` is a DSP-generated
    # cache-buster nonce substituted here; the `${AUCTION_*}` OpenRTB §4.4 macros are
    # left literal for the exchange to substitute on win. (VAST [CACHEBUSTING] lives
    # inside the adm, which is correct there.)
    cb = str(random.randint(10_000_000, 99_999_999))

    def _fill(t: Any) -> str:
        return str(t).replace("[CB]", cb)

    bid = {
        "id": f"{req_id}-{imp.get('id', '1')}",
        "impid": str(imp.get("id", "1")),
        "price": price,
        "adm": adm,
        "nurl": _fill(cfg["nurl_template"]),
        "burl": _fill(cfg["burl_template"]),
        "lurl": _fill(cfg["lurl_template"]),
        "adid": crid,
        "cid": str(cfg["campaign_id"]),
        "crid": crid,
        # iurl: non-cache-busted preview image for ad-quality/safety checks (§4.2.3).
        "iurl": str(cfg["iurl"]),
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
                 total_bid_value=0.0, last_request=None, last_response=None,
                 tracked={}, last_tracked=None)
    return STATS


@router.get("/track")
async def dsp_track(request: Request) -> Response:
    """Impression/quartile/click sink for this advertiser's own creative pixels.

    The VAST built by _vast_adm points its <Impression>/<Tracking>/<ClickTracking>
    here, so when the ad is 'played' (server-side by the simulator, or by any
    player that can reach this host) the hit is counted per event. Returns a 1x1
    GIF so it also works as a plain <img> pixel."""
    params = dict(request.query_params)
    ev = params.get("ev", "unknown")
    STATS["tracked"][ev] = STATS["tracked"].get(ev, 0) + 1
    STATS["last_tracked"] = {"ev": ev, "params": params}
    if CONFIG.get("verbose"):
        logger.info("  MOCK DSP (advertiser)  <--  TRACKER FIRED  ev=%s  %s", ev, params)
    return Response(content=_PIXEL_GIF, media_type="image/gif",
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})


@router.get("/vast")
async def dsp_vast(request: Request) -> Response:
    """Serve the advertiser's VAST creative directly as a tag URL.

    Handy for VAST inspectors/players that accept a tag URL (that can reach this
    host). The creative is self-contained with a public MP4, so it also plays when
    the XML is pasted into a viewer."""
    crid = str(CONFIG["crid"])
    w = int(request.query_params.get("w", CONFIG["video_w"]))
    h = int(request.query_params.get("h", CONFIG["video_h"]))
    xml = _vast_adm(crid, w, h)
    return Response(content=xml, media_type="application/xml",
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"})


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
        _nbr = int(CONFIG.get("nbr_code", 0) or 0)
        _log_decision(summary, {"type": "no_bid", "nbr": _nbr, "reason": "configured mode=no_bid"})
        return _no_bid_response(req_id, "configured mode=no_bid", nbr=_nbr)
    if random.random() > float(CONFIG["bid_rate"]):
        _log_decision(summary, {"type": "no_bid", "nbr": 0, "reason": "lost internal bid throttle (bid_rate)"})
        return _no_bid_response(req_id, "bid_rate throttle", nbr=0)

    imps = body.get("imp") or []
    if not imps:
        _log_decision(summary, {"type": "no_bid", "nbr": 2, "reason": "no imp in request"})
        return _no_bid_response(req_id, "no imp", nbr=2)

    # Advanced: a full custom response template overrides the auto-built bid (bid mode).
    # Macros: quoted "{{price}}" -> JSON number; {{price}}/{{impid}}/{{id}}/{{crid}}/
    # {{seat}}/{{cur}} substituted as strings. Falls back to the auto bid on any error.
    custom = CONFIG.get("custom_response")
    if custom:
        try:
            price0, reason0 = _value_imp(imps[0], CONFIG)
            if price0 is None:
                _nbr = int(CONFIG.get("nbr_code", 0) or 0)
                _log_decision(summary, {"type": "no_bid", "nbr": _nbr, "reason": reason0})
                return _no_bid_response(req_id, reason0, nbr=_nbr)
            s = json.dumps(custom).replace('"{{price}}"', json.dumps(price0))
            for tok, val in (("{{price}}", str(price0)), ("{{impid}}", str(imps[0].get("id", "1"))),
                             ("{{id}}", req_id), ("{{crid}}", str(CONFIG["crid"])),
                             ("{{seat}}", str(CONFIG["seat"])), ("{{cur}}", str(CONFIG["currency"]))):
                s = s.replace(tok, val)
            resp = json.loads(s)
            if isinstance(resp, dict):
                resp.setdefault("id", req_id)
            STATS["bids"] += 1
            STATS["total_bid_value"] = round(STATS["total_bid_value"] + float(price0), 4)
            STATS["last_response"] = {"decision": "bid_custom", "prices": [price0]}
            _log_decision(summary, {"type": "bid", "seat": CONFIG["seat"], "cur": CONFIG["currency"],
                                    "bids": [{"impid": str(imps[0].get("id", "1")), "price": price0,
                                              "mtype": "custom", "crid": str(CONFIG["crid"]),
                                              "adomain": list(CONFIG["adomain"]), "nurl": "(custom template)"}]})
            return Response(status_code=200, content=json.dumps(resp), media_type="application/json")
        except Exception as e:  # noqa: BLE001 — a bad template must never crash the DSP
            logger.warning("MOCK DSP custom_response failed (%s); falling back to auto-built bid", e)

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
