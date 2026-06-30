"""IAB conformance validators (VAST 4.x, VMAP 1.0, OpenRTB 2.5/2.6 response).

These are PURE functions of the response text/body — no network, no SUT — so the
offline pytest suite can exercise them against static spec fixtures (build prompt
§7). Each validator returns a structured result plus a list of `Finding`s that
say, per the published spec, what conformed and what did not.

Design principle (build prompt §1): we validate against the STANDARD, never
against what the SUT happens to emit. A missing required node is a `fail`, full
stop — even though the live SUT always "fills".

Spec references:
  VAST 4.2 — IAB Tech Lab, "Video Ad Serving Template" (digitalvideo/vast).
  VMAP 1.0 — IAB Tech Lab, "Video Multiple Ad Playlist".
  OpenRTB 2.5/2.6 — IAB Tech Lab, "OpenRTB API Specification".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from app.conformance import FAIL, INFO, PASS, WARN, Finding, FindingSet

# ---------------------------------------------------------------- XML helpers

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _findall(root: ET.Element, name: str) -> List[ET.Element]:
    return [el for el in root.iter() if _local(el.tag) == name]


def _first(root: ET.Element, name: str) -> Optional[ET.Element]:
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


_DURATION_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}(\.\d{1,3})?$")
# VMAP timeOffset: start | end | HH:MM:SS(.mmm) | n% | #m (position)
_TIMEOFFSET_RE = re.compile(r"^(start|end|\d{1,2}:\d{2}:\d{2}(\.\d{1,3})?|\d{1,3}%|#\d+)$")
_VAST_VERSIONS = {"2.0", "3.0", "4.0", "4.1", "4.2", "4.3"}
_QUARTILES = ["start", "firstQuartile", "midpoint", "thirdQuartile", "complete"]

VAST = "VAST 4.x"
VMAP = "VMAP"
ORTB = "OpenRTB 2.6"


# ----------------------------------------------------------------- VAST result

@dataclass
class VastResult:
    well_formed: bool
    ad_type: str                                  # inline | wrapper | empty | unparseable
    version: Optional[str] = None
    ad_id: Optional[str] = None                   # <Ad id> attribute (creative id surrogate)
    ad_system: Optional[str] = None
    ad_title: Optional[str] = None
    duration: Optional[str] = None
    impression_urls: List[str] = field(default_factory=list)
    clickthrough_url: Optional[str] = None
    click_tracking_urls: List[str] = field(default_factory=list)
    tracking_events: Dict[str, List[str]] = field(default_factory=dict)  # event -> urls
    error_urls: List[str] = field(default_factory=list)
    media_files: List[Dict[str, Any]] = field(default_factory=list)
    wrapper_uri: Optional[str] = None
    has_omid: bool = False
    findings: List[Finding] = field(default_factory=list)
    raw: str = ""

    @property
    def filled(self) -> bool:
        return self.ad_type in ("inline", "wrapper")

    @property
    def conformant(self) -> bool:
        return not any(f.severity == FAIL for f in self.findings)


def validate_vast(xml_text: str, *, endpoint: str = "", scenario: str = "") -> VastResult:
    """Validate a VAST document against VAST 4.x structural requirements."""
    fs = FindingSet()

    def add(section, check, severity, expected, observed):
        fs.add(VAST, section, check, severity, expected, observed, endpoint=endpoint, scenario=scenario)

    if not xml_text or not xml_text.strip():
        add("VAST §2.2", "non_empty", INFO, "a VAST document",
            "empty body (treated as no-fill; not spec-compliant — IAB wants <VAST><Error>)")
        return VastResult(well_formed=False, ad_type="empty", findings=fs.findings, raw="")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        add("VAST §2.2", "well_formed_xml", FAIL, "well-formed XML", f"XML parse error: {e}")
        return VastResult(well_formed=False, ad_type="unparseable", findings=fs.findings, raw=xml_text[:4000])

    res = VastResult(well_formed=True, ad_type="empty", findings=fs.findings, raw=xml_text[:4000])

    if _local(root.tag) != "VAST":
        add("VAST §2.2.1", "root_element", FAIL, "<VAST> root element", f"root is <{_local(root.tag)}>")
        res.ad_type = "unparseable"
        return res

    res.version = root.get("version")
    if not res.version:
        add("VAST §2.2.1", "version_attr", FAIL, "VAST version attribute", "missing version attribute")
    elif res.version not in _VAST_VERSIONS:
        add("VAST §2.2.1", "version_attr", WARN, "a known VAST version (2.0–4.3)", f"version={res.version}")
    else:
        fs.ok(VAST, "VAST §2.2.1", "version_attr", f"version={res.version}", endpoint=endpoint, scenario=scenario)

    ads = _findall(root, "Ad")
    if not ads:
        # Empty VAST = a spec-correct no-fill (VAST §2.2.4). Allowed.
        add("VAST §2.2.4", "no_fill", INFO, "empty <VAST/> is a valid no-fill", "no <Ad> present (no-fill)")
        return res

    ad = ads[0]
    res.ad_id = ad.get("id")
    inline = _first(ad, "InLine")
    wrapper = _first(ad, "Wrapper")

    # --- Shared: impressions + error + OMID + AdVerifications --------------
    res.impression_urls = [t for t in (_text(e) for e in _findall(ad, "Impression")) if t]
    res.error_urls = [t for t in (_text(e) for e in _findall(ad, "Error")) if t]
    res.has_omid = bool(_findall(ad, "Verification") or _findall(ad, "AdVerifications"))
    res.tracking_events = _extract_tracking_events(ad)
    res.click_tracking_urls = [t for t in (_text(e) for e in _findall(ad, "ClickTracking")) if t]
    ct = _first(ad, "ClickThrough")
    res.clickthrough_url = _text(ct)
    res.ad_system = _text(_first(ad, "AdSystem"))
    res.ad_title = _text(_first(ad, "AdTitle"))

    if not res.impression_urls:
        add("VAST §3.4.1", "impression", FAIL, "at least one <Impression>", "no <Impression> node")
    else:
        fs.ok(VAST, "VAST §3.4.1", "impression", f"{len(res.impression_urls)} <Impression>",
              endpoint=endpoint, scenario=scenario)

    if res.has_omid:
        fs.ok(VAST, "VAST §3.15 OMID", "ad_verifications", "<AdVerifications> present",
              endpoint=endpoint, scenario=scenario)
    else:
        add("VAST §3.15 OMID", "ad_verifications", INFO,
            "<AdVerifications>/<Verification> for viewability (OMID)", "no AdVerifications (non-blocking)")

    if wrapper is not None and inline is None:
        res.ad_type = "wrapper"
        _validate_wrapper(wrapper, fs, endpoint, scenario, res)
    elif inline is not None:
        res.ad_type = "inline"
        _validate_inline(inline, ad, fs, endpoint, scenario, res)
    else:
        add("VAST §3.2", "inline_or_wrapper", FAIL, "<Ad> contains <InLine> or <Wrapper>",
            "<Ad> has neither <InLine> nor <Wrapper>")
    return res


def _extract_tracking_events(ad: ET.Element) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for tr in _findall(ad, "Tracking"):
        ev = tr.get("event")
        url = _text(tr)
        if ev and url:
            out.setdefault(ev, []).append(url)
    return out


def _validate_inline(inline: ET.Element, ad: ET.Element, fs: FindingSet,
                     endpoint: str, scenario: str, res: VastResult) -> None:
    def add(section, check, severity, expected, observed):
        fs.add(VAST, section, check, severity, expected, observed, endpoint=endpoint, scenario=scenario)

    def ok(section, check, observed):
        fs.ok(VAST, section, check, observed, endpoint=endpoint, scenario=scenario)

    # Required top-level InLine nodes.
    if not res.ad_system:
        add("VAST §3.4.2", "adsystem", FAIL, "<AdSystem>", "missing")
    else:
        ok("VAST §3.4.2", "adsystem", res.ad_system)
    if not res.ad_title:
        add("VAST §3.4.3", "adtitle", FAIL, "<AdTitle>", "missing")
    else:
        ok("VAST §3.4.3", "adtitle", res.ad_title)

    linear = _first(ad, "Linear")
    if _first(ad, "Creative") is None:
        add("VAST §3.5", "creatives", FAIL, "<Creatives>/<Creative>", "no <Creative>")
        return
    if linear is None:
        # Could be a companion/nonlinear-only ad; flag, don't hard-pass.
        add("VAST §3.7", "linear", WARN, "<Linear> creative for video", "no <Linear> (non-linear/companion only?)")
        return
    ok("VAST §3.5", "creatives", "<Creative>/<Linear> present")

    # Duration HH:MM:SS.
    res.duration = _text(_first(linear, "Duration"))
    if not res.duration:
        add("VAST §3.7.1", "duration", FAIL, "<Duration> HH:MM:SS", "missing <Duration>")
    elif not _DURATION_RE.match(res.duration):
        add("VAST §3.7.1", "duration", FAIL, "Duration as HH:MM:SS", f"malformed Duration '{res.duration}'")
    else:
        ok("VAST §3.7.1", "duration", res.duration)

    # MediaFiles + attributes.
    media = _findall(linear, "MediaFile")
    if not media:
        add("VAST §3.7.3", "mediafiles", FAIL, "<MediaFiles>/<MediaFile>", "no <MediaFile>")
    else:
        for mf in media:
            entry = {
                "url": _text(mf), "delivery": mf.get("delivery"), "type": mf.get("type"),
                "width": mf.get("width"), "height": mf.get("height"), "bitrate": mf.get("bitrate"),
            }
            res.media_files.append(entry)
        first = res.media_files[0]
        required_attrs = ("delivery", "type", "width", "height")
        missing = [a for a in required_attrs if not first.get(a)]
        if missing:
            add("VAST §3.7.3", "mediafile_attrs", FAIL,
                "MediaFile with delivery, type, width, height (bitrate recommended)",
                f"MediaFile missing attrs: {', '.join(missing)}")
        elif not first.get("bitrate"):
            add("VAST §3.7.3", "mediafile_attrs", WARN,
                "MediaFile with bitrate", "MediaFile missing bitrate (recommended)")
        else:
            ok("VAST §3.7.3", "mediafile_attrs", f"{len(media)} MediaFile(s) with required attrs")

    # VideoClicks / ClickThrough.
    if not res.clickthrough_url:
        add("VAST §3.7.5", "clickthrough", WARN, "<VideoClicks>/<ClickThrough>", "no ClickThrough URL")
    else:
        ok("VAST §3.7.5", "clickthrough", res.clickthrough_url)

    # Quartile tracking events.
    present = [q for q in _QUARTILES if q in res.tracking_events]
    missing_q = [q for q in _QUARTILES if q not in res.tracking_events]
    if missing_q:
        add("VAST §3.7.4", "quartile_tracking", WARN,
            "TrackingEvents: " + ", ".join(_QUARTILES),
            f"present: {present or 'none'}; missing: {', '.join(missing_q)}")
    else:
        ok("VAST §3.7.4", "quartile_tracking", "all quartile events present")


def _validate_wrapper(wrapper: ET.Element, fs: FindingSet,
                      endpoint: str, scenario: str, res: VastResult) -> None:
    def add(section, check, severity, expected, observed):
        fs.add(VAST, section, check, severity, expected, observed, endpoint=endpoint, scenario=scenario)

    uri = _first(wrapper, "VASTAdTagURI")
    res.wrapper_uri = _text(uri)
    if not res.wrapper_uri:
        add("VAST §3.3.1", "vastadtaguri", FAIL, "<VASTAdTagURI> in a Wrapper", "missing VASTAdTagURI")
    else:
        fs.ok(VAST, "VAST §3.3.1", "vastadtaguri", res.wrapper_uri, endpoint=endpoint, scenario=scenario)


# ----------------------------------------------------------------- VMAP result

@dataclass
class VmapResult:
    well_formed: bool
    version: Optional[str] = None
    ad_breaks: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    raw: str = ""

    @property
    def conformant(self) -> bool:
        return not any(f.severity == FAIL for f in self.findings)


def validate_vmap(xml_text: str, *, endpoint: str = "", scenario: str = "") -> VmapResult:
    """Validate a VMAP 1.0 ad playlist (pre/mid/post-roll scheduling)."""
    fs = FindingSet()

    def add(section, check, severity, expected, observed):
        fs.add(VMAP, section, check, severity, expected, observed, endpoint=endpoint, scenario=scenario)

    if not xml_text or not xml_text.strip():
        add("VMAP §2", "non_empty", FAIL, "a VMAP document", "empty body")
        return VmapResult(well_formed=False, findings=fs.findings)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        add("VMAP §2", "well_formed_xml", FAIL, "well-formed XML", f"parse error: {e}")
        return VmapResult(well_formed=False, findings=fs.findings, raw=xml_text[:2000])

    res = VmapResult(well_formed=True, findings=fs.findings, raw=xml_text[:2000])
    if _local(root.tag) != "VMAP":
        add("VMAP §2.2", "root_element", FAIL, "<vmap:VMAP> root", f"root is <{_local(root.tag)}>")
        return res
    res.version = root.get("version") or _attr_endswith(root, "version")
    if not res.version:
        add("VMAP §2.2", "version_attr", WARN, "VMAP version attribute", "missing version")

    breaks = _findall(root, "AdBreak")
    if not breaks:
        add("VMAP §3", "adbreak", FAIL, "at least one <vmap:AdBreak>", "no AdBreak")
        return res

    for i, br in enumerate(breaks):
        offset = br.get("timeOffset")
        break_type = br.get("breakType")
        has_source = _first(br, "AdSource") is not None
        entry = {"index": i, "timeOffset": offset, "breakType": break_type, "has_ad_source": has_source}
        res.ad_breaks.append(entry)
        if not offset:
            add("VMAP §3.1", "timeoffset", FAIL, "AdBreak@timeOffset", f"break #{i}: missing timeOffset")
        elif not _TIMEOFFSET_RE.match(offset):
            add("VMAP §3.1", "timeoffset", FAIL,
                "timeOffset = start|end|HH:MM:SS|n%|#pos", f"break #{i}: malformed timeOffset '{offset}'")
        if not break_type:
            add("VMAP §3.1", "breaktype", WARN, "AdBreak@breakType", f"break #{i}: missing breakType")
        if not has_source:
            add("VMAP §3.2", "adsource", FAIL, "AdBreak/<vmap:AdSource>", f"break #{i}: missing AdSource")

    if not fs.failed:
        fs.ok(VMAP, "VMAP §3", "structure", f"{len(breaks)} well-formed AdBreak(s)",
              endpoint=endpoint, scenario=scenario)
    return res


def _attr_endswith(el: ET.Element, suffix: str) -> Optional[str]:
    for k, v in el.attrib.items():
        if _local(k) == suffix:
            return v
    return None


# ------------------------------------------------------------- OpenRTB result

@dataclass
class OrtbResult:
    filled: bool
    no_bid: bool
    findings: List[Finding] = field(default_factory=list)
    best: Optional[Dict[str, Any]] = None
    nbr: Optional[int] = None
    cur: Optional[str] = None

    @property
    def conformant(self) -> bool:
        return not any(f.severity == FAIL for f in self.findings)


def validate_bid_response(status_code: int, body: Any, *, request: Optional[Dict[str, Any]] = None,
                          endpoint: str = "", scenario: str = "") -> OrtbResult:
    """Validate an OpenRTB BidResponse against 2.5/2.6 §4.2."""
    fs = FindingSet()

    def add(section, check, severity, expected, observed):
        fs.add(ORTB, section, check, severity, expected, observed, endpoint=endpoint, scenario=scenario)

    req_id = (request or {}).get("id")
    bidfloor = None
    if request and request.get("imp"):
        bidfloor = (request["imp"][0] or {}).get("bidfloor")

    # No-bid forms the SUT actually uses: bare 204, or 200 with empty seatbid.
    if status_code == 204:
        add("OpenRTB §4.3.2", "nbr", INFO,
            "a no-bid SHOULD carry an nbr reason code (and may be a 204)",
            "HTTP 204 with empty body — no nbr available (SUT trait)")
        return OrtbResult(filled=False, no_bid=True, findings=fs.findings)
    if not isinstance(body, dict):
        add("OpenRTB §4.2.1", "json_body", WARN, "JSON BidResponse object or 204",
            f"HTTP {status_code} with non-JSON / empty body")
        return OrtbResult(filled=False, no_bid=True, findings=fs.findings)

    res = OrtbResult(filled=False, no_bid=False, findings=fs.findings)
    res.nbr = body.get("nbr")
    res.cur = body.get("cur")

    if not body.get("id"):
        add("OpenRTB §4.2.1", "response_id", FAIL, "BidResponse.id", "missing id")
    elif req_id and body["id"] != req_id:
        add("OpenRTB §4.2.1", "response_id", FAIL, f"BidResponse.id echoes request id {req_id}",
            f"id={body['id']} != request {req_id}")
    else:
        fs.ok(ORTB, "OpenRTB §4.2.1", "response_id", f"id={body.get('id')}", endpoint=endpoint, scenario=scenario)

    seatbids = body.get("seatbid") or []
    bids = [b for sb in seatbids for b in (sb.get("bid") or [])]
    if not bids:
        res.no_bid = True
        if res.nbr is not None:
            fs.ok(ORTB, "OpenRTB §4.3.2", "nbr", f"no-bid with nbr={res.nbr}", endpoint=endpoint, scenario=scenario)
        else:
            add("OpenRTB §4.3.2", "nbr", INFO,
                "empty seatbid SHOULD carry nbr", "200 with empty seatbid and no nbr (SUT trait)")
        return res

    if not res.cur:
        add("OpenRTB §4.2.1", "cur", WARN, "BidResponse.cur", "missing cur (USD assumed)")

    best = max(bids, key=lambda b: b.get("price") or 0)
    res.best = best
    res.filled = (best.get("price") or 0) > 0

    # Per-bid required fields (§4.2.3).
    if not best.get("impid"):
        add("OpenRTB §4.2.3", "bid_impid", FAIL, "bid.impid", "missing impid")
    if best.get("price") is None:
        add("OpenRTB §4.2.3", "bid_price", FAIL, "bid.price", "missing price")
    if not (best.get("adm") or best.get("nurl")):
        add("OpenRTB §4.2.3", "bid_adm_or_nurl", FAIL, "bid.adm or bid.nurl", "neither adm nor nurl present")
    if not best.get("crid"):
        add("OpenRTB §4.2.3", "bid_crid", WARN, "bid.crid (creative id)", "missing crid")
    if not best.get("adomain"):
        add("OpenRTB §4.2.3", "bid_adomain", WARN, "bid.adomain (advertiser domain)", "missing adomain")
    if bidfloor is not None and best.get("price") is not None and best["price"] < bidfloor:
        add("OpenRTB §4.2.3", "price_vs_floor", FAIL,
            f"winning price >= bidfloor {bidfloor}", f"price {best['price']} < floor {bidfloor}")
    if not fs.failed:
        fs.ok(ORTB, "OpenRTB §4.2.3", "bid_fields", f"valid bid price={best.get('price')} crid={best.get('crid')}",
              endpoint=endpoint, scenario=scenario)
    return res
