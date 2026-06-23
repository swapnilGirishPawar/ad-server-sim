# Ad Server Simulator

A local load + behaviour simulator for the **Voise Ad Server**. It seeds a realistic
ecosystem (publishers, ad units, advertisers, DSPs/line items, campaigns, creatives),
generates configurable traffic over **VAST** and **OpenRTB**, fires impressions / clicks /
win-notices, runs predefined business scenarios, and reports everything on a live dashboard.

> **Design philosophy:** the simulator is a *standard, correct* AdTech harness and the
> **source of truth**. The Voise Ad Server is the system-under-test. Where the server does
> not behave the way a correct ad server should, the simulator reports it as a **GAP** (with
> evidence) instead of bending its own logic to hide the problem. Several such gaps exist in
> the current server — see [Findings](#findings-real-ad-server-behaviour-surfaced).

---

## Contents
- [Architecture](#architecture)
- [How it integrates with the ad server](#how-it-integrates-with-the-ad-server)
- [Findings (real ad-server behaviour surfaced)](#findings-real-ad-server-behaviour-surfaced)
- [Prerequisites](#prerequisites)
- [Setup](#setup) · [Local](#local-dev) · [Docker](#docker)
- [Configuration](#configuration)
- [Usage](#usage) · [Dashboard](#dashboard) · [HTTP API](#http-api)
- [Scenarios](#scenarios)
- [Tests](#tests)
- [Project layout](#project-layout)
- [Extending](#extending)

---

## Architecture

```
ad-server-sim/
  backend/                 Python · FastAPI · httpx · aiosqlite
    app/
      config.py            env-based settings (pydantic-settings)
      db.py                async SQLite store (runs, requests, events, users, scenarios)
      adserver/            integration with the target ad server
        client.py          auth, seeding (REST), VAST + OpenRTB requests, tracking, reporting reads
        vast.py            VAST 4.2 parser (winner + tracking URLs)
        ortb.py            OpenRTB 2.6 request builder + response parser
        tracking.py        tracking-URL normalisation + canonical builders
      modules/
        seeder.py          M1 — seed data generator
        traffic.py         M2 — traffic generator (asyncio workers, RPS pacing, concurrency)
        impressions.py     M3 — impression simulator (impression_rate + delay)
        clicks.py          M4 — click simulator (CTR)
        users.py           M5 — user simulator (new/returning, frequency)
        scenarios.py       M6 — scenario engine (A–D, PASS/GAP/FAIL verdicts)
        metrics.py         aggregation (sim-measured + server cross-check)
      api/                 REST + WebSocket (run orchestration, live progress)
    tests/                 pytest (VAST/ORTB/tracking/metrics)
  dashboard/               React · Vite · Tailwind · Recharts
  Dockerfile · docker-compose.yml
  scenarios/               example scenario definitions + sample output
```

The spec named Node.js/TypeScript; this implementation uses **Python/FastAPI + React** to
match the team's stack. Every functional requirement (seed, traffic, impressions, clicks,
users, scenarios, dashboard, SQLite storage, Docker) is met. The Python analogue of "Worker
Threads" is asyncio + httpx with a concurrency semaphore and a token-bucket RPS pacer.

## How it integrates with the ad server

The Voise Ad Server is **VAST/video-centric** — there is no JSON display-decision endpoint.
The simulator therefore drives the real serving + tracking endpoints:

| Purpose | Endpoint | Notes |
|---|---|---|
| Auth (seeding) | `POST /api/auth/login` | HS256 JWT; admin/V1-admin role needed for some entities |
| Ad request (VAST) | `GET /api/v/{tag_id}?pub=…` | runs the internal auction `decide_vast_ad`; returns VAST 4.2 |
| Ad request (OpenRTB) | `POST /api/b/{tag_id}?pub=…` | OpenRTB 2.6; fans out to demand partners |
| Impression | `GET /api/track/impression` | 1×1 GIF |
| Click | `GET /api/track/click` | 302 redirect |
| Win notice | `GET /api/track/win` | the only path that increments campaign spend |
| Reporting | `GET /api/campaigns/{id}/stats`, `/reports/timeseries`, `/rtb-stats` | server-side cross-check |

The auction (`backend/services/decisioning_core.py:decide_vast_ad`) selects campaigns
**globally** by `target_cpm`, gated on budget/dates, joined to a creative. The simulator
parses the winning campaign + tracking URLs out of the returned VAST. Metrics are computed
from the simulator's own record of what it sent/observed (authoritative), and optionally
cross-checked against the server's own reports.

## Findings (real ad-server behaviour surfaced)

Running the simulator against the current server surfaces these issues. They are **expected**
and reported as findings, not simulator errors:

1. **`POST /api/publishers` returns HTTP 500.** Publisher (and therefore ad-unit) creation
   fails. The simulator continues with **synthetic tag_ids** — serving ignores ad units, so
   this does not block traffic, but it is a real server bug.
2. **Campaigns created via REST are unserveable as-is.** The create API stores
   `format_targets` / `cpm_bid` / `cached_spend_*`, but the auction reads `ad_format` /
   `target_cpm` / `spent`. A freshly created campaign matches **zero** decisioning queries.
   The simulator applies a **REST `PUT` shim** (`update_campaign` does a raw `$set`) to add the
   decisioning field names so campaigns can serve. *(Field-name divergence between the create
   API and the decisioning engine is the headline bug.)*
3. **Campaign / advertiser creation requires `platform_admin`/`tenant_admin`** (RBAC #295),
   but `/api/auth/register` only ever grants `trafficker`. You must point the simulator at a
   V1-admin account (see [Prerequisites](#prerequisites)).
4. **Country/device targeting is not enforced** by the internal auction → Scenario B = GAP.
5. **No per-user frequency capping** in the internal auction → Scenario D = GAP.
6. **Budget never closes the loop** — eligibility reads `spent`, but wins increment `spend`,
   and spend attribution needs a line-item→campaign link → Scenario A = GAP.
7. **The internal VAST endpoint always returns an ad** (a default "Video Ad" filler when no
   real campaign is selected). The simulator treats the filler as a no-fill so fill-rate and
   win-distribution reflect *real campaign* serving.
8. **Embedded tracking URLs use a production host and omit `/api`** (e.g.
   `https://voiseadserver.com/track/impression`). The simulator rewrites scheme/host and adds
   `/api` (toggle `TRACKING_PREFIX_FIX`), logging each rewrite so the bug stays visible.

## Prerequisites

- The **Voise Ad Server running locally** (default `http://localhost:8001`, `GET /api/ping` → `{"pong":true}`) with its MongoDB.
- A **V1-admin** user (`platform_admin` or `tenant_admin`). Registration cannot grant this, so promote one once, e.g. on the local Mongo:
  ```js
  // mongosh  (db name is typically voisetech_adserver_local)
  db.users.updateOne({ email: "dev@localhost.com" }, { $set: { role: "platform_admin" } })
  ```
  Then set that account's credentials in the simulator's `.env`.
- Python 3.12+ and Node 18+ for local dev (the repo is verified on Python 3.14 + Node 24).

## Setup

### Local dev

```bash
# 1) Backend
cd ad-server-sim/backend
python -m venv .venv && . .venv/Scripts/activate      # Windows; use bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env                                   # then edit AD_SERVER_EMAIL / PASSWORD
uvicorn app.main:app --port 8090 --reload

# 2) Dashboard (separate terminal)
cd ad-server-sim/dashboard
npm install
npm run dev            # http://localhost:5173  (proxies /api -> :8090)
```

Or build the dashboard once and let the backend serve it at `http://localhost:8090/`:
```bash
cd ad-server-sim/dashboard && npm run build
# the backend auto-serves dashboard/dist at /
```

### Docker

```bash
cd ad-server-sim
AD_SERVER_PASSWORD=yourpass docker compose up --build
# dashboard + API on http://localhost:8090
```
The container reaches an ad server on the host via `host.docker.internal:8001` (override with
`AD_SERVER_URL`). SQLite is persisted in the `sim-data` volume.

## Configuration

All via env / `.env` (see `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `AD_SERVER_URL` | `http://localhost:8001` | target ad server base URL |
| `AD_SERVER_EMAIL` / `AD_SERVER_PASSWORD` | `dev@localhost.com` / — | V1-admin credentials for seeding |
| `AUTO_REGISTER` | `true` | self-register the sim user if login fails (grants `trafficker` only) |
| `REQUESTS_PER_SECOND` | `50` | traffic pacing |
| `CONCURRENCY` | `10` | in-flight ad requests |
| `TOTAL_REQUESTS` | `500` | bounded run size (`DURATION_SECONDS>0` overrides) |
| `SERVE_PROTOCOLS` | `vast` | `vast`, `ortb`, or `vast,ortb` |
| `DEFAULT_IMPRESSION_RATE` | `0.9` | share of fills that fire an impression |
| `DEFAULT_CTR` | `0.03` | share of impressions that click |
| `TRACKING_PREFIX_FIX` | `true` | rewrite embedded `/track` URLs to `/api/track` |
| `SIM_DB_PATH` | `./sim.db` | SQLite path |
| `COUNTRIES` / `DEVICES` / `BROWSERS` | IN,US,UK,CA / mobile,desktop,tablet / chrome,firefox,safari,edge | traffic dimension pools |

## Usage

### Dashboard
Open the dashboard, then: **1 · Seed data** → **2 · Generate traffic** → **3 · Business
scenarios**. Live run progress streams over WebSocket; metrics, charts (requests/impressions/
clicks/spend over time), the campaign table, auction stats (avg & P95 latency, RPS, win
distribution) and scenario verdicts update automatically. Use the **View** dropdown to filter
metrics by a specific run.

### HTTP API
The simulator's own API is served under `/api` on port 8090:

```bash
# Seed an ecosystem
curl -X POST localhost:8090/api/seed -H 'Content-Type: application/json' \
  -d '{"publishers":3,"campaigns":6,"cpm_min":5,"cpm_max":150}'

# Run traffic (background; returns {run_id})
curl -X POST localhost:8090/api/run -H 'Content-Type: application/json' \
  -d '{"label":"smoke","total_requests":300,"requests_per_second":50,"protocols":["vast"]}'

# Run a scenario (A | B | C | D | all)
curl -X POST localhost:8090/api/scenario -H 'Content-Type: application/json' -d '{"scenario":"all"}'

# Metrics
curl localhost:8090/api/metrics/overview
curl localhost:8090/api/metrics/campaigns
curl localhost:8090/api/metrics/auctions
curl localhost:8090/api/metrics/timeseries
curl localhost:8090/api/metrics/scenarios
```

## Scenarios

`scenarios/*.json` contain the definitions; `scenarios/example_output.json` is real captured
output. Each scenario asserts the **standard** expected behaviour:

| # | Scenario | Standard expectation | Verdict vs current server |
|---|---|---|---|
| A | Budget exhaustion | stops serving at budget | **GAP** — `spent` vs `spend` mismatch; budget never closes |
| B | Country targeting (IN only) | only IN served | **GAP** — no geo targeting in the auction |
| C | Bid competition | higher CPM wins more | **PASS** — auction ranks by `target_cpm` |
| D | Frequency cap (3/user) | 4th+ request not served | **GAP** — no per-user frequency cap |

## Tests

```bash
cd ad-server-sim/backend && . .venv/Scripts/activate
pytest            # VAST parser, OpenRTB build/parse, tracking normalisation, metric math
```
Tests are fully offline (no live ad server needed).

## Project layout

See [Architecture](#architecture). The integration layer (`app/adserver/`) is the only place
that knows the ad server's wire format; modules and the dashboard are decoupled from it.

## Extending

The design anticipates additional AdTech concepts. Likely extension points:
- **More protocols / exchanges** — add a builder/parser under `app/adserver/` and a branch in
  `traffic.py` (OpenRTB is already implemented as the second protocol).
- **Pacing algorithms** — extend the traffic pacer in `traffic.py`.
- **New scenarios** — add a method to `ScenarioEngine` and an entry to the dispatch map.
- **MongoDB storage** — the spec's optional store; swap the `Database` implementation in `db.py`.
