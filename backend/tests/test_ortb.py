from app.adserver.ortb import build_bid_request, parse_bid_response


def test_build_video_request_ctv_format():
    r = build_bid_request(request_id="r1", tag_id="351511", publisher_id="1192",
                          country="US", device="ctv", browser="chrome", user_id="u1")
    assert r["id"] == "r1"
    assert r["imp"][0]["tagid"] == "351511"
    assert r["imp"][0]["bidfloor"] == 5.775
    assert r["imp"][0]["clickbrowser"] == 0
    assert r["imp"][0]["video"]["w"] == 1920
    assert r["imp"][0]["video"]["h"] == 1080
    assert r["imp"][0]["video"]["minduration"] == 3
    assert r["imp"][0]["video"]["maxduration"] == 300
    assert r["imp"][0]["video"]["protocols"] == [1, 2, 3, 4, 5, 6]
    assert r["imp"][0]["video"]["sequence"] == 1
    assert r["imp"][0]["video"]["boxingallowed"] == 1
    assert r["app"]["name"] == "Philo: Shows, Movies, and Live TV"
    assert r["app"]["publisher"]["id"] == "1192"
    assert r["device"]["devicetype"] == 3
    assert r["device"]["make"] == "Samsung"
    assert r["device"]["os"] == "Tizen"
    assert r["device"]["geo"]["country"] == "USA"
    assert r["device"]["ext"]["ifa_type"] == "tifa"
    assert r["user"] == {}
    assert r["tmax"] == 660
    assert r["bcat"] == ["IAB26"]
    assert r["source"]["fd"] == 1
    assert r["regs"]["coppa"] == 0
    assert r["regs"]["ext"]["us_privacy"] == "1YNN"
    schain = r["source"]["ext"]["schain"]
    assert schain["nodes"][0]["asi"] == "voisetech.com"
    assert schain["nodes"][0]["sid"] == "1192"
    assert schain["nodes"][0]["rid"] == "r1"


def test_build_video_request_mobile_geo():
    r = build_bid_request(request_id="r1", tag_id="t1", publisher_id="p1",
                          country="IN", device="mobile", browser="chrome", user_id="u1")
    assert r["device"]["geo"]["country"] == "IND"
    assert r["device"]["devicetype"] == 4
    assert "app" in r


def test_build_banner_request():
    r = build_bid_request(request_id="r2", tag_id="t", publisher_id=None, country="US",
                          device="desktop", browser="edge", user_id="u", ad_format="display")
    assert "banner" in r["imp"][0]
    assert "site" in r
    assert r["device"]["devicetype"] == 2
    assert "bcat" not in r


def test_privacy_consent_on_user():
    r = build_bid_request(request_id="r3", tag_id="t", publisher_id="p", country="DE",
                          device="mobile", browser="chrome", user_id="u",
                          gdpr=1, consent="CP-test", us_privacy="1YNN")
    assert r["user"]["ext"]["consent"] == "CP-test"
    assert r["regs"]["ext"]["gdpr"] == 1


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
