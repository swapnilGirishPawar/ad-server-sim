"""Pydantic request models for the simulator's own HTTP API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SeedRequest(BaseModel):
    """Module 1 — Seed Data Generator configuration."""
    publishers: int = 3
    ad_units_per_publisher: int = 3
    demand_partners: int = 3
    advertisers: int = 3
    campaigns: int = 6
    line_items_per_partner: int = 1
    budget_min: float = 500.0
    budget_max: float = 5000.0
    cpm_min: float = 1.0
    cpm_max: float = 20.0
    # The internal auction only serves video/ctv/dooh formats.
    ad_format: str = "video"
    label: Optional[str] = None
    publisher_names: Optional[List[str]] = None
    advertiser_names: Optional[List[str]] = None
    dsp_names: Optional[List[str]] = None
    # Randomly assign country/device targeting to seeded campaigns.
    randomize_targeting: bool = True
    # Register the simulator's fake DSP as a demand partner so the OpenRTB auction
    # has something to win (enables S10 / real bid responses).
    seed_fake_dsp: bool = True
    # Deterministic seed so re-runs produce the same world (idempotent).
    rng_seed: Optional[int] = 1337


class RunRequest(BaseModel):
    """Modules 2-5 — a traffic run."""
    label: Optional[str] = None
    protocols: Optional[List[str]] = None
    requests_per_second: Optional[float] = None
    concurrency: Optional[int] = None
    total_requests: Optional[int] = None
    duration_seconds: Optional[int] = None
    impression_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ctr: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    countries: Optional[List[str]] = None
    devices: Optional[List[str]] = None
    browsers: Optional[List[str]] = None
    user_pool_size: Optional[int] = None
    returning_user_ratio: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    fire_impressions: bool = True
    fire_clicks: bool = True
    fire_wins: bool = True
    # Fire the full ordered quartile sequence (start..complete) per impression (S11).
    fire_quartiles: bool = True
    # Linear RPS ramp-up over the first N seconds (warm-up) — 0 disables (S14).
    ramp_seconds: int = 0
    # Load/stress SLO thresholds; when set, the run gets a pass/fail SLO verdict (S14).
    slo_p95_ms: Optional[float] = None
    slo_error_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ScenarioRequest(BaseModel):
    """Module 6 — run a predefined conformance scenario.

    Accepts S1..S15 (corrected catalogue), the legacy letters A-D, or 'all'.
    """
    scenario: str = Field(description="S1..S15 | A | B | C | D | all")
    label: Optional[str] = None
    total_requests: Optional[int] = None
    requests_per_second: Optional[float] = None


class FlowRequest(BaseModel):
    """One-click Flow B: fire a single OpenRTB auction at the ad server."""
    tag_id: Optional[str] = None       # None -> use the most recent seeded ad unit
    dsp_mode: Optional[str] = None      # bid | no_bid | timeout | error (sets the DSP first)
    bidfloor: float = 5.775
    device: str = "ctv"
    country: str = "US"
    timeout_s: float = 60.0             # the SUT auction can be slow on a cold start


class PublisherAdRequest(BaseModel):
    """Manual 'publisher ad request' tester — fire N IAB-compliant requests for a
    specific publisher + ad unit at the ad server, and see exactly what it returns.

    protocol 'vast' → GET the VAST tag; 'ortb' → POST an OpenRTB bid request.
    Independent of seeding/traffic runs — you supply the publisher_id + tag_id.
    """
    publisher_id: str = Field(default="1192", description="Publisher/seller id (schain sid, pub= param)")
    tag_id: str = Field(default="351511", description="Ad unit / tag id (path + imp.tagid)")
    count: int = Field(default=1, ge=1, le=500, description="How many requests to fire")
    protocol: str = Field(default="ortb", description="ortb | vast")
    # oRTB imp media type; VAST is always video.
    ad_format: str = Field(default="video", description="video | banner | native | audio")
    device: str = Field(default="ctv", description="ctv | mobile | desktop | tablet")
    country: str = Field(default="US")
    width: int = 1920
    height: int = 1080
    bidfloor: float = 5.775
    # app vs site inventory (CTV/mobile apps → app; web → site).
    app_mode: bool = True
    concurrency: int = Field(default=10, ge=1, le=50)
    # Privacy signals (all optional passthrough).
    gdpr: Optional[int] = None
    gdpr_consent: Optional[str] = None
    us_privacy: Optional[str] = None
    gpp: Optional[str] = None
    coppa: Optional[int] = None
    # Paste a real publisher OpenRTB body to send verbatim (overrides the builder).
    custom_request: Optional[Dict[str, Any]] = None
    randomize_id: bool = True  # give each fired request a fresh id (custom_request path)
    # Build the request(s) and return them WITHOUT sending — for inspection/learning.
    preview_only: bool = False
    # After a win, simulate the ad being played: fire the winning VAST's
    # impression/quartile pixels + the win notices (nurl/burl) server-side, so the
    # ad server records the paid impression and the fake DSP records its trackers.
    simulate_playback: bool = False


class DspConfig(BaseModel):
    """Runtime control of the built-in mock DSP."""
    mode: Optional[str] = Field(default=None, description="bid | no_bid | timeout | error")
    price: Optional[float] = None
    bid_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    timeout_ms: Optional[int] = None
    seat: Optional[str] = None
    adomain: Optional[List[str]] = None
    crid: Optional[str] = None
    cat: Optional[List[str]] = None
    # valuation / floor handling
    currency: Optional[str] = None
    bid_margin: Optional[float] = Field(default=None, ge=0.0)
    max_cpm: Optional[float] = Field(default=None, ge=0.0)
    jitter: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    respect_floor: Optional[bool] = None
    emit_nbr: Optional[bool] = None
    verbose: Optional[bool] = None

    def patch(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class DspCreate(BaseModel):
    """Register a new independently-configurable mock DSP (POST /dsps)."""
    name: Optional[str] = Field(default=None, description="Display name, e.g. 'DSP B'")
    dsp_id: Optional[str] = Field(default=None, description="Optional explicit id/slug; auto-derived from name if omitted")
