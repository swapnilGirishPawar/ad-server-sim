# How to Use the Ad Server Simulator — Simple Guide

This guide is written for **anyone** — you do **not** need to be deeply technical to use this tool.
Just follow the steps in order. When you get to **DSP Settings** and **end-to-end testing**, follow
those recipes like a checklist — they are how you prove the ad server’s auction really works
(and how you catch failures on purpose).

---

## 1. What is this tool, in plain words?

Think of the **ad server** as the machine that decides which advert to show and then keeps score
of how many people saw it and clicked it.

Normally, to test that machine you would need thousands of real people visiting real websites.
That's not practical. So this **Simulator** *pretends* to be:

- the **publisher** (the app/site asking for an ad),
- the **visitor** (watching and clicking), and
- a **buyer / DSP** (a demand partner that bids money in an auction).

It sends fake-but-realistic visits, watches what the server does, and tells you — in a simple
dashboard — whether the server behaved correctly.

You use it to answer questions like:

- *Are adverts actually being shown?*
- *Does the auction pick a winning bid correctly?*
- *What happens when the buyer refuses to bid, times out, or crashes?*
- *Does it stop spending money when a budget runs out?*
- *Is it fast enough?*
- *Do tracking pixels (view / quartiles / win notices) actually fire?*

---

## 2. A few words you'll see (and what they mean)

| Word | What it means in everyday language |
|---|---|
| **Ad request** | One pretend visit asking "show me an advert." |
| **Impression** | The advert was actually shown to the visitor. |
| **Click** | The visitor clicked the advert. |
| **Fill rate** | Out of all the requests, how many got a real advert back (as a %). |
| **CTR** | "Click-through rate" — out of all adverts shown, how many were clicked (as a %). |
| **Campaign** | An advertiser's ad project (e.g. "Nike Summer Sale") with a budget. |
| **VAST** | The industry format for a **video** ad (XML that a player understands). |
| **OpenRTB** | The industry format for an **auction** — "who wants to buy this ad slot?" |
| **DSP** | "Demand-Side Platform" — the **buyer**. Our tool includes a fake one you control. |
| **Bid** | The buyer says "I'll pay $X for this slot" and sends an ad creative. |
| **No-bid** | The buyer says "I don't want this slot" (so the auction may return no ad). |
| **Floor / bidfloor** | The minimum price the publisher will accept. |
| **Seed** | Create pretend advertisers/campaigns so there is something to serve. |
| **Scenario** | A specific automated test with a clear right answer (S1–S15). |
| **PASS / GAP / FAIL** | **PASS** = server did the right thing. **GAP** = server is missing or not doing something it should. **FAIL** = the test could not run. **BLOCKED** = feature doesn't exist yet to test. |

> **Important:** A **GAP** is **not** a problem with this tool. It means the tool found something
> the ad server isn't doing correctly yet. That's exactly what it's for — finding issues to
> hand to the development team.

---

## 3. Before you start

Two things must be true. A developer usually sets these up once:

