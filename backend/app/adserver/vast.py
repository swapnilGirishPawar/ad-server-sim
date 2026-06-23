"""Minimal, namespace-tolerant VAST 4.2 parser.

The target server emits plain (un-namespaced) VAST from `build_vast_xml`, but we
strip namespaces defensively so wrapped/SDK variants parse too. We only extract
what the simulator needs: the winning campaign/creative and the tracking URLs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _findall_local(root: ET.Element, name: str) -> List[ET.Element]:
    return [el for el in root.iter() if _local(el.tag) == name]


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def parse_vast(xml_text: str) -> Dict[str, Any]:
    """Return a structured view of a VAST document.

    filled is False for empty / no-ad / unparseable responses.
    """
    result: Dict[str, Any] = {
        "filled": False,
        "creative_id": None,
        "campaign": None,
        "impression_urls": [],
        "clickthrough_url": None,
        "click_tracking_urls": [],
        "tracking_event_urls": [],
        "media_url": None,
        "no_fill_reason": None,
    }
    if not xml_text or not xml_text.strip():
        result["no_fill_reason"] = "empty_response"
        return result
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        result["no_fill_reason"] = "parse_error"
        return result

    ads = _findall_local(root, "Ad")
    if not ads:
        result["no_fill_reason"] = "no_ad"
        return result

    ad = ads[0]
    result["filled"] = True
    result["creative_id"] = ad.get("id")

    title_els = _findall_local(ad, "AdTitle")
    if title_els:
        result["campaign"] = _text(title_els[0])

    result["impression_urls"] = [t for t in (_text(e) for e in _findall_local(ad, "Impression")) if t]

    ct = _findall_local(ad, "ClickThrough")
    if ct:
        result["clickthrough_url"] = _text(ct[0])
    result["click_tracking_urls"] = [t for t in (_text(e) for e in _findall_local(ad, "ClickTracking")) if t]
    result["tracking_event_urls"] = [t for t in (_text(e) for e in _findall_local(ad, "Tracking")) if t]

    mf = _findall_local(ad, "MediaFile")
    if mf:
        result["media_url"] = _text(mf[0])

    # A Wrapper with only a redirect URI and no creative is still a "fill" attempt
    # but carries no impression of its own; treat presence of <Ad> as filled.
    return result
