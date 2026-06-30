# Voise Ad Sim — IAB Conformance + Load Simulator

A standalone test harness for the **Voise Ad Server** (the *system under test*, "SUT"). It
seeds a serveable ecosystem, drives realistic traffic over **VAST** and **OpenRTB**, behaves
like a real player/exchange (follows wrappers, substitutes macros, fires ordered quartiles),
and **validates every response against the published IAB specs** — reporting honestly where
the SUT does or does not conform.

> **Design philosophy (unchanged, now enforced):** the simulator validates against the
> **IAB standard, never the implementation**. Where the SUT deviates from spec it is a
> **GAP** (with evidence + spec reference), never a loosened assertion. See
> [Conformance](#conformance) and [Scenarios](#scenarios-s1s15).

---

## What's new in v1.0

- **Real IAB validators** (`app/adserver/validators.py`): VAST 4.x structural validation
  (version, InLine vs Wrapper, required nodes, `Duration` HH:MM:SS, `MediaFile` attrs,
  `VideoClicks`, quartile `TrackingEvents`, OMID `AdVerifications`), VMAP 1.0 (AdBreak /
  timeOffset / AdSource), and OpenRTB 2.5/2.6 BidResponse.
- **Recursive Wrapper following** — resolves `VASTAdTagURI` with a depth cap + loop detection.
- **Macro substitution** (`app/adserver/macros.py`) — `[CACHEBUSTING]`, `[TIMESTAMP]`,
  `[CONTENTPLAYHEAD]`, `[ERRORCODE]` fired like a real player.
- **Ordered quartile fire-back** — `start → firstQuartile → midpoint → thirdQuartile → complete`.
- **Complete OpenRTB requests** — `regs` (gdpr/us_privacy/gpp/coppa), `user.ext.consent`,
  `source.ext.schain` (SupplyChain), app/site + `device.ifa`, and 2.6 video **pods**.
- **Built-in fake DSP** (`app/dsp/`) — a controllable bidder the SUT fans out to, so the
  OpenRTB auction can actually win (enables S10). Modes: `bid` / `no_bid` / `timeout` / `error`.
- **Target discovery** (`app/discovery.py`) — reads the SUT's `/openapi.json` on startup and
  repoints to live routes (so it never drives the dead `/api/serve/*` paths).
- **Supply-chain validation** — fetches + validates `ads.txt` / `app-ads.txt` / `sellers.json`.
- **Full S1–S15 scenario catalogue** with recalibrated PASS / GAP / BLOCKED / FAIL oracles.
- **Conformance deliverables** — a per-standard **scorecard**, auto-generated **`GAP_REPORT.md`**,
  and machine-readable **`gaps.json`**.
- **Load SLOs** — p50/p95/p99 latency, error rate, RPS, ramp-up, and a pass/fail SLO verdict.

---

## Architecture

```
ad-server-sim/
  backend/                 Python · FastAPI · httpx · aiosqlite
    app/
      config.py            env-based settings (target URL, DSP url, discovery, SLOs)
      conformance.py       Finding model + per-standard scorecard
      discovery.py         reads SUT /openapi.json → resolves live routes
      report.py            GAP_REPORT.md + gaps.json + scorecard
      findings_recorder.py de-duplicating per-run conformance-finding store
      adserver/
        client.py          auth, seeding, VAST+OpenRTB requests, wrapper-follow, fire-back, supply fetch
        validators.py      IAB validators: VAST 4.x, VMAP 1.0, OpenRTB 2.5/2.6
        macros.py          VAST macro substitution
        vast.py            lightweight VAST extractor (kept for back-compat)
        ortb.py            OpenRTB 2.5/2.6 request builder (+schain/privacy/pods) + response parser
        tracking.py        host/prefix rewrite + macro substitution + canonical builders
        supplychain.py     ads.txt / app-ads.txt / sellers.json / sChain validators
      dsp/router.py        the controllable fake DSP (mounted at /dsp)
      modules/
        seeder.py          M1 — seed data (+ registers the fake DSP)
        traffic.py         M2 — traffic generator (RPS pacing, ramp, percentiles, SLO)
        impressions.py     M3 · clicks.py M4 · users.py M5
        scenarios.py       M6 — S1–S15 scenario engine (PASS/GAP/BLOCKED/FAIL)
        metrics.py         aggregation, fill breakdown, scorecard, reconciler
      api/                 REST + WebSocket control plane
    tests/                 pytest — validators, macros, supply-chain, ORTB, VAST, tracking, metrics
  dashboard/               React · Vite · Tailwind · Recharts (scorecard, fill, latency, findings)
  Dockerfile · docker-compose.yml
```

## How it integrates with the ad server

The SUT is **VAST/video-centric**. The simulator drives the **actually-mounted** live routes
(verified via target discovery — the old `/api/serve/*vast` router is dead code and 404s):

| Purpose | Live endpoint | Notes |
|---|---|---|
| Canonical VAST (decisioning) | `GET /api/v/{tag_id}` | runs `decide_vast_ad`; **always fills** (real ad or "Video Ad" filler) |
| OpenRTB auction | `POST /api/b/{tag_id}` (== `/ortb/bid/{tag_id}`) | first-price; no-bid = bare **204** (no `nbr`) |
| Impression / click / win / event / error | `GET /api/track/*` | public, no auth |
| ads.txt / app-ads.txt / sellers.json | root `/ads.txt`, `/app-ads.txt`, `/sellers.json` (or `/api/ortb/*`) | **not** `/ortb/*` |
| VMAP (static) | `GET /api/m/{tag_id}` | 3-break template (no real ad pods exist in the SUT) |

Target discovery resolves these at startup; if `/openapi.json` is unreachable it falls back to
the corrected defaults above.

## Conformance

Every VAST/OpenRTB response and supply-chain file is run through the validators, which emit
**findings** `{standard, spec_section, check, severity, expected, observed, endpoint, scenario}`.
Severity is `pass` / `fail` / `warn` / `info` (an `info` like "OMID absent" is never a failure).
Findings roll up into a **scorecard** (per standard) and the **GAP report**:

```bash
curl localhost:8090/api/metrics/scorecard          # per-standard pass/fail/warn
curl localhost:8090/api/report/gaps.json           # machine-readable gaps + scorecard
curl localhost:8090/api/report/markdown            # human-readable GAP_REPORT.md
# files are also written to ./reports/GAP_REPORT.md and ./reports/gaps.json
```

### Known SUT gaps this surfaces (expected — not simulator errors)
1. `POST /api/publishers` 500 → synthetic tag_ids (serving ignores ad units).
2. Campaign create writes `format_targets`/`cpm_bid`; auction reads `ad_format`/`target_cpm` →
   REST campaigns serve filler until the simulator's `PUT` shim fixes the field names.
3. Campaign/advertiser create needs `platform_admin`/`tenant_admin` (register grants `trafficker`).
4. No geo/device targeting (S5), no frequency cap (S6), budget never closes — `spent` vs `spend` (S7).
5. Every live VAST route always fills → no spec-correct no-fill / empty-VAST (S4).
6. `decide_vast_ad` VAST embeds `/track/...` **without `/api`** (prod host) → the sim rewrites
   host **and** adds `/api`, logging each rewrite as a finding (S11).
7. No real ad pods anywhere; no `nbr` on no-bid; deals/2.6-pods not auctioned (S9/S10).

## Prerequisites

- The **Voise Ad Server running** (default `http://localhost:8001`) with MongoDB.
- A **V1-admin** user for full seeding (`platform_admin`/`tenant_admin`). Registration only
  grants `trafficker`, so promote one once:
  ```js
  // mongosh, db voisetech_adserver_local
  db.users.updateOne({ email: "dev@localhost.com" }, { $set: { role: "platform_admin" } })
  ```
  Put those creds in the simulator's `.env`. (Smoke/S1/S3 work without admin since the SUT
  always fills; targeting/budget scenarios need real campaigns.)