1. **The ad server is running** on this computer (usually at `http://localhost:8001`).
2. **This simulator has been set up** (done already on this machine — see the last section if
   you're on a brand-new computer).

If you're not sure, don't worry — Step 5 shows you a green/red light that tells you instantly.

---

## 4. Start the tool

**Easiest way:** double-click the file **`start.bat`** inside the `ad-server-sim` folder.

- A black window will open and show some text. **Leave this window open** while you work — it's
  the engine running. (To stop the tool later, just close that window.)
- After a few seconds, your web browser opens the dashboard automatically at
  **http://localhost:8090**
- If the page looks blank or says "can't connect," wait 5 seconds and **refresh** the page.

*(The tool may already be running — if so, just open http://localhost:8090 in your browser.)*

**Tip:** Keep the black engine window visible when testing auctions. The fake DSP prints each
bid decision there — that's your live proof the buyer was called.

---

## 5. Check the connection (the traffic light)

Look at the **top-right corner** of the dashboard:

- 🟢 **Green dot + a web address** = the simulator is connected to the ad server.
- 🔴 **Red dot** = the ad server is **not** running. Ask a developer to start it, then refresh.

You should also see **`role: platform_admin`** — that just means the tool has permission to set
up test data.

If the light is green, you're ready.

---

## 6. The three tabs (where everything lives)

At the top of the page you'll see three tabs. Use them for different jobs:

| Tab | What it's for |
|---|---|
| **Dashboard** | Create test data, send bulk traffic, run automated S1–S15 scenarios, read scorecards |
| **Publisher Ad Request** | Fire a specific publisher's ad request (VAST or OpenRTB), inspect the response, optionally **simulate playback** |
| **DSP Settings** | Control the fake buyer — bid / no-bid / timeout / error, price, creative, notice URLs |

A good testing day usually goes: **Dashboard (seed)** → **DSP Settings (set the buyer)** →
**Publisher Ad Request (fire a real auction)** → **Dashboard (run scenarios / read GAP report)**.

---

## 7. The Dashboard 3-step flow (main everyday path)

On the **Dashboard** tab, three boxes at the top are numbered **1**, **2**, **3**. Use them left to right.

### Step 1 — Create test data ("Seed data")

In box **1 · Seed data**, click **"Seed ecosystem"**.

- This creates pretend advertisers and ad campaigns inside the ad server so there's something
  to show. (You can leave the number boxes at their defaults.)
- Importantly, seeding also **registers the fake DSP as a demand partner**, so OpenRTB auctions
  have a real buyer to call.
- Wait a couple of seconds. A **"Live run"** panel appears showing what was created, and may
  list a few **findings** in amber — these are notes about things the server struggled with.
  That's normal and useful.

You only need to do this **once** each time you start fresh (or again if the auction stops
calling the buyer).

### Step 2 — Send pretend traffic ("Generate traffic")

In box **2 · Generate traffic**, click **"Run traffic"**.

- This makes the simulator send lots of pretend visits to the ad server.
- Watch the **"Live run"** numbers climb: **requests**, **impressions**, **clicks**.
- The word **"● running…"** appears at the top while it works, and disappears when it's done
  (a few seconds for the default amount).
- You can change **"Total requests"** to a bigger number (e.g. `1000`) to push the server
  harder, then click **Run traffic** again.

### Step 3 — Read the results

Scroll down. The dashboard fills in automatically:

- **Overview** (six tiles): total requests, responses, impressions, clicks, fill rate, CTR.
- **Charts**: activity over time, and how much the campaigns "spent."
- **Campaign Metrics** (table): each campaign, how many times it was shown, clicks, spend, and
  budget left.
- **Auction Metrics**: how **fast** the server replied (latency — lower is better), how many
  requests per second it handled, and which campaigns **won** the most.
- **Conformance Scorecard / Findings**: industry-standard grades and detailed notes.

---

## 8. Run the important tests ("Conformance scenarios")

This is the most valuable automated part. In box **3 · Conformance scenarios (S1–S15)**:

1. Leave the dropdown on **"All (S1–S15)"** (or pick a single one, e.g. *S7 · Budget* or *S10 · OpenRTB*).
2. Click **"Run scenario"**.
3. **Be patient** — "All" runs 15 full tests and can take **one to two minutes**. The
   "● running…" indicator shows it's working.

When it finishes, scroll down to **"Scenario Results"**. Each test shows a coloured badge:

- 🟩 **PASS** — the server did the right thing.
- 🟨 **GAP** — the server did **not** do something it should (this is a finding for the devs).
- 🟦 **BLOCKED** — the server doesn't have that feature at all, so there's nothing to test yet.
- 🟥 **FAIL / ERROR** — the test couldn't complete.

Each result has an **Expected** line (what *should* happen) and an **Actual** line (what the
server *actually* did). Read those two lines and you'll understand the result.

### What the tests check (plain words)

| Test | In plain words | Likely result today |
|---|---|---|
| **S1 Smoke** | One advert request comes back as a valid video ad. | PASS |
| **S2 Normal traffic** | Lots of requests all return valid ads. | PASS |
| **S3 Real vs filler** | Are real campaign ads shown, or just a placeholder? | PASS after seeding |
| **S4 No-fill** | When there's no ad, it should say so cleanly. | GAP — always shows a placeholder |
| **S5 Country targeting** | "India only" shouldn't show in the US/UK. | GAP |
| **S6 Frequency cap** | Same person shouldn't see it too many times. | GAP |
| **S7 Budget** | When the money runs out, stop showing. | GAP |
| **S8 Schedule** | An expired campaign shouldn't be picked. | PASS |
| **S9 Ad pods / VMAP** | Ad-break playlists are well-formed; real pods exist. | PASS + BLOCKED |
| **S10 OpenRTB** | A programmatic bid request gets a valid response. | PASS with the built-in test bidder |
| **S11 Tracking** | View/quartile pixels record correctly and in order. | PASS |
| **S12 Privacy** | GDPR / US-privacy / GPP signals are accepted. | PASS (with a note) |
| **S13 ads.txt** | The transparency files are valid. | PASS |
| **S14 Load** | Stays fast and error-free under load. | PASS/FAIL vs targets |
| **S15 Resilience** | Doesn't crash on bad/garbage requests. | PASS |

### Tip — run one scenario at a time when debugging

| If you're checking… | Run this |
|---|---|
| Auction + fake buyer | **S10** (set DSP to **Bid** first — see §9) |
| Tracking pixels | **S11** (or Publisher tab + Simulate playback) |
| Budget stop | **S7** |
| Geo targeting | **S5** |
| Bad requests don't crash the server | **S15** |
| Everything | **All (S1–S15)** |

### The scorecard and the GAP report

At the top of the results you'll see a **Conformance Scorecard** — a green/amber/red grade per
industry standard (VAST, VMAP, OpenRTB, ads.txt, …). To hand findings to developers, click
**"GAP report"** (a readable summary) or **"gaps.json"** (a machine-readable file) in box 3.

---

## 9. DSP Settings — controlling the fake buyer

Open the **DSP Settings** tab.

Think of this screen as the remote control for a **pretend advertiser** that your ad server
calls during an OpenRTB auction. Whatever you set here applies on the **next** request —
no restart needed.

### 9.1 What you see on the screen

1. **Behaviour buttons** — **Bid** / **No-bid** / **Timeout** / **Error**  
   These are the most important controls. Click one — it applies immediately.
2. **Live stats** — Requests, Bids, No-bids, Timeouts, Errors, Total bid $  
   Proof the ad server is (or isn't) calling the buyer.
3. **Behaviour detail** — bid rate, timeout delay, no-bid reason code, verbose logging.
4. **Pricing** — how much the buyer is willing to pay (CPM), floor margin, max price, jitter.
5. **Who's bidding** — seat name, creative id, campaign id, advertiser domain, category.
6. **The creative** — the actual video ad (MP4 URL, size, duration, landing page, tracking base).
7. **Notice URLs** — win / billing / loss / preview image URLs.
8. **Advanced · custom bid response** — paste a full JSON response (power users).
9. Buttons: **Save settings**, **Send test bid**, **Reset stats**, **Refresh**.

### 9.2 Behaviour modes (memorise these)

| Mode | What the fake buyer does | Use it to test… |
|---|---|---|
| **Bid** | Offers a price + a playable video ad | Happy path — auction should return a winner |
| **No-bid** | Refuses to buy (204 or a reason code) | Auction with no demand — should return no ad / empty |
| **Timeout** | Waits too long, then no-bids | Slow partner — server should not hang forever |
| **Error** | Returns HTTP 500 | Broken partner — server should survive and not 5xx the publisher |

### 9.3 How to change settings safely

1. Click a **Behaviour** button for quick flips (Bid ↔ No-bid is the common demo).
2. Edit pricing / creative / notice fields as needed.
3. Click **Save settings** (required for everything except the instant mode buttons).
4. Optionally click **Send test bid** — this hits the fake DSP *directly* (bypasses the ad
   server) so you can see the exact JSON it would return. Useful to confirm your creative/price
   before you involve the auction.
5. Click **Reset stats** when you want a clean counter for the next test round.

### 9.4 Pricing — what the numbers mean

| Field | Plain meaning | Practical tip |
|---|---|---|
| **Base price (CPM)** | What the buyer normally offers | Raise it to win more often |
| **Bid margin (× floor)** | Bid at least `floor × margin` so you clear the minimum | `1.2` means 20% above floor |
| **Max CPM** | Never bid higher than this | Cap for safety |
| **Price jitter** | Small random wiggle so bids look realistic | Leave default unless comparing exact prices |
| **Respect floor** | If our price is below the floor → no-bid that slot | Turn **off** only when testing below-floor behaviour |
| **Currency** | Usually `USD` | Match what the publisher request uses |

### 9.5 Creative — the ad that comes back

The fake DSP returns a **real watchable video** (a public sample MP4) inside VAST. You can:

- Change **Video URL** to another MP4 if you prefer.
- Change **Advertiser name** / **Landing URL** (where a click would go).
- Set **Tracking base URL** to where this simulator is reachable (default
  `http://localhost:8090`) so impression/quartile pixels land on **`/dsp/track`**.

After a win, open **Publisher Ad Request**, tick **Simulate playback**, and send — you'll see
ad-server hits vs advertiser (`/dsp/track`) hits counted.

### 9.6 Notice URLs (win / billing / loss)

These are the URLs the exchange pings when the bid wins, gets billed, or loses.

- Keep `${AUCTION_PRICE}` style macros as written — the exchange fills them in.
- `[CB]` is a cache-buster the fake DSP fills itself.

You usually leave these alone unless a developer asks you to point them somewhere specific.

### 9.7 Advanced — custom bid response

Tick **Use custom response**, paste a full OpenRTB `BidResponse` JSON, then **Save settings**.

Macros you can put in the JSON:

| Macro | Becomes |
|---|---|
| `"{{price}}"` (quoted) | A real number (the computed CPM) |
| `{{price}}` | Price as text |
| `{{impid}}` / `{{id}}` / `{{crid}}` / `{{seat}}` / `{{cur}}` | Identity fields |

Use this when QA needs a **weird but specific** response shape (missing fields, odd `adm`, etc.).
If the JSON is invalid, the DSP falls back to its normal auto-built bid so the auction doesn't crash.

### 9.8 No-bid reason codes

When mode is **No-bid** and "No-bid as 200 + nbr" is ticked, pick a reason (0–10), e.g.:

- `0` Unknown · `1` Technical error · `2` Invalid request · `6` Unsupported device ·
  `7` Blocked publisher · `9` Daily reader cap · `10` Daily domain cap

Untick that box to return a bare **HTTP 204** instead (also a valid industry no-bid).

---

## 10. Publisher Ad Request — one publisher, one tag, clear results

Open the **Publisher Ad Request** tab when you want to test **one real-looking request** instead
of bulk traffic.

### What to fill in

1. **Publisher id** and **Ad unit / tag id** (defaults are fine for demos; use real IDs for real inventory).
2. **Type**: OpenRTB (auction) or VAST (video tag).
3. For OpenRTB: format (video / banner / …), app vs site, device, country, floor.
4. **How many requests** (start with `1`, then try `5`).
5. Optional privacy fields (US privacy, GDPR, GPP, COPPA).
6. Optional: paste a **real publisher OpenRTB body** (custom JSON) and fire it verbatim.
7. Optional: tick **Simulate playback** — after a win, the tool fires the ad's trackers and win
   notices for you (like a player would).

Then:

- **Preview request** — see the exact IAB JSON/URL without sending.
- **Send** — fire it at the ad server through the simulator (avoids browser CORS issues).

### What you get back

- Aggregate tiles: fill / no-fill / errors / latency.
- Sample request + sample response (with conformance findings).
- **Winning ad creative (VAST)** — copy it and paste into a VAST inspector to **watch the ad**.
- **Playback** panel (if you ticked Simulate playback) — which pixels succeeded, how many hit
  the ad server vs the fake advertiser.

---

## 11. End-to-end testing recipes (do these in order)

These recipes combine **Dashboard + DSP Settings + Publisher Ad Request**. They are the
practical "real testing" path — not just reading numbers.

### Recipe A — Happy path: auction wins a real bid

**Goal:** Prove the ad server calls the buyer and returns a winning video ad.

1. **Dashboard** → Seed ecosystem (once).
2. **DSP Settings** → click **Bid** → **Reset stats** → (optional) **Send test bid** and confirm you see a VAST in `adm`.
3. **Publisher Ad Request** → protocol **OpenRTB**, format **video**, count `1`.
4. Tick **Simulate playback** → **Send**.
5. **Expect:**
   - A filled response with a price and VAST creative.
   - DSP stats: Requests ↑, Bids ↑.
   - Black engine window shows `DECISION: BID`.
   - Playback panel shows ad-server hits + advertiser (`/dsp/track`) hits.
6. Optional: open **Dashboard** → run scenario **S10** → expect **PASS**.

### Recipe B — Buyer refuses: no-bid

**Goal:** Prove the auction depends on demand (not a hard-coded fake win).

1. **DSP Settings** → click **No-bid** → **Reset stats**.
2. **Publisher Ad Request** → same OpenRTB request as Recipe A → **Send** (playback off is fine).
3. **Expect:**
   - No winning ad (empty / 204 / no seatbid — depending on the server).
   - DSP stats: No-bids ↑.
   - Engine window shows `DECISION: NO-BID`.
4. Flip DSP back to **Bid** and Send again — the ad should return. That on/off flip is the proof.

### Recipe C — Buyer too slow: timeout

**Goal:** Slow demand partner must not freeze the publisher forever.

1. **DSP Settings** → **Timeout**, set **Timeout delay** to e.g. `2000` ms → **Save settings** → **Reset stats**.
2. **Publisher Ad Request** → Send **1** OpenRTB request.
3. **Expect:**
   - Response eventually comes back (no endless hang).
   - DSP stats: Timeouts ↑.
   - Latency tile is higher than in Recipe A, but the UI still finishes.
4. Set behaviour back to **Bid** when done.

### Recipe D — Buyer crashes: error 500

**Goal:** Broken demand partner must not crash the ad server.

1. **DSP Settings** → **Error** → **Reset stats**.
2. **Publisher Ad Request** → Send **1** OpenRTB request.
3. **Expect:**
   - Publisher-facing response is handled (no uncaught 5xx from the sim UI if the SUT is resilient).
   - DSP stats: Errors ↑.
   - Engine window shows forced error.
4. Return DSP to **Bid**.

### Recipe E — Floor / price edge

**Goal:** Bid below the publisher floor should not win (when "Respect floor" is on).

1. **DSP Settings** → **Bid**, set **Base price** low (e.g. `1.0`), **Max CPM** low (e.g. `1.5`),
   **Respect floor** ON → **Save**.
2. **Publisher Ad Request** → set **bidfloor** high (e.g. `20`) → **Send**.
3. **Expect:** no-bid / no win for that floor.
4. Raise **Max CPM** / **Base price** above the floor (or lower the floor) → Send again → expect a win.

### Recipe F — Tracking / playback proof

**Goal:** After a win, impressions and quartiles actually fire.

1. DSP = **Bid**.
2. Publisher tab → OpenRTB win path → tick **Simulate playback** → **Send**.
3. **Expect:** Playback table shows ✓ for impression / quartile / win-or-billing URLs.
4. Optional: copy **Winning VAST** into a VAST viewer and watch the sample video play.

### Recipe G — Full automated sweep

**Goal:** Hand a complete conformance picture to developers.

1. Seed once, DSP = **Bid**.
2. Dashboard → **All (S1–S15)** → Run scenario.
3. Download **GAP report** + **gaps.json**.
4. Report every **GAP** / **FAIL** with the Expected vs Actual lines (don't "fix" GAPs — they are the findings).

---

## 12. Negative scenarios & edge cases (intentionally break things)

Use these when you want to **stress** the auction and reporting — not just the happy path.

### Buyer-side negatives (DSP Settings)

| Case | How to set it | What "good" looks like |
|---|---|---|
| Buyer always refuses | Mode **No-bid** | Auction returns no winner; stats show no-bids; flipping back to Bid restores wins |
| Buyer sometimes refuses | Mode **Bid**, **Bid rate** = `0.3` → Save | Mix of wins and no-fills over `count: 20` |
| Buyer sleeps | Mode **Timeout**, delay `3000–5000` | Request completes without freezing the UI; timeouts counted |
| Buyer crashes | Mode **Error** | Ad server survives; errors counted; publisher path still returns something sensible |
| Below-floor bid | Low price + high bidfloor + Respect floor ON | No win |
| Ignore floor (edge) | Respect floor **OFF**, low price, high floor | Documents whatever the SUT does — capture it for the GAP report |
| No-bid with reason code | No-bid + nbr code `7` (blocked publisher) | Response shape includes `nbr` when "200 + nbr" is on |
| Bare 204 no-bid | No-bid + untick "200 + nbr" | Bare empty no-bid |
| Weird custom response | Advanced custom JSON missing `seatbid` / bad `adm` | Capture SUT behaviour; DSP won't crash (falls back if JSON invalid) |

### Publisher / request negatives (Publisher Ad Request)

| Case | How to do it | What to look for |
|---|---|---|
| Wrong tag id | `tag_id` = `99999999` | Error or no-fill — should not crash the sim |
| Wrong publisher id | Nonsense `publisher_id` | Same — graceful handling |
| Empty / tiny count | `count` = `1` then `5` | Stable results both times |
| High floor | `bidfloor` = `999` with normal DSP price | Likely no-bid / no win |
| Banner vs video | Switch **ad_format** | Correct creative type in response (HTML vs VAST) |
| Privacy signals | Set `us_privacy`, `gdpr=1`, `gpp`, `coppa=1` | Request accepted; note any findings in sample response |
| Custom broken JSON | Paste invalid JSON in custom OpenRTB | UI shows a clear error — fix JSON and retry |
| Custom real body | Paste a production OpenRTB sample | Same auction path; compare fill vs builder path |
| Preview only | Click **Preview request** | Exact outbound request shown; nothing sent yet |

### Scenario / product negatives (Dashboard scenarios)

These are **expected** to GAP on today's ad server — still run them; the GAP *is* the finding:

| Scenario | Negative intent |
|---|---|
| **S4** | Server never admits "no ad" cleanly |
| **S5** | Off-geo traffic still gets served |
| **S6** | Same user can be over-exposed (no frequency cap) |
| **S7** | Budget doesn't actually stop delivery |
| **S9** (pods part) | True multi-ad pods missing → BLOCKED |
| **S14** | Push load high — watch p95 / error rate |
| **S15** | Garbage requests must not produce server 5xx |

### Operational edge cases

| Situation | What to do |
|---|---|
| First OpenRTB call is very slow (~30s) | Normal cold start — wait; don't spam Send |
| DSP stats stay at 0 during auction | Re-seed (registers the fake DSP), confirm DSP mode, watch engine window |
| Playback shows advertiser misses | Check **Tracking base URL** is `http://localhost:8090` and DSP is reachable |
| You changed creative but still see old ad | Click **Save settings**, then Send again (next request picks it up) |
| Numbers from an old test confuse you | **Reset stats** on DSP Settings; pick a fresh run in the Dashboard **View** dropdown |
| Auction works in Bid, fails in No-bid (or vice versa) | That's useful — screenshot both; it proves demand sensitivity |

---

## 13. How to read the overall result

- If a scenario is **PASS** → that feature works.
- If a scenario is **GAP** → write down which one (e.g. S5, S7) and the "Actual" line, and
  send it to the development team. The simulator has found a real issue for them to fix.
- If DSP **Bid** fills and DSP **No-bid** does not → the auction is truly using the buyer. 👍
- The **Overview** and **Auction** numbers tell you general health: a healthy server replies
  quickly (low latency) and shows adverts (reasonable fill rate).

You don't need to judge anything deeply technical — just **report the colours, the Expected vs
Actual text, and (for auction tests) whether Bid vs No-bid flipped the outcome**.

---

## 14. Doing another round

- You can click **Run traffic** or **Run scenario** again any time.
- Flip DSP modes between rounds to compare outcomes.
- Results add up over time. To look at just **one** run on its own, use the **"View"** dropdown
  (above the Overview tiles) and pick a run from the list. Choose **"All runs (aggregate)"** to
  see everything together.
- The **Refresh** button reloads the numbers if they look stale.
- On DSP Settings, use **Reset stats** so the next recipe starts from zero.

---

## 15. When you're finished

1. On **DSP Settings**, put the buyer back to **Bid** (so the next person isn't confused).
2. Close the black engine window (the one that opened in Step 4). That stops the tool.

Nothing is harmed — you can start it again anytime by double-clicking `start.bat`.

---

## 16. If something doesn't work

| What you see | What to do |
|---|---|
| Browser says "can't connect" to localhost:8090 | Wait 5 seconds, refresh. Make sure the black engine window is still open. |
| 🔴 Red dot at the top | The ad server isn't running. Ask a developer to start it, then refresh. |
| Auction always empty even on Bid | Seed again; confirm DSP Settings = Bid; watch the engine window for `MOCK DSP` lines. |
| DSP Settings tab errors / 404 in Vite dev | Backend must be on `:8090`; `/dsp` must be proxied (developers: see `README.md`). |
| First auction times out | Wait up to ~60s once; cold start is normal. Don't click Send repeatedly. |
| Simulate playback shows failures | DSP = Bid and you actually won an ad first; tracking base should be localhost:8090. |
| A button does nothing / an error bar appears | Take a screenshot of the red message and send it to a developer. |
| The tool won't start at all | Restart the computer and try `start.bat` again. If it still fails, a developer may need to redo the one-time setup below. |

---

## 17. Suggested "full QA session" checklist

Use this when someone asks you to "test the simulator end to end":

- [ ] Green traffic light + `platform_admin`
- [ ] Seed ecosystem once
- [ ] DSP **Bid** → Publisher OpenRTB Send (+ Simulate playback) → win + pixels OK
- [ ] DSP **No-bid** → same request → no win → flip back to Bid → win again
- [ ] DSP **Timeout** → request still completes
- [ ] DSP **Error** → server survives
- [ ] Floor edge (high floor / low bid) → no win
- [ ] Dashboard → run **S10**, then **All (S1–S15)**
- [ ] Download GAP report / gaps.json and share GAPs with Expected vs Actual
- [ ] Leave DSP on **Bid** when done

---

## 18. One-time setup (for a developer, on a new computer)

Only needed once. Follow the full simple guide in **[`setup.md`](setup.md)**.

Short version:

```bash
# 1. Backend
cd ad-server-sim/backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then set AD_SERVER_EMAIL / AD_SERVER_PASSWORD to an ADMIN login

# 2. Dashboard (build once so it's served at http://localhost:8090)
cd ../dashboard
npm install
npm run build
```

The admin account in `.env` must have the role `platform_admin` or `tenant_admin` on the ad
server (a normal sign-up is not enough). See `README.md` → *Prerequisites* for the one-line
command to grant it. After this, day-to-day users just double-click `start.bat`.

For deeper technical reference (API paths, env vars, architecture), see **`README.md`**.
