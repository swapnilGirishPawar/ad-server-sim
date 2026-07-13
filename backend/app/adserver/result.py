"""Normalised result of a single ad request, across VAST and OpenRTB."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AdResult:
    protocol: str                       # "vast" | "ortb"
    status_code: int
    latency_ms: float
    filled: bool                        # a REAL campaign ad was served (filler/no-fill => False)
    # Response classification (build prompt §5.5):
    #   real | filler | no_fill | error | empty
    classification: str = "unknown"
    campaign: Optional[str] = None          # campaign name (VAST <AdTitle>)
    campaign_id: Optional[str] = None       # ORTB bid.cid (VAST has no campaign id in markup)
    creative_id: Optional[str] = None       # VAST <Ad id> / ORTB bid.crid
    price: Optional[float] = None           # CPM (ORTB bid.price)
    impression_urls: List[str] = field(default_factory=list)
    click_urls: List[str] = field(default_factory=list)
    event_urls: List[str] = field(default_factory=list)          # all <Tracking> URLs (flat)
    tracking_events: Dict[str, List[str]] = field(default_factory=dict)  # event -> urls (ordered)
    error_urls: List[str] = field(default_factory=list)          # VAST <Error> URLs
    win_urls: List[str] = field(default_factory=list)            # ORTB nurl/burl
    media_urls: List[str] = field(default_factory=list)
    # Conformance / structural metadata.
    ad_type: Optional[str] = None           # inline | wrapper | empty | unparseable (VAST)
    vast_version: Optional[str] = None
    has_omid: bool = False
    wrapper_depth: int = 0
    findings: List[Dict[str, Any]] = field(default_factory=list)  # conformance findings (dicts)
    no_fill_reason: Optional[str] = None
    trace_id: Optional[str] = None
    adm: Optional[str] = None            # full winning creative markup (ORTB bid.adm / VAST)
    raw: str = ""
