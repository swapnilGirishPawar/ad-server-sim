"""Config & Target Discovery (build prompt §4.1 / §9.1).

Before testing, read the SUT's OpenAPI document and verify which routes are
actually mounted. This is what stops the simulator from silently driving dead
routes: the build prompt's original §3 listed `/api/serve/*vast` and `/ortb/*`
paths that the updated SUT does NOT mount (serve.py is never include_router'd).

`discover()` returns:
  - the resolved live path for each logical capability the sim drives,
  - which prompt-claimed paths are present vs missing (dead),
  - conformance findings for anything important that is absent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings

logger = logging.getLogger("adsim.discovery")

# logical capability -> ordered candidate paths (first present wins).
# Templated segments use {id}; we match the OpenAPI path template.
_CANDIDATES: Dict[str, List[str]] = {
    "vast_canonical": ["/api/v/{tag_id}", "/v/{tag_id}"],
    "vast_serve_ad": ["/api/serve/ad/vast"],
    "vast_short": ["/api/v"],
    "ctv": ["/api/ctv"],
    "vmap": ["/api/m/{tag_id}", "/api/vmap"],
    "dooh_vast": ["/api/dooh/vast"],
    "ortb_auction": ["/api/b/{tag_id}", "/ortb/bid/{tag_id}"],
    "ads_txt": ["/ads.txt", "/api/ortb/ads.txt"],
    "app_ads_txt": ["/app-ads.txt", "/api/ortb/app-ads.txt"],
    "sellers_json": ["/sellers.json", "/api/ortb/sellers.json"],
}

# Paths the original build prompt assumed but the updated SUT does NOT mount.
# Their absence is expected and is itself a finding worth surfacing.
_DEAD_CLAIMED = [
    "/api/serve/vast", "/api/serve/dooh/vast", "/api/serve/player/vast",
    "/api/serve/fast/vast", "/ortb/ads.txt", "/ortb/sellers.json",
]


async def fetch_openapi(client: httpx.AsyncClient, base: str) -> Optional[Dict[str, Any]]:
    for path in ("/openapi.json", "/api/openapi.json"):
        try:
            r = await client.get(base.rstrip("/") + path)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                return r.json()
        except (httpx.HTTPError, ValueError):
            continue
    return None


def _normalize_paths(openapi: Dict[str, Any]) -> set:
    """Return path templates with any param name collapsed, e.g. /api/v/{x} -> /api/v/{id}."""
    import re
    out = set()
    for p in (openapi.get("paths") or {}):
        out.add(p)
        out.add(re.sub(r"\{[^}]+\}", "{id}", p))
    return out


def _match(candidate: str, normalized: set) -> bool:
    import re
    return candidate in normalized or re.sub(r"\{[^}]+\}", "{id}", candidate) in normalized


async def discover(settings: Settings) -> Dict[str, Any]:
    base = settings.root_base
    resolved: Dict[str, Optional[str]] = {}
    present: Dict[str, Optional[str]] = {}
    findings: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=settings.http_timeout, verify=settings.verify_tls) as c:
        openapi = await fetch_openapi(c, base)
        if not openapi:
            # No OpenAPI reachable — fall back to the corrected-§3 defaults so the
            # sim is still usable, but flag it.
            for cap, cands in _CANDIDATES.items():
                resolved[cap] = cands[0]
            return {
                "openapi_ok": False, "path_count": 0, "resolved": resolved, "present": present,
                "dead_referenced": [], "fallback": True,
                "findings": [{
                    "standard": "Discovery", "spec_section": "OpenAPI", "check": "openapi_reachable",
                    "severity": "warn", "endpoint": base + "/openapi.json",
                    "expected": "GET /openapi.json returns the route map",
                    "observed": "OpenAPI not reachable; using corrected-§3 default paths", "scenario": "",
                }],
            }

        normalized = _normalize_paths(openapi)
        for cap, cands in _CANDIDATES.items():
            chosen = next((p for p in cands if _match(p, normalized)), None)
            resolved[cap] = chosen or cands[0]
            present[cap] = chosen
            if chosen is None:
                sev = "fail" if cap in ("vast_canonical", "ortb_auction") else "warn"
                findings.append({
                    "standard": "Discovery", "spec_section": "OpenAPI route map", "check": f"present:{cap}",
                    "severity": sev, "endpoint": cands[0],
                    "expected": f"{cap} mounted at one of {cands}",
                    "observed": "no matching route in OpenAPI", "scenario": "",
                })

        dead_found = [p for p in _DEAD_CLAIMED if _match(p, normalized)]
        for p in _DEAD_CLAIMED:
            if _match(p, normalized):
                findings.append({
                    "standard": "Discovery", "spec_section": "build prompt §3", "check": "dead_route_now_live",
                    "severity": "info", "endpoint": p,
                    "expected": "(prompt assumed this route was dead)",
                    "observed": f"{p} IS present in OpenAPI now", "scenario": "",
                })

    return {
        "openapi_ok": True, "path_count": len(openapi.get("paths") or {}),
        "resolved": resolved, "present": present, "dead_referenced": dead_found,
        "fallback": False, "findings": findings,
    }
