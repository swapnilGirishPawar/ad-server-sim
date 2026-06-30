"""ads.txt / sellers.json / SupplyChain validator tests."""
from app.adserver import ortb, supplychain


def test_ads_txt_valid():
    text = ("# comment\n"
            "voisetech.com, 1192, DIRECT, abc123\n"
            "dsp-a.com, 55, RESELLER\n"
            "CONTACT=adops@voisetech.com\n")
    out = supplychain.validate_ads_txt(text)
    assert len(out["records"]) == 2
    assert "1192" in out["seller_ids"]
    assert not any(f["severity"] == "fail" for f in out["findings"])


def test_ads_txt_bad_relationship_and_short_line():
    text = "voisetech.com, 1, AFFILIATE\nbroken line only\n"
    out = supplychain.validate_ads_txt(text)
    checks = {f["check"] for f in out["findings"] if f["severity"] == "fail"}
    assert "relationship" in checks
    assert "record_format" in checks


def test_sellers_json_valid_and_consistency():
    obj = {"version": "1.0", "contact_email": "adops@voisetech.com",
           "identifiers": [{"name": "TAG-ID", "value": "9009"}],
           "sellers": [{"seller_id": "1192", "seller_type": "PUBLISHER"}]}
    out = supplychain.validate_sellers_json(obj, ads_txt_seller_ids=["1192"])
    assert out["seller_ids"] == ["1192"]
    assert not any(f["severity"] == "fail" for f in out["findings"])


def test_sellers_json_missing_sellers_fails():
    out = supplychain.validate_sellers_json({"version": "1.0", "sellers": []})
    assert any(f["check"] == "sellers" and f["severity"] == "fail" for f in out["findings"])


def test_schain_present_on_built_request():
    req = ortb.build_bid_request(request_id="r1", tag_id="t", publisher_id="p1",
                                 country="US", device="desktop", browser="chrome", user_id="u")
    findings = supplychain.validate_schain(req)
    assert not any(f["severity"] == "fail" for f in findings)


def test_schain_absent_fails():
    findings = supplychain.validate_schain({"source": {}})
    assert any(f["check"] == "present" and f["severity"] == "fail" for f in findings)
