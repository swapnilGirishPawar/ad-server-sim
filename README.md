# Voise Ad Sim — IAB Conformance + Load Simulator

A standalone test harness for the **Voise Ad Server** (the *system under test*, **SUT**). It seeds a serveable ecosystem, drives realistic traffic over **VAST** and **OpenRTB**, behaves like a real player/exchange (follows wrappers, substitutes macros, fires ordered quartiles), and **validates every response against the published IAB specs** — reporting honestly where the SUT does or does not conform.

> **Design philosophy:** the simulator validates against the **IAB standard, never the implementation**. Where the SUT deviates from spec it is a **GAP** (with evidence + spec reference), never a loosened assertion. See [Conformance](#conformance) and [Scenarios (S1–S15)](#scenarios-s1s15).

| | |
|---|---|
| **Simulator UI + API** | `http://localhost:8090` |
| **Mock DSP** | `http://localhost:8090/dsp/bid` |
| **Target ad server (SUT)** | `http://localhost:8001` (default) |
| **API docs (OpenAPI)** | `http://localhost:8090/docs` |

### Related docs

| Doc | Audience | Purpose |
|---|---|---|
| [`setup.md`](setup.md) | Anyone | Step-by-step install on a new machine |
| [`HOW-TO-USE.md`](HOW-TO-USE.md) | Non-technical | Plain-language walkthrough of the dashboard |
| [`postman/README.md`](postman/README.md) | QA / engineers | Click-through E2E flows in Postman |
| [`scenarios/README.md`](scenarios/README.md) | Engineers | Legacy A–D scenario fixtures |
| [`docs/SCREENSHOTS.md`](docs/SCREENSHOTS.md) | Docs | Dashboard screenshot checklist |

---

## What this repo does

1. **Seeds** publishers, ad units, advertisers, campaigns, creatives, and optionally registers the built-in mock DSP as a demand partner.
2. **Drives traffic** (VAST tags and/or OpenRTB auctions) at configurable RPS/concurrency with ramp-up and SLO checks.
3. **Acts as the buyer** via a controllable **mock DSP** so OpenRTB auctions can actually win.
4. **Simulates a player** — wrapper resolution, VAST macros, ordered quartile fire-back, optional post-win **playback** of impression/quartile/win pixels.
5. **Validates** every response against IAB VAST 4.x, VMAP 1.0, OpenRTB 2.5/2.6, and supply-chain files (`ads.txt` / `app-ads.txt` / `sellers.json` / sChain).
6. **Reports** a per-standard scorecard, machine-readable `gaps.json`, and human-readable `GAP_REPORT.md`.

---

## Architecture

```
ad-server-sim/
├── backend/                      Python · FastAPI · httpx · aiosqlite
│   ├── app/
│   │   ├── main.py               ASGI entry: mounts /api, /dsp, static dashboard
│   │   ├── config.py             env-based settings (target URL, DSP, discovery, SLOs)
│   │   ├── models.py             Pydantic request bodies (seed, run, scenario, publisher, DSP)
│   │   ├── conformance.py        Finding model + per-standard scorecard
│   │   ├── discovery.py          reads SUT /openapi.json → resolves live routes
│   │   ├── report.py             GAP_REPORT.md + gaps.json + scorecard writers
│   │   ├── findings_recorder.py  de-duplicating per-run conformance store
│   │   ├── db.py                 SQLite (runs, metrics, seed entities)
│   │   ├── adserver/
│   │   │   ├── client.py         auth, seeding, VAST+OpenRTB, wrapper-follow, fire-back
│   │   │   ├── result.py         AdResult (fill, price, findings, adm, win_urls, …)
│   │   │   ├── validators.py     IAB validators: VAST 4.x, VMAP 1.0, OpenRTB 2.5/2.6
│   │   │   ├── macros.py         VAST macro substitution ([CACHEBUSTING], …)
│   │   │   ├── vast.py           VAST parse/extract helpers
│   │   │   ├── ortb.py           OpenRTB request builder + response parser
│   │   │   ├── tracking.py       host/prefix rewrite + macro sub + canonical builders
│   │   │   └── supplychain.py    ads.txt / app-ads.txt / sellers.json / sChain
│   │   ├── dsp/router.py         mock DSP (bid / track / vast / config) at /dsp
│   │   ├── modules/
│   │   │   ├── seeder.py         M1 — seed data (+ register fake DSP)
│   │   │   ├── traffic.py        M2 — RPS pacing, ramp, percentiles, SLO
│   │   │   ├── impressions.py    M3 — impression fire-back
│   │   │   ├── clicks.py         M4 — click fire-back
│   │   │   ├── users.py          M5 — synthetic user pool
│   │   │   ├── scenarios.py      M6 — S1–S15 scenario engine
│   │   │   └── metrics.py        aggregation, fill, scorecard, reconciler
│   │   └── api/
│   │       ├── routes.py         REST + WebSocket control plane
│   │       └── run_manager.py    background run orchestration
│   ├── tests/                    pytest (offline unit tests)
│   ├── reports/                  generated GAP_REPORT.md / gaps.json
│   ├── requirements.txt
│   └── .env.example
├── dashboard/                    React · Vite · Tailwind · Recharts
│   └── src/
│       ├── App.jsx               shell + 3 views (Dashboard / Publisher / DSP)
│       ├── publisher.jsx         Publisher Ad Request tester (+ simulate playback)
│       ├── dsp_settings.jsx      Mock DSP control UI
│       ├── panels.jsx            scorecard, charts, findings, scenarios, …
│       ├── api.js                /api client + /dsp helpers
│       └── ui.jsx                shared UI primitives
├── postman/                      E2E Postman collection
├── scenarios/                    legacy A–D JSON fixtures + example output
├── docs/                         screenshot notes
├── docker-compose.yml · Dockerfile
├── start.bat · start.sh          one-click local launch (after setup)
├── setup.md · HOW-TO-USE.md
└── README.md                     ← this file (source of truth)
```

### Runtime mounts (`app/main.py`)

| Mount | Purpose |
|---|---|
| `/api/*` | Simulator control, metrics, reports, publisher tester |
| `/dsp/*` | Mock DSP (bid endpoint the SUT fans out to) |
| `/` | Built React dashboard (`dashboard/dist`) when present |
| `/docs` | FastAPI Swagger UI |

---

## How it integrates with the ad server

The SUT is **VAST / video-centric**. On startup the simulator reads the SUT’s `/openapi.json` (when `DISCOVER_ON_START=true`) and repoints to **live** routes. If discovery fails it falls back to these defaults:

| Purpose | Live endpoint | Notes |
|---|---|---|
| Canonical VAST (decisioning) | `GET /api/v/{tag_id}` | runs `decide_vast_ad`; **always fills** (real ad or "Video Ad" filler) |
| OpenRTB auction | `POST /api/b/{tag_id}` (== `/ortb/bid/{tag_id}`) | first-price; no-bid = bare **204** (no `nbr`) |
| Impression / click / win / event / error | `GET /api/track/*` | public, no auth |
| ads.txt / app-ads.txt / sellers.json | root `/ads.txt`, `/app-ads.txt`, `/sellers.json` (or `/api/ortb/*`) | **not** `/ortb/*` |
| VMAP (static) | `GET /api/m/{tag_id}` | 3-break template (no real ad pods in the SUT) |

```
 Publisher / traffic gen                 Voise Ad Server (SUT)              Mock DSP (this repo)
 ─────────────────────                   ────────────────────              ────────────────────
 GET /api/v/{tag}  ──────────────────►   decide_vast_ad ──► VAST
 POST /api/b/{tag} ──────────────────►   OpenRTB auction ──POST /dsp/bid──► BidResponse (adm=VAST)
                                         ◄── seatbid / 204 ◄──────────────┘
 GET /api/track/*  ◄── player pixels ──  records impression / win
 GET /dsp/track    ◄── advertiser pixels (from winning adm)
```

---

## Modules (backend)

| Module | File | Role |
|---|---|---|
| **M1 Seeder** | `modules/seeder.py` | Creates publishers, ad units, advertisers, campaigns, creatives; optionally registers the fake DSP as a demand partner (`seed_fake_dsp`) |
| **M2 Traffic** | `modules/traffic.py` | Paced request generator (RPS, concurrency, ramp, latency percentiles, SLO pass/fail) |
| **M3 Impressions** | `modules/impressions.py` | Post-fill impression + ordered quartile fire-back |
| **M4 Clicks** | `modules/clicks.py` | CTR-based click fire-back |
| **M5 Users** | `modules/users.py` | Synthetic user pool (returning-user ratio, device/geo/browser) |
| **M6 Scenarios** | `modules/scenarios.py` | S1–S15 conformance scenarios with PASS / GAP / BLOCKED / FAIL oracles |
| **Metrics** | `modules/metrics.py` | Overview, fill breakdown, findings, scorecard, sim-vs-server reconcile |

Supporting layers: `adserver/client.py` (HTTP to SUT), `validators.py` (IAB checks), `dsp/router.py` (buyer), `api/routes.py` (control plane).

---

## Mock DSP (OpenRTB bidder)

The simulator ships a **mock DSP** (`backend/app/dsp/router.py`, mounted at `/dsp`) so the SUT’s auction has something to bid against.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/dsp/bid` · `/dsp/bid/{tag_id}` | OpenRTB BidRequest → BidResponse / 204 / nbr |
| `GET` | `/dsp/config` | Current runtime config |
| `POST` | `/dsp/config` | Patch config (applies on next request; no restart) |
| `POST` | `/dsp/reset` | Reset bid/track stats |
| `GET` | `/dsp/health` | Config + stats |
| `GET` | `/dsp/track` | Advertiser impression/quartile/click pixel sink (1×1 GIF) |
| `GET` | `/dsp/vast` | Serve the current creative VAST as a tag URL (for inspectors) |

Also mirrored under the control API: `GET /api/dsp`, `POST /api/dsp/config` (subset of fields via `DspConfig` model). The dashboard **DSP Settings** tab writes the full config via `POST /dsp/config`.

### How it bids (OpenRTB 2.5 / 2.6)

1. The ad server POSTs a `BidRequest` to `SIM_PUBLIC_URL + /dsp/bid` (seed with `POST /api/seed {"seed_fake_dsp": true}`).
2. For **each `imp`** the DSP reads format (video/banner/native/audio), size, and `bidfloor`, computes  
   `min(max_cpm, max(price, floor × bid_margin))` with jitter, and — if it clears the floor — emits a bid.
3. It returns a spec-correct `BidResponse`: `seatbid[].bid[]` with `impid`, `price`, `adm` (playable VAST for video, HTML for banner), `nurl`/`burl`/`lurl` (OpenRTB `${AUCTION_*}` macros left literal; `[CB]` cache-buster filled), `crid`, `adid`, `cid`, `adomain`, `cat`, `mtype`, `w`/`h`, `protocol` (VAST 4.0 = 7), and `dealid` when `imp.pmp.deals` is present. It bids on **every** eligible imp (one bid per CTV/pod slot).
4. **No-bid** = bare **HTTP 204**, or `200 {id, seatbid:[], nbr}` — toggled by `emit_nbr` / `nbr_code`.

### Modes

| Mode | Behaviour |
|---|---|
| `bid` | Valuation + BidResponse (or `custom_response` template) |
| `no_bid` | 204 or `{nbr}` |
| `timeout` | Sleep `timeout_ms`, then no-bid |
| `error` | HTTP 500 |

### Playable creative + advertiser tracking

Video bids embed a **real public MP4** (configurable `video_url`) inside a VAST 4.2 InLine, with Impression / quartile / click / error pixels pointing at **`/dsp/track`**. That means:

- You can paste the winning `adm` into any VAST viewer and **watch the ad**.
- Server-side **Simulate playback** (Publisher tab) or a real player that can reach the sim will increment `STATS.tracked`.

Key creative config knobs: `video_url`, `video_w`/`h`/`bitrate`/`duration`, `advertiser_name`, `landing_url`, `track_base` (must be reachable by whoever fires the pixels).

### Custom BidResponse template

Set `custom_response` to a JSON object. In `bid` mode the DSP returns it instead of the auto-built bid, substituting:

| Macro | Meaning |
|---|---|
| `{{price}}` | Computed CPM (quoted `"{{price}}"` → JSON number) |
| `{{impid}}` | First imp id |
| `{{id}}` | BidRequest id |
| `{{crid}}` / `{{seat}}` / `{{cur}}` | Identity / currency |

Bad templates fall back to the auto-built bid (never crash the DSP).

### Terminal logging

With `verbose: true` every request prints a decision block in the uvicorn terminal:

```
==================================================================
  MOCK DSP  <--  OpenRTB bid request
------------------------------------------------------------------
  request id : auction-7f3a
  imps       : 1  [video 640x480 floor=2.50]
  …
  DECISION   : BID   seat=voise-fake-dsp  cur=USD
==================================================================
```

### Control via curl

```bash
curl -X POST localhost:8090/dsp/config -H 'Content-Type: application/json' \
  -d '{"mode":"bid","price":8.0,"bid_margin":1.3,"max_cpm":30,"respect_floor":true}'
# modes: bid | no_bid | timeout | error

curl localhost:8090/api/dsp          # live config + stats
curl -X POST localhost:8090/dsp/reset

# Hit the DSP directly (bypass the ad server):
curl -X POST localhost:8090/dsp/bid -H 'Content-Type: application/json' \
  -d '{"id":"r1","imp":[{"id":"1","bidfloor":2.5,"video":{"w":640,"h":480}}],"site":{"id":"s"},"device":{"devicetype":2}}'
```

Standalone process: `python -m app.dsp.router` → `:8095/dsp/bid`.

---

## Dashboard

Open `http://localhost:8090` (production build served by FastAPI) or `http://localhost:5173` (Vite dev; proxies `/api` and `/dsp` to the backend).

Three views in the header:

### 1. Dashboard

**1 · Seed** → **2 · Generate traffic** → **3 · Scenarios**. Shows:

- Conformance **scorecard**, real-vs-filler **fill breakdown**, **latency percentiles**
- Charts, **findings** table, per-scenario verdicts
- Export via **GAP report** / **gaps.json**
- Optional one-click OpenRTB flow (`POST /api/flow/ortb`)

Header traffic light: green = SUT reachable + authenticated role shown.

### 2. Publisher Ad Request

Focused tester — no seeding required (serve endpoints are public):

1. Enter **publisher id** + **ad unit / tag id**.
2. Choose **VAST** (`GET`) or **OpenRTB** (`POST`), format (video/banner/native/audio), app vs site, count.
3. **Preview** the exact IAB request, or **Send** N requests through the simulator backend (avoids CORS).
4. Optionally paste a **real publisher OpenRTB body** and fire it verbatim.

**Simulate playback** (checkbox): after a win, the backend parses the winning VAST, fires impression + quartile pixels and win/billing notices (`nurl`/`burl`) server-side. DSP pixels at `/dsp/track` are left as-is (with `https→http` downgrade for local fake DSP); ad-server pixels get host/prefix normalization. Response includes:

- `winning_vast` — full creative markup (copyable for a VAST inspector)
- `playback` — per-pixel fire results + ad-server vs advertiser hit counts

### 3. DSP Settings

UI for the mock buyer (`dashboard/src/dsp_settings.jsx`):

- One-click **behaviour**: bid / no-bid / timeout / error
- **Pricing**, **identity**, **creative** (MP4 URL, size, duration, landing, `track_base`)
- **Notice URL** templates (`nurl` / `burl` / `lurl` / `iurl`)
- **Advanced** custom `BidResponse` JSON
- Live stats + **Send test bid** / **Reset stats**

Reads `GET /api/dsp`, writes `POST /dsp/config`. Changes apply on the **next** request.

### Dev proxy note

Vite must proxy **both** `/api` and `/dsp`. Override the backend target with:

```bash
VITE_PROXY_TARGET=http://localhost:9999 npm run dev
```

---

## Conformance

Every VAST / OpenRTB response and supply-chain file is run through the validators, which emit **findings**:

`{standard, spec_section, check, severity, expected, observed, endpoint, scenario}`

Severity: `pass` / `fail` / `warn` / `info` (`info` like “OMID absent” is never a failure). Findings roll up into a **scorecard** and the **GAP report**:

```bash
curl localhost:8090/api/metrics/scorecard
curl localhost:8090/api/report/gaps.json
curl localhost:8090/api/report/markdown
# also written under backend/reports/ (or REPORT_DIR)
```

### Known SUT gaps this surfaces (expected — not simulator errors)

1. `POST /api/publishers` 500 → synthetic tag_ids (serving ignores ad units).
2. Campaign create writes `format_targets`/`cpm_bid`; auction reads `ad_format`/`target_cpm` → REST campaigns serve filler until the simulator’s `PUT` shim fixes field names.
3. Campaign/advertiser create needs `platform_admin`/`tenant_admin` (open registration grants `trafficker`).
4. No geo/device targeting (S5), no frequency cap (S6), budget never closes — `spent` vs `spend` (S7).
5. Every live VAST route always fills → no spec-correct no-fill / empty-VAST (S4).
6. `decide_vast_ad` VAST embeds `/track/...` **without `/api`** (prod host) → the sim rewrites host **and** adds `/api`, logging each rewrite as a finding (S11).
7. No real ad pods; no `nbr` on no-bid; deals/2.6-pods not auctioned (S9/S10).

---

## Prerequisites

- **Voise Ad Server** running (default `http://localhost:8001`) with MongoDB.
- A **V1-admin** user for full seeding (`platform_admin` / `tenant_admin`). Registration only grants `trafficker`, so promote one once:

  ```js
  // mongosh, db voisetech_adserver_local
  db.users.updateOne({ email: "dev@localhost.com" }, { $set: { role: "platform_admin" } })
  ```

  Put those credentials in the simulator’s `.env`. Smoke / S1 / S3 work without admin (SUT always fills); targeting / budget scenarios need real campaigns.
- For **S10** (OpenRTB win): the SUT must reach the sim’s fake DSP at `SIM_PUBLIC_URL + /dsp/bid` (default `http://localhost:8090/dsp/bid`).
- **Python 3.12+** and **Node 18+** for local dev.

---

## Setup

### Quick start (after one-time setup)

```bash
# Windows
start.bat
# *nix
./start.sh
```

Opens `http://localhost:8090`. Full install walkthrough: [`setup.md`](setup.md). Non-technical usage: [`HOW-TO-USE.md`](HOW-TO-USE.md).

### Local development

```bash
cd ad-server-sim/backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# *nix:
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # set AD_SERVER_EMAIL / AD_SERVER_PASSWORD
uvicorn app.main:app --port 8090 --reload

# Build dashboard once so FastAPI serves it at :8090/
cd ../dashboard && npm install && npm run build

# Or run the UI in hot-reload mode (proxies /api and /dsp → :8090):
npm run dev                           # http://localhost:5173
```

### Docker

```bash
cd ad-server-sim
AD_SERVER_PASSWORD=yourpass docker compose up --build   # http://localhost:8090
```

The container reaches a host ad server via `host.docker.internal:8001`. For S10 set:

```bash
SIM_PUBLIC_URL=http://host.docker.internal:8090
```

so the SUT can call the fake DSP.

---

## Configuration

All knobs come from environment variables or `backend/.env` (see `backend/.env.example` and `app/config.py`).

| Variable | Default | Purpose |
|---|---|---|
| `AD_SERVER_URL` | `http://localhost:8001` | Target ad server base URL |
| `AD_SERVER_EMAIL` / `AD_SERVER_PASSWORD` | (see `.env.example`) | Admin creds for seeding |
| `AUTO_REGISTER` | `true` | Self-register sim user if login fails (still becomes trafficker) |
| `DISCOVER_ON_START` | `true` | Read SUT `/openapi.json` and repoint live routes |
| `SIM_PUBLIC_URL` | `http://localhost:8090` | URL the SUT uses to reach the fake DSP |
| `DSP_PATH` | `/dsp/bid` | Path appended to `SIM_PUBLIC_URL` |
| `REQUESTS_PER_SECOND` / `CONCURRENCY` / `TOTAL_REQUESTS` | `50` / `10` / `500` | Traffic pacing |
| `SERVE_PROTOCOLS` | `vast` | `vast`, `ortb`, or `vast,ortb` |
| `DEFAULT_IMPRESSION_RATE` / `DEFAULT_CTR` | `0.9` / `0.03` | Post-fill behaviour |
| `TRACKING_PREFIX_FIX` | `true` | Rewrite embedded `/track` → `/api/track` |
| `REPORT_DIR` | `./reports` | Where `GAP_REPORT.md` / `gaps.json` are written |
| `SIM_DB_PATH` | `./sim.db` | SQLite path |
| `COUNTRIES` / `DEVICES` / `BROWSERS` | pools | Random traffic dimensions |
| `DASHBOARD_DIST` | (repo `dashboard/dist`) | Override static dashboard path (Docker sets this) |
| `VITE_PROXY_TARGET` | `http://localhost:8090` | Vite dev proxy target (dashboard only) |

---

## HTTP API reference

Base: `http://localhost:8090/api`. Interactive docs: `/docs`.

### Control & health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Sim + SUT reachability |
| `GET` | `/config` | Effective settings |
| `GET` | `/target` | Discovered live routes |
| `POST` | `/seed` | M1 seed (`SeedRequest`) |
| `POST` | `/run` | M2–M5 traffic run (`RunRequest`) |
| `POST` | `/scenario` | M6 scenarios (`S1`…`S15` \| `A`–`D` \| `all`) |
| `POST` | `/runs/stop` | Stop active run |
| `GET` | `/runs` · `/runs/active` | Run history / current |
| `WS` | `/ws` | Live run progress |

### Publisher & flows

| Method | Path | Description |
|---|---|---|
| `POST` | `/publisher-request` | Fire N VAST/OpenRTB requests for a publisher + tag; supports `preview_only`, `custom_request`, `simulate_playback` |
| `POST` | `/flow/ortb` | One-click OpenRTB auction (optional `dsp_mode`) |

### Metrics & reports

| Method | Path | Description |
|---|---|---|
| `GET` | `/metrics/overview` · `/campaigns` · `/auctions` · `/timeseries` · `/scenarios` | Aggregates |
| `GET` | `/metrics/fill` | Real vs filler breakdown |
| `GET` | `/metrics/findings` · `/scorecard` | Conformance |
| `GET` | `/metrics/reconcile` · `/cross-check` | Sim vs SUT counts |
| `GET` | `/supply-chain` | ads.txt / sellers.json validation |
| `GET` | `/report` · `/report/markdown` · `/report/gaps.json` | GAP deliverables |

### DSP (control plane)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dsp` | Endpoint URL + config + stats |
| `POST` | `/api/dsp/config` | Patch common DSP fields (`DspConfig`) |
| `POST` | `/dsp/config` | Full config patch (creative, templates, `custom_response`, …) |

### Example curls

```bash
curl localhost:8090/api/target
curl -X POST localhost:8090/api/seed -H 'Content-Type: application/json' \
  -d '{"campaigns":6,"seed_fake_dsp":true}'
curl -X POST localhost:8090/api/run -H 'Content-Type: application/json' \
  -d '{"total_requests":300,"protocols":["vast"],"fire_quartiles":true}'
curl -X POST localhost:8090/api/scenario -H 'Content-Type: application/json' \
  -d '{"scenario":"all"}'

# Publisher tester — OpenRTB + simulate playback
curl -X POST localhost:8090/api/publisher-request -H 'Content-Type: application/json' \
  -d '{"protocol":"ortb","ad_format":"video","publisher_id":"1192","tag_id":"351511","count":1,"simulate_playback":true}'

# Preview only (do not send)
curl -X POST localhost:8090/api/publisher-request -H 'Content-Type: application/json' \
  -d '{"protocol":"ortb","tag_id":"351511","preview_only":true}'

curl localhost:8090/api/metrics/scorecard
curl localhost:8090/api/metrics/fill
curl localhost:8090/api/metrics/reconcile
curl localhost:8090/api/supply-chain
curl localhost:8090/api/report/markdown
```

### `PublisherAdRequest` fields (high signal)

| Field | Default | Notes |
|---|---|---|
| `publisher_id` / `tag_id` | `1192` / `351511` | schain sid + ad unit |
| `protocol` | `ortb` | `ortb` \| `vast` |
| `ad_format` | `video` | video \| banner \| native \| audio |
| `count` | `1` | 1–500 |
| `preview_only` | `false` | Build request, do not send |
| `custom_request` | `null` | Paste a real OpenRTB body verbatim |
| `simulate_playback` | `false` | After a win, fire VAST trackers + win notices server-side |
| Privacy | optional | `gdpr`, `gdpr_consent`, `us_privacy`, `gpp`, `coppa` |

Response extras when not preview: `winning_vast`, `playback` (`fired[]`, `ad_server_hits`, `advertiser_hits`), per-request `adm` / `win_urls` / findings.

---

## Scenarios (S1–S15)

`POST /api/scenario {"scenario": "S7" | "all" | "A".."D"}`.

**Verdicts:**

| Verdict | Meaning |
|---|---|
| **PASS** | SUT conforms to the standard expectation |
| **GAP** | SUT deviates — this *is* the finding (not a sim bug) |
| **BLOCKED** | No live SUT capability to assert against |
| **FAIL** | Could not validate (e.g. nothing served) |
| **ERROR** | Setup / transport failure |

Legacy letters: `A→S7`, `B→S5`, `D→S6`, `C→` bid competition.

| # | Scenario | Expectation | Typical vs current SUT |
|---|---|---|---|
| S1 | Smoke | Spec-valid VAST 4.x | **PASS** |
| S2 | Normal traffic | Valid markup, sane fill/latency | **PASS** |
| S3 | Real-vs-filler | Real fill > 0 after workaround | **PASS** (else GAP) |
| S4 | No-fill semantics | Empty VAST / `<Error>` / 204+nbr | **GAP** — always fills |
| S5 | Geo targeting | Off-geo not served | **GAP** — no geo targeting |
| S6 | Frequency cap | Capped after N | **GAP** — no cap |
| S7 | Budget exhaustion | Stops at budget | **GAP** — `spent`≠`spend` |
| S8 | Schedule / flight | Expired not selected | **PASS** — date gating works |
| S9 | Ad pods / VMAP | Valid VMAP + multi-ad pod | **PASS** (VMAP) + **BLOCKED** (pods) |
| S10 | OpenRTB conformance | Spec-valid BidResponse or 204 | **PASS** with fake DSP, else **BLOCKED** |
| S11 | Tracking accuracy | Ordered quartiles record | **PASS** (notes `/api`-prefix bug) |
| S12 | Privacy (GDPR/GPP) | OpenRTB regs passthrough | **PASS** (serving drops them — GAP) |
| S13 | ads.txt / sellers.json / sChain | Valid files + schain | **PASS** |
| S14 | Load / SLO | p95 + error-rate SLOs | PASS/FAIL vs thresholds |
| S15 | Resilience | Graceful on malformed (no 5xx) | **PASS** |

JSON fixtures for legacy A–D live under [`scenarios/`](scenarios/).

---

## Tests

Offline unit tests (no live ad server required):

```bash
cd ad-server-sim/backend
.venv\Scripts\activate          # or: source .venv/bin/activate
pytest
```

Coverage includes: validators, macros, supply-chain, ORTB, VAST, tracking, metrics, DSP, seeder budget.

---

## Postman

Import [`postman/Voise-AdSim.postman_collection.json`](postman/Voise-AdSim.postman_collection.json). Folders 0–5 cover health → seed → VAST → OpenRTB auction (with DSP on/off) → S1–S15 → reports. Details: [`postman/README.md`](postman/README.md). Raise Postman request timeout to **60000 ms** (cold auction can be slow).

---

## Extending

- **New IAB validator** — add to `app/adserver/validators.py`, emit `Finding`s; scorecard + GAP report pick them up automatically.
- **New scenario** — add an `sN` method on `ScenarioEngine` and register it in the dispatch map in `modules/scenarios.py`.
- **DSP behaviours** — extend `app/dsp/router.py` (seat shaping, deal matching, creative templates) and expose knobs in `dsp_settings.jsx` if they should be UI-tunable.
- **New dashboard view** — add a tab in `App.jsx` and a panel component under `dashboard/src/`.

---

## Tech stack

| Layer | Stack |
|---|---|
| Backend | Python 3.12+, FastAPI, httpx, pydantic v2, aiosqlite, uvicorn |
| Frontend | React 18, Vite 5, Tailwind CSS 3, Recharts |
| Packaging | Multi-stage Docker (Node build → Python serve), docker-compose |
| Standards exercised | VAST 4.x, VMAP 1.0, OpenRTB 2.5/2.6, ads.txt / app-ads.txt / sellers.json / SupplyChain |

---

## Changelog highlights (since last README refresh)

Material capability added after the previous README commit (2026-07-09):

- **DSP Settings** dashboard tab — full runtime control of the mock buyer from the UI.
- **Playable mock creatives** — public MP4 VAST adm, `/dsp/track` advertiser pixels, `/dsp/vast` tag URL.
- **Configurable creative + notice URLs** + **custom BidResponse** templates (`{{price}}`, …).
- **Simulate playback** on Publisher Ad Request — server-side fire of winning trackers + win notices; returns `winning_vast` + playback stats.
- **`AdResult.adm`** preserved end-to-end for inspection / VAST paste.
- **Vite** proxies `/dsp` (and `VITE_PROXY_TARGET`) so the DSP Settings tab works in dev.
- **`setup.md`** — dedicated local install guide.
