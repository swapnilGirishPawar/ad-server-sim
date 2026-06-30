# Corrected BUILD PROMPT — §3 (Real Endpoints) & §6 (Scenario Catalog)

> Replaces the original §3 and §6. Corrections are based on a full audit of the
> updated Voise-Adserver SUT (branch `swapnil-simulator-testing`, 2026-06-30).
> The original CRITICAL PRINCIPLE still holds: **test against the IAB standard,
> not the implementation.** What changed is *which endpoints are live* and *what
> outcome each scenario's oracle should expect* given confirmed SUT behavior.

---

## 3. THE SYSTEM UNDER TEST — REAL ENDPOINTS (re-verified in code)

Confirm live paths via the SUT's OpenAPI (`/openapi.json`) on startup before
running tests. The simulator MUST do route discovery first — the previous prompt
listed several routes that are now dead (see "DO NOT DRIVE" below). App routes
are under prefix `/api` unless noted; some have root-level aliases.

### 3.0 ENDPOINT MAP — drive these, not those

| Purpose | DRIVE (live) | DO NOT DRIVE (404 / wrong) |
|---|---|---|
| Canonical VAST (decisioning) | `GET /api/v/{tag_id}` (or root `/v/{tag_id}`) | — |
| Universal VAST (decisioning) | `GET /api/serve/ad/vast?aid=&sid=` | `GET /api/serve/vast` *(dead — `serve.py` unmounted)* |
| DOOH VAST | `GET /api/dooh/vast?screen_id=` | `GET /api/serve/dooh/vast` *(dead)* |
| Player / FAST VAST | *(none — no live server-side route)* | `/api/serve/player/vast`, `/api/serve/fast/vast` *(dead)* |
| Static VAST (no decisioning) | `GET /api/v?aid=`, `GET /api/ctv?aid=` | — |
| VMAP (static) | `GET /api/m/{tag_id}` (3-break), `GET /api/vmap?aid=`, `GET /api/dooh/vmap` | — |
| OpenRTB auction | `POST /ortb/bid/{tag_id}` **== `POST /api/b/{tag_id}`** | `POST /api/bid` & short `/bid` *(stub: `200 {seatbid:[]}`)* |
| ads.txt / app-ads.txt / sellers.json | root `/ads.txt`, `/app-ads.txt`, `/sellers.json` **or** `/api/ortb/{…}` | `/ortb/ads.txt`, `/ortb/sellers.json` *(404)* |

### 3.1 AD REQUEST — VAST serving
- `GET /api/v/{tag_id}?pub=&bundle=&ifa=&devicetype=&os=&w=&h=` → **canonical**;
  runs `decide_vast_ad`. **Always returns a populated VAST 4.2 InLine** — emits a
  filler "default" ad when nothing matches (media `…/creative/{tag_id}.mp4`,
  ClickThrough `https://voise.com`, AdTitle `Video Ad`, ad_id == tag_id). There is
  **no empty-VAST and no `X-No-Fill-Reason` header on any live route.** The
  validator MUST distinguish a REAL campaign ad from this filler.
- `GET /v/{tag_id}` — root-level duplicate of the canonical endpoint.
- `GET /api/serve/ad/vast?aid=&sid=&w=&h=` (aid+sid required) — also runs
  `decide_vast_ad`; same always-filler semantics. Closest live analog to the old
  (dead) `/api/serve/vast`.
- **Static, NO decisioning** (hand-built XML, ignore for real-vs-filler logic):
  `GET /api/v?aid=&pid=&w=&h=` (note: distinct from `/api/v/{tag_id}`),
  `GET /api/ctv?aid=&pid=&dur=` (1920×1080).
- **VMAP (static templates):** `GET /api/m/{tag_id}` (preroll/midroll/postroll,
  3 AdBreaks, AdTagURI→`/api/v/{tag_id}`); root `GET /m/{tag_id}` (single preroll);
  `GET /api/vmap?aid=&content_id=` (single AdBreak Wrapper→`/ctv`).
- **DOOH:** `GET /api/dooh/vast?screen_id=` → real DB-driven, **single-slot** VAST,
  emits a proper empty VAST on no screen/creative; `GET /api/dooh/vmap` → 48-break
  loop VMAP (note: `timeOffset` is malformed `MM:SS`, e.g. `60:00` — a SUT bug).
