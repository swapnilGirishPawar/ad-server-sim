# Dashboard screenshots

The dashboard runs at `http://localhost:8090` (backend-served build) or
`http://localhost:5173` (Vite dev). Capture screenshots there; the views below were verified
live against the local Voise Ad Server.

To capture: start the backend, `npm run build` (or `npm run dev`), open the URL, and use your
OS screenshot tool. Suggested shots for `docs/screenshots/`:

1. **Controls** (`controls.png`) — the three panels: *1 · Seed data*, *2 · Generate traffic*
   (protocol selector, RPS, concurrency, impression-rate, CTR), *3 · Business scenarios*.
   The header shows a green dot + the ad-server URL + the authenticated role (`platform_admin`).

2. **Overview + charts** (`overview.png`) — six KPI tiles (Requests, Responses, Impressions,
   Clicks, Fill Rate, CTR) above two Recharts time-series: requests/impressions/clicks, and
   modelled campaign spend.

3. **Campaign + auctions** (`auctions.png`) — the Campaign Metrics table (impressions, clicks,
   CTR, spend, budget, remaining) beside the Auction panel (avg latency, P95 latency, RPS) and
   the Win Distribution bar chart.

4. **Scenario results** (`scenarios.png`) — the headline view: each scenario with a colour-coded
   verdict badge — **PASS** (green), **GAP** (amber), **FAIL/ERROR** (red/grey) — plus the
   expected-vs-actual explanation. A typical run shows **C = PASS** and **A/B/D = GAP**.

See `../scenarios/example_output.json` for the real verdict payloads captured during
verification.
