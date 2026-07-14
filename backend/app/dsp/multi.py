"""Multi-DSP control plane — list/create/delete mock DSPs and serve each one's
own bid/config/track/vast/health endpoints under `/dsps/{dsp_id}/...`.

`dsp-1` (the original single fake DSP in `app.dsp.router`) is registered here
too, so it's reachable both the historical way (`/dsp/bid`) and uniformly
alongside every other DSP (`/dsps/dsp-1/bid`) — same underlying config/stats.

Point a second (third, ...) demand partner's `endpoint_url` on the real ad
server at `/dsps/{dsp_id}/bid` to have it compete against dsp-1 (or any other
registered DSP) in the same live auction.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request, Response

from app.config import get_settings
from app.dsp import registry
from app.dsp.router import (
    _get_config, _handle_bid, _health, _reset_stats, _serve_vast, _set_config, _track_hit,
)
from app.models import DspCreate

router = APIRouter()


def _endpoint_url(dsp_id: str) -> str:
    base = get_settings().sim_public_url.rstrip("/")
    return f"{base}/dsps/{dsp_id}/bid"


def _summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry["id"], "name": entry["name"],
        "endpoint_url": _endpoint_url(entry["id"]),
        "config": entry["config"], "stats": entry["stats"],
    }


@router.get("/")
async def list_dsps() -> List[Dict[str, Any]]:
    return [_summary(e) for e in registry.DSPS.values()]


@router.post("/")
async def create_dsp(body: DspCreate) -> Dict[str, Any]:
    entry = registry.create_dsp(name=body.name, dsp_id=body.dsp_id)
    return _summary(entry)


@router.delete("/{dsp_id}")
async def delete_dsp(dsp_id: str) -> Dict[str, Any]:
    registry.delete_dsp(dsp_id)
    return {"ok": True}


@router.get("/{dsp_id}/config")
async def get_config(dsp_id: str) -> Dict[str, Any]:
    return _get_config(registry.get_dsp(dsp_id)["config"])


@router.post("/{dsp_id}/config")
async def set_config(dsp_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    return _set_config(registry.get_dsp(dsp_id)["config"], patch)


@router.post("/{dsp_id}/reset")
async def reset(dsp_id: str) -> Dict[str, Any]:
    return _reset_stats(registry.get_dsp(dsp_id)["stats"])


@router.get("/{dsp_id}/health")
async def health(dsp_id: str) -> Dict[str, Any]:
    entry = registry.get_dsp(dsp_id)
    return _health(entry["config"], entry["stats"])


@router.get("/{dsp_id}/track")
async def track(dsp_id: str, request: Request) -> Response:
    entry = registry.get_dsp(dsp_id)
    return await _track_hit(entry["config"], entry["stats"], request, label=f"MOCK DSP [{dsp_id}] (advertiser)")


@router.get("/{dsp_id}/vast")
async def vast(dsp_id: str, request: Request) -> Response:
    entry = registry.get_dsp(dsp_id)
    return _serve_vast(entry["config"], request, track_path=f"/dsps/{dsp_id}/track")


@router.api_route("/{dsp_id}/bid", methods=["POST"])
@router.api_route("/{dsp_id}/bid/{tag_id}", methods=["POST"])
async def bid(dsp_id: str, request: Request, tag_id: str = "") -> Response:
    entry = registry.get_dsp(dsp_id)
    return await _handle_bid(entry["config"], entry["stats"], request, tag_id,
                             track_path=f"/dsps/{dsp_id}/track", label=f"MOCK DSP [{dsp_id}]")