- For S10 (OpenRTB win): the SUT must be able to reach the sim's fake DSP at
  `SIM_PUBLIC_URL + /dsp/bid` (default `http://localhost:8090/dsp/bid`).
- Python 3.12+ and Node 18+ for local dev.

## Setup

### Local dev
```bash
cd ad-server-sim/backend
python -m venv .venv && . .venv/Scripts/activate     # Windows; bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env                                  # set AD_SERVER_EMAIL / PASSWORD
uvicorn app.main:app --port 8090 --reload
# build the dashboard once so it is served at http://localhost:8090/
cd ../dashboard && npm install && npm run build
```

### Docker
```bash
cd ad-server-sim
AD_SERVER_PASSWORD=yourpass docker compose up --build   # http://localhost:8090
```
The container reaches a host ad server via `host.docker.internal:8001`. For S10, set
`SIM_PUBLIC_URL=http://host.docker.internal:8090` so the SUT can reach the fake DSP.

## Configuration (env / `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `AD_SERVER_URL` | `http://localhost:8001` | target ad server base URL |
| `AD_SERVER_EMAIL` / `AD_SERVER_PASSWORD` | `dev@localhost.com` / — | admin creds for seeding |
| `DISCOVER_ON_START` | `true` | read SUT `/openapi.json` and repoint to live routes |
| `SIM_PUBLIC_URL` | `http://localhost:8090` | URL the SUT uses to reach the fake DSP |
| `REQUESTS_PER_SECOND` / `CONCURRENCY` / `TOTAL_REQUESTS` | `50` / `10` / `500` | traffic pacing |
| `SERVE_PROTOCOLS` | `vast` | `vast`, `ortb`, or `vast,ortb` |
| `DEFAULT_IMPRESSION_RATE` / `DEFAULT_CTR` | `0.9` / `0.03` | post-fill behaviour |
| `TRACKING_PREFIX_FIX` | `true` | rewrite embedded `/track` → `/api/track` |
| `REPORT_DIR` | `./reports` | where GAP_REPORT.md / gaps.json are written |
| `SIM_DB_PATH` | `./sim.db` | SQLite path |