- **Not VAST:** `GET /api/t` → JSON JS-loader; `GET /api/pb` → JSON prebid config.
- **DEAD CODE — returns 404:** `backend/routers/serve.py` (`/serve/vast`,
  `/serve/dooh/vast`, `/serve/player/vast`, `/serve/fast/vast` — the only
  pod-aware / supply-type-aware / empty-VAST+`X-No-Fill-Reason` handlers) is never
  `include_router`'d and would ImportError if mounted. The no-fill design the old
  prompt described **does not exist live.** Some generated tags
  (`player_public.py`, `dooh_publisher_mgmt.py`) point at these dead routes — that
  itself is a GAP to report.

### 3.2 OpenRTB (programmatic)
- `POST /ortb/bid/{tag_id}` **== `POST /api/b/{tag_id}`** — the only real auction.
  First-price; fans out to seeded demand partners; on a winner returns
  `200 {id, seatbid:[{bid:[best], seat:"voisetech"}], cur:"USD", ext:{…}}`. The
  winner's `nurl`/`burl` are **rewritten to VoiseTech tracking URLs** (DSP nurl
  chained via `&dsp_nurl=`) and a VoiseTech Impression pixel is injected into the
  VAST `adm`; `price`/`crid`/`adomain`/`cat` pass through from the DSP. **No-bid =
  bare HTTP 204, empty body, no `nbr`, no `cur`.** Rejects bad JSON / missing
  `id`|`imp` with 400; duplicate `id` → 204.
- `POST /api/bid` and short `/bid` — **stub**: `200 {seatbid:[]}`, ignores `imp`.
- `POST /dooh/openrtb/bid` — separate self-bidding DOOH surface; no-bid → `200 {seatbid:[]}`.
- **Unsupported end-to-end (scope out or assert as GAP):** OpenRTB 2.6 ad pods
  (`podid`/`mincpmpersec` absent), PMP/Deals (CRUD-only, never auctioned, no
  `bid.dealid`), Prebid Server s2s (`/openrtb2/auction` does not exist — `/prebid/*`
  is config/reporting only).

### 3.3 TRACKING (public, no auth)
- `GET /api/track/impression?aid=&sid=&pid=&type=&price=&bid_id=&trace_id=&li=&pub=&dsp_burl=` → 1×1 GIF.
- `GET /api/track/click?aid=&sid=&redirect=&partner=&trace_id=&li=` → 302 redirect.
- `GET /api/track/event?e=&aid=&sid=&type=&partner=&cb=` — `e` ∈
  {`start`,`firstQuartile`,`midpoint`,`thirdQuartile`,`complete`,`click`,`error`} → GIF.
- `GET /api/track/win?bid=&price=&aid=&partner=&pub=&li=&trace_id=&dsp_nurl=` → spend/revenue record; fires DSP nurl.
- `GET /api/track/error?code=&type=&aid=&cb=` → 204.
- Short pixel (root, no `/api`): `GET /e/{event_type}` (`imp`|`clk`|`vid`), params `aid`,`bid`,`e`.
- **KNOWN ISSUE (still present):** VAST from `decide_vast_ad` embeds tracking URLs
  as `https://{ADSERVER_DOMAIN}/track/…` — production host **and missing the `/api`
  prefix** (those `/track/*` paths 404; the real ones are `/api/track/*`). The
  simulator MUST rewrite host **and** insert `/api`, and LOG every rewrite as a
  conformance finding. (CSAI templates and short `/v`,`/ctv` correctly use `/api/…`
  — only `decisioning_core` VAST is wrong.)

### 3.4 REPORTING / METRICS (auth required)
`reports`, `reports_timeseries`, `adtag_report`, `metrics` routers under `/api`.
Discover exact paths from OpenAPI. Use to reconcile counts.

### 3.5 SUPPLY-CHAIN TRANSPARENCY
- Live at root `/ads.txt`, `/app-ads.txt`, `/sellers.json` (IAB crawler-canonical)
  **or** `/api/ortb/{ads.txt,app-ads.txt,sellers.json}`. The old `/ortb/…` paths 404.
- SUT gaps to record (not sim defects): `app-ads.txt` is byte-identical to
  `ads.txt`; `sellers.json` may truncate a UUID `seller_id` to 12 chars; inbound
  `source.ext.schain` is read+appended but **never validated/rejected**.
- `/api/ads-txt/*` is an unrelated third-party crawler — do not conflate.

