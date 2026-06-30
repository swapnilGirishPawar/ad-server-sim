"""Environment-based configuration for the Ad Server Simulator.

All knobs are overridable via environment variables or a local `.env` file
(see `.env.example`). The simulator never hard-codes anything about the target
ad server beyond sensible localhost defaults.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


def _csv(value: str, upper: bool = False) -> List[str]:
    items = [v.strip() for v in (value or "").split(",") if v.strip()]
    return [i.upper() for i in items] if upper else [i.lower() for i in items]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- Target ad server -------------------------------------------------
    ad_server_url: str = "http://localhost:8001"
    # Must be a valid (non-reserved-TLD) email — the server validates with EmailStr.
    ad_server_email: str = "adsim@voisesim.com"
    ad_server_password: str = "AdSim-Local-2026"
    ad_server_user_name: str = "Ad Server Simulator"
    # Registerable roles are enum-constrained to {admin, trafficker, analyst,
    # publisher}; "admin" can create the network entities we seed.
    ad_server_user_role: str = "admin"
    # If login fails, self-register the sim user (open POST /api/auth/register).
    auto_register: bool = True
    tenant: str = "voisetech"
    http_timeout: float = 15.0
    verify_tls: bool = False

    # --- Traffic generation defaults -------------------------------------
    requests_per_second: float = 50.0
    concurrency: int = 10
    total_requests: int = 500
    duration_seconds: int = 0  # > 0 overrides total_requests (time-bounded run)
    # Comma-separated subset of {vast, ortb}.
    serve_protocols: str = "vast"

    # --- Impression / click defaults -------------------------------------
    default_impression_rate: float = 0.9
    default_ctr: float = 0.03
    impression_delay_min_ms: int = 200
    impression_delay_max_ms: int = 2500

    # --- Tracking behaviour ----------------------------------------------
    # The ad server embeds tracking URLs without the `/api` prefix and with a
    # production host. When true we rewrite them to the configured base so the
    # events actually record — every rewrite is logged as a finding so the
    # underlying server bug stays visible.
    tracking_prefix_fix: bool = True

    # --- User simulation --------------------------------------------------
    user_pool_size: int = 200
    returning_user_ratio: float = 0.6

    # --- Target discovery + fake DSP --------------------------------------
    # Read the SUT's /openapi.json on startup to repoint to live routes.
    discover_on_start: bool = True
    # Public URL at which THIS simulator is reachable BY THE SUT, so the SUT's
    # auction can fan out to the built-in fake DSP. When the SUT runs on the host
    # and the sim in Docker, the sim's published port on the host is correct.
    sim_public_url: str = "http://localhost:8090"
    dsp_path: str = "/dsp/bid"

    # --- Conformance -------------------------------------------------------
    # Findings are de-duplicated per run; this caps distinct findings stored.
    max_findings_per_run: int = 2000
    # Where auto-generated GAP_REPORT.md / gaps.json are written.
    report_dir: str = "./reports"

    # --- Storage ----------------------------------------------------------
    sim_db_path: str = "./sim.db"

    # --- Random traffic dimension pools ----------------------------------
    countries: str = "IN,US,UK,CA"
    devices: str = "mobile,desktop,tablet"
    browsers: str = "chrome,firefox,safari,edge"

    # ---------------------------------------------------------------------
    @property
    def protocols(self) -> List[str]:
        return _csv(self.serve_protocols) or ["vast"]

    @property
    def country_list(self) -> List[str]:
        return _csv(self.countries, upper=True) or ["IN", "US", "UK", "CA"]

    @property
    def device_list(self) -> List[str]:
        return _csv(self.devices) or ["mobile", "desktop", "tablet"]

    @property
    def browser_list(self) -> List[str]:
        return _csv(self.browsers) or ["chrome", "firefox", "safari", "edge"]

    @property
    def api_base(self) -> str:
        return self.ad_server_url.rstrip("/") + "/api"

    @property
    def root_base(self) -> str:
        return self.ad_server_url.rstrip("/")

    @property
    def dsp_endpoint_url(self) -> str:
        """Absolute URL the SUT should POST OpenRTB bid requests to (fake DSP)."""
        return self.sim_public_url.rstrip("/") + self.dsp_path


@lru_cache
def get_settings() -> Settings:
    return Settings()
