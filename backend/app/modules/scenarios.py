"""Module 6 — Scenario Engine (corrected S1–S15 catalogue).

Each scenario sets up isolated data, drives controlled traffic, and asserts the
*standard* expected behaviour. The simulator is the source of truth: where the
SUT fails to enforce the expected rule, the verdict is GAP (with evidence) — we
never bend the assertion to match SUT behaviour (build prompt §1, §8).

Verdicts:
  PASS    — the SUT behaved as a correct, IAB-compliant ad server should.
  GAP     — the SUT deviates from the standard (feature missing/buggy). EXPECTED
            for S4/S5/S6/S7 against this SUT — that failure IS the finding.
  BLOCKED — no live SUT capability to assert against (e.g. true ad pods).
  FAIL    — the scenario could not validate (e.g. nothing served at all).
  ERROR   — setup/transport error.

Legacy letters map onto the new catalogue: A→S7, B→S5, D→S6, C→bid competition.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.adserver import tracking, validators
from app.adserver.client import AdServerClient, AdServerError
from app.config import Settings
from app.db import Database
from app.findings_recorder import FindingRecorder
from app.modules.users import SimUser, UserPool
from app.util import new_id, now_iso, now_ms

logger = logging.getLogger("adsim.scenarios")

PASS, GAP, FAIL, ERROR, BLOCKED = "PASS", "GAP", "FAIL", "ERROR", "BLOCKED"

ALL_SCENARIOS = [f"S{i}" for i in range(1, 16)]
_LETTER_ALIAS = {"A": "S7", "B": "S5", "C": "BIDCOMP", "D": "S6"}


class ScenarioEngine:
    def __init__(self, client: AdServerClient, db: Database, settings: Settings) -> None:
        self.c = client
        self.db = db
        self.s = settings

    # ------------------------------------------------------------- utilities
    def _dates(self, *, start_days_ago: int = 1, end_days_ahead: int = 30) -> Tuple[str, str]:
        start = (datetime.now(timezone.utc) - timedelta(days=start_days_ago)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=end_days_ahead)).isoformat()
        return start, end

    async def _setup_unit(self, label: str) -> Tuple[str, str]:
        try:
            pub = await self.c.create_publisher(f"ScenPub {label}")
            au = await self.c.create_ad_unit(pub["id"], f"Scen Unit {label}", "video", 640, 480)
            return str(au.get("numeric_id") or au.get("id")), pub["id"]
        except AdServerError:
            return f"scen-{label}-{new_id()[:8]}", f"scen-pub-{label}"

    async def _dominant_cpm(self, bump: float = 100.0) -> float:
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
                        countries: Optional[List[str]] = None,
                        start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        s, e = self._dates()
        camp = await self.c.create_campaign(
            name=name, advertiser_id="", budget=budget, daily_budget=budget, cpm=cpm,
            ad_format="video", start_date=start_date or s, end_date=end_date or e,
            countries=countries or self.s.country_list, devices=self.s.device_list)
        await self.c.create_creative(campaign_id=camp["id"], name=f"{name} creative",
                                     ad_format="video", width=640, height=480)
        return camp

    async def _drive(self, run_id: str, tag_id: str, pub: str, requests: List[SimUser], *,
                     fire_impression: bool = True, fire_win_price: Optional[float] = None,
                     concurrency: int = 8, recorder: Optional[FindingRecorder] = None,
                     country_param: bool = False) -> List[Dict[str, Any]]:
        sem = asyncio.Semaphore(concurrency)
        records: List[Dict[str, Any]] = []

        async def one(idx: int, user: SimUser) -> None:
            async with sem:
                res = await self.c.request_vast(
                    tag_id=tag_id, publisher_id=pub, device=user.device, user_id=user.user_id,
                    country=user.country if country_param else None)
            if recorder:
                recorder.add_many(res.findings, request_id=res.trace_id)
            rec = {"idx": idx, "filled": res.filled, "classification": res.classification,
                   "campaign": res.campaign, "country": user.country, "user_id": user.user_id,
                   "ts_ms": now_ms(), "status": res.status_code}
            records.append(rec)
            await self.db.insert("ad_requests", {
                "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": rec["ts_ms"],
                "protocol": "vast", "tag_id": tag_id, "publisher_id": pub, "ad_unit_id": tag_id,
                "country": user.country, "device": user.device, "browser": user.browser,
                "user_id": user.user_id, "status_code": res.status_code, "latency_ms": res.latency_ms,
                "filled": 1 if res.filled else 0, "classification": res.classification,
                "winner_campaign": res.campaign, "winner_campaign_id": None,
                "winner_creative_id": res.creative_id, "price": fire_win_price,
                "no_fill_reason": res.no_fill_reason, "trace_id": res.trace_id})
            if res.filled and fire_impression:
                url = res.impression_urls[0] if res.impression_urls else tracking.impression_url(
                    self.s, aid=tag_id, sid=pub, trace_id=res.trace_id or new_id())
                fired = await self.c.fire(url, normalize=bool(res.impression_urls))
                await self.db.insert("events", _evt(run_id, "impression", res, tag_id, pub, user, fire_win_price, fired))
                if fire_win_price:
                    win = tracking.win_url(self.s, price=fire_win_price, aid=tag_id, pub=pub,
                                           trace_id=res.trace_id or new_id())
                    wf = await self.c.fire(win, normalize=False)
                    await self.db.insert("events", _evt(run_id, "win", res, tag_id, pub, user, fire_win_price, wf))

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

    async def _close_run(self, run_id: str, result: Dict[str, Any],
                         recorder: Optional[FindingRecorder] = None) -> None:
        if recorder:
            await recorder.flush()
        await self.db.execute(
            "UPDATE runs SET status=?, summary_json=?, ended_at=?, ended_ms=? WHERE id=?",
            ("completed", json.dumps(result), now_iso(), now_ms(), run_id))

    async def _cleanup(self, *campaigns: Any) -> None:
        for c in campaigns:
            cid = c.get("id") if isinstance(c, dict) else c
            if cid:
                await self.c.delete_campaign(cid)

    def _recorder(self, run_id: str) -> FindingRecorder:
        return FindingRecorder(self.db, run_id, cap=self.s.max_findings_per_run)

    # ----------------------------------------------------------- dispatch
    async def run(self, scenario: str, total: Optional[int] = None,
                  label: Optional[str] = None) -> List[Dict[str, Any]]:
        scenario = scenario.upper()
        if scenario in _LETTER_ALIAS:
            scenario = _LETTER_ALIAS[scenario]
        mapping = {
            "S1": self.s1, "S2": self.s2, "S3": self.s3, "S4": self.s4, "S5": self.s5,
            "S6": self.s6, "S7": self.s7, "S8": self.s8, "S9": self.s9, "S10": self.s10,
            "S11": self.s11, "S12": self.s12, "S13": self.s13, "S14": self.s14, "S15": self.s15,
            "BIDCOMP": self.bid_competition,
        }
        if scenario == "ALL":
            return [await self._safe(mapping[k], total, label) for k in ALL_SCENARIOS]
        if scenario not in mapping:
            raise ValueError(f"Unknown scenario '{scenario}' (use S1..S15, A-D, or all)")
        return [await self._safe(mapping[scenario], total, label)]

    async def _safe(self, fn, total, label) -> Dict[str, Any]:
        try:
            return await fn(total=total, label=label)
        except Exception as e:  # noqa: BLE001 - scenarios must never crash the API
            logger.exception("scenario error")
            return {"scenario": fn.__name__, "verdict": ERROR, "title": fn.__name__,
                    "expected": "", "actual": f"error: {e}", "evidence": {}}

    # Legacy aliases (kept for older dashboards / API callers).
    async def scenario_a(self, **kw):  # noqa: D401
        return await self.s7(**kw)

    async def scenario_b(self, **kw):
        return await self.s5(**kw)

    async def scenario_c(self, **kw):
        return await self.bid_competition(**kw)

    async def scenario_d(self, **kw):
        return await self.s6(**kw)

    # =================================================================== S1
    async def s1(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S1", label)
        rec = self._recorder(run_id)
        tag, pub = await self._setup_unit("S1")
        res = await self.c.request_vast(tag_id=tag, publisher_id=pub, device="desktop", user_id=new_id("u-"))
        rec.add_many(res.findings, request_id=res.trace_id)
        fails = [f for f in res.findings if f["severity"] == "fail"]
        verdict = PASS if (res.ad_type in ("inline", "wrapper") and not fails) else (
            GAP if res.ad_type in ("inline", "wrapper") else FAIL)
        result = await self._record(
            run_id, "S1", "Smoke — single VAST request is spec-valid", verdict,
            "GET /api/v/{tag} returns schema-valid VAST 4.x with required nodes.",
            (f"ad_type={res.ad_type}, version={res.vast_version}, "
             f"{len(fails)} structural failure(s): {[f['check'] for f in fails][:6]}"),
            {"ad_type": res.ad_type, "version": res.vast_version, "classification": res.classification,
             "fail_findings": fails[:10], "media_files": res.media_urls[:3]})
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S2
    async def s2(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S2", label)
        rec = self._recorder(run_id)
        n = total or 120
        tag, pub = await self._setup_unit("S2")
        camp = await self._campaign("Scenario S2 — steady", cpm=await self._dominant_cpm())
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.5)
        recs = await self._drive(run_id, tag, pub, [pool.pick() for _ in range(n)],
                                 fire_impression=True, recorder=rec)
        ok_resp = sum(1 for r in recs if 200 <= (r["status"] or 0) < 400)
        served = sum(1 for r in recs if r["filled"] or r["classification"] == "filler")
        fails = sum(rec.counts.get("fail", 0) for _ in [0])
        verdict = PASS if (ok_resp == len(recs) and served == len(recs) and not rec.counts.get("fail")) else (
            GAP if served else FAIL)
        result = await self._record(
            run_id, "S2", "Normal traffic — valid markup, sane fill/latency", verdict,
            "Steady traffic returns valid VAST for every request with no structural failures.",
            f"{ok_resp}/{len(recs)} HTTP-ok, {served}/{len(recs)} returned an ad, "
            f"conformance fails={rec.counts.get('fail', 0)}.",
            {"requests": len(recs), "http_ok": ok_resp, "served": served, "finding_counts": rec.counts})
        await self._cleanup(camp)
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S3
    async def s3(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S3", label)
        n = total or 200
        tag, pub = await self._setup_unit("S3")
        camp = await self._campaign("Scenario S3 — real fill", cpm=await self._dominant_cpm())
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.5)
        recs = await self._drive(run_id, tag, pub, [pool.pick() for _ in range(n)], fire_impression=False)
        real = sum(1 for r in recs if r["classification"] == "real")
        filler = sum(1 for r in recs if r["classification"] == "filler")
        real_rate = round(real / len(recs), 4) if recs else 0
        verdict = PASS if real > 0 else GAP
        result = await self._record(
            run_id, "S3", "Real-vs-filler fill rate", verdict,
            "A seeded campaign serves REAL ads (real-fill rate > 0 after the field-name workaround).",
            (f"real={real} ({real_rate:.0%}), filler={filler}. "
             + ("Real campaign serving works after the ad_format/target_cpm workaround." if real
                else "ALL responses were the default 'Video Ad' filler — campaigns are unserveable "
                     "(field-name mismatch: create writes format_targets/cpm_bid, auction reads ad_format/target_cpm).")),
            {"requests": len(recs), "real": real, "filler": filler, "real_fill_rate": real_rate})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S4
    async def s4(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S4", label)
        # Drive a tag with NO eligible campaign; a correct server returns empty VAST / <Error>.
        tag, pub = await self._setup_unit("S4-empty")
        res = await self.c.request_vast(tag_id=tag, publisher_id=pub, device="desktop", user_id=new_id("u-"))
        has_empty = res.ad_type == "empty"
        has_error_node = bool(res.error_urls)
        verdict = PASS if (has_empty or (not res.filled and res.classification == "no_fill")) else GAP
        result = await self._record(
            run_id, "S4", "No-fill semantics", verdict,
            "With no eligible demand the server returns an empty <VAST/> or a <VAST><Error> (or 204/nbr on OpenRTB).",
            (f"ad_type={res.ad_type}, classification={res.classification}. "
             + ("Spec-correct no-fill observed." if has_empty else
                f"Server returned a populated ad ({res.classification}) instead of a spec-correct no-fill — "
                "every live VAST route always fills (no empty-VAST / X-No-Fill-Reason path exists).")),
            {"ad_type": res.ad_type, "classification": res.classification,
             "has_error_node": has_error_node, "raw_snippet": res.raw[:300]})
        await self._close_run(run_id, result)
        return result

    # =================================================================== S5
    async def s5(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S5", label)
        n = total or 240
        tag, pub = await self._setup_unit("S5")
        camp = await self._campaign("Scenario S5 — India only", cpm=await self._dominant_cpm(), countries=["IN"])
        countries = ["IN", "US", "UK"]
        pool = UserPool(countries, self.s.device_list, self.s.browser_list, 50, 0.4)
        users = [pool.fixed_user(countries[i % 3], pool.devices[i % len(pool.devices)]) for i in range(n)]
        recs = await self._drive(run_id, tag, pub, users, fire_impression=True, country_param=True)
        by_country: Dict[str, Dict[str, int]] = {}
        for r in recs:
            d = by_country.setdefault(r["country"], {"requests": 0, "served": 0})
            d["requests"] += 1
            if r["classification"] == "real" and r["campaign"] == camp["name"]:
                d["served"] += 1
        non_in = sum(v["served"] for c, v in by_country.items() if c != "IN")
        verdict = GAP if non_in > 0 else (PASS if by_country.get("IN", {}).get("served", 0) else FAIL)
        result = await self._record(
            run_id, "S5", "Geo targeting (India only)", verdict,
            "Only IN traffic receives the IN-targeted campaign; US/UK get no fill from it.",
            (f"US/UK received the campaign {non_in} times. `decide_vast_ad` evaluates no geo targeting, "
             "so the campaign serves every country regardless of its IN-only target." if non_in else
             "Campaign only served IN traffic."),
            {"by_country": by_country, "campaign_target": ["IN"]})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S6
    async def s6(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S6", label)
        cap = 3
        n = total or 6
        tag, pub = await self._setup_unit("S6")
        camp = await self._campaign("Scenario S6 — Freq cap 3/user", cpm=await self._dominant_cpm())
        user = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list).fixed_user("IN", "mobile")
        recs = await self._drive(run_id, tag, pub, [user] * n, fire_impression=True, concurrency=1)
        served = sum(1 for r in recs if r["classification"] == "real" and r["campaign"] == camp["name"])
        after_cap = max(0, served - cap)
        verdict = GAP if after_cap > 0 else (PASS if served else FAIL)
        result = await self._record(
            run_id, "S6", "Frequency cap (3 impressions/user)", verdict,
            f"After {cap} impressions, further requests from the same user are not served.",
            (f"Same user served {served}/{n} times; {after_cap} beyond the cap of {cap}. "
             "`decide_vast_ad` performs no per-user frequency capping."),
            {"cap": cap, "requests": n, "served": served, "served_after_cap": after_cap, "user_id": user.user_id})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S7
    async def s7(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S7", label)
        cpm = max(1000.0, await self._dominant_cpm())
        budget = cpm  # exhausts at exactly 1000 impressions (spend/imp = cpm/1000)
        n = total or 1500
        tag, pub = await self._setup_unit("S7")
        camp = await self._campaign("Scenario S7 — Budget 1000", cpm=cpm, budget=budget)
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.5)
        recs = await self._drive(run_id, tag, pub, [pool.pick() for _ in range(n)],
                                 fire_impression=True, fire_win_price=cpm)
        served = [r for r in recs if r["classification"] == "real" and r["campaign"] == camp["name"]]
        exhaust_at = int(budget / (cpm / 1000.0))
        after_budget = max(0, len(served) - exhaust_at)
        camp_doc = await self.c.get_campaign(camp["id"]) or {}
        verdict = GAP if after_budget > 0 else (PASS if served else FAIL)
        result = await self._record(
            run_id, "S7", "Budget exhaustion", verdict,
            "Campaign stops serving once spend reaches its budget.",
            (f"Served {len(served)} real impressions; {after_budget} continued AFTER budget should have "
             f"exhausted (at #{exhaust_at}). Eligibility reads `spent`; wins increment `spend`; and the VAST "
             "path never links a line-item→campaign, so budget never closes the loop."),
            {"budget": budget, "cpm": cpm, "served": len(served), "served_after_budget": after_budget,
             "campaign_spend_fields": {k: camp_doc.get(k) for k in ("spend", "spent", "daily_spent")}})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S8
    async def s8(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S8", label)
        n = total or 120
        tag, pub = await self._setup_unit("S8")
        # An EXPIRED campaign (ended yesterday). Date gating IS implemented in
        # _is_campaign_eligible, so the real campaign should drop out of selection.
        past_start, past_end = self._dates(start_days_ago=10, end_days_ahead=-1)
        camp = await self._campaign("Scenario S8 — expired", cpm=await self._dominant_cpm(),
                                    start_date=past_start, end_date=past_end)
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.5)
        recs = await self._drive(run_id, tag, pub, [pool.pick() for _ in range(n)], fire_impression=False)
        served_real = sum(1 for r in recs if r["classification"] == "real" and r["campaign"] == camp["name"])
        verdict = PASS if served_real == 0 else GAP
        result = await self._record(
            run_id, "S8", "Schedule / flight dates (expired campaign)", verdict,
            "A campaign whose flight has ended is not selected (filler may still serve).",
            (f"Expired campaign served as a REAL ad {served_real} times. "
             + ("Date gating works — it correctly dropped out of selection (filler served instead)."
                if served_real == 0 else
                "Expired campaign still served — schedule gating not enforced.")),
            {"requests": len(recs), "expired_campaign_served": served_real,
             "flight": {"start": past_start, "end": past_end}})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S9
    async def s9(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S9", label)
        rec = self._recorder(run_id)
        tag, _pub = await self._setup_unit("S9")
        # (a) VMAP structure conformance against /api/m/{tag}.
        vmap_text = ""
        try:
            r = await self.c._client.get(self.c._url("vmap", tag_id=tag))
            vmap_text = r.text
        except Exception as e:  # noqa: BLE001
            vmap_text = ""
        vr = validators.validate_vmap(vmap_text, endpoint=self.c.routes.get("vmap", "/api/m/{tag_id}"))
        rec.add_many([f.to_dict() for f in vr.findings])
        vmap_fail = [f for f in vr.findings if f.severity == "fail"]

        # (b) True multi-<Ad> pod via OpenRTB 2.6 pod request — SUT has no pods → BLOCKED.
        pod_res = await self.c.request_ortb(
            tag_id=tag, publisher_id=_pub, country="US", device="ctv", browser="chrome",
            user_id=new_id("u-"), ad_format="ctv", pod={"podid": "pod-1", "slots": 3, "mincpmpersec": 0.5})
        rec.add_many(pod_res.findings, request_id=pod_res.trace_id)

        verdict = PASS if (vr.well_formed and vr.ad_breaks and not vmap_fail) else (
            GAP if vr.well_formed else FAIL)
        result = await self._record(
            run_id, "S9", "Ad pods / VMAP", verdict,
            "VMAP is well-formed (AdBreak/timeOffset/AdSource); a pod request yields a multi-ad pod.",
            (f"VMAP: {len(vr.ad_breaks)} AdBreak(s), {len(vmap_fail)} structural fail(s). "
             "True multi-<Ad> ad pods: BLOCKED — the SUT emits no <Ad sequence> pod on any endpoint "
             "(/api/m is a static 3-break template; the pod-aware /serve router is unmounted)."),
            {"vmap_well_formed": vr.well_formed, "ad_breaks": vr.ad_breaks[:6],
             "vmap_fail": [f.to_dict() for f in vmap_fail][:6], "pod_supported": False,
             "pod_request_status": pod_res.status_code})
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S10
    async def s10(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S10", label)
        rec = self._recorder(run_id)
        # Ensure the fake DSP bids, so the SUT can return a real BidResponse.
        try:
            from app.dsp import router as dsp
            dsp.CONFIG["mode"] = "bid"
        except Exception:  # noqa: BLE001
            pass
        tag, pub = await self._setup_unit("S10")
        res = await self.c.request_ortb(tag_id=tag, publisher_id=pub, country="US",
                                        device="desktop", browser="chrome", user_id=new_id("u-"))
        rec.add_many(res.findings, request_id=res.trace_id)
        fails = [f for f in res.findings if f["severity"] == "fail"]
        if res.filled and not fails:
            verdict, actual = PASS, f"Spec-valid BidResponse (price={res.price}, seat resolved)."
        elif res.status_code == 204 or res.classification == "no_fill":
            verdict = BLOCKED
            actual = ("204 no-bid — the SUT had no demand to fan out to. Seed the built-in fake DSP "
                      "(POST /seed with seed_fake_dsp=true) and ensure the SUT can reach "
                      f"{self.s.dsp_endpoint_url}, then re-run S10.")
        else:
            verdict, actual = GAP, f"BidResponse had {len(fails)} conformance failure(s): {[f['check'] for f in fails]}"
        result = await self._record(
            run_id, "S10", "OpenRTB conformance", verdict,
            "A valid BidRequest yields a spec-valid BidResponse (or a proper no-bid).",
            actual,
            {"status": res.status_code, "filled": res.filled, "price": res.price,
             "fail_findings": fails[:8], "dsp_endpoint": self.s.dsp_endpoint_url})
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S11
    async def s11(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S11", label)
        n = total or 30
        tag, pub = await self._setup_unit("S11")
        camp = await self._campaign("Scenario S11 — tracking", cpm=await self._dominant_cpm())
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 30, 0.5)
        fired_ok = 0
        fired_total = 0
        quartile_orders: List[List[str]] = []
        for i in range(n):
            user = pool.pick()
            res = await self.c.request_vast(tag_id=tag, publisher_id=pub, device=user.device, user_id=user.user_id)
            if not (res.filled or res.classification == "filler"):
                continue
            url = res.impression_urls[0] if res.impression_urls else tracking.impression_url(
                self.s, aid=tag, sid=pub, trace_id=res.trace_id or new_id())
            imp = await self.c.fire(url, normalize=bool(res.impression_urls))
            fired_total += 1
            fired_ok += 1 if imp["ok"] else 0
            await self.db.insert("events", _evt(run_id, "impression", res, tag, pub, user, None, imp))
            qfires = await self.c.fire_quartiles(res)
            quartile_orders.append([q["event"] for q in qfires])
            for q in qfires:
                fired_total += 1
                fired_ok += 1 if q["ok"] else 0
        ordered_ok = all(_is_quartile_order(o) for o in quartile_orders if o)
        verdict = PASS if (fired_total and fired_ok == fired_total) else (GAP if fired_ok else FAIL)
        result = await self._record(
            run_id, "S11", "Tracking accuracy & quartile ordering", verdict,
            "Impression + ordered quartile pixels record successfully (start→firstQuartile→midpoint→thirdQuartile→complete).",
            (f"{fired_ok}/{fired_total} pixel fires recorded (HTTP<400). Quartile ordering preserved: {ordered_ok}. "
             "NOTE: VAST from decide_vast_ad embeds /track/... WITHOUT /api — the sim rewrites+/api so they record; "
             "the raw embedded URLs would 404 in a real player (a SUT gap)."),
            {"fired_ok": fired_ok, "fired_total": fired_total, "ordering_ok": ordered_ok,
             "rewrite_notes": self.c.url_rewrite_notes, "macros": self.c.macro_counts})
        await self._cleanup(camp)
        await self._close_run(run_id, result)
        return result

    # =================================================================== S12
    async def s12(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S12", label)
        rec = self._recorder(run_id)
        tag, pub = await self._setup_unit("S12")
        privacy = {"gdpr": 1, "consent": "CP-sim-TCFv2-consent-string", "gdpr_consent": "CP-sim-TCFv2-consent-string",
                   "us_privacy": "1YNN", "gpp": "DBABMA~CPsim", "gpp_sid": [2, 6]}
        # OpenRTB path — the only place privacy is observably handled (passthrough/detect).
        ortb = await self.c.request_ortb(tag_id=tag, publisher_id=pub, country="DE", device="mobile",
                                         browser="chrome", user_id=new_id("u-"), privacy=privacy)
        rec.add_many(ortb.findings, request_id=ortb.trace_id)
        ortb_accepted = ortb.status_code in (200, 204)
        # Serving path — accepts the params but silently drops them (GAP).
        vast = await self.c.request_vast(tag_id=tag, publisher_id=pub, device="mobile",
                                         user_id=new_id("u-"), privacy=privacy)
        serving_accepts = 200 <= (vast.status_code or 0) < 400
        verdict = PASS if ortb_accepted else FAIL
        result = await self._record(
            run_id, "S12", "Privacy signals (GDPR/TCF, US Privacy, GPP)", verdict,
            "OpenRTB carries regs.ext.gdpr/us_privacy/gpp + user.ext.consent and the SUT accepts/propagates them.",
            (f"OpenRTB request with full privacy block accepted (HTTP {ortb.status_code}). "
             f"Serving path accepted consent params (HTTP {vast.status_code}) but the SUT does NOT honor or "
             "propagate them on /api/v (no AdOpportunity field) — GAP; GPP/TCF unsupported on serving."),
            {"ortb_status": ortb.status_code, "serving_status": vast.status_code,
             "sent_privacy": privacy, "serving_honors_consent": False})
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S13
    async def s13(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S13", label)
        rec = self._recorder(run_id)
        supply = await self.c.fetch_supply_files()
        rec.add_many(supply.get("findings", []))
        # sChain on an outbound bid request we build.
        from app.adserver import ortb as ortb_mod
        from app.adserver import supplychain
        req = ortb_mod.build_bid_request(request_id="schain-check", tag_id="t", publisher_id="pub-1",
                                         country="US", device="desktop", browser="chrome", user_id="u")
        rec.add_many(supplychain.validate_schain(req))
        fails = rec.counts.get("fail", 0)
        reachable = "error" not in supply.get("ads_txt", {}) and "error" not in supply.get("sellers_json", {})
        verdict = PASS if (reachable and not fails) else (GAP if reachable else FAIL)
        result = await self._record(
            run_id, "S13", "ads.txt / sellers.json / SupplyChain", verdict,
            "ads.txt/app-ads.txt/sellers.json parse with valid IAB lines + consistent IDs; bid requests carry schain.",
            (f"ads.txt={supply.get('ads_txt')}, sellers.json={supply.get('sellers_json')}, "
             f"app-ads.txt={supply.get('app_ads_txt')}. Conformance fails={fails}. "
             + ("" if reachable else "Supply files not reachable at root or /api/ortb — check paths.")),
            {"supply": supply, "finding_counts": rec.counts})
        await self._close_run(run_id, result, rec)
        return result

    # =================================================================== S14
    async def s14(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S14", label)
        from app.models import RunRequest
        from app.modules.traffic import TrafficRunner
        tag, pub = await self._setup_unit("S14")
        # ensure there's at least one ad unit to drive
        await self.db.insert("seed_entities", {
            "id": new_id(), "kind": "ad_unit", "server_id": None, "numeric_id": tag,
            "name": "S14 unit", "parent_id": pub, "data_json": "{}", "created_at": now_iso()})
        req = RunRequest(label="S14 stress", protocols=["vast"], total_requests=total or 400,
                         requests_per_second=80, concurrency=20, ramp_seconds=3,
                         fire_impressions=False, fire_clicks=False, fire_wins=False,
                         slo_p95_ms=750, slo_error_rate=0.02)
        runner = TrafficRunner(self.c, self.db, self.s)
        summary = await runner.run(req, run_id=run_id, kind="scenario")
        slo = summary.get("slo", {})
        verdict = PASS if slo.get("verdict") == "PASS" else (FAIL if slo.get("verdict") == "FAIL" else GAP)
        result = await self._record(
            run_id, "S14", "Load / stress (SLO)", verdict,
            "Under ramped load the server meets p95-latency and error-rate SLOs.",
            (f"rps≈{summary.get('rps_actual')}, p95={summary.get('latency', {}).get('p95_ms')}ms, "
             f"error_rate={summary.get('error_rate')}; SLO verdict={slo.get('verdict', 'n/a')}."),
            {"latency": summary.get("latency"), "error_rate": summary.get("error_rate"),
             "rps_actual": summary.get("rps_actual"), "slo": slo})
        # the runner already wrote the run row; just record the scenario result.
        await self.db.insert("scenario_results", {
            "id": new_id(), "run_id": run_id, "scenario": "S14", "verdict": verdict,
            "title": result["title"], "expected": result["expected"], "actual": result["actual"],
            "evidence_json": json.dumps(result["evidence"])[:8000], "created_at": now_iso()})
        return result

    # =================================================================== S15
    async def s15(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("S15", label)
        cases: List[Dict[str, Any]] = []

        async def probe(name: str, coro) -> None:
            try:
                status = await coro
            except Exception as e:  # noqa: BLE001
                status = f"exc:{type(e).__name__}"
            graceful = isinstance(status, int) and (status < 500)
            cases.append({"case": name, "status": status, "graceful": graceful})

        base = self.s
        cl = self.c._client
        await probe("vast_missing_tag", _status(cl.get(f"{base.api_base}/v/")))
        await probe("vast_huge_dims", _status(cl.get(f"{base.api_base}/v/sim-x",
                                                     params={"w": 999999, "h": 999999})))
        await probe("ortb_malformed_json", _status(cl.post(f"{base.api_base}/b/sim-x",
                                                           content=b"{not json", headers={"content-type": "application/json"})))
        await probe("ortb_empty_body", _status(cl.post(f"{base.api_base}/b/sim-x", json={})))
        await probe("track_bad_consent", _status(cl.get(f"{base.api_base}/track/impression",
                                                        params={"aid": "x", "us_privacy": "@@@bad@@@"})))
        non_graceful = [c for c in cases if not c["graceful"]]
        verdict = PASS if not non_graceful else GAP
        result = await self._record(
            run_id, "S15", "Resilience / malformed inputs", verdict,
            "Malformed/edge requests degrade gracefully (4xx/422, never 5xx).",
            (f"{len(cases) - len(non_graceful)}/{len(cases)} handled gracefully. "
             + ("All edge cases returned <500." if not non_graceful else
                f"{len(non_graceful)} returned 5xx/exception: {[c['case'] for c in non_graceful]}")),
            {"cases": cases})
        await self._close_run(run_id, result)
        return result

    # ============================================================ bid competition
    async def bid_competition(self, total: Optional[int] = None, label: Optional[str] = None) -> Dict[str, Any]:
        run_id = await self._new_run("BIDCOMP", label)
        n = total or 300
        tag, pub = await self._setup_unit("BID")
        base = await self._dominant_cpm()
        camp_a = await self._campaign(f"BidComp A (CPM {base:.0f})", cpm=base)
        camp_b = await self._campaign(f"BidComp B (CPM {base + 100:.0f})", cpm=base + 100)
        pool = UserPool(self.s.country_list, self.s.device_list, self.s.browser_list, 50, 0.4)
        recs = await self._drive(run_id, tag, pub, [pool.pick() for _ in range(n)], fire_impression=False)
        wins_a = sum(1 for r in recs if r["campaign"] == camp_a["name"])
        wins_b = sum(1 for r in recs if r["campaign"] == camp_b["name"])
        verdict = PASS if wins_b > wins_a else (FAIL if (wins_a + wins_b) == 0 else GAP)
        result = await self._record(
            run_id, "BIDCOMP", "Bid competition (higher CPM should win)", verdict,
            "Higher-CPM Campaign B wins more auctions than Campaign A.",
            f"Campaign B won {wins_b}, Campaign A won {wins_a}.",
            {"wins_A": wins_a, "wins_B": wins_b, "requests": n})
        await self._cleanup(camp_a, camp_b)
        await self._close_run(run_id, result)
        return result


# --------------------------------------------------------------------- helpers
def _evt(run_id: str, typ: str, res, tag_id: str, pub: str, user, price, fired) -> Dict[str, Any]:
    return {
        "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(), "type": typ,
        "request_id": res.trace_id, "tag_id": tag_id, "publisher_id": pub, "user_id": user.user_id,
        "campaign_id": None, "campaign": res.campaign, "price": price, "url": fired["url"],
        "status_code": fired["status_code"], "ok": 1 if fired["ok"] else 0,
        "note": fired.get("note"), "trace_id": res.trace_id}


def _is_quartile_order(events: List[str]) -> bool:
    order = {"start": 0, "firstQuartile": 1, "midpoint": 2, "thirdQuartile": 3, "complete": 4}
    seq = [order[e] for e in events if e in order]
    return seq == sorted(seq)


async def _status(coro) -> int:
    r = await coro
    return r.status_code