### 3.6 PRIVACY (where it's observable)
- **Serving path does NOT honor privacy.** Even the dead `/serve/vast` only
  *accepted* `gdpr`/`gdpr_consent`/`us_privacy` then silently dropped them; no live
  serving route reads consent; GPP/`gpp_sid`/TCF are unsupported on serving.
- **OpenRTB path is the only real assertion target:** `regs.ext.gdpr` and
  `regs.ext.us_privacy` are passed through and detected (`has_gdpr`/`has_ccpa` in
  auction logs). Drive `/api/b/{tag_id}` with `regs.ext` set and assert passthrough.

### 3.7 AUTH & SEEDING REALITIES (still apply)
- `POST /api/auth/register` grants `trafficker` only; advertiser/campaign create
  needs `platform_admin`/`tenant_admin` → promote in Mongo
  (`db voisetech_adserver_local`) or use an admin token.
- `POST /api/publishers` 500 (insert bug) → Mongo-direct fallback.
- **FIELD-NAME MISMATCH (still present):** active create handler `routers/campaigns.py`
  writes `format_targets`/`cpm_bid`/`cached_spend_*` and NO `ad_format`/`target_cpm`/
  `spent`; `decide_vast_ad` queries `ad_format` → REST-created campaigns serve filler.
  (`routers/campaigns_new.py` uses the right names but its POST is shadowed.)
  Seeder MUST `PUT`/Mongo-`$set` `ad_format`/`target_cpm`/`spent` and LOG it.
- **Budget split (still present):** eligibility reads `spent`; the only writer
  `$inc`s `spend` and only when a line-item `campaign_id` exists — the VAST path has
  none, so campaign spend never increments. Budget exhaustion is a no-op for VAST.
- `decide_vast_ad` does NOT enforce country/device targeting, frequency caps,
  ad-unit↔tag_id matching, or ad pods. (A separate path, `routers/wrapper_public.py`,
  *does* implement real caps/no-fill — optionally probe it.)

---

## 6. SCENARIO CATALOG — recalibrated oracles

**Oracle legend (never loosen an oracle to turn a GAP green):**
- ✅ **PASS-able** — a green result is genuinely achievable against the live SUT.
- ⚠️ **GAP (expected-fail)** — the SUT deviates from the IAB spec; the oracle
  SHOULD fail, and that failure IS the finding to report.
- ⛔ **BLOCKED** — no live endpoint implements the capability, so there is nothing
  to assert; record the reason, do not fabricate a pass.