## Usage

### Dashboard (recommended)
Open `http://localhost:8090`, then **1 · Seed** → **2 · Generate traffic** → **3 · Scenarios**.
The page shows the conformance **scorecard**, real-vs-filler **fill breakdown**, **latency
percentiles**, charts, the **findings** table, and per-scenario verdicts. Use **GAP report** /
**gaps.json** buttons to export.

### HTTP API (port 8090, under `/api`)
```bash
curl localhost:8090/api/target                      # what live routes were discovered
curl -X POST localhost:8090/api/seed -d '{"campaigns":6,"seed_fake_dsp":true}' -H 'Content-Type: application/json'
curl -X POST localhost:8090/api/run  -d '{"total_requests":300,"protocols":["vast"],"fire_quartiles":true}' -H 'Content-Type: application/json'
curl -X POST localhost:8090/api/scenario -d '{"scenario":"all"}' -H 'Content-Type: application/json'   # S1..S15 | A-D | all
curl localhost:8090/api/metrics/scorecard
curl localhost:8090/api/metrics/fill
curl localhost:8090/api/metrics/reconcile           # sim-vs-server, within-tolerance verdict
curl localhost:8090/api/supply-chain                # ads.txt / sellers.json validation
curl localhost:8090/api/report/markdown             # GAP_REPORT.md
curl -X POST localhost:8090/api/dsp/config -d '{"mode":"no_bid"}' -H 'Content-Type: application/json'  # control the fake DSP
```

## Scenarios (S1–S15)

`POST /api/scenario {"scenario": "S7" | "all" | "A".."D"}`. Verdicts:
**PASS** (SUT conforms) · **GAP** (SUT deviates — the finding) · **BLOCKED** (no live capability) · **FAIL** (couldn't validate).

| # | Scenario | Expectation | Expected vs current SUT |
|---|---|---|---|
| S1 | Smoke | spec-valid VAST 4.x | **PASS** |
| S2 | Normal traffic | valid markup, sane fill/latency | **PASS** |
| S3 | Real-vs-filler | real-fill > 0 after workaround | **PASS** (else GAP) |
| S4 | No-fill semantics | empty VAST / `<Error>` / 204+nbr | **GAP** — SUT always fills |
| S5 | Geo targeting | off-geo not served | **GAP** — no geo targeting |
| S6 | Frequency cap | capped after N | **GAP** — no cap |
| S7 | Budget exhaustion | stops at budget | **GAP** — `spent`≠`spend` |
| S8 | Schedule / flight | expired not selected | **PASS** — date gating works |
| S9 | Ad pods / VMAP | valid VMAP + multi-ad pod | **PASS** (VMAP) + **BLOCKED** (pods) |
| S10 | OpenRTB conformance | spec-valid BidResponse or 204 | **PASS** with fake DSP, else **BLOCKED** |
| S11 | Tracking accuracy | ordered quartiles record | **PASS** (notes `/api`-prefix bug) |
| S12 | Privacy (GDPR/GPP) | OpenRTB regs passthrough | **PASS** (serving drops them — GAP) |
| S13 | ads.txt/sellers.json/sChain | valid files + schain | **PASS** |
| S14 | Load / SLO | p95 + error-rate SLOs | PASS/FAIL vs thresholds |
| S15 | Resilience | graceful on malformed (no 5xx) | **PASS** |

## Tests
```bash
cd ad-server-sim/backend && . .venv/Scripts/activate
pytest      # validators, macros, supply-chain, ORTB, VAST, tracking, metrics — fully offline
```

## Extending
- **New standard validator** — add to `app/adserver/validators.py`, emit `Finding`s; it shows
  up in the scorecard + gap report automatically.
- **New scenario** — add an `sN` method to `ScenarioEngine` and an entry to its dispatch map.
- **DSP behaviours** — extend `app/dsp/router.py` (e.g. seat-bid shaping, deal IDs).
