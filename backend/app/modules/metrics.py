"""Metrics aggregation.

Everything here is computed from the simulator's OWN record of what it sent and
observed (the SQLite tables) — that is the authoritative, standard view. Where a
caller wants to cross-check the ad server's own numbers, the client's reporting
reads are used separately (see api/routes cross_check).

Spend is "modelled spend": filled impressions x winning CPM / 1000. This is the
correct economic value of the traffic the simulator generated, independent of
whether the server attributed it (which it often does not — a reported finding).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.db import Database


def _where(run_id: Optional[str]):
    return ("WHERE run_id=?", (run_id,)) if run_id else ("", ())


async def overview(db: Database, run_id: Optional[str] = None) -> Dict[str, Any]:
    w, p = _where(run_id)
    req = await db.fetchone(f"SELECT COUNT(*) n, SUM(filled) fills, "
                            f"SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END) resp "
                            f"FROM ad_requests {w}", p)
    we, pe = _where(run_id)
    imp = await db.fetchone(f"SELECT COUNT(*) n FROM events {we} {'AND' if we else 'WHERE'} type='impression'", pe)
    clk = await db.fetchone(f"SELECT COUNT(*) n FROM events {we} {'AND' if we else 'WHERE'} type='click'", pe)
    n = (req or {}).get("n") or 0
    fills = (req or {}).get("fills") or 0
    resp = (req or {}).get("resp") or 0
    impressions = (imp or {}).get("n") or 0
    clicks = (clk or {}).get("n") or 0
    return {
        "total_requests": n,
        "total_responses": resp,
        "total_fills": fills,
        "total_impressions": impressions,
        "total_clicks": clicks,
        "fill_rate": round(fills / n, 4) if n else 0.0,
        "ctr": round(clicks / impressions, 4) if impressions else 0.0,
    }


async def campaign_metrics(db: Database, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    we, pe = _where(run_id)
    cond = (we + " AND") if we else "WHERE"
    rows = await db.fetchall(
        f"SELECT campaign, "
        f"SUM(CASE WHEN type='impression' THEN 1 ELSE 0 END) impressions, "
        f"SUM(CASE WHEN type='click' THEN 1 ELSE 0 END) clicks, "
        f"SUM(CASE WHEN type='impression' THEN COALESCE(price,0) ELSE 0 END)/1000.0 spend "
        f"FROM events {cond} campaign IS NOT NULL GROUP BY campaign", pe)

    budgets = {r["name"]: _budget_of(r["data_json"])
               for r in await db.fetchall("SELECT name, data_json FROM seed_entities WHERE kind='campaign'")}
    out = []
    for r in rows:
        budget = budgets.get(r["campaign"])
        spend = round(r["spend"] or 0.0, 4)
        out.append({
            "campaign": r["campaign"], "impressions": r["impressions"] or 0,
            "clicks": r["clicks"] or 0, "spend": spend,
            "ctr": round((r["clicks"] or 0) / r["impressions"], 4) if r["impressions"] else 0.0,
            "budget": budget,
            "remaining_budget": round(budget - spend, 4) if budget is not None else None,
        })
    out.sort(key=lambda x: x["impressions"], reverse=True)
    return out


def _budget_of(data_json: Optional[str]) -> Optional[float]:
    try:
        d = json.loads(data_json or "{}")
    except json.JSONDecodeError:
        return None
    b = d.get("budget") or d.get("budget_total")
    return float(b) if b is not None else None


def _pctile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 2)
    k = (len(sorted_vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo), 2)


async def auction_metrics(db: Database, run_id: Optional[str] = None) -> Dict[str, Any]:
    w, p = _where(run_id)
    lat_rows = await db.fetchall(f"SELECT latency_ms FROM ad_requests {w} {'AND' if w else 'WHERE'} "
                                 f"latency_ms IS NOT NULL ORDER BY latency_ms", p)
    lats = [r["latency_ms"] for r in lat_rows]
    avg = round(sum(lats) / len(lats), 2) if lats else 0.0

    tot = await db.fetchone(
        f"SELECT COUNT(*) n, SUM(CASE WHEN status_code=0 OR status_code>=500 THEN 1 ELSE 0 END) errs "
        f"FROM ad_requests {w}", p)
    n = (tot or {}).get("n") or 0
    errs = (tot or {}).get("errs") or 0

    span = await db.fetchone(f"SELECT MIN(ts_ms) lo, MAX(ts_ms) hi, COUNT(*) n FROM ad_requests {w}", p)
    rps = 0.0
    if span and span["n"] and span["hi"] and span["lo"] and span["hi"] > span["lo"]:
        rps = round(span["n"] / ((span["hi"] - span["lo"]) / 1000.0), 2)

    win_rows = await db.fetchall(f"SELECT winner_campaign c, COUNT(*) n FROM ad_requests {w} "
                                 f"{'AND' if w else 'WHERE'} filled=1 GROUP BY winner_campaign "
                                 f"ORDER BY n DESC", p)
    return {
        "avg_latency_ms": avg,
        "p50_latency_ms": _pctile(lats, 0.50),
        "p95_latency_ms": _pctile(lats, 0.95),
        "p99_latency_ms": _pctile(lats, 0.99),
        "requests_per_second": rps,
        "error_rate": round(errs / n, 4) if n else 0.0,
        "win_distribution": [{"campaign": r["c"] or "(unknown)", "wins": r["n"]} for r in win_rows],
    }


async def fill_breakdown(db: Database, run_id: Optional[str] = None) -> Dict[str, Any]:
    """Real vs filler vs no-fill vs error split (build prompt §5.5 / S3)."""
    w, p = _where(run_id)
    rows = await db.fetchall(
        f"SELECT COALESCE(classification,'unknown') c, COUNT(*) n FROM ad_requests {w} GROUP BY c", p)
    counts = {r["c"]: r["n"] for r in rows}
    total = sum(counts.values())
    return {
        "total": total, "by_classification": counts,
        "real": counts.get("real", 0), "filler": counts.get("filler", 0),
        "no_fill": counts.get("no_fill", 0), "error": counts.get("error", 0),
        "real_fill_rate": round(counts.get("real", 0) / total, 4) if total else 0.0,
        "filler_rate": round(counts.get("filler", 0) / total, 4) if total else 0.0,
    }


async def findings_summary(db: Database, run_id: Optional[str] = None) -> Dict[str, Any]:
    """All conformance findings + a per-standard scorecard."""
    from app.conformance import scorecard
    w, p = _where(run_id)
    rows = await db.fetchall(f"SELECT * FROM findings {w} ORDER BY "
                             f"CASE severity WHEN 'fail' THEN 0 WHEN 'warn' THEN 1 "
                             f"WHEN 'info' THEN 2 ELSE 3 END, standard", p)
    findings = [{
        "standard": r["standard"], "spec_section": r["spec_section"], "check": r["check_id"],
        "severity": r["severity"], "expected": r["expected"], "observed": r["observed"],
        "endpoint": r["endpoint"], "scenario": r["scenario"],
    } for r in rows]
    return {"scorecard": scorecard(findings), "findings": findings}


async def reconcile(db: Database, client, run_id: Optional[str] = None,
                    tolerance: float = 0.05) -> Dict[str, Any]:
    """Compare what the simulator SENT/observed against the SUT's own reports,
    per campaign, with a within-tolerance pass/fail verdict (build prompt §4.8 / S11)."""
    sim = {c["campaign"]: c for c in await campaign_metrics(db, run_id)}
    rows = await db.fetchall("SELECT server_id, name FROM seed_entities WHERE kind='campaign'")
    per_campaign = []
    agg = {"sim_impressions": 0, "server_impressions": 0}
    for r in rows:
        sm = sim.get(r["name"], {})
        srv_stats = await client.campaign_stats(r["server_id"]) or {}
        srv_spend = await client.campaign_spend(r["server_id"]) or {}
        sim_imp = sm.get("impressions", 0)
        srv_imp = srv_stats.get("impressions")
        delta = None
        verdict = "BLOCKED"
        if srv_imp is not None:
            delta = srv_imp - sim_imp
            denom = sim_imp or 1
            verdict = "PASS" if abs(delta) / denom <= tolerance else "FAIL"
            agg["sim_impressions"] += sim_imp
            agg["server_impressions"] += srv_imp
        per_campaign.append({
            "campaign": r["name"], "sim_impressions": sim_imp, "server_impressions": srv_imp,
            "delta": delta, "within_tolerance": verdict,
            "sim_clicks": sm.get("clicks", 0), "server_clicks": srv_stats.get("clicks"),
            "sim_spend": sm.get("spend", 0.0),
            "server_spend": (srv_stats.get("spend") if srv_stats else None) or srv_spend.get("spend_total"),
        })
    overall_delta = agg["server_impressions"] - agg["sim_impressions"]
    denom = agg["sim_impressions"] or 1
    return {
        "tolerance": tolerance, "per_campaign": per_campaign, "aggregate": agg,
        "aggregate_delta": overall_delta,
        "aggregate_verdict": ("PASS" if agg["server_impressions"] and abs(overall_delta) / denom <= tolerance
                              else ("FAIL" if agg["server_impressions"] else "BLOCKED")),
        "note": ("Server impression counts unavailable (reporting endpoints not reachable / not "
                 "attributing) — reconciliation BLOCKED. The simulator's own counts remain authoritative."),
    }


async def timeseries(db: Database, run_id: Optional[str] = None, bucket_ms: int = 1000) -> List[Dict[str, Any]]:
    w, p = _where(run_id)
    req = await db.fetchall(
        f"SELECT (ts_ms/{bucket_ms})*{bucket_ms} b, COUNT(*) n FROM ad_requests {w} GROUP BY b ORDER BY b", p)
    we, pe = _where(run_id)
    cond = (we + " AND") if we else "WHERE"
    ev = await db.fetchall(
        f"SELECT (ts_ms/{bucket_ms})*{bucket_ms} b, "
        f"SUM(CASE WHEN type='impression' THEN 1 ELSE 0 END) imp, "
        f"SUM(CASE WHEN type='click' THEN 1 ELSE 0 END) clk, "
        f"SUM(CASE WHEN type='impression' THEN COALESCE(price,0) ELSE 0 END)/1000.0 spend "
        f"FROM events {cond} type IN ('impression','click') GROUP BY b ORDER BY b", pe)

    buckets: Dict[int, Dict[str, Any]] = {}
    for r in req:
        buckets.setdefault(r["b"], {"t": r["b"], "requests": 0, "impressions": 0, "clicks": 0, "spend": 0.0})
        buckets[r["b"]]["requests"] = r["n"]
    for r in ev:
        b = buckets.setdefault(r["b"], {"t": r["b"], "requests": 0, "impressions": 0, "clicks": 0, "spend": 0.0})
        b["impressions"] = r["imp"] or 0
        b["clicks"] = r["clk"] or 0
        b["spend"] = round(r["spend"] or 0.0, 4)
    return [buckets[k] for k in sorted(buckets)]


async def list_runs(db: Database, limit: int = 50) -> List[Dict[str, Any]]:
    rows = await db.fetchall("SELECT id, kind, label, status, started_at, ended_at, summary_json "
                             "FROM runs ORDER BY started_ms DESC LIMIT ?", (limit,))
    out = []
    for r in rows:
        try:
            summary = json.loads(r["summary_json"]) if r["summary_json"] else None
        except json.JSONDecodeError:
            summary = None
        out.append({**{k: r[k] for k in ("id", "kind", "label", "status", "started_at", "ended_at")},
                    "summary": summary})
    return out


async def scenario_results(db: Database, run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    w, p = _where(run_id)
    rows = await db.fetchall(f"SELECT * FROM scenario_results {w} ORDER BY created_at DESC", p)
    for r in rows:
        try:
            r["evidence"] = json.loads(r.pop("evidence_json") or "{}")
        except json.JSONDecodeError:
            r["evidence"] = {}
    return rows
