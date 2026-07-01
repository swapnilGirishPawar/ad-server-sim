"""Advertiser-budget allocation: total campaign budget must never exceed the
advertiser's credit_limit (the seeder's financial-consistency invariant)."""
import random

from app.modules.seeder import allocate_advertiser_budgets


def test_total_campaign_budget_never_exceeds_credit_limit():
    rng = random.Random(1337)
    budgets = [rng.uniform(500, 5000) for _ in range(13)]
    alloc = allocate_advertiser_budgets(budgets, n_adv=3, rng=rng, default_min=500, default_max=5000)
    assert len(alloc) == 3
    for a in alloc:
        assert a["campaign_budget_total"] <= a["credit_limit"]
        assert a["within_budget"] is True
    # every campaign is assigned exactly once
    assert sum(a["campaigns"] for a in alloc) == 13


def test_advertiser_with_no_campaigns_still_gets_a_credit_limit():
    rng = random.Random(7)
    alloc = allocate_advertiser_budgets([100.0], n_adv=4, rng=rng, default_min=500, default_max=5000)
    empty = [a for a in alloc if a["campaigns"] == 0]
    assert empty, "expected some advertisers with no campaigns"
    for a in empty:
        assert a["credit_limit"] >= 500 and a["within_budget"] is True


def test_round_robin_is_balanced():
    rng = random.Random(1)
    alloc = allocate_advertiser_budgets([1.0] * 10, n_adv=3, rng=rng, default_min=1, default_max=2)
    counts = sorted(a["campaigns"] for a in alloc)
    assert counts == [3, 3, 4]  # 10 campaigns across 3 advertisers


def test_deterministic_for_same_seed():
    b = [1000.0, 2000.0, 3000.0, 4000.0]
    a1 = allocate_advertiser_budgets(b, 2, random.Random(42), 500, 5000)
    a2 = allocate_advertiser_budgets(b, 2, random.Random(42), 500, 5000)
    assert [x["credit_limit"] for x in a1] == [x["credit_limit"] for x in a2]


# --- Integration: full seeder run against a fake client (offline) -------------
import itertools

import pytest

from app.config import Settings
from app.db import Database
from app.models import SeedRequest
from app.modules.seeder import Seeder


class FakeClient:
    """Minimal stand-in for AdServerClient that records what the seeder creates."""
    def __init__(self):
        self._ids = itertools.count(1)
        self.url_rewrite_notes = {}
        self.advertisers = {}     # id -> credit_limit
        self.credited = {}        # id -> amount funded into available balance
        self.campaigns = []       # {advertiser_id, budget}

    async def create_publisher(self, name, domain=""):
        return {"id": f"pub-{next(self._ids)}", "name": name}

    async def create_ad_unit(self, publisher_id, name, ad_format, width, height):
        i = next(self._ids)
        return {"id": f"au-{i}", "numeric_id": str(1000 + i), "name": name}

    async def create_advertiser(self, name, credit_limit=0.0):
        aid = f"adv-{next(self._ids)}"
        self.advertisers[aid] = credit_limit
        return {"id": aid, "name": name, "credit_limit": credit_limit}

    async def credit_advertiser(self, advertiser_id, amount, note=""):
        self.credited[advertiser_id] = self.credited.get(advertiser_id, 0.0) + amount
        return {"amount": amount}

    async def create_demand_partner(self, name, ad_format, bid_floor, endpoint_url=""):
        return {"id": f"dp-{next(self._ids)}", "name": name}

    async def create_line_item(self, partner_id, name, ad_format, floor_price, geo_targets, device_targets):
        return {"id": f"li-{next(self._ids)}", "name": name}

    async def create_campaign(self, *, name, advertiser_id, budget, daily_budget, cpm,
                              ad_format, start_date, end_date, countries, devices):
        self.campaigns.append({"advertiser_id": advertiser_id, "budget": budget})
        return {"id": f"camp-{next(self._ids)}", "name": name}

    async def create_creative(self, *, campaign_id, name, ad_format, width, height):
        return {"id": f"cr-{next(self._ids)}", "name": name}


@pytest.fixture
async def memdb():
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


async def test_seeder_keeps_campaigns_within_advertiser_credit(memdb):
    fake = FakeClient()
    s = Settings(ad_server_url="http://localhost:8001")
    summary = await Seeder(fake, memdb, s).run(
        SeedRequest(advertisers=3, campaigns=9, demand_partners=1, seed_fake_dsp=False))

    # 1) Available balance was funded to equal the credit limit for every advertiser.
    for aid, credit in fake.advertisers.items():
        assert fake.credited.get(aid) == credit

    # 2) Sum of created campaign budgets per advertiser never exceeds its credit limit.
    spent = {}
    for c in fake.campaigns:
        spent[c["advertiser_id"]] = spent.get(c["advertiser_id"], 0.0) + c["budget"]
    for aid, total in spent.items():
        assert total <= fake.advertisers[aid] + 1e-6, f"{aid} overspent its credit"

    # 3) The summary reports the invariant holds.
    assert all(a["within_budget"] for a in summary["advertiser_budgets"])
    assert all(a["available_balance"] >= 0 for a in summary["advertiser_budgets"])
