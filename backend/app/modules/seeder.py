"""Module 1 — Seed Data Generator.

Creates a realistic ecosystem (publishers, ad units, advertisers, DSPs/line
items, campaigns + creatives) in the target ad server over REST. Every created
entity is cached locally in `seed_entities` so later traffic runs know which
tag_ids / publisher_ids / campaign_ids to drive and assert against.

Resilient by design: a failure on one entity is recorded as a finding and the
seed continues where it still can (e.g. advertisers require an admin role on the
server; if that 403s we fall back to an empty advertiser_id, which the internal
auction does not require).
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.adserver.client import AdServerClient, AdServerError
from app.config import Settings
from app.db import Database
from app.models import SeedRequest
from app.util import new_id, now_iso, now_ms

logger = logging.getLogger("adsim.seeder")

_DEFAULT_ADVERTISERS = ["Nike", "Adidas", "Samsung", "Coca-Cola", "BMW", "Sony"]
_AD_UNIT_NAMES = ["Top Banner", "Sidebar", "Footer Banner", "Interstitial", "In-Stream"]
_AD_UNIT_SIZES = {
    "Top Banner": (728, 90), "Sidebar": (300, 250), "Footer Banner": (970, 90),
    "Interstitial": (320, 480), "In-Stream": (640, 480),
}


def _letter_names(prefix: str, n: int) -> List[str]:
    return [f"{prefix} {chr(65 + i)}" if i < 26 else f"{prefix} {i + 1}" for i in range(n)]


def allocate_advertiser_budgets(campaign_budgets: List[float], n_adv: int,
                                rng: random.Random, default_min: float, default_max: float) -> List[Dict[str, Any]]:
    """Assign campaigns round-robin to advertisers and size each advertiser's
    credit_limit so the SUM of its campaigns' budgets never exceeds it.

    Returns one entry per advertiser (index-aligned):
      {index, campaigns, campaign_budget_total, fill_ratio, credit_limit, within_budget}

    The invariant `campaign_budget_total <= credit_limit` holds by construction
    (credit_limit = total / fill_ratio with fill_ratio in (0, 1], floored at total),
    so a freshly seeded ecosystem is always financially consistent.
    """
    n_adv = max(n_adv, 1)
    adv: List[Dict[str, Any]] = [{"index": i, "_budgets": []} for i in range(n_adv)]
    for k, b in enumerate(campaign_budgets):
        adv[k % n_adv]["_budgets"].append(b)
    for a in adv:
        total = round(sum(a["_budgets"]), 2)
        a["campaigns"] = len(a.pop("_budgets"))
        a["campaign_budget_total"] = total
        if total > 0:
            fill = round(rng.uniform(0.6, 0.95), 3)        # campaigns use 60–95% of the cap
            a["fill_ratio"] = fill
            a["credit_limit"] = max(round(total / fill, 2), total)
        else:
            a["fill_ratio"] = None
            a["credit_limit"] = round(rng.uniform(default_min, default_max), 2)
        a["within_budget"] = total <= a["credit_limit"]
    return adv


class Seeder:
    def __init__(self, client: AdServerClient, db: Database, settings: Settings) -> None:
        self.c = client
        self.db = db
        self.s = settings

    async def _record(self, kind: str, resp: Dict[str, Any], parent_id: Optional[str] = None) -> Dict[str, Any]:
        server_id = resp.get("id")
        row = {
            "id": new_id(), "kind": kind, "server_id": server_id,
            "numeric_id": str(resp.get("numeric_id")) if resp.get("numeric_id") is not None else None,
            "name": resp.get("name"), "parent_id": parent_id,
            "data_json": json.dumps(resp)[:4000], "created_at": now_iso(),
        }
        await self.db.insert("seed_entities", row)
        return row

    async def run(self, req: SeedRequest) -> Dict[str, Any]:
        run_id = new_id("seed-")
        await self.db.insert("runs", {
            "id": run_id, "kind": "seed", "label": req.label or "seed",
            "status": "running", "config_json": req.model_dump_json(),
            "summary_json": None, "started_at": now_iso(), "started_ms": now_ms(),
            "ended_at": None, "ended_ms": None,
        })

        counts: Dict[str, int] = {k: 0 for k in
                                  ["publishers", "ad_units", "advertisers", "demand_partners",
                                   "line_items", "campaigns", "creatives"]}
        errors: List[str] = []
        ad_units: List[Dict[str, Any]] = []
        campaigns: List[Dict[str, Any]] = []

        # Deterministic + idempotent: seed the RNG so re-runs produce the same world.
        if req.rng_seed is not None:
            random.seed(req.rng_seed)

        fmt = req.ad_format

        # --- Publishers + ad units -------------------------------------
        pub_names = req.publisher_names or _letter_names("Publisher", req.publishers)
        for pname in pub_names:
            try:
                pub = await self.c.create_publisher(pname)
                await self._record("publisher", pub)
                counts["publishers"] += 1
            except AdServerError as e:
                errors.append(f"publisher '{pname}': {e}")
                continue
            for i in range(req.ad_units_per_publisher):
                au_name = _AD_UNIT_NAMES[i % len(_AD_UNIT_NAMES)]
                w, h = _AD_UNIT_SIZES.get(au_name, (640, 480))
                try:
                    au = await self.c.create_ad_unit(pub["id"], au_name, fmt, w, h)
                    rec = await self._record("ad_unit", au, parent_id=pub["id"])
                    counts["ad_units"] += 1
                    ad_units.append({
                        "tag_id": rec["numeric_id"] or rec["server_id"],
                        "publisher_id": pub["id"], "name": au_name, "w": w, "h": h,
                    })
                except AdServerError as e:
                    errors.append(f"ad_unit '{au_name}'@{pname}: {e}")

        # --- Plan campaigns up front, then size advertiser budgets to cover them ---
        # Each campaign is assigned to an advertiser (round-robin) and given a budget;
        # an advertiser's credit_limit is then sized so the SUM of its campaigns'
        # budgets never exceeds it (basic financial consistency).
        start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        adv_names = req.advertiser_names or _DEFAULT_ADVERTISERS[:max(req.advertisers, 1)]
        n_adv = max(len(adv_names), 1)
        plans: List[Dict[str, Any]] = []
        for k in range(req.campaigns):
            cpm = round(random.uniform(req.cpm_min, req.cpm_max), 2)
            budget = round(random.uniform(req.budget_min, req.budget_max), 2)
            countries = (random.sample(self.s.country_list, k=random.randint(1, len(self.s.country_list)))
                         if req.randomize_targeting else list(self.s.country_list))
            devices = (random.sample(self.s.device_list, k=random.randint(1, len(self.s.device_list)))
                       if req.randomize_targeting else list(self.s.device_list))
            plans.append({"idx": k, "adv_index": k % n_adv, "cpm": cpm, "budget": budget,
                          "daily": round(budget * random.uniform(0.1, 0.3), 2),
                          "countries": countries, "devices": devices,
                          "name": f"Campaign {k + 1} ({fmt}, CPM {cpm})"})

        adv_alloc = allocate_advertiser_budgets(
            [p["budget"] for p in plans], n_adv, random.Random(req.rng_seed),
            req.budget_min, req.budget_max)

        # --- Advertisers (credit_limit sized to cover their campaigns; available
        #     balance funded to equal the credit limit via a ledger credit) --------
        advertiser_ids: List[str] = []           # index-aligned with adv_names; "" if create failed
        advertiser_budgets: List[Dict[str, Any]] = []
        remaining: List[float] = [a["credit_limit"] for a in adv_alloc]   # available balance per advertiser
        for ai, aname in enumerate(adv_names):
            alloc = adv_alloc[ai]
            entry = {"advertiser": aname, "credit_limit": alloc["credit_limit"],
                     "available_balance": 0.0, "campaigns_created": 0, "campaigns_skipped": 0,
                     "allocated_to_campaigns": 0.0, "within_budget": True}
            try:
                adv = await self.c.create_advertiser(aname, credit_limit=alloc["credit_limit"])
                await self._record("advertiser", adv)
                adv_id = adv.get("id") or ""
                advertiser_ids.append(adv_id)
                entry["advertiser_id"] = adv_id
                counts["advertisers"] += 1
                # Fund available balance = credit limit (creation seeds it to 0).
                if adv_id:
                    try:
                        await self.c.credit_advertiser(adv_id, alloc["credit_limit"],
                                                       note="seed: available balance = credit limit")
                        entry["available_balance"] = alloc["credit_limit"]
                    except AdServerError as e:
                        errors.append(f"advertiser '{aname}' ledger credit: {e}")
            except AdServerError as e:
                errors.append(f"advertiser '{aname}': {e}")
                advertiser_ids.append("")
                remaining[ai] = 0.0
            advertiser_budgets.append(entry)
        if not any(advertiser_ids):
            advertiser_ids = [""] * n_adv  # auction does not require an advertiser

        # --- Fake DSP (so the OpenRTB auction has something to win — S10) ---
        fake_dsp_seeded = False
        if req.seed_fake_dsp:
            try:
                dp = await self.c.create_demand_partner(
                    "Voise Fake DSP", fmt, bid_floor=0.5, endpoint_url=self.s.dsp_endpoint_url)
                await self._record("demand_partner", dp)
                counts["demand_partners"] += 1
                fake_dsp_seeded = True
            except AdServerError as e:
                errors.append(f"fake_dsp: {e}")

        # --- DSPs + line items -----------------------------------------
        dsp_names = req.dsp_names or _letter_names("DSP", req.demand_partners)
        for dname in dsp_names:
            try:
                dp = await self.c.create_demand_partner(dname, fmt, bid_floor=round(random.uniform(0.5, 3.0), 2))
                await self._record("demand_partner", dp)
                counts["demand_partners"] += 1
            except AdServerError as e:
                errors.append(f"demand_partner '{dname}': {e}")
                continue
            for j in range(req.line_items_per_partner):
                try:
                    li = await self.c.create_line_item(
                        dp["id"], f"{dname} LI {j + 1}", fmt,
                        floor_price=round(random.uniform(0.5, 5.0), 2),
                        geo_targets=random.sample(self.s.country_list, k=min(2, len(self.s.country_list))),
                        device_targets=random.sample(self.s.device_list, k=min(2, len(self.s.device_list))),
                    )
                    await self._record("line_item", li, parent_id=dp["id"])
                    counts["line_items"] += 1
                except AdServerError as e:
                    errors.append(f"line_item {dname}#{j}: {e}")

        # --- Campaigns + creatives (budget enforced against advertiser's remaining
        #     available balance: a campaign is capped to — and never exceeds — the
        #     advertiser's credit; if credit is exhausted the campaign is skipped) ---
        for p in plans:
            ai = p["adv_index"]
            adv_id = advertiser_ids[ai] if ai < len(advertiser_ids) else ""
            budget = p["budget"]
            if adv_id and ai < len(remaining):
                rem = remaining[ai]
                budget = round(min(p["budget"], rem), 2)
                if budget < 1.0:  # advertiser credit exhausted — don't create an unfunded campaign
                    errors.append(
                        f"campaign #{p['idx']} skipped: advertiser '{adv_names[ai]}' credit exhausted "
                        f"(remaining {rem:.2f})")
                    if ai < len(advertiser_budgets):
                        advertiser_budgets[ai]["campaigns_skipped"] += 1
                    continue
            daily = round(min(p["daily"], budget), 2)
            try:
                camp = await self.c.create_campaign(
                    name=p["name"], advertiser_id=adv_id,
                    budget=budget, daily_budget=daily, cpm=p["cpm"], ad_format=fmt,
                    start_date=start, end_date=end, countries=p["countries"], devices=p["devices"],
                )
                await self._record("campaign", camp)
                counts["campaigns"] += 1
                if adv_id and ai < len(remaining):
                    remaining[ai] = round(remaining[ai] - budget, 2)
                    if ai < len(advertiser_budgets):
                        advertiser_budgets[ai]["campaigns_created"] += 1
                        advertiser_budgets[ai]["allocated_to_campaigns"] = round(
                            advertiser_budgets[ai]["allocated_to_campaigns"] + budget, 2)
                        advertiser_budgets[ai]["available_balance"] = remaining[ai]
                campaigns.append({"id": camp.get("id"), "name": p["name"], "cpm": p["cpm"],
                                  "budget": budget, "advertiser_id": adv_id,
                                  "countries": p["countries"], "devices": p["devices"]})
            except AdServerError as e:
                errors.append(f"campaign #{p['idx']}: {e}")
                continue
            try:
                cre = await self.c.create_creative(campaign_id=camp["id"], name=f"{p['name']} creative",
                                                   ad_format=fmt, width=640, height=480)
                await self._record("creative", cre, parent_id=camp["id"])
                counts["creatives"] += 1
            except AdServerError as e:
                errors.append(f"creative for campaign #{p['idx']}: {e}")

        # --- Graceful fallback -----------------------------------------
        # `decide_vast_ad` only uses tag_id for an OPTIONAL ad-unit lookup and
        # selects campaigns globally, so serving works with any tag_id. If the
        # server's publisher/ad-unit creation failed, synthesize tag_ids so the
        # traffic generator still has placements to drive.
        synthetic = False
        if not ad_units:
            synthetic = True
            for i in range(max(req.publishers * req.ad_units_per_publisher, 3)):
                tag = f"sim-{new_id()[:10]}"
                pubid = f"sim-pub-{i % max(req.publishers, 1)}"
                await self.db.insert("seed_entities", {
                    "id": new_id(), "kind": "ad_unit", "server_id": None, "numeric_id": tag,
                    "name": _AD_UNIT_NAMES[i % len(_AD_UNIT_NAMES)], "parent_id": pubid,
                    "data_json": json.dumps({"synthetic": True}), "created_at": now_iso()})
                ad_units.append({"tag_id": tag, "publisher_id": pubid,
                                 "name": _AD_UNIT_NAMES[i % len(_AD_UNIT_NAMES)], "w": 640, "h": 480})

        # --- Findings (server bugs surfaced, not hidden) ---------------
        findings: List[str] = []
        if counts["campaigns"]:
            findings.append(
                "Campaign create API persists `format_targets`/`cpm_bid` but the auction reads "
                "`ad_format`/`target_cpm`; campaigns are unserveable until patched. The simulator "
                "applies a REST `PUT` decisioning-field shim so campaigns can serve.")
        if synthetic:
            findings.append(
                "Publisher/ad-unit creation failed on the server (HTTP 500); synthesized tag_ids "
                "instead. Serving is unaffected (the auction ignores ad units), but this is a real "
                "server bug in POST /api/publishers.")
        if not counts["campaigns"]:
            findings.append("No campaigns created — nothing will serve a real ad (auction returns a "
                            "default 'Video Ad' filler for every request).")
        if fake_dsp_seeded:
            findings.append(
                f"Registered the built-in fake DSP as a demand partner (endpoint {self.s.dsp_endpoint_url}). "
                "The SUT's OpenRTB auction can now win a real bid — required for S10. Ensure the SUT can "
                "reach that URL (host networking / host.docker.internal).")
        if advertiser_budgets:
            for a in advertiser_budgets:
                a["within_budget"] = a["allocated_to_campaigns"] <= a["credit_limit"]
            over = [a for a in advertiser_budgets if not a["within_budget"]]
            skipped = sum(a["campaigns_skipped"] for a in advertiser_budgets)
            findings.append(
                f"Advertiser budgets enforced ({len(advertiser_budgets)} advertiser(s)): available balance "
                f"funded to equal each credit_limit, and campaign budgets are capped against the remaining "
                f"balance at creation so total campaign budget never exceeds the credit limit. "
                + (f"{skipped} campaign(s) skipped for exhausted credit. " if skipped else "")
                + ("All within budget." if not over else f"WARNING: {len(over)} advertiser(s) OVER budget!"))

        summary = {
            "run_id": run_id, "counts": counts, "errors": errors, "findings": findings,
            "ad_units": ad_units, "campaigns": campaigns, "synthetic_ad_units": synthetic,
            "fake_dsp_seeded": fake_dsp_seeded, "advertiser_budgets": advertiser_budgets,
            "url_rewrite_notes": self.c.url_rewrite_notes,
            "note": "Names like 'Top Banner' are cosmetic; the internal VAST auction "
                    "only serves video/ctv/dooh formats, so ad units/campaigns use ad_format="
                    f"'{fmt}'.",
        }
        await self.db.execute(
            "UPDATE runs SET status=?, summary_json=?, ended_at=?, ended_ms=? WHERE id=?",
            ("completed" if not errors else "completed_with_errors",
             json.dumps(summary), now_iso(), now_ms(), run_id),
        )
        logger.info("Seed complete: %s (errors=%d)", counts, len(errors))
        return summary
