# How to Use the Ad Server Simulator — Simple Guide

This guide is written for **anyone** — you do **not** need to be technical to use this tool.
Just follow the steps in order.

---

## 1. What is this tool, in plain words?

Think of the **ad server** as the machine that decides which advert to show on a website and
then keeps score of how many people saw it and clicked it.

Normally, to test that machine you would need thousands of real people visiting real websites.
That's not practical. So this **Simulator** *pretends* to be all those people and websites. It
sends fake-but-realistic visits to the ad server, watches what the server does, and tells you —
in a simple dashboard — whether the server behaved correctly.

You use it to answer questions like:
- *Are adverts actually being shown?*
- *Is the server picking the right advert?*
- *Does it stop spending money when a budget runs out?*
- *Is it fast enough?*

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
| **Scenario** | A specific test with a clear right answer (e.g. "the bigger bidder should win"). |
| **PASS / GAP / FAIL** | The test result. **PASS** = server did the right thing. **GAP** = the server is missing or not doing something it should. **FAIL** = the test could not run. |

> **Important:** A **GAP** is **not** a problem with this tool. It means the tool found something
> the ad server isn't doing correctly yet. That's exactly what it's for — finding issues to
> hand to the development team.

---

## 3. Before you start

Two things must be true. A developer usually sets these up once:

1. **The ad server is running** on this computer.
2. **This simulator has been set up** (done already on this machine — see the last section if
   you're on a brand-new computer).

If you're not sure, don't worry — Step 4 shows you a green/red light that tells you instantly.

---

## 4. Start the tool

**Easiest way:** double-click the file **`start.bat`** inside the `ad-server-sim` folder.

- A black window will open and show some text. **Leave this window open** while you work — it's
  the engine running. (To stop the tool later, just close that window.)
- After a few seconds, your web browser opens the dashboard automatically at
  **http://localhost:8090**
- If the page looks blank or says "can't connect," wait 5 seconds and **refresh** the page.

*(The tool may already be running — if so, just open http://localhost:8090 in your browser.)*

---

## 5. Check the connection (the traffic light)

Look at the **top-right corner** of the dashboard:

- 🟢 **Green dot + a web address** = the simulator is connected to the ad server. 
- 🔴 **Red dot** = the ad server is **not** running. Ask a developer to start it, then refresh.

You should also see **`role: platform_admin`** — that just means the tool has permission to set
up test data.

If the light is green, you're ready.

---

## 6. The 3-step flow (this is the main part)

The dashboard has three boxes at the top, numbered **1**, **2**, **3**. Use them left to right.

### Step 1 — Create test data ("Seed data")
In box **1 · Seed data**, just click the **"Seed ecosystem"** button.

- This creates pretend advertisers and ad campaigns inside the ad server so there's something
  to show. (You can leave the number boxes at their defaults.)
- Wait a couple of seconds. A **"Live run"** panel appears showing what was created, and may
  list a few **findings** in amber — these are notes about things the server struggled with.
  That's normal and useful.

You only need to do this **once** each time you start fresh.

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

---

## 7. Run the important tests ("Conformance scenarios")

This is the most valuable part. In box **3 · Conformance scenarios (S1–S15)**:

1. Leave the dropdown on **"All (S1–S15)"** (or pick a single one, e.g. *S7 · Budget*).
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

### The scorecard and the GAP report
At the top of the results you'll see a **Conformance Scorecard** — a green/amber/red grade per
industry standard (VAST, VMAP, OpenRTB, ads.txt, …). To hand findings to developers, click
**"GAP report"** (a readable summary) or **"gaps.json"** (a machine-readable file) in box 3.

---

## 8. How to read the overall result

- If a scenario is **PASS** → that feature works. 👍
- If a scenario is **GAP** → write down which one (A, B, C, or D) and the "Actual" line, and
  send it to the development team. The simulator has found a real issue for them to fix.
- The **Overview** and **Auction** numbers tell you general health: a healthy server replies
  quickly (low latency) and shows adverts (reasonable fill rate).

You don't need to judge anything technical — just **report the colours and the "Actual" text**.

---

## 9. Doing another round

- You can click **Run traffic** or **Run scenario** again any time.
- Results add up over time. To look at just **one** run on its own, use the **"View"** dropdown
  (above the Overview tiles) and pick a run from the list. Choose **"All runs (aggregate)"** to
  see everything together.
- The **Refresh** button reloads the numbers if they look stale.

---

## 10. When you're finished

Close the black engine window (the one that opened in Step 4). That stops the tool. Nothing is
harmed — you can start it again anytime by double-clicking `start.bat`.

---

## 11. If something doesn't work

| What you see | What to do |
|---|---|
| Browser says "can't connect" to localhost:8090 | Wait 5 seconds, refresh. Make sure the black engine window is still open. |
| 🔴 Red dot at the top | The ad server isn't running. Ask a developer to start it, then refresh. |
| A button does nothing / an error bar appears | Take a screenshot of the red message and send it to a developer. |
| The tool won't start at all | Restart the computer and try `start.bat` again. If it still fails, a developer may need to redo the one-time setup below. |

---

## 12. One-time setup (for a developer, on a new computer)

Only needed once, by someone technical:

```bash
# 1. Backend
cd ad-server-sim/backend
python -m venv .venv
.venv\Scripts\activate          # Windows
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
