"""OpenRTB 2.5 / 2.6 bid-request builder and bid-response parser.

The target server's OpenRTB endpoint (`POST /api/b/{tag_id}` == `/ortb/bid/{tag_id}`)
fans out to configured demand partners. We build spec-correct 2.5/2.6 requests —
including `regs` privacy signals, `source.ext.schain` (SupplyChain), app/site +
device identifiers, and optional 2.6 video pods — so the RTB plumbing and the
SUT's passthrough/auction behaviour are properly exercised and measured.

Spec: IAB OpenRTB 2.5 §3.2 (BidRequest) and 2.6 §3.2.7 (pods), Appendix A.2 (sChain).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

# alpha-2 (our traffic dimension) -> alpha-3 (OpenRTB device.geo.country)
_ISO3 = {"IN": "IND", "US": "USA", "UK": "GBR", "GB": "GBR", "CA": "CAN", "AU": "AUS", "DE": "DEU"}
# OpenRTB device types (2.6 Table: 1 mobile/tablet,2 pc,3 connected tv,4 phone,5 tablet,7 set top box)
_DEVICE_TYPE = {"mobile": 4, "phone": 4, "tablet": 5, "desktop": 2, "pc": 2, "ctv": 3, "tv": 3}

_SCHAIN_ASI = "voisetech.com"
_DEFAULT_BCAT = ["IAB26"]
_DEFAULT_TMAX = 660
_DEFAULT_BIDFLOOR = 5.775

# VoiseTech inbound CTV bid-request template (Supply → VoiseTech).
_CTV_VIDEO: Dict[str, Any] = {
    "mimes": ["video/mp4"],
    "minduration": 3,
    "maxduration": 300,
    "startdelay": 0,
    "protocols": [1, 2, 3, 4, 5, 6],
    "linearity": 1,
    "sequence": 1,
    "boxingallowed": 1,
    "playbackmethod": [1],
    "api": [1, 2],
}
_CTV_APP: Dict[str, Any] = {
    "id": "9887674",
    "name": "Philo: Shows, Movies, and Live TV",
    "bundle": "G22223020133",
    "storeurl": "https://samsung.com/us/appstore/app/G22223020133",
    "cat": ["IAB4", "IAB5", "IAB2", "IAB3", "IAB1"],
    "content": {
        "genre": "Adventure",
        "cat": ["IAB1-5"],
        "videoquality": 1,
        "context": 1,
        "contentrating": "TV-MA",
        "livestream": 0,
        "len": 1380,
        "language": "en",
    },
}
_CTV_DEVICE: Dict[str, Any] = {
    "ua": (
        "Mozilla/5.0 (SMART-TV; LINUX; Tizen 6.0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) 76.0.3809.146/6.0 TV Safari/537.36"
    ),
    "ip": "132.147.164.4",
    "make": "Samsung",
    "model": "UN70TU6985FXZA",
    "os": "Tizen",
    "osv": "6.0",
    "js": 1,
    "language": "en",
    "carrier": "Nextlink Broadband",
    "connectiontype": 2,
    "ext": {"ifa_type": "tifa"},
}
_GEO_BY_COUNTRY: Dict[str, Dict[str, Any]] = {
    "US": {
        "lat": 32.9074, "lon": -97.4257, "type": 2, "country": "USA",
        "region": "TX", "city": "Fort Worth", "zip": "76179",
    },
    "IN": {"lat": 28.6139, "lon": 77.2090, "type": 2, "country": "IND", "region": "DL", "city": "New Delhi"},
    "UK": {"lat": 51.5074, "lon": -0.1278, "type": 2, "country": "GBR", "region": "ENG", "city": "London"},
    "GB": {"lat": 51.5074, "lon": -0.1278, "type": 2, "country": "GBR", "region": "ENG", "city": "London"},
    "CA": {"lat": 43.6532, "lon": -79.3832, "type": 2, "country": "CAN", "region": "ON", "city": "Toronto"},
    "DE": {"lat": 52.5200, "lon": 13.4050, "type": 2, "country": "DEU", "region": "BE", "city": "Berlin"},
    "AU": {"lat": -33.8688, "lon": 151.2093, "type": 2, "country": "AUS", "region": "NSW", "city": "Sydney"},
}

# OpenRTB Audio object (2.5/2.6 §3.2.8) — a spec-plausible podcast/music slot.
# protocols 9/10 = DAAST 1.0 / DAAST 1.0 Wrapper; feed 1 = music streaming service.
_AUDIO: Dict[str, Any] = {
    "mimes": ["audio/mp4", "audio/mpeg", "audio/aac"],
    "minduration": 5,
    "maxduration": 30,
    "startdelay": 0,
    "protocols": [9, 10],
    "feed": 1,
    "nvol": 3,
    "api": [2],
}


def _native_request_str() -> str:
    """The OpenRTB Native 1.2 request markup, JSON-encoded into imp.native.request.

    context 1 = Content-centric; plcmttype 4 = Recommendation widget. A title +
    main image + sponsored-by text is the canonical minimal in-feed native asset set.
    """
    return json.dumps({
        "ver": "1.2",
        "context": 1,
        "plcmttype": 4,
        "plcmtcnt": 1,
        "assets": [
            {"id": 1, "required": 1, "title": {"len": 90}},
            {"id": 2, "required": 1, "img": {"type": 3, "wmin": 1200, "hmin": 627}},
            {"id": 3, "required": 0, "data": {"type": 2, "len": 150}},
        ],
    }, separators=(",", ":"))


def _trace_id() -> str:
    return uuid.uuid4().hex[:18].upper()


def _ifa(ifa: Optional[str], user_id: str) -> str:
    if ifa:
        return ifa
    try:
        uuid.UUID(str(user_id))
        return str(user_id)
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid4())


def _geo(country: str) -> Dict[str, Any]:
    key = country.upper()
    if key in _GEO_BY_COUNTRY:
        return dict(_GEO_BY_COUNTRY[key])
    return {"country": _ISO3.get(key, key), "type": 2}


def build_schain(*, publisher_id: Optional[str], request_id: str, complete: int = 1) -> Dict[str, Any]:
    """One-node SupplyChain matching the VoiseTech inbound request format."""
    return {
        "complete": complete,
        "ver": "1.0",
        "nodes": [{
            "asi": _SCHAIN_ASI,
            "sid": str(publisher_id or "1192"),
            "rid": request_id,
            "hp": 1,
        }],
    }


def _regs(*, gdpr: Optional[int], us_privacy: Optional[str], gpp: Optional[str],
          gpp_sid: Optional[List[int]], coppa: Optional[int]) -> Dict[str, Any]:
    ext: Dict[str, Any] = {"us_privacy": us_privacy if us_privacy is not None else "1YNN"}
    if gdpr is not None:
        ext["gdpr"] = gdpr
    if gpp is not None:
        ext["gpp"] = gpp
    if gpp_sid is not None:
        ext["gpp_sid"] = gpp_sid
    return {"coppa": 0 if coppa is None else coppa, "ext": ext}


def _device_block(*, device: str, country: str, ifa: Optional[str], user_id: str) -> Dict[str, Any]:
    devicetype = _DEVICE_TYPE.get(device, 3)
    if devicetype == 3:
        obj = dict(_CTV_DEVICE)
        obj.update({
            "geo": _geo(country),
            "dnt": 0,
            "lmt": 0,
            "devicetype": 3,
            "ifa": _ifa(ifa, user_id),
        })
        return obj

    os_name = "Android" if device in ("mobile", "tablet", "phone") else "Windows"
    ua = f"AdServerSim/{device}"
    if devicetype == 4:
        ua = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Mobile Safari/537.36"
    return {
        "ua": ua,
        "devicetype": devicetype,
        "os": os_name,
        "geo": _geo(country),
        "ip": "203.0.113.10",
        "lmt": 0,
        "dnt": 0,
        "js": 1,
        "language": "en",
        "ifa": _ifa(ifa, user_id),
    }


def build_bid_request(
    *,
    request_id: str,
    tag_id: str,
    publisher_id: Optional[str],
    country: str,
    device: str,
    browser: str,
    user_id: str,
    width: int = 1920,
    height: int = 1080,
    ad_format: str = "video",
    bidfloor: float = _DEFAULT_BIDFLOOR,
    # --- identifiers / inventory type ---
    app_mode: bool = False,
    bundle: Optional[str] = None,
    ifa: Optional[str] = None,
    app_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    # --- privacy signals ---
    gdpr: Optional[int] = None,
    consent: Optional[str] = None,
    us_privacy: Optional[str] = None,
    gpp: Optional[str] = None,
    gpp_sid: Optional[List[int]] = None,
    coppa: Optional[int] = None,
    # --- supply chain + 2.6 pods ---
    schain: bool = True,
    pod: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    fmt = (ad_format or "video").lower()
    is_video = fmt in ("video", "ctv")

    def _base_imp() -> Dict[str, Any]:
        return {
            "id": "1",
            "tagid": tag_id,
            "bidfloor": bidfloor,
            "bidfloorcur": "USD",
            "secure": 1,
        }

    if is_video:
        video: Dict[str, Any] = {**_CTV_VIDEO, "w": width, "h": height}
        if pod:  # OpenRTB 2.6 video pod fields
            video["podid"] = str(pod.get("podid", "pod-1"))
            video["mincpmpersec"] = pod.get("mincpmpersec", 0.5)
            video["poddur"] = pod.get("poddur", 60)
            video["maxseq"] = pod.get("maxseq", pod.get("slots", 3))
            video["rqddurs"] = pod.get("rqddurs", [15, 30])
            video["placement"] = 1
            video["plcmt"] = 1
        imp = {**_base_imp(), "clickbrowser": 0, "video": video}
        imps = [imp]
        if pod:
            slots = int(pod.get("slots", pod.get("maxseq", 3)))
            imps = []
            for i in range(max(slots, 1)):
                slot = {k: (dict(v) if isinstance(v, dict) else v) for k, v in imp.items()}
                slot["id"] = str(i + 1)
                slot["video"]["slotinpod"] = 0 if slots == 1 else (1 if i == 0 else (3 if i == slots - 1 else 2))
                imps.append(slot)
    elif fmt == "native":
        imps = [{**_base_imp(), "native": {"request": _native_request_str(), "ver": "1.2"}}]
    elif fmt == "audio":
        imps = [{**_base_imp(), "audio": dict(_AUDIO)}]
    else:  # banner / display
        imps = [{**_base_imp(), "banner": {
            "w": width, "h": height, "pos": 1, "format": [{"w": width, "h": height}]}}]

    pub_id = str(publisher_id or "1192")
    if is_video or app_mode or _DEVICE_TYPE.get(device, 3) == 3:
        app = {**_CTV_APP, "publisher": {"id": pub_id}}
        if app_id:
            app["id"] = str(app_id)
        if bundle:
            app["bundle"] = bundle
        inventory_key = "app"
        inventory = app
    else:
        inventory_key = "site"
        inventory = {
            "id": pub_id,
            "domain": "sim.local",
            "page": "https://sim.local/page",
            "publisher": {"id": pub_id, "name": "Voise Sim Publisher"},
        }

    user: Dict[str, Any] = {}
    if consent:
        user["ext"] = {"consent": consent}

    req: Dict[str, Any] = {
        "id": request_id,
        "imp": imps,
        inventory_key: inventory,
        "device": _device_block(device=device, country=country, ifa=ifa, user_id=user_id),
        "user": user,
        "at": 1,
        "tmax": _DEFAULT_TMAX,
        "cur": ["USD"],
    }

    if is_video:
        req["bcat"] = list(_DEFAULT_BCAT)
        req["regs"] = _regs(gdpr=gdpr, us_privacy=us_privacy, gpp=gpp, gpp_sid=gpp_sid, coppa=coppa)

    source: Dict[str, Any] = {"fd": 1, "tid": trace_id or _trace_id()}
    if schain:
        source["ext"] = {"schain": build_schain(publisher_id=publisher_id, request_id=request_id)}
    req["source"] = source

    # For non-video (banner/native/audio) attach regs only when a privacy signal is
    # actually present, so a plain request stays minimal (matches IAB + existing tests).
    if not is_video:
        if any(x is not None for x in (gdpr, gpp, gpp_sid, us_privacy)) or coppa not in (None, 0):
            req["regs"] = _regs(gdpr=gdpr, us_privacy=us_privacy, gpp=gpp, gpp_sid=gpp_sid, coppa=coppa)
    return req


def parse_bid_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Pick the highest-priced valid bid from an OpenRTB response (extraction only;
    conformance checks live in validators.validate_bid_response)."""
    out: Dict[str, Any] = {
        "filled": False, "price": None, "adm": None, "nurl": None, "burl": None,
        "creative_id": None, "campaign_id": None, "adomain": None, "seat": None,
        "no_fill_reason": None,
    }
    if status_code == 204:
        out["no_fill_reason"] = "no_bid_204"
        return out
    if not isinstance(body, dict):
        out["no_fill_reason"] = "no_bid_empty"
        return out

    best: Optional[Dict[str, Any]] = None
    best_seat: Optional[str] = None
    for seatbid in body.get("seatbid", []) or []:
        for bid in seatbid.get("bid", []) or []:
            price = bid.get("price") or 0
            if price > 0 and (best is None or price > (best.get("price") or 0)):
                best = bid
                best_seat = seatbid.get("seat")

    if best is None:
        out["no_fill_reason"] = "no_bid_empty"
        return out

    out.update(
        filled=True, price=best.get("price"), adm=best.get("adm"),
        nurl=best.get("nurl"), burl=best.get("burl"), creative_id=best.get("crid"),
        campaign_id=best.get("cid"), adomain=best.get("adomain"), seat=best_seat,
    )
    return out
