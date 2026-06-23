"""Ad Server Simulator — FastAPI application entrypoint.

Run:  uvicorn app.main:app --port 8090 --reload   (from the backend/ dir)
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

from app.adserver.client import AdServerClient
from app.api.routes import router
from app.api.run_manager import RunManager
from app.config import get_settings
from app.db import Database, set_db

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
    try:
        yield
    finally:
        await client.aclose()
        await db.close()


app = FastAPI(title="Ad Server Simulator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(router, prefix="/api")

_DIST = Path(os.environ.get("DASHBOARD_DIST") or (Path(__file__).resolve().parents[2] / "dashboard" / "dist"))
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")
else:
    @app.get("/")
    async def _root():
        return JSONResponse({
            "name": "Ad Server Simulator",
            "api": "/api",
            "docs": "/docs",
            "note": "Dashboard not built. Run the Vite dev server in ../dashboard, "
                    "or `npm run build` to serve it from here.",
        })
