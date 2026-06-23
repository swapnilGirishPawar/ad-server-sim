"""Normalised result of a single ad request, across VAST and OpenRTB."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AdResult:
    protocol: str                       # "vast" | "ortb"
    status_code: int
    latency_ms: float
    filled: bool
    campaign: Optional[str] = None          # campaign name (VAST <AdTitle>)
    campaign_id: Optional[str] = None       # ORTB bid.cid (VAST has no campaign id in markup)
    creative_id: Optional[str] = None       # VAST <Ad id> / ORTB bid.crid
    price: Optional[float] = None           # CPM (ORTB bid.price)
    impression_urls: List[str] = field(default_factory=list)
    click_urls: List[str] = field(default_factory=list)
    event_urls: List[str] = field(default_factory=list)
    win_urls: List[str] = field(default_factory=list)   # ORTB nurl/burl
    no_fill_reason: Optional[str] = None
    trace_id: Optional[str] = None
    raw: str = ""
