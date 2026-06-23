"""OpenRTB 2.6 bid-request builder and bid-response parser.

The target server's OpenRTB endpoint (`POST /api/b/{tag_id}`) fans out to
configured demand partners; locally, with no real DSP endpoints, it typically
no-bids (204 / empty seatbid). We still build spec-correct requests and parse
whatever comes back so the RTB plumbing is exercised and measured.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# alpha-2 (our traffic dimension) -> alpha-3 (OpenRTB device.geo.country)
_ISO3 = {"IN": "IND", "US": "USA", "UK": "GBR", "GB": "GBR", "CA": "CAN"}
# OpenRTB 2.6 device types
_DEVICE_TYPE = {"mobile": 4, "phone": 4, "tablet": 5, "desktop": 2, "pc": 2, "ctv": 3, "tv": 3}


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
) -> Dict[str, Any]:
    if ad_format in ("video", "ctv"):
        imp_obj = {
            "video": {
                "mimes": ["video/mp4"],
                "minduration": 5,
                "maxduration": 30,
                "protocols": [2, 3, 5, 6],
                "w": width,
                "h": height,
                "linearity": 1,
                "placement": 1,
            }
        }
    else:
        imp_obj = {"banner": {"w": width, "h": height}}

    imp = {"id": "1", "tagid": tag_id, "bidfloor": bidfloor, "bidfloorcur": "USD", **imp_obj}

    return {
        "id": request_id,
        "at": 1,
        "tmax": 300,
        "cur": ["USD"],
        "imp": [imp],
        "site": {
            "id": publisher_id or "sim-site",
            "domain": "sim.local",
            "page": "https://sim.local/page",
            "publisher": {"id": publisher_id or "sim-pub"},
        },
        "device": {
            "ua": f"AdServerSim/{browser}",
            "devicetype": _DEVICE_TYPE.get(device, 2),
            "os": "Android" if device in ("mobile", "tablet") else "Windows",
            "geo": {"country": _ISO3.get(country.upper(), country.upper())},
            "ip": "203.0.113.10",
        },
        "user": {"id": user_id},
    }


def parse_bid_response(status_code: int, body: Any) -> Dict[str, Any]:
    """Pick the highest-priced valid bid from an OpenRTB response."""
    out: Dict[str, Any] = {
        "filled": False,
        "price": None,
        "adm": None,
        "nurl": None,
        "burl": None,
        "creative_id": None,
        "campaign_id": None,
        "no_fill_reason": None,
    }
    if status_code == 204:
        out["no_fill_reason"] = "no_bid_204"
        return out
    if not isinstance(body, dict):
        out["no_fill_reason"] = "no_bid_empty"
        return out

    best: Optional[Dict[str, Any]] = None
    for seatbid in body.get("seatbid", []) or []:
        for bid in seatbid.get("bid", []) or []:
            price = bid.get("price") or 0
            if price > 0 and (best is None or price > (best.get("price") or 0)):
                best = bid

    if best is None:
        out["no_fill_reason"] = "no_bid_empty"
        return out

    out.update(
        filled=True,
        price=best.get("price"),
        adm=best.get("adm"),
        nurl=best.get("nurl"),
        burl=best.get("burl"),
        creative_id=best.get("crid"),
        campaign_id=best.get("cid"),
    )
    return out