| # | Scenario | Target | Oracle & expected outcome |
|---|---|---|---|
| **S1** | Smoke / single request | `GET /api/v/{tag_id}` | ✅ PASS if the response is schema-valid VAST 4.x with required nodes (`AdSystem`,`AdTitle`,`Impression`,`Creatives/Creative/Linear`,`Duration` HH:MM:SS,`MediaFiles/MediaFile`,`VideoClicks/ClickThrough`,quartile `TrackingEvents`). Always fills, so this is reliably green. |
| **S2** | Normal traffic | `/api/v/{tag_id}` + `/api/b/{tag_id}` | ✅ steady RPS; markup stays valid; impressions reconcile within tolerance. NOTE: every VAST request "fills" (real or filler) → raw fill-rate ≈ 100% and is meaningless; the real metric is S3. |
| **S3** | Real-vs-filler fill rate | `/api/v/{tag_id}` | ✅/⚠️ classify each ad REAL vs filler (filler = media `…/creative/{tag_id}.mp4`, click `voise.com`, title `Video Ad`, ad_id==tag_id). Report both rates. Due to the field-mismatch bug, real-fill ≈ 0% until the seeder applies the `ad_format`/`target_cpm`/`spent` workaround → PASS = real-fill > 0 after workaround; a high filler-share without the workaround is the GAP. |
| **S4** | No-fill semantics | `/api/v/{tag_id}`, `/api/b/{tag_id}` | ⚠️ GAP. No live VAST route returns empty `<VAST>` / `X-No-Fill-Reason` / a VAST `<Error>` — all always emit filler. Oracle = "spec-correct no-fill observed" → WILL FAIL = GAP. The only real no-fill signal is OpenRTB's bare 204 (but it carries no `nbr` — also a GAP). (Optional: probe `wrapper_public.py` which does implement empty-VAST.) |
| **S5** | Geo/device targeting | `/api/v/{tag_id}` with excluded geo/device | ⚠️ GAP. PASS if NOT served; `decide_vast_ad` ignores geo/device → always serves → expected-fail = targeting GAP. |
| **S6** | Frequency cap | same user/IFA N+1 times | ⚠️ GAP. PASS if capped after N; no cap logic exists → always served → expected-fail = freq-cap GAP. |
| **S7** | Budget exhaustion | spend past budget, then re-request | ⚠️ GAP. PASS if campaign stops serving; `spend`≠`spent` split + VAST path never increments campaign spend → never caps → expected-fail = pacing GAP. |
| **S8** | Schedule (start/end date) | campaign with past/future window | ✅/⚠️ `_is_campaign_eligible` DOES gate on start/end dates, so the REAL campaign correctly drops out of selection when out of window — PASS if the classifier shows real-ad → filler (not a real ad) outside the window. Caveat: result is filler, not a true no-fill (that part is the S4 GAP). |
| **S9** | Ad pods / VMAP | `/api/m/{tag_id}`, `/api/dooh/vmap`; (pods: none) | ⛔/⚠️ Split: (a) ✅ VMAP **structure** check on `/api/m/{tag_id}` (3 `AdBreak`s w/ `timeOffset`,`breakType`,`AdSource`) — PASS-able; flag `/api/dooh/vmap`'s malformed `MM:SS` offsets as a GAP. (b) ⛔ True multi-`<Ad>` pod (sequenced ads, max-ads, no-dupes): NO endpoint emits >1 `<Ad>` → BLOCKED; record "no pod assembly in SUT". |
| **S10** | OpenRTB conformance | `POST /api/b/{tag_id}` + **fake DSP** seeded as demand partner | ✅/⚠️ PASS if winner is spec-valid `200` (`seat:"voisetech"`,`cur:"USD"`, winner `price`/`crid`/`adomain`/`cat`, expect rewritten `nurl`/`burl` + injected adm pixel) OR a bare 204 no-bid. Requires the fake DSP (§4.4) or you only ever see 204. ⚠️ GAPs to record: no `nbr` on no-bid; no 2.6 pods; deals not honored; first-price gross clearing. |
| **S11** | Tracking accuracy | `/api/track/{impression,event,win}` | ✅/⚠️ fire X impressions + ordered quartiles (`start→firstQuartile→midpoint→thirdQuartile→complete`); PASS if SUT reports == X within tolerance and ordering is recorded. MUST fire the correct `/api/track/*` (or rewrite `decisioning_core` VAST URLs to add `/api`). ⚠️ Record that the raw embedded `/track/…` URLs 404 (lost events) as a GAP. |
| **S12** | Privacy (GDPR/TCF/usp/GPP) | `POST /api/b/{tag_id}` with `regs.ext` | ✅/⚠️ On OpenRTB: PASS if `regs.ext.gdpr`/`us_privacy` are passed through/detected. ⚠️ GAP on serving: send consent to `/api/v/{tag_id}` and assert honoring → SUT silently drops it (can only confirm `200`, not honoring); GPP/`gpp_sid`/TCF unsupported everywhere = GAP. |
| **S13** | ads.txt / sellers.json / sChain | root `/ads.txt`,`/app-ads.txt`,`/sellers.json` (or `/api/ortb/*`); outbound bid req | ✅/⚠️ PASS if files parse with valid IAB line format and consistent IDs, AND outbound bid requests carry `source.ext.schain` (`ver`/`complete`/`nodes` + a VoiseTech node) + `pchain`. ⚠️ Record SUT gaps: `app-ads.txt`==`ads.txt`, 12-char seller_id truncation, no inbound-schain rejection. |
| **S14** | Load / stress | `/api/v/{tag_id}` ramp | ✅ ramp RPS with warm-up; record latency p50/p95/p99, error rate; PASS/FAIL against declared SLO thresholds. |
| **S15** | Resilience / malformed | all entry points | ✅ missing params, huge sizes, bad consent strings, malformed JSON to `/api/b`; PASS if SUT degrades gracefully (4xx/422, no 5xx). Note `/api/b` correctly 400s on bad JSON / missing `id`|`imp`; short tags 422 on missing `aid` — both graceful. |

> Every host/prefix rewrite (§3.3) and every seeding workaround (§3.7) must also be
> emitted as conformance findings — these ARE gaps the developer needs to see.
