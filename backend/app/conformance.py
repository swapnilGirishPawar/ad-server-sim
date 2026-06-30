"""Conformance findings model + scorecard.

A `Finding` is the atomic unit the simulator emits whenever it checks a server
response against an IAB standard. Findings are persisted (see `db.findings`),
rolled up into a per-standard scorecard, and exported to `gaps.json` /
`GAP_REPORT.md` (see `app.report`).

Severity legend (mirrors the build prompt's oracle legend):
  pass  — the response conforms to the standard for this check.
  fail  — the response violates the standard (a real GAP to fix).
  warn  — the response is technically tolerable but sub-spec / risky.
  info  — observational (e.g. OMID absent, no-fill observed) — never a failure.

The `gaps.json` entry shape required by the build prompt §7 is:
  {standard, spec_section, endpoint, expected, observed, severity, scenario}
`Finding.to_gap()` produces exactly that.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

PASS = "pass"
FAIL = "fail"
WARN = "warn"
INFO = "info"

_SEVERITY_RANK = {PASS: 0, INFO: 1, WARN: 2, FAIL: 3}


@dataclass
class Finding:
    """One conformance observation against a published standard."""
    standard: str            # "VAST 4.x" | "VMAP" | "OpenRTB 2.6" | "ads.txt" | "sellers.json" | "Tracking" | "Privacy"
    spec_section: str        # human spec reference, e.g. "VAST 4.2 §3.4 MediaFile"
    check: str               # short stable id, e.g. "mediafile_attrs"
    severity: str            # pass | fail | warn | info
    expected: str
    observed: str
    endpoint: str = ""
    scenario: str = ""
    request_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_gap(self) -> Dict[str, Any]:
        """The machine-readable gaps.json entry shape (build prompt §7)."""
        return {
            "standard": self.standard,
            "spec_section": self.spec_section,
            "check": self.check,
            "endpoint": self.endpoint,
            "expected": self.expected,
            "observed": self.observed,
            "severity": self.severity,
            "scenario": self.scenario,
        }


@dataclass
class FindingSet:
    """A small accumulator passed through a validator."""
    findings: List[Finding] = field(default_factory=list)

    def add(self, standard: str, spec_section: str, check: str, severity: str,
            expected: str, observed: str, *, endpoint: str = "", scenario: str = "") -> None:
        self.findings.append(Finding(
            standard=standard, spec_section=spec_section, check=check, severity=severity,
            expected=expected, observed=observed, endpoint=endpoint, scenario=scenario))

    def ok(self, standard: str, spec_section: str, check: str, observed: str,
            *, endpoint: str = "", scenario: str = "") -> None:
        self.add(standard, spec_section, check, PASS, "conforms", observed,
                 endpoint=endpoint, scenario=scenario)

    @property
    def failed(self) -> bool:
        return any(f.severity == FAIL for f in self.findings)

    def worst(self) -> str:
        if not self.findings:
            return PASS
        return max((f.severity for f in self.findings), key=lambda s: _SEVERITY_RANK.get(s, 0))


def scorecard(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll a flat list of finding-dicts into a per-standard scorecard."""
    by_standard: Dict[str, Dict[str, int]] = {}
    totals = {PASS: 0, FAIL: 0, WARN: 0, INFO: 0}
    for f in findings:
        sev = f.get("severity", INFO)
        std = f.get("standard", "(unknown)")
        bucket = by_standard.setdefault(std, {PASS: 0, FAIL: 0, WARN: 0, INFO: 0, "total": 0})
        bucket[sev] = bucket.get(sev, 0) + 1
        bucket["total"] += 1
        totals[sev] = totals.get(sev, 0) + 1

    standards = []
    for std, b in sorted(by_standard.items()):
        checked = b["total"]
        passed = b[PASS]
        # grade ignores info-level observations (they are never failures).
        gradable = checked - b[INFO]
        rate = round(passed / gradable, 4) if gradable else None
        standards.append({
            "standard": std, "pass": b[PASS], "fail": b[FAIL], "warn": b[WARN],
            "info": b[INFO], "total": checked, "pass_rate": rate,
            "grade": _grade(b),
        })
    overall = {
        "checks": sum(totals.values()),
        **totals,
        "grade": _grade({PASS: totals[PASS], FAIL: totals[FAIL], WARN: totals[WARN], INFO: totals[INFO]}),
    }
    return {"overall": overall, "standards": standards}


def _grade(b: Dict[str, int]) -> str:
    if b.get(FAIL, 0) > 0:
        return "FAIL"
    if b.get(WARN, 0) > 0:
        return "WARN"
    if b.get(PASS, 0) > 0:
        return "PASS"
    return "INFO"
