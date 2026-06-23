"""Module 4 — Click Simulator.

Given an impression occurred, fire a click with probability `ctr`. Uses the
clickthrough/click-tracking URL from the VAST response when present, otherwise a
canonical `/api/track/click` call.
"""
from __future__ import annotations

import random
from typing import Any, Dict, Optional

from app.adserver import tracking
from app.adserver.client import AdServerClient
from app.adserver.result import AdResult
from app.config import Settings
from app.util import new_id, now_iso, now_ms


def should_click(ctr: float, rng: random.Random) -> bool:
    return rng.random() < ctr


async def fire_click(
    client: AdServerClient, settings: Settings, *, run_id: str, result: AdResult,
    tag_id: str, publisher_id: str, user_id: str, campaign_id: Optional[str],
    campaign: Optional[str],
) -> Dict[str, Any]:
    if result.click_urls:
        url = result.click_urls[0]
        fired = await client.fire(url)
    else:
        url = tracking.click_url(settings, aid=tag_id, sid=publisher_id,
                                 redirect="https://advertiser.example.com/landing",
                                 trace_id=result.trace_id or new_id())
        fired = await client.fire(url, normalize=False)
    return {
        "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
        "type": "click", "request_id": result.trace_id, "tag_id": tag_id,
        "publisher_id": publisher_id, "user_id": user_id, "campaign_id": campaign_id,
        "campaign": campaign, "price": None, "url": fired["url"],
        "status_code": fired["status_code"], "ok": 1 if fired["ok"] else 0,
        "note": fired.get("note"), "trace_id": result.trace_id,
    }
