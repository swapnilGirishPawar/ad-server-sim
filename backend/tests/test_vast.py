from app.adserver.vast import parse_vast

FILLED = """<?xml version="1.0"?><VAST version="4.2"><Ad id="cr-9"><InLine>
<AdSystem>Voise</AdSystem><AdTitle>Nike Summer</AdTitle>
<Impression><![CDATA[https://voiseadserver.com/track/impression?aid=1&trace_id=t1]]></Impression>
<Creatives><Creative><Linear>
<TrackingEvents><Tracking event="start"><![CDATA[https://x/track/event?e=start]]></Tracking></TrackingEvents>
<VideoClicks><ClickThrough><![CDATA[https://voiseadserver.com/track/click?redirect=https://nike.com]]></ClickThrough>
<ClickTracking><![CDATA[https://x/track/click?aid=1]]></ClickTracking></VideoClicks>
<MediaFiles><MediaFile type="video/mp4"><![CDATA[https://cdn/x.mp4]]></MediaFile></MediaFiles>
</Linear></Creative></Creatives></InLine></Ad></VAST>"""


def test_parse_filled():
    r = parse_vast(FILLED)
    assert r["filled"] is True
    assert r["campaign"] == "Nike Summer"
    assert r["creative_id"] == "cr-9"
    assert r["impression_urls"] and "track/impression" in r["impression_urls"][0]
    assert r["clickthrough_url"].endswith("nike.com")
    assert len(r["click_tracking_urls"]) == 1
    assert r["tracking_event_urls"] and "e=start" in r["tracking_event_urls"][0]
    assert r["media_url"] == "https://cdn/x.mp4"


def test_parse_empty():
    r = parse_vast('<VAST version="4.2"></VAST>')
    assert r["filled"] is False
    assert r["no_fill_reason"] == "no_ad"


def test_parse_blank():
    assert parse_vast("")["no_fill_reason"] == "empty_response"


def test_parse_garbage():
    assert parse_vast("not xml <<<")["no_fill_reason"] == "parse_error"
