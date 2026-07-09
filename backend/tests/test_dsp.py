"""Mock DSP bidding tests — offline via TestClient (no SUT needed)."""
import copy

import pytest
from starlette.testclient import TestClient

from app.adserver import validators
from app.dsp import router as dsp

_DEFAULTS = copy.deepcopy(dsp.CONFIG)


@pytest.fixture
def client():
    dsp.CONFIG.clear()
    dsp.CONFIG.update(copy.deepcopy(_DEFAULTS))
    dsp.CONFIG["jitter"] = 0.0  # deterministic pricing for assertions
    app = dsp.create_dsp_app()
    with TestClient(app) as c:
        yield c


def _video_req(imp_id="1", floor=1.0, n=1):
    return {"id": "req-1", "cur": ["USD"],
            "imp": [{"id": str(i + 1), "bidfloor": floor, "bidfloorcur": "USD",
                     "video": {"w": 640, "h": 480, "mimes": ["video/mp4"]}} for i in range(n)],
            "site": {"id": "s", "domain": "sim.local", "publisher": {"id": "p"}},
            "device": {"devicetype": 2, "geo": {"country": "USA"}},
            "regs": {"ext": {"gdpr": 1, "us_privacy": "1YNN"}}}


def test_video_bid_is_spec_valid(client):
    req = _video_req(floor=1.0)
    r = client.post("/dsp/bid/tag1", json=req)
    assert r.status_code == 200
    body = r.json()
    bid = body["seatbid"][0]["bid"][0]
    assert body["id"] == "req-1" and body["cur"] == "USD"
    assert body["seatbid"][0]["seat"] == "voise-fake-dsp"
    assert bid["impid"] == "1"
    assert bid["price"] >= 1.0            # clears the floor
    assert bid["mtype"] == 2              # video (2.6 dual-compat)
    assert bid["protocol"] == 7           # §4.2.3 / List 5.8: VAST markup protocol
    assert bid["iurl"]                    # §4.2.3 preview image
    assert bid["crid"] and bid["adomain"]
    assert "${AUCTION_PRICE}" in bid["nurl"]
    # OpenRTB notice URLs must not carry the VAST [CACHEBUSTING] macro (§4.4)...
    assert "[CACHEBUSTING]" not in bid["nurl"] and "[CACHEBUSTING]" not in bid["burl"]
    # ...but the VAST adm still should (correct there).
    assert "[CACHEBUSTING]" in bid["adm"]
    assert bid["adm"].startswith("<VAST")
    # our own validator agrees the response conforms
    v = validators.validate_bid_response(200, body, request=req)
    assert v.filled and v.conformant


def test_no_bid_mode_emits_nbr_with_empty_seatbid(client):
    dsp.CONFIG["mode"] = "no_bid"
    r = client.post("/dsp/bid", json=_video_req())
    assert r.status_code == 200
    body = r.json()
    assert body["nbr"] == 0               # 0 = Unknown/other (List 5.24)
    assert body["seatbid"] == []          # §7.1 canonical no-bid-with-reason shape


def test_malformed_json_returns_400(client):
    r = client.post("/dsp/bid", content=b"{not valid json",
                    headers={"content-type": "application/json"})
    assert r.status_code == 400           # §2.1 malformed payload -> 400
    assert r.content == b""


def test_no_bid_mode_bare_204_when_configured(client):
    dsp.CONFIG["mode"] = "no_bid"
    dsp.CONFIG["emit_nbr"] = False
    r = client.post("/dsp/bid", json=_video_req())
    assert r.status_code == 204
    assert r.content == b""


def test_respect_floor_no_bid_when_valuation_below_floor(client):
    dsp.CONFIG["price"] = 1.0
    dsp.CONFIG["max_cpm"] = 5.0
    r = client.post("/dsp/bid", json=_video_req(floor=50.0))
    # valuation capped at 5.0 < floor 50 -> no-bid (204, or 200 with nbr + empty seatbid)
    assert (r.status_code == 204) or (r.json().get("nbr") is not None and not r.json().get("seatbid"))


def test_pod_request_yields_one_bid_per_imp(client):
    r = client.post("/dsp/bid", json=_video_req(n=3))
    bids = r.json()["seatbid"][0]["bid"]
    assert len(bids) == 3
    assert {b["impid"] for b in bids} == {"1", "2", "3"}


def test_banner_bid_has_mtype_1(client):
    req = {"id": "r", "imp": [{"id": "1", "bidfloor": 0.5, "banner": {"w": 300, "h": 250}}],
           "site": {"id": "s"}, "device": {"devicetype": 2}}
    r = client.post("/dsp/bid", json=req)
    bid = r.json()["seatbid"][0]["bid"][0]
    assert bid["mtype"] == 1 and bid["w"] == 300 and bid["h"] == 250


def test_deal_id_echoed_when_pmp_present(client):
    req = {"id": "r", "imp": [{"id": "1", "bidfloor": 1.0, "video": {"w": 640, "h": 480},
                               "pmp": {"deals": [{"id": "DEAL-123"}]}}],
           "site": {"id": "s"}, "device": {"devicetype": 2}}
    r = client.post("/dsp/bid", json=req)
    assert r.json()["seatbid"][0]["bid"][0]["dealid"] == "DEAL-123"
