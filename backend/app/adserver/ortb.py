"""OpenRTB 2.5 / 2.6 bid-request builder and bid-response parser.

The target server's OpenRTB endpoint (`POST /api/b/{tag_id}` == `/ortb/bid/{tag_id}`)
fans out to configured demand partners. We build spec-correct 2.5/2.6 requests —
including `regs` privacy signals, `source.ext.schain` (SupplyChain), app/site +
device identifiers, and optional 2.6 video pods — so the RTB plumbing and the
SUT's passthrough/auction behaviour are properly exercised and measured.

Spec: IAB OpenRTB 2.5 §3.2 (BidRequest) and 2.6 §3.2.7 (pods), Appendix A.2 (sChain).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# alpha-2 (our traffic dimension) -> alpha-3 (OpenRTB device.geo.country)
_ISO3 = {"IN": "IND", "US": "USA", "UK": "GBR", "GB": "GBR", "CA": "CAN", "AU": "AUS", "DE": "DEU"}
# OpenRTB device types (2.6 Table: 1 mobile/tablet,2 pc,3 connected tv,4 phone,5 tablet,7 set top box)
_DEVICE_TYPE = {"mobile": 4, "phone": 4, "tablet": 5, "desktop": 2, "pc": 2, "ctv": 3, "tv": 3}


def build_schain(*, publisher_id: Optional[str], request_id: str, complete: int = 1) -> Dict[str, Any]:
    """Minimal one-node SupplyChain identifying the simulator as the seller of record."""
    return {
        "complete": complete,
        "ver": "1.0",
        "nodes": [{
            "asi": "voise-ad-sim.local",
            "sid": str(publisher_id or "sim-seller"),
            "rid": request_id,
            "hp": 1,
        }],
    }


def _regs(*, gdpr: Optional[int], us_privacy: Optional[str], gpp: Optional[str],
          gpp_sid: Optional[List[int]], coppa: Optional[int]) -> Optional[Dict[str, Any]]:
    ext: Dict[str, Any] = {}
    if gdpr is not None:
        ext["gdpr"] = gdpr
    if us_privacy is not None:
        ext["us_privacy"] = us_privacy
    if gpp is not None:
        ext["gpp"] = gpp
    if gpp_sid is not None:
        ext["gpp_sid"] = gpp_sid
    regs: Dict[str, Any] = {}
    if coppa is not None:
        regs["coppa"] = coppa
    if ext:
        regs["ext"] = ext
    return regs or None


def build_bid_request(
    *,
    request_id: str,
    tag_id: str,
    publisher_id: Optional[str],
    country: str,
    device: str,
    browser: str,
    user_id: str,
    width: int = 640,
    height: int = 480,
    ad_format: str = "video",
    bidfloor: float = 0.1,
    # --- identifiers / inventory type ---
    app_mode: bool = False,
    bundle: Optional[str] = None,
    ifa: Optional[str] = None,
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
    devicetype = _DEVICE_TYPE.get(device, 2)
    is_ctv = devicetype == 3
    if ad_format in ("video", "ctv"):
        video: Dict[str, Any] = {
            "mimes": ["video/mp4"],
            "minduration": 5,
            "maxduration": 30,
            "protocols": [2, 3, 5, 6, 7, 8],
            "w": width,
            "h": height,
            "linearity": 1,
            "placement": 1 if not is_ctv else 1,
            "plcmt": 1,           # 2.6: instream
            "startdelay": 0,
            "skip": 0,
        }
        if pod:  # OpenRTB 2.6 video pod fields
            video["podid"] = str(pod.get("podid", "pod-1"))
            video["mincpmpersec"] = pod.get("mincpmpersec", 0.5)
            video["poddur"] = pod.get("poddur", 60)
            video["maxseq"] = pod.get("maxseq", pod.get("slots", 3))
            video["rqddurs"] = pod.get("rqddurs", [15, 30])
        imp_obj = {"video": video}
    else:
        imp_obj = {"banner": {"w": width, "h": height, "pos": 1}}

    imp = {"id": "1", "tagid": tag_id, "bidfloor": bidfloor, "bidfloorcur": "USD",
           "secure": 1, **imp_obj}
    imps = [imp]
    # A real pod request carries one imp per slot sharing the podid (2.6 §3.2.7).
    if pod and ad_format in ("video", "ctv"):
        slots = int(pod.get("slots", pod.get("maxseq", 3)))
        imps = []
        for i in range(max(slots, 1)):
            slot = {k: (dict(v) if isinstance(v, dict) else v) for k, v in imp.items()}
            slot["id"] = str(i + 1)
            slot["video"]["slotinpod"] = 0 if slots == 1 else (1 if i == 0 else (3 if i == slots - 1 else 2))
            imps.append(slot)

    publisher = {"id": str(publisher_id or "sim-pub"), "name": "Voise Sim Publisher"}
    inventory_key = "app" if (app_mode or is_ctv) else "site"
    if inventory_key == "app":
        inventory = {
            "id": str(publisher_id or "sim-app"),
            "name": "Voise Sim App",
            "bundle": bundle or "com.voisesim.app",
            "storeurl": "https://play.google.com/store/apps/details?id=com.voisesim.app",
            "publisher": publisher,
        }
    else:
        inventory = {
            "id": str(publisher_id or "sim-site"),
            "domain": "sim.local",
            "page": "https://sim.local/page",
            "publisher": publisher,
        }

    device_obj: Dict[str, Any] = {
        "ua": f"AdServerSim/{browser}",
        "devicetype": devicetype,
        "os": "Android" if device in ("mobile", "tablet") or is_ctv else "Windows",
        "geo": {"country": _ISO3.get(country.upper(), country.upper()), "type": 2},
        "ip": "203.0.113.10",
        "lmt": 0,
        "dnt": 0,
        "language": "en",
    }
    if ifa or app_mode or is_ctv:
        device_obj["ifa"] = ifa or user_id

    user: Dict[str, Any] = {"id": user_id}
    if consent:
        user["ext"] = {"consent": consent}

    req: Dict[str, Any] = {
        "id": request_id,
        "at": 1,
        "tmax": 300,
        "cur": ["USD"],
        "imp": imps,
        inventory_key: inventory,
        "device": device_obj,
        "user": user,
    }

    source: Dict[str, Any] = {"fd": 0, "tid": request_id}
    if schain:
        source["ext"] = {"schain": build_schain(publisher_id=publisher_id, request_id=request_id)}
    req["source"] = source

    regs = _regs(gdpr=gdpr, us_privacy=us_privacy, gpp=gpp, gpp_sid=gpp_sid, coppa=coppa)
    if regs:
        req["regs"] = regs
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
