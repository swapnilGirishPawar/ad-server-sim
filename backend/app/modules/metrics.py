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


async def auction_metrics(db: Database, run_id: Optional[str] = None) -> Dict[str, Any]:
    w, p = _where(run_id)
    lat_rows = await db.fetchall(f"SELECT latency_ms FROM ad_requests {w} {'AND' if w else 'WHERE'} "
                                 f"latency_ms IS NOT NULL ORDER BY latency_ms", p)
    lats = [r["latency_ms"] for r in lat_rows]
    avg = round(sum(lats) / len(lats), 2) if lats else 0.0
    p95 = round(lats[min(len(lats) - 1, int(len(lats) * 0.95))], 2) if lats else 0.0

    span = await db.fetchone(f"SELECT MIN(ts_ms) lo, MAX(ts_ms) hi, COUNT(*) n FROM ad_requests {w}", p)
    rps = 0.0
    if span and span["n"] and span["hi"] and span["lo"] and span["hi"] > span["lo"]:
        rps = round(span["n"] / ((span["hi"] - span["lo"]) / 1000.0), 2)

    win_rows = await db.fetchall(f"SELECT winner_campaign c, COUNT(*) n FROM ad_requests {w} "
                                 f"{'AND' if w else 'WHERE'} filled=1 GROUP BY winner_campaign "
                                 f"ORDER BY n DESC", p)
    return {
        "avg_latency_ms": avg, "p95_latency_ms": p95, "requests_per_second": rps,
        "win_distribution": [{"campaign": r["c"] or "(unknown)", "wins": r["n"]} for r in win_rows],
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
