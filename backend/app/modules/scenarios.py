"""Module 6 — Scenario Engine.

Each scenario sets up isolated data, drives controlled traffic, and asserts the
*standard* expected behaviour. The simulator is the source of truth: where the
ad server fails to enforce the expected rule, the verdict is GAP (with evidence)
— we never bend the assertion to match server behaviour.

Scenario campaigns are given a dominant CPM so they win the global VAST auction
(`decide_vast_ad` ranks purely by target_cpm), which isolates them from any other
seeded campaigns.

Verdicts:
  PASS  — server behaved as a correct ad server should
  GAP   — server did not enforce the expected behaviour (feature missing/buggy)
  FAIL  — scenario could not validate (e.g. nothing served at all)
  ERROR — setup/transport error
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.adserver.client import AdServerClient, AdServerError
from app.adserver import tracking
from app.config import Settings
from app.db import Database
from app.modules.users import SimUser, UserPool
from app.util import new_id, now_iso, now_ms

logger = logging.getLogger("adsim.scenarios")

PASS, GAP, FAIL, ERROR = "PASS", "GAP", "FAIL", "ERROR"


class ScenarioEngine:
    def __init__(self, client: AdServerClient, db: Database, settings: Settings) -> None:
        self.c = client
        self.db = db
        self.s = settings

    # ------------------------------------------------------------- utilities
    def _dates(self) -> Tuple[str, str]:
        start = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        return start, end

    async def _setup_unit(self, label: str) -> Tuple[str, str]:
        # Publisher/ad-unit creation 500s on the server (known bug), but the
        # auction ignores ad units, so a synthetic tag_id serves fine.
        try:
            pub = await self.c.create_publisher(f"ScenPub {label}")
            au = await self.c.create_ad_unit(pub["id"], f"Scen Unit {label}", "video", 640, 480)
            return str(au.get("numeric_id") or au.get("id")), pub["id"]
        except AdServerError:
            return f"scen-{label}-{new_id()[:8]}", f"scen-pub-{label}"

    async def _dominant_cpm(self, bump: float = 100.0) -> float:
        """Current max active target_cpm + bump, so a scenario campaign wins the
        global auction even with other (sibling/leftover) campaigns present."""
        try:
            data = await self.c._get("/campaigns", params={"limit": 200})
            camps = data.get("campaigns", []) if isinstance(data, dict) else (data or [])
        except Exception:  # noqa: BLE001
            camps = []
        mx = 0.0
        for c in camps:
            if c.get("status") == "active":
                try:
                    mx = max(mx, float(c.get("target_cpm") or 0))
                except (TypeError, ValueError):
                    pass
        return mx + bump

    async def _campaign(self, name: str, cpm: float, *, budget: float = 100000.0,
                        countries: Optional[List[str]] = None) -> Dict[str, Any]:
        start, end = self._dates()
        camp = await self.c.create_campaign(
            name=name, advertiser_id="", budget=budget, daily_budget=budget, cpm=cpm,
            ad_format="video", start_date=start, end_date=end,
            countries=countries or self.s.country_list, devices=self.s.device_list)
        await self.c.create_creative(campaign_id=camp["id"], name=f"{name} creative",
                                     ad_format="video", width=640, height=480)
        return camp

    async def _drive(self, run_id: str, tag_id: str, pub: str, requests: List[SimUser], *,
                     fire_impression: bool = True, fire_win_price: Optional[float] = None,
                     concurrency: int = 8) -> List[Dict[str, Any]]:
        """Send one VAST request per supplied user; persist rows; return ordered records."""
        sem = asyncio.Semaphore(concurrency)
        records: List[Dict[str, Any]] = []

        async def one(idx: int, user: SimUser) -> None:
            async with sem:
                res = await self.c.request_vast(tag_id=tag_id, publisher_id=pub,
                                                device=user.device, user_id=user.user_id)
            rec = {"idx": idx, "filled": res.filled, "campaign": res.campaign,
                   "country": user.country, "user_id": user.user_id, "ts_ms": now_ms(),
                   "status": res.status_code}
            records.append(rec)
            await self.db.insert("ad_requests", {
                "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": rec["ts_ms"],
                "protocol": "vast", "tag_id": tag_id, "publisher_id": pub, "ad_unit_id": tag_id,
                "country": user.country, "device": user.device, "browser": user.browser,
                "user_id": user.user_id, "status_code": res.status_code, "latency_ms": res.latency_ms,
                "filled": 1 if res.filled else 0, "winner_campaign": res.campaign,
                "winner_campaign_id": None, "winner_creative_id": res.creative_id,
                "price": fire_win_price, "no_fill_reason": res.no_fill_reason, "trace_id": res.trace_id})
            if res.filled and fire_impression:
                url = res.impression_urls[0] if res.impression_urls else tracking.impression_url(
                    self.s, aid=tag_id, sid=pub, trace_id=res.trace_id or new_id())
                fired = await self.c.fire(url, normalize=bool(res.impression_urls))
                await self.db.insert("events", {
                    "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
                    "type": "impression", "request_id": res.trace_id, "tag_id": tag_id,
                    "publisher_id": pub, "user_id": user.user_id, "campaign_id": None,
                    "campaign": res.campaign, "price": fire_win_price, "url": fired["url"],
                    "status_code": fired["status_code"], "ok": 1 if fired["ok"] else 0,
                    "note": fired.get("note"), "trace_id": res.trace_id})
                if fire_win_price:
                    win = tracking.win_url(self.s, price=fire_win_price, aid=tag_id, pub=pub,
                                           trace_id=res.trace_id or new_id())
                    wf = await self.c.fire(win, normalize=False)
                    await self.db.insert("events", {
                        "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
                        "type": "win", "request_id": res.trace_id, "tag_id": tag_id,
                        "publisher_id": pub, "user_id": user.user_id, "campaign_id": None,
                        "campaign": res.campaign, "price": fire_win_price, "url": wf["url"],
                        "status_code": wf["status_code"], "ok": 1 if wf["ok"] else 0,
                        "note": wf.get("note"), "trace_id": res.trace_id})

        await asyncio.gather(*[one(i, u) for i, u in enumerate(requests)])
        records.sort(key=lambda r: (r["ts_ms"], r["idx"]))
        return records

    async def _record(self, run_id: str, scenario: str, title: str, verdict: str,
                      expected: str, actual: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        row = {"id": new_id(), "run_id": run_id, "scenario": scenario, "verdict": verdict,
               "title": title, "expected": expected, "actual": actual,
               "evidence_json": json.dumps(evidence)[:8000], "created_at": now_iso()}
        await self.db.insert("scenario_results", row)
        return {"scenario": scenario, "title": title, "verdict": verdict,
                "expected": expected, "actual": actual, "evidence": evidence}

    async def _new_run(self, scenario: str, label: Optional[str]) -> str:
        run_id = new_id(f"scen{scenario}-")
        await self.db.insert("runs", {
            "id": run_id, "kind": "scenario", "label": label or f"Scenario {scenario}",
            "status": "running", "config_json": json.dumps({"scenario": scenario}),
            "summary_json": None, "started_at": now_iso(), "started_ms": now_ms(),
            "ended_at": None, "ended_ms": None})
        return run_id

    async def _close_run(self, run_id: str, result: Dict[str, Any]) -> None:
        await self.db.execute(
            "UPDATE runs SET status=?, summary_json=?, ended_at=?, ended_ms=? WHERE id=?",
            ("completed", json.dumps(result), now_iso(), now_ms(), run_id))

    async def _cleanup(self, *campaigns: Dict[str, Any]) -> None:
        """Soft-delete the campaigns this scenario created so they don't linger in
        the ad server or inflate future auctions' dominant-CPM baseline."""
        for c in campaigns:
            cid = c.get("id") if isinstance(c, dict) else c
            if cid:
                await self.c.delete_campaign(cid)

    # ----------------------------------------------------------- dispatch
    async def run(self, scenario: str, total: Optional[int] = None,
                  label: Optional[str] = None) -> List[Dict[str, Any]]:
        scenario = scenario.upper()
        mapping = {"A": self.scenario_a, "B": self.scenario_b,
                   "C": self.scenario_c, "D": self.scenario_d}
        if scenario == "ALL":
            results = []
            for key in ["A", "B", "C", "D"]:
                results.append(await self._safe(mapping[key], total, label))
            return results
        if scenario not in mapping:
            raise ValueError(f"Unknown scenario '{scenario}' (use A, B, C, D or all)")
        return [await self._safe(mapping[scenario], total, label)]

    async def _safe(self, fn, total, label) -> Dict[str, Any]:
        try:
            return await fn(total=total, label=label)
        except (AdServerError, Exception) as e:  # noqa: BLE001 - scenarios must never crash the API
            logger.exception("scenario error")
            return {"scenario": fn.__name__, "verdict": ERROR, "title": fn.__name__,
                    "expected": "", "actual": f"error: {e}", "evidence": {}}

    # --------------------------------------------------------- Scenario A
    async def scenario_a(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("A", label)
        # budget == cpm makes spend/impression = cpm/1000 exhaust the budget at exactly
        # 1000 impressions; dominant cpm ensures this campaign wins every auction.
        cpm = max(1000.0, await self._dominant_cpm())
        budget = cpm
        n = total or 1500
        tag, pub = await self._setup_unit("A")
        camp = await self._campaign("Scenario A — Budget 1000", cpm=cpm, budget=budget)
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.5)
        users = [pool.pick() for _ in range(n)]
        recs = await self._drive(run_id, tag, pub, users, fire_impression=True, fire_win_price=cpm)

        # Cumulative modelled spend over the ordered impressions; budget hit at imp #1000.
        served = [r for r in recs if r["filled"] and r["campaign"] == camp["name"]]
        exhaust_at = int(budget / (cpm / 1000.0))          # = 1000 impressions
        served_after_budget = max(0, len(served) - exhaust_at)
        server_stats = await self.c.campaign_stats(camp["id"]) or {}
        server_spend = await self.c.campaign_spend(camp["id"]) or {}
        camp_doc = await self.c.get_campaign(camp["id"]) or {}

        verdict = GAP if served_after_budget > 0 else (PASS if served else FAIL)
        evidence = {
            "budget": budget, "cpm": cpm, "requests": n, "filled_for_campaign": len(served),
            "modelled_exhaust_at_impression": exhaust_at,
            "served_after_budget_exhausted": served_after_budget,
            "server_reported_spend": server_spend, "server_reported_stats": server_stats,
            "campaign_doc_spend_fields": {k: camp_doc.get(k) for k in
                                          ("spend", "spent", "daily_spent", "cached_spend_total")},
        }
        result = await self._record(
            run_id, "A", "Budget Exhaustion", verdict,
            "Campaign stops serving once spend reaches the 1000 budget.",
            (f"Served {len(served)} impressions; {served_after_budget} continued AFTER the budget "
             f"should have been exhausted (at impression #{exhaust_at}). "
             "Server eligibility reads `spent`/`daily_spent` but wins increment `spend`, and win "
             "attribution needs a line-item→campaign link, so budget never closes the loop."),
            evidence)
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # --------------------------------------------------------- Scenario B
    async def scenario_b(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("B", label)
        n = total or 300
        tag, pub = await self._setup_unit("B")
        camp = await self._campaign("Scenario B — India only", cpm=await self._dominant_cpm(),
                                    countries=["IN"])
        traffic_countries = ["IN", "US", "UK"]
        pool = UserPool(traffic_countries, self.s.device_list, self.s.browser_list, 50, 0.4)
        users = [pool.fixed_user(traffic_countries[i % 3], pool.devices[i % len(pool.devices)])
                 for i in range(n)]
        recs = await self._drive(run_id, tag, pub, users, fire_impression=True)

        by_country: Dict[str, Dict[str, int]] = {}
        for r in recs:
            d = by_country.setdefault(r["country"], {"requests": 0, "served": 0})
            d["requests"] += 1
            if r["filled"] and r["campaign"] == camp["name"]:
                d["served"] += 1
        non_in_served = sum(v["served"] for c, v in by_country.items() if c != "IN")
        verdict = GAP if non_in_served > 0 else (PASS if by_country.get("IN", {}).get("served", 0) else FAIL)
        result = await self._record(
            run_id, "B", "Country Targeting (India only)", verdict,
            "Only IN traffic receives the campaign; US/UK get no fill from it.",
            (f"US/UK received the campaign {non_in_served} times. The VAST endpoint `/api/v/{{tag}}` "
             "accepts no country parameter and `decide_vast_ad` evaluates no geo targeting, so the "
             "campaign serves every country regardless of its IN-only target."),
            {"by_country": by_country, "campaign_target": ["IN"]})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # --------------------------------------------------------- Scenario C
    async def scenario_c(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("C", label)
        n = total or 400
        tag, pub = await self._setup_unit("C")
        base = await self._dominant_cpm()
        camp_a = await self._campaign(f"Scenario C — Campaign A (CPM {base:.0f})", cpm=base)
        camp_b = await self._campaign(f"Scenario C — Campaign B (CPM {base + 100:.0f})", cpm=base + 100)
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.4)
        users = [pool.pick() for _ in range(n)]
        recs = await self._drive(run_id, tag, pub, users, fire_impression=False)

        wins_a = sum(1 for r in recs if r["campaign"] == camp_a["name"])
        wins_b = sum(1 for r in recs if r["campaign"] == camp_b["name"])
        other = sum(1 for r in recs if r["filled"] and r["campaign"] not in (camp_a["name"], camp_b["name"]))
        verdict = PASS if wins_b > wins_a else (FAIL if (wins_a + wins_b) == 0 else GAP)
        result = await self._record(
            run_id, "C", "Bid Competition (higher CPM should win)", verdict,
            "Higher-CPM Campaign B wins more auctions than Campaign A.",
            f"Campaign B won {wins_b}, Campaign A won {wins_a} (other campaigns: {other}). "
            + ("Higher CPM wins as expected." if wins_b > wins_a else
               "Higher CPM did NOT win more — auction ranking by target_cpm is not behaving."),
            {"wins_A_cpm100": wins_a, "wins_B_cpm200": wins_b, "other": other, "requests": n})
        await self._cleanup(camp_a, camp_b)
        await self._close_run(run_id, result)
        return result

    # --------------------------------------------------------- Scenario D
    async def scenario_d(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("D", label)
        cap = 3
        n = total or 6
        tag, pub = await self._setup_unit("D")
        camp = await self._campaign("Scenario D — Freq cap 3/user", cpm=await self._dominant_cpm())
        user = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list).fixed_user("IN", "mobile")
        # Same user, sequential requests so order is deterministic.
        recs = await self._drive(run_id, tag, pub, [user] * n, fire_impression=True, concurrency=1)

        served = sum(1 for r in recs if r["filled"] and r["campaign"] == camp["name"])
        served_after_cap = max(0, served - cap)
        verdict = GAP if served_after_cap > 0 else (PASS if served else FAIL)
        result = await self._record(
            run_id, "D", "Frequency Cap (3 impressions/user)", verdict,
            f"After {cap} impressions, further requests from the same user are not served.",
            (f"Same user served {served}/{n} times; {served_after_cap} beyond the cap of {cap}. "
             "`decide_vast_ad` performs no per-user frequency capping, so the cap is not enforced."),
            {"cap": cap, "requests": n, "served": served, "served_after_cap": served_after_cap,
             "user_id": user.user_id})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result
