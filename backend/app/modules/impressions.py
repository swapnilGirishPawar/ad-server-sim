"""Module 3 — Impression Simulator.

After a successful ad response, fire an impression with probability
`impression_rate`, after a random human-like delay. Uses the impression URL
embedded in the VAST response when present (realistic), otherwise a canonical
`/api/track/impression` call.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Dict, Optional

from app.adserver import tracking
from app.adserver.client import AdServerClient
from app.adserver.result import AdResult
from app.config import Settings
from app.util import new_id, now_iso, now_ms


def should_fire(rate: float, rng: random.Random) -> bool:
    return rng.random() < rate


async def random_delay(settings: Settings, rng: random.Random) -> None:
    lo, hi = settings.impression_delay_min_ms, settings.impression_delay_max_ms
    if hi > 0:
        await asyncio.sleep(rng.uniform(lo, hi) / 1000.0)


async def fire_impression(
    client: AdServerClient, settings: Settings, *, run_id: str, result: AdResult,
    tag_id: str, publisher_id: str, user_id: str, campaign_id: Optional[str],
    campaign: Optional[str], price: Optional[float],
) -> Dict[str, Any]:
    """Fire one impression and return the event row to persist."""
    if result.impression_urls:
        url = result.impression_urls[0]
        fired = await client.fire(url)
    else:
        url = tracking.impression_url(settings, aid=tag_id, sid=publisher_id,
                                      trace_id=result.trace_id or new_id(), cpm=price)
        fired = await client.fire(url, normalize=False)
    return {
        "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
        "type": "impression", "request_id": result.trace_id, "tag_id": tag_id,
        "publisher_id": publisher_id, "user_id": user_id, "campaign_id": campaign_id,
        "campaign": campaign, "price": price, "url": fired["url"],
        "status_code": fired["status_code"], "ok": 1 if fired["ok"] else 0,
        "note": fired.get("note"), "trace_id": result.trace_id,
    }
