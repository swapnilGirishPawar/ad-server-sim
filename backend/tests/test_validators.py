"""Offline VAST 4.x / VMAP / OpenRTB conformance validator tests (static fixtures)."""
from app.adserver import validators

GOOD_INLINE = """<?xml version="1.0"?>
<VAST version="4.2"><Ad id="cr-9"><InLine>
<AdSystem version="1.0">Voise</AdSystem><AdTitle>Nike Summer</AdTitle>
<Impression><![CDATA[https://x/track/impression?aid=1]]></Impression>
<AdVerifications><Verification vendor="moat.com"></Verification></AdVerifications>
<Creatives><Creative id="cr-9"><Linear>
<Duration>00:00:30</Duration>
<TrackingEvents>
<Tracking event="start"><![CDATA[https://x/e?ev=start]]></Tracking>
<Tracking event="firstQuartile"><![CDATA[https://x/e?ev=q1]]></Tracking>
<Tracking event="midpoint"><![CDATA[https://x/e?ev=mid]]></Tracking>
<Tracking event="thirdQuartile"><![CDATA[https://x/e?ev=q3]]></Tracking>
<Tracking event="complete"><![CDATA[https://x/e?ev=complete]]></Tracking>
</TrackingEvents>
<VideoClicks><ClickThrough><![CDATA[https://nike.com]]></ClickThrough></VideoClicks>
<MediaFiles><MediaFile delivery="progressive" type="video/mp4" width="640" height="480" bitrate="800">
<![CDATA[https://cdn/x.mp4]]></MediaFile></MediaFiles>
</Linear></Creative></Creatives></InLine></Ad></VAST>"""

WRAPPER = """<VAST version="4.2"><Ad id="w1"><Wrapper>
<AdSystem>Voise</AdSystem>
<VASTAdTagURI><![CDATA[https://upstream/vast.xml]]></VASTAdTagURI>
<Impression><![CDATA[https://x/imp]]></Impression>
</Wrapper></Ad></VAST>"""

MISSING_DURATION = """<VAST version="4.2"><Ad id="a"><InLine>
<AdSystem>Voise</AdSystem><AdTitle>T</AdTitle><Impression>https://x/i</Impression>
<Creatives><Creative><Linear>
<MediaFiles><MediaFile delivery="progressive" type="video/mp4" width="640" height="480" bitrate="700">https://cdn/x.mp4</MediaFile></MediaFiles>
</Linear></Creative></Creatives></InLine></Ad></VAST>"""


def _fail_checks(findings):
    return {f.check for f in findings if f.severity == "fail"}


def test_good_inline_is_conformant():
    r = validators.validate_vast(GOOD_INLINE)
    assert r.ad_type == "inline"
    assert r.version == "4.2"
    assert r.conformant is True
    assert r.has_omid is True
    assert set(["start", "firstQuartile", "midpoint", "thirdQuartile", "complete"]).issubset(r.tracking_events)
    assert r.media_files[0]["bitrate"] == "800"
    assert r.ad_id == "cr-9"


def test_wrapper_detected():
    r = validators.validate_vast(WRAPPER)
    assert r.ad_type == "wrapper"
    assert r.wrapper_uri == "https://upstream/vast.xml"
    assert "vastadtaguri" not in _fail_checks(r.findings)


def test_missing_duration_fails():
    r = validators.validate_vast(MISSING_DURATION)
    assert r.ad_type == "inline"
    assert "duration" in _fail_checks(r.findings)
    assert r.conformant is False


def test_empty_vast_is_no_fill_not_failure():
    r = validators.validate_vast('<VAST version="4.2"></VAST>')
    assert r.ad_type == "empty"
    assert r.conformant is True  # empty VAST is a valid no-fill


def test_unparseable_fails():
    r = validators.validate_vast("not xml <<<")
    assert r.ad_type == "unparseable"
    assert r.conformant is False


# ----------------------------------------------------------------- VMAP
GOOD_VMAP = """<vmap:VMAP xmlns:vmap="http://www.iab.net/vmap-1.0" version="1.0">
<vmap:AdBreak timeOffset="start" breakType="linear" breakId="pre">
<vmap:AdSource><vmap:VASTAdData></vmap:VASTAdData></vmap:AdSource></vmap:AdBreak>
<vmap:AdBreak timeOffset="00:05:00" breakType="linear" breakId="mid"><vmap:AdSource/></vmap:AdBreak>
</vmap:VMAP>"""

BAD_OFFSET_VMAP = """<vmap:VMAP xmlns:vmap="http://www.iab.net/vmap-1.0" version="1.0">
<vmap:AdBreak timeOffset="60:00" breakType="linear"><vmap:AdSource/></vmap:AdBreak></vmap:VMAP>"""


def test_vmap_good():
    r = validators.validate_vmap(GOOD_VMAP)
    assert r.well_formed and r.conformant
    assert len(r.ad_breaks) == 2


def test_vmap_bad_offset_flagged():
    r = validators.validate_vmap(BAD_OFFSET_VMAP)
    assert any(f.check == "timeoffset" and f.severity == "fail" for f in r.findings)


# ----------------------------------------------------------------- OpenRTB
def test_ortb_204_is_no_bid():
    r = validators.validate_bid_response(204, None)
    assert r.no_bid and not r.filled


def test_ortb_valid_bid():
    req = {"id": "req-1", "imp": [{"id": "1", "bidfloor": 1.0}]}
    body = {"id": "req-1", "cur": "USD", "seatbid": [{"seat": "s", "bid": [
        {"impid": "1", "price": 3.0, "adm": "<VAST/>", "crid": "c1", "adomain": ["a.com"]}]}]}
    r = validators.validate_bid_response(200, body, request=req)
    assert r.filled and r.conformant


def test_ortb_price_below_floor_fails():
    req = {"id": "r", "imp": [{"id": "1", "bidfloor": 5.0}]}
    body = {"id": "r", "seatbid": [{"bid": [{"impid": "1", "price": 1.0, "adm": "x", "crid": "c"}]}]}
    r = validators.validate_bid_response(200, body, request=req)
    assert any(f.check == "price_vs_floor" and f.severity == "fail" for f in r.findings)


def test_ortb_id_mismatch_fails():
    req = {"id": "r1", "imp": [{"id": "1"}]}
    body = {"id": "DIFFERENT", "seatbid": [{"bid": [{"impid": "1", "price": 2, "adm": "x", "crid": "c"}]}]}
    r = validators.validate_bid_response(200, body, request=req)
    assert any(f.check == "response_id" and f.severity == "fail" for f in r.findings)
