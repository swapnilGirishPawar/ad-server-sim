"""Pydantic request models for the simulator's own HTTP API."""
from __future__ import annotations

from typing import List, Optional

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


class RunRequest(BaseModel):
    """Module 2-5 — a traffic run."""
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


class ScenarioRequest(BaseModel):
    """Module 6 — run a predefined business scenario."""
    scenario: str = Field(description="A | B | C | D | all")
    label: Optional[str] = None
    total_requests: Optional[int] = None
    requests_per_second: Optional[float] = None
