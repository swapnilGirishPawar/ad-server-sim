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


class DspConfig(BaseModel):
    """Runtime control of the built-in fake DSP."""
    mode: Optional[str] = Field(default=None, description="bid | no_bid | timeout | error")
    price: Optional[float] = None
    bid_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    timeout_ms: Optional[int] = None
    seat: Optional[str] = None
    adomain: Optional[List[str]] = None
    crid: Optional[str] = None
    cat: Optional[List[str]] = None

    def patch(self) -> Dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v is not None}
