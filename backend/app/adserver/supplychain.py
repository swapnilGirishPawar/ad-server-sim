"""ads.txt / app-ads.txt / sellers.json + SupplyChain validators (IAB §13).

Validates supply-chain transparency artefacts against the IAB specs:
  ads.txt 1.1        — one record per line: <domain>, <account_id>, <DIRECT|RESELLER>[, <cert_authority_id>]
  sellers.json 1.0   — JSON with contact_email/contact_address, version, identifiers[], sellers[]
  SupplyChain (sChain)— source.ext.schain on outbound bid requests: complete, ver, nodes[{asi,sid,hp}]

All pure functions — fixture-testable offline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.conformance import FAIL, INFO, PASS, WARN, Finding, FindingSet

ADSTXT = "ads.txt"
SELLERS = "sellers.json"
SCHAIN = "SupplyChain"


def validate_ads_txt(text: str, *, endpoint: str = "", app: bool = False) -> Dict[str, Any]:
    """Parse + validate an ads.txt / app-ads.txt body."""
    standard = "app-ads.txt" if app else ADSTXT
    fs = FindingSet()
    records: List[Dict[str, str]] = []
    variables: Dict[str, str] = {}

    if not text or not text.strip():
        fs.add(standard, "IAB ads.txt §3", "non_empty", FAIL, "a non-empty ads.txt", "empty body", endpoint=endpoint)
        return {"records": records, "variables": variables,
                "findings": [f.to_dict() for f in fs.findings], "seller_ids": []}

    bad_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" in line and "," not in line:
            k, v = line.split("=", 1)
            variables[k.strip().upper()] = v.strip()
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            bad_lines.append(line)
            continue
        rel = parts[2].upper()
        rec = {"domain": parts[0], "account_id": parts[1], "relationship": rel,
               "cert_authority_id": parts[3] if len(parts) > 3 else ""}
        records.append(rec)
        if rel not in ("DIRECT", "RESELLER"):
            fs.add(standard, "IAB ads.txt §3.1", "relationship", FAIL,
                   "relationship is DIRECT or RESELLER", f"'{rel}' in line: {line}", endpoint=endpoint)

    if bad_lines:
        fs.add(standard, "IAB ads.txt §3", "record_format", FAIL,
               "each record has >=3 comma-separated fields",
               f"{len(bad_lines)} malformed line(s), e.g. '{bad_lines[0]}'", endpoint=endpoint)
    if not records:
        fs.add(standard, "IAB ads.txt §3", "has_records", FAIL,
               "at least one authorized-seller record", "no valid records parsed", endpoint=endpoint)
    else:
        directs = [r for r in records if r["relationship"] == "DIRECT"]
        if not directs:
            fs.add(standard, "IAB ads.txt §3.1", "direct_seller", WARN,
                   "at least one DIRECT relationship", "no DIRECT records", endpoint=endpoint)
        fs.ok(standard, "IAB ads.txt §3", "record_format", f"{len(records)} valid record(s)", endpoint=endpoint)

    return {"records": records, "variables": variables,
            "findings": [f.to_dict() for f in fs.findings],
            "seller_ids": sorted({r["account_id"] for r in records})}


def validate_sellers_json(obj: Any, *, endpoint: str = "",
                          ads_txt_seller_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """Validate a sellers.json document (IAB sellers.json 1.0)."""
    fs = FindingSet()
    if not isinstance(obj, dict):
        fs.add(SELLERS, "sellers.json §3", "json_object", FAIL, "a JSON object", f"got {type(obj).__name__}",
               endpoint=endpoint)
        return {"findings": [f.to_dict() for f in fs.findings], "seller_ids": []}

    if not obj.get("version"):
        fs.add(SELLERS, "sellers.json §3.1", "version", WARN, "version field", "missing version", endpoint=endpoint)
    if not (obj.get("contact_email") or obj.get("contact_address")):
        fs.add(SELLERS, "sellers.json §3.1", "contact", WARN, "contact_email/contact_address",
               "no contact info", endpoint=endpoint)
    if not obj.get("identifiers"):
        fs.add(SELLERS, "sellers.json §3.1", "identifiers", INFO,
               "identifiers[] (e.g. TAG-ID)", "no identifiers", endpoint=endpoint)

    sellers = obj.get("sellers") or []
    if not sellers:
        fs.add(SELLERS, "sellers.json §3.2", "sellers", FAIL, "at least one seller entry", "empty sellers[]",
               endpoint=endpoint)
        return {"findings": [f.to_dict() for f in fs.findings], "seller_ids": []}

    seller_ids: List[str] = []
    for s in sellers:
        sid = str(s.get("seller_id")) if s.get("seller_id") is not None else None
        if not sid:
            fs.add(SELLERS, "sellers.json §3.2", "seller_id", FAIL, "each seller has seller_id",
                   f"seller missing seller_id: {s}", endpoint=endpoint)
            continue
        seller_ids.append(sid)
        stype = (s.get("seller_type") or "").upper()
        if stype not in ("PUBLISHER", "INTERMEDIARY", "BOTH"):
            fs.add(SELLERS, "sellers.json §3.2", "seller_type", WARN,
                   "seller_type in {PUBLISHER, INTERMEDIARY, BOTH}", f"seller_type='{stype or '(none)'}'",
                   endpoint=endpoint)
        if len(sid) == 12 and not str(s.get("seller_id")).strip().isdigit():
            # 12-char non-numeric IDs are the SUT's UUID-truncation symptom.
            fs.add(SELLERS, "sellers.json §3.2", "seller_id_truncation", WARN,
                   "full seller_id (not truncated)", f"seller_id '{sid}' looks truncated to 12 chars",
                   endpoint=endpoint)

    if not fs.failed:
        fs.ok(SELLERS, "sellers.json §3.2", "sellers", f"{len(seller_ids)} seller(s)", endpoint=endpoint)

    # Cross-check ID consistency with ads.txt account ids (SPO transparency).
    if ads_txt_seller_ids:
        missing = sorted(set(ads_txt_seller_ids) - set(seller_ids))
        if missing:
            fs.add(SCHAIN, "SPO consistency", "ads_txt_vs_sellers", WARN,
                   "ads.txt account IDs appear in sellers.json",
                   f"{len(missing)} ads.txt account id(s) absent from sellers.json (e.g. {missing[:3]})",
                   endpoint=endpoint)
        else:
            fs.ok(SCHAIN, "SPO consistency", "ads_txt_vs_sellers", "ads.txt IDs reconcile with sellers.json",
                  endpoint=endpoint)
    return {"findings": [f.to_dict() for f in fs.findings], "seller_ids": sorted(set(seller_ids))}


def validate_schain(req: Dict[str, Any], *, endpoint: str = "") -> List[Dict[str, Any]]:
    """Validate the source.ext.schain we attach to outbound bid requests."""
    fs = FindingSet()
    source = req.get("source") or {}
    schain = ((source.get("ext") or {}).get("schain")) or source.get("schain")
    if not schain:
        fs.add(SCHAIN, "OpenRTB SupplyChain §A.2", "present", FAIL,
               "source.ext.schain on the bid request", "no schain", endpoint=endpoint)
        return [f.to_dict() for f in fs.findings]
    if schain.get("complete") not in (0, 1):
        fs.add(SCHAIN, "SupplyChain §A.2", "complete", WARN, "schain.complete in {0,1}",
               f"complete={schain.get('complete')}", endpoint=endpoint)
    if not schain.get("ver"):
        fs.add(SCHAIN, "SupplyChain §A.2", "ver", WARN, "schain.ver (e.g. 1.0)", "missing ver", endpoint=endpoint)
    nodes = schain.get("nodes") or []
    if not nodes:
        fs.add(SCHAIN, "SupplyChain §A.2", "nodes", FAIL, "schain.nodes[] with >=1 node", "empty nodes",
               endpoint=endpoint)
    else:
        for i, n in enumerate(nodes):
            if not n.get("asi") or not n.get("sid"):
                fs.add(SCHAIN, "SupplyChain §A.3.1", "node_fields", FAIL,
                       "each node has asi + sid", f"node #{i} missing asi/sid", endpoint=endpoint)
        if not fs.failed:
            fs.ok(SCHAIN, "SupplyChain §A.2", "schain", f"{len(nodes)} node(s), complete={schain.get('complete')}",
                  endpoint=endpoint)
    return [f.to_dict() for f in fs.findings]
