from app.config import Settings
from app.adserver import tracking

S = Settings(ad_server_url="http://localhost:8001", tracking_prefix_fix=True)


def test_rewrite_host_and_prefix():
    url, rewritten, note = tracking.normalize_url(
        "https://voiseadserver.com/track/impression?aid=1", S)
    assert url == "http://localhost:8001/api/track/impression?aid=1"
    assert rewritten is True
    assert "host" in note and "prefix" in note


def test_no_rewrite_when_already_canonical():
    url, rewritten, _ = tracking.normalize_url("http://localhost:8001/api/track/click?aid=1", S)
    assert url == "http://localhost:8001/api/track/click?aid=1"
    assert rewritten is False


def test_prefix_fix_disabled():
    s = Settings(ad_server_url="http://localhost:8001", tracking_prefix_fix=False)
    url, _, _ = tracking.normalize_url("https://voiseadserver.com/track/imp?a=1", s)
    assert url == "http://localhost:8001/track/imp?a=1"   # host rewritten, prefix left as-is


def test_canonical_builders():
    assert tracking.impression_url(S, aid="a", sid="p", trace_id="t").startswith(
        "http://localhost:8001/api/track/impression?")
    assert "redirect=" in tracking.click_url(S, aid="a", sid="p", redirect="https://x", trace_id="t")
    assert "price=5.5" in tracking.win_url(S, price=5.5, aid="a", pub="p", trace_id="t")
