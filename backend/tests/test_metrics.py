import json
import pytest
from app.db import Database
from app.modules import metrics


@pytest.fixture
async def db():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


async def _seed(d):
    await d.insert("seed_entities", {
        "id": "se1", "kind": "campaign", "server_id": "c1", "numeric_id": "1",
        "name": "Camp X", "parent_id": None, "data_json": json.dumps({"budget": 1000.0}),
        "created_at": "now"})
    reqs = [
        ("r1", 1, 200, "Camp X", 100.0), ("r2", 1, 200, "Camp X", 120.0),
        ("r3", 1, 200, "Camp X", 80.0), ("r4", 0, 200, None, 200.0),
    ]
    for rid, filled, sc, camp, lat in reqs:
        await d.insert("ad_requests", {
            "id": rid, "run_id": "run1", "ts": "t", "ts_ms": 1000 + int(rid[1]) * 1000,
            "protocol": "vast", "tag_id": "tag", "publisher_id": "p", "ad_unit_id": "tag",
            "country": "IN", "device": "mobile", "browser": "chrome", "user_id": "u",
            "status_code": sc, "latency_ms": lat, "filled": filled,
            "winner_campaign": camp, "winner_campaign_id": None, "winner_creative_id": None,
            "price": 50.0, "no_fill_reason": None, "trace_id": rid})
    evts = [("e1", "impression", 1, 50.0), ("e2", "impression", 1, 50.0), ("e3", "click", 1, None)]
    for eid, typ, ok, price in evts:
        await d.insert("events", {
            "id": eid, "run_id": "run1", "ts": "t", "ts_ms": 2000, "type": typ,
            "request_id": "r1", "tag_id": "tag", "publisher_id": "p", "user_id": "u",
            "campaign_id": "c1", "campaign": "Camp X", "price": price, "url": "u",
            "status_code": 200, "ok": ok, "note": None, "trace_id": "r1"})


async def test_overview(db):
    await _seed(db)
    o = await metrics.overview(db)
    assert o["total_requests"] == 4
    assert o["total_fills"] == 3
    assert o["total_impressions"] == 2
    assert o["total_clicks"] == 1
    assert o["fill_rate"] == 0.75
    assert o["ctr"] == 0.5


async def test_campaign_metrics(db):
    await _seed(db)
    rows = await metrics.campaign_metrics(db)
    cx = next(r for r in rows if r["campaign"] == "Camp X")
    assert cx["impressions"] == 2
    assert cx["clicks"] == 1
    # spend = sum(impression prices)/1000 = (50+50)/1000 = 0.1
    assert cx["spend"] == 0.1
    assert cx["budget"] == 1000.0
    assert cx["remaining_budget"] == 999.9


async def test_auction_metrics(db):
    await _seed(db)
    a = await metrics.auction_metrics(db)
    assert a["avg_latency_ms"] == 125.0   # (100+120+80+200)/4
    assert a["p95_latency_ms"] > 0
    win = {w["campaign"]: w["wins"] for w in a["win_distribution"]}
    assert win.get("Camp X") == 3


async def test_timeseries(db):
    await _seed(db)
    ts = await metrics.timeseries(db, bucket_ms=1000)
    assert len(ts) >= 1
    total_req = sum(p["requests"] for p in ts)
    assert total_req == 4
