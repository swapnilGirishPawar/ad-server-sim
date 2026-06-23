from app.adserver.ortb import build_bid_request, parse_bid_response


def test_build_video_request():
    r = build_bid_request(request_id="r1", tag_id="t1", publisher_id="p1",
                          country="IN", device="mobile", browser="chrome", user_id="u1")
    assert r["id"] == "r1"
    assert r["imp"][0]["tagid"] == "t1"
    assert r["imp"][0]["video"]["w"] == 640
    assert r["device"]["geo"]["country"] == "IND"   # alpha-2 -> alpha-3
    assert r["device"]["devicetype"] == 4           # mobile
    assert r["user"]["id"] == "u1"


def test_build_banner_request():
    r = build_bid_request(request_id="r2", tag_id="t", publisher_id=None, country="US",
                          device="desktop", browser="edge", user_id="u", ad_format="display")
    assert "banner" in r["imp"][0]
    assert r["device"]["devicetype"] == 2


def test_parse_no_bid_204():
    out = parse_bid_response(204, None)
    assert out["filled"] is False and out["no_fill_reason"] == "no_bid_204"


def test_parse_empty_seatbid():
    out = parse_bid_response(200, {"seatbid": []})
    assert out["filled"] is False


def test_parse_best_bid():
    body = {"seatbid": [
        {"bid": [{"price": 1.5, "adm": "a", "crid": "c1", "cid": "camp1"}]},
        {"bid": [{"price": 3.2, "adm": "b", "nurl": "http://n", "crid": "c2", "cid": "camp2"}]},
    ]}
    out = parse_bid_response(200, body)
    assert out["filled"] is True
    assert out["price"] == 3.2
    assert out["campaign_id"] == "camp2"
    assert out["creative_id"] == "c2"
    assert out["nurl"] == "http://n"


def test_parse_ignores_zero_price():
    out = parse_bid_response(200, {"seatbid": [{"bid": [{"price": 0, "adm": "x"}]}]})
    assert out["filled"] is False
