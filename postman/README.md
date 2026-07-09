# Postman — Voise Ad Sim E2E Flows (simple guide)

This Postman collection lets you run the whole end-to-end validation **by clicking Send**, instead of typing PowerShell. It drives the Ad Server (Voise) through the Simulator + mock DSP.

---

## 1. What you need running first

Two things must already be running (both frontend + backend, as you have them):


| Thing                    | Default URL             | What it is                                       |
| ------------------------ | ----------------------- | ------------------------------------------------ |
| **Ad server (Voise)**    | `http://localhost:8001` | the system being tested                          |
| **Simulator + mock DSP** | `http://localhost:8090` | drives traffic, plays the buyer (DSP), validates |


Also keep the **simulator's backend terminal visible** — the mock DSP prints each bid request + decision there. That's your live view of the auction.

---



## 2. Import the collection

1. Open Postman → **Import** (top-left).
2. Drag in `Voise-AdSim.postman_collection.json` (this folder).
3. You'll see a collection called **"Voise Ad Sim — E2E Flows"** with 6 folders (0–5).

> If your ports are different: click the collection name → **Variables** tab → edit `sim_base` and `adserver_base` → **Save**.

---



## 3. One-time Postman setting (important for the auction)

The ad server's auction can take **up to ~30 seconds** on the first call. So raise Postman's request timeout:

- **Settings** (⚙ top-right) → **General** → **Request timeout in ms** → set to `60000` (or `0` = no limit) → close.

---



## 4. How to run it — just go top to bottom

Open each folder and click **Send** on each request, **in order**. Here's what each folder does and what "good" looks like. Open the **Console** (bottom-left "Console") to see the friendly log lines the requests print.

### 📁 0 — Check everything is running

- **Check simulator and ad server are up** → expect `"ad_server_reachable": true`. (If false, the ad server isn't reachable — fix that first.)
- **See which ad server URLs the simulator found** / **See mock buyer (DSP) status** → optional sanity checks.



### 📁 1 — Set up test data  ⚠️ run this before folder 3

- **Create test advertisers and save ad tag ID** → creates advertisers/campaigns/publishers and registers the mock DSP as a buyer.
- ✨ It **auto-saves a real** `tag_id` into the collection so folder 3 works. Check the **Console**: you'll see `Saved ad tag ID → ...`.



### 📁 2 — Test video ads (VAST)

- **Send 200 video ad requests** → sends 200 video ad requests and fires impression/quartile pixels.
- **See request totals** → requests, impressions, clicks.
- **See real ads vs placeholder ads** → how many were **real** campaign ads vs the **filler** "Video Ad".



### 📁 3 — Test ad auction (OpenRTB)  ⭐ the main event

Run these **in order**:

1. **Turn mock buyer ON (will place bids)** — tell your DSP to buy.
2. **Send ad auction request — expect an ad back** — sends the team's CTV OpenRTB sample to the **ad server**; it runs an auction and calls your mock buyer.
  - 👀 **Watch the sim terminal**: a `MOCK DSP <-- ... DECISION: BID` block appears.
  - ✅ Response should be **HTTP 200** with `seatbid`, a `price`, and a `<VAST>` creative in `adm`. The **Console** prints `Ad returned — seat=... price=...`. Test results turn green.
  - ⏳ First call may take ~30s — be patient, don't spam Send.
  - The request body matches the inbound CTV sample (Samsung Tizen, Philo app, publisher `1192`, supply chain, etc.). Only `tag_id` comes from seed; `request_id` is generated per send.
3. **Check mock buyer received the request** — `bids` incremented. Proof the DSP was used.
4. **Turn mock buyer OFF (will not bid)** — make the DSP refuse.
5. **Send same auction request — expect no ad** — same request; now expect **no winner** (204 or empty seatbid). Sim terminal shows `DECISION: NO-BID`. This proves the auction truly depends on your DSP.
6. **Turn mock buyer back ON** — put it back to normal.
7. *(Optional)* **Optional — test mock buyer directly** — hits the DSP alone (bypassing the ad server) to see a raw bid response.



### 📁 4 — Run automated checks

- **Run all 15 automated compliance checks** → automated checks (1–2 min, background).
- **Run one check only** → e.g. `S10` (OpenRTB). Change the `scenario` value to S1..S15.



### 📁 5 — View results

- **See pass/fail grades by standard** → per-standard grade (VAST, OpenRTB, ads.txt…).
- **See detailed issues found** → every conformance finding with a spec reference.
- **Compare simulator counts vs ad server** → sim counts vs the ad server's reported counts.
- **Check ads.txt and sellers.json files** → validates ads.txt / sellers.json.
- **Download human-readable report** / **Download machine-readable report** → the shareable report for developers.

---



## 5. Reading verdicts (what the colours mean)

- **PASS** — the ad server did the right thing.
- **GAP** — the ad server deviates from the IAB standard (a finding for devs). **Expected** on: S4 no-fill, S5 geo-targeting, S6 frequency cap, S7 budget — those aren't enforced yet.
- **BLOCKED** — the ad server has no such capability to test (e.g., true ad pods).

A **GAP is not a bug in this tool** — it's the tool doing its job (finding something for the ad-server team to fix).

---



## 6. If something goes wrong


| Symptom                                       | Fix                                                                                         |
| --------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Auction request times out                     | Raise Postman request timeout (step 3) to 60000; Send again. First call is a cold start.    |
| Auction returns **no ad** with buyer ON       | Run **folder 1 (Set up test data)** again so the DSP is registered; make sure buyer is ON.  |
| `{{tag_id}}` looks empty in the URL           | You skipped **Create test advertisers and save ad tag ID**. Run it first.                   |
| Sim Health shows `ad_server_reachable: false` | The ad server (`:8001`) isn't up or the URL is wrong (check `adserver_base` variable).      |
| No DSP block in the sim terminal              | The ad server didn't call the DSP — re-seed (folder 1), then retry folder 3.                |


---



## 7. The end-to-end story (one paragraph)

You **set up test data** → drive **VAST** traffic (simple serve + tracking) → run the **OpenRTB auction** where the ad server asks your **mock DSP** for a bid and returns the winning creative → flip the DSP to **no-bid** to prove the auction reacts → run **S1–S15 conformance** → read the **scorecard + GAP report**. That's a full ad-tech loop: **ad request → auction → DSP bid → creative → tracking → reporting → conformance**.
