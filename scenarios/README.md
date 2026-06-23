# Example scenarios

Predefined business scenarios for the simulator's **Scenario Engine** (Module 6). Run them
from the dashboard ("3 · Business scenarios") or via the API:

```bash
curl -X POST localhost:8090/api/scenario -H 'Content-Type: application/json' -d '{"scenario":"A"}'
# scenario: "A" | "B" | "C" | "D" | "all"
```

Each scenario asserts the **standard** expected behaviour of a correct ad server and emits a
verdict — `PASS`, `GAP` (server doesn't enforce the rule), `FAIL` (couldn't validate), or
`ERROR` — with supporting evidence.

| File | Scenario | Expected verdict vs the current Voise Ad Server |
|---|---|---|
| `scenario_a_budget.json` | A · Budget exhaustion | **GAP** |
| `scenario_b_country.json` | B · Country targeting | **GAP** |
| `scenario_c_bid.json` | C · Bid competition | **PASS** |
| `scenario_d_freqcap.json` | D · Frequency cap | **GAP** |

`example_output.json` is **real output** captured from this simulator against the local ad
server — three of the four scenarios surface genuine gaps in the server's decisioning, exactly
as a conformance harness should.
