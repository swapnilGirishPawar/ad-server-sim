"""Ad Server Simulator — FastAPI application entrypoint.

Run:  uvicorn app.main:app --port 8090 --reload   (from the backend/ dir)

Mounts:
  /api    — simulator control + metrics + report API
  /dsp    — the built-in fake DSP (the SUT fans out to /dsp/bid)
  /       — the built React dashboard (if dashboard/dist exists)
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import discovery as discovery_mod
from app.adserver.client import AdServerClient
from app.api.routes import router
from app.api.run_manager import RunManager
from app.config import get_settings
from app.db import Database, set_db
from app.dsp.router import router as dsp_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("adsim")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    db = Database(s.sim_db_path)
    await db.connect()
    set_db(db)
    client = AdServerClient(s)
    app.state.settings = s
    app.state.db = db
    app.state.client = client
    app.state.run_manager = RunManager(db, client, s)
    logger.info("Simulator started. Target ad server: %s", s.ad_server_url)
    if s.discover_on_start:
        try:
            disc = await discovery_mod.discover(s)
            client.apply_discovery(disc)
            logger.info("Target discovery: openapi_ok=%s, %d routes, resolved=%s",
                        disc.get("openapi_ok"), disc.get("path_count", 0), client.routes)
        except Exception as e:  # noqa: BLE001 - discovery must never block startup
            logger.warning("Target discovery failed (using default routes): %s", e)
    try:
        yield
    finally:
        await client.aclose()
        await db.close()


app = FastAPI(title="Ad Server Simulator", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router, prefix="/api")
app.include_router(dsp_router, prefix="/dsp")

_DIST = Path(os.environ.get("DASHBOARD_DIST") or (Path(__file__).resolve().parents[2] / "dashboard" / "dist"))
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")
else:
    @app.get("/")
    async def _root():
        return JSONResponse({
            "name": "Ad Server Simulator",
            "api": "/api",
            "dsp": "/dsp/bid",
            "docs": "/docs",
            "note": "Dashboard not built. Run the Vite dev server in ../dashboard, "
                    "or `npm run build` to serve it from here.",
        })
