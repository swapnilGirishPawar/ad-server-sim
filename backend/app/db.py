"""Async SQLite storage for the simulator.

A single shared aiosqlite connection (WAL mode) backs the whole app. aiosqlite
serialises operations on its own worker thread, so a shared connection is safe
under asyncio concurrency. High-volume inserts (ad requests / events) go through
`insert_batch` to avoid per-row commit overhead.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, List, Optional, Sequence

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id           TEXT PRIMARY KEY,
    kind         TEXT,
    label        TEXT,
    status       TEXT,
    config_json  TEXT,
    summary_json TEXT,
    started_at   TEXT,
    started_ms   INTEGER,
    ended_at     TEXT,
    ended_ms     INTEGER
);

CREATE TABLE IF NOT EXISTS ad_requests (
    id                 TEXT PRIMARY KEY,
    run_id             TEXT,
    ts                 TEXT,
    ts_ms              INTEGER,
    protocol           TEXT,
    tag_id             TEXT,
    publisher_id       TEXT,
    ad_unit_id         TEXT,
    country            TEXT,
    device             TEXT,
    browser            TEXT,
    user_id            TEXT,
    status_code        INTEGER,
    latency_ms         REAL,
    filled             INTEGER,
    winner_campaign    TEXT,
    winner_campaign_id TEXT,
    winner_creative_id TEXT,
    price              REAL,
    no_fill_reason     TEXT,
    trace_id           TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    run_id       TEXT,
    ts           TEXT,
    ts_ms        INTEGER,
    type         TEXT,
    request_id   TEXT,
    tag_id       TEXT,
    publisher_id TEXT,
    user_id      TEXT,
    campaign_id  TEXT,
    campaign     TEXT,
    price        REAL,
    url          TEXT,
    status_code  INTEGER,
    ok           INTEGER,
    note         TEXT,
    trace_id     TEXT
);

CREATE TABLE IF NOT EXISTS sim_users (
    user_id       TEXT PRIMARY KEY,
    country       TEXT,
    device        TEXT,
    browser       TEXT,
    first_ms      INTEGER,
    last_ms       INTEGER,
    request_count INTEGER
);

CREATE TABLE IF NOT EXISTS seed_entities (
    id         TEXT PRIMARY KEY,
    kind       TEXT,
    server_id  TEXT,
    numeric_id TEXT,
    name       TEXT,
    parent_id  TEXT,
    data_json  TEXT,
    created_at TEXT,
    UNIQUE(kind, server_id)
);

CREATE TABLE IF NOT EXISTS scenario_results (
    id            TEXT PRIMARY KEY,
    run_id        TEXT,
    scenario      TEXT,
    verdict       TEXT,
    title         TEXT,
    expected      TEXT,
    actual        TEXT,
    evidence_json TEXT,
    created_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_req_run  ON ad_requests(run_id);
CREATE INDEX IF NOT EXISTS idx_req_ts   ON ad_requests(ts_ms);
CREATE INDEX IF NOT EXISTS idx_evt_run  ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_evt_ts   ON events(ts_ms);
CREATE INDEX IF NOT EXISTS idx_evt_type ON events(type);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected; call connect() first.")
        return self._conn

    async def execute(self, sql: str, params: Sequence[Any] = (), commit: bool = True) -> None:
        async with self._lock:
            await self.conn.execute(sql, params)
            if commit:
                await self.conn.commit()

    async def insert(self, table: str, row: Dict[str, Any]) -> None:
        await self.insert_batch(table, [row])

    async def insert_batch(self, table: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
        values = [tuple(r.get(c) for c in cols) for r in rows]
        async with self._lock:
            await self.conn.executemany(sql, values)
            await self.conn.commit()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def upsert_user_counts(self, rows: Iterable[Dict[str, Any]]) -> None:
        """Increment per-user request counts (used for frequency-cap analysis)."""
        sql = (
            "INSERT INTO sim_users (user_id, country, device, browser, first_ms, last_ms, request_count) "
            "VALUES (:user_id, :country, :device, :browser, :ms, :ms, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET last_ms=excluded.last_ms, "
            "request_count=request_count+1"
        )
        async with self._lock:
            for r in rows:
                await self.conn.execute(sql, r)
            await self.conn.commit()


# Module-level singleton, initialised by the FastAPI lifespan / CLI bootstrap.
_db: Optional[Database] = None


def set_db(db: Database) -> None:
    global _db
    _db = db


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialised.")
    return _db
