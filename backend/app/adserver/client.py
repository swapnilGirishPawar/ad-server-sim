"""HTTP client for the target ad server.

Responsibilities:
  * auth bootstrap (login, with open-registration fallback for local dev)
  * entity creation for seeding (publishers, ad units, advertisers, DSPs,
    line items, campaigns, creatives)
  * ad requests over VAST and OpenRTB, validated against IAB specs into a
    normalised AdResult (with conformance findings + classification)
  * recursive VAST Wrapper following (VASTAdTagURI, depth cap, loop detection)
  * firing tracking pixels with macro substitution + host/prefix rewrite
  * supply-chain transparency fetch (ads.txt / app-ads.txt / sellers.json)
  * reading back the server's own reports for cross-verification

Seeding raises on failure (a broken seed must be loud). Ad requests and pixel
fires never raise — they return structured results so a load run keeps going.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.adserver import ortb as ortb_mod
from app.adserver import tracking
from app.adserver import validators
from app.adserver.result import AdResult
from app.config import Settings
from app.util import new_id

logger = logging.getLogger("adsim.client")

# Corrected-§3 live routes (used until target discovery overrides them).
DEFAULT_ROUTES: Dict[str, str] = {
    "vast_canonical": "/api/v/{tag_id}",
    "ortb_auction": "/api/b/{tag_id}",
    "vmap": "/api/m/{tag_id}",
    "dooh_vast": "/api/dooh/vast",
    "ads_txt": "/ads.txt",
    "app_ads_txt": "/app-ads.txt",
    "sellers_json": "/sellers.json",
}

WRAPPER_MAX_DEPTH = 5


class AdServerError(RuntimeError):
    pass


class AdServerClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.token: Optional[str] = None
        self.user: Dict[str, Any] = {}
        self.routes: Dict[str, str] = dict(DEFAULT_ROUTES)
        self.discovery: Dict[str, Any] = {}
        self._client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            verify=settings.verify_tls,
            follow_redirects=False,
        )
        # rewrites observed while normalising embedded tracking URLs (findings)
        self.url_rewrite_notes: Dict[str, int] = {}
        # macros we substituted while firing (so we can prove we behaved like a player)
        self.macro_counts: Dict[str, int] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AdServerClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    def apply_discovery(self, disc: Dict[str, Any]) -> None:
        """Repoint serving/supply routes to the SUT's actually-mounted paths."""
        self.discovery = disc
        for cap, path in (disc.get("resolved") or {}).items():
            if path:
                self.routes[cap] = path

    def _url(self, cap: str, **fmt: Any) -> str:
        path = self.routes.get(cap, DEFAULT_ROUTES.get(cap, ""))
        return self.s.root_base + path.format(**fmt)

    # ------------------------------------------------------------------ auth
    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def ping(self) -> bool:
        for path in ("/ping", "/health", "/openapi.json"):
            try:
                r = await self._client.get(f"{self.s.api_base}{path}" if path == "/ping"
                                           else f"{self.s.root_base}{path}")
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                continue
        return False

    async def ensure_auth(self) -> None:
        """Login; if that fails and auto_register is on, register then login."""
        if self.token:
            return
        creds = {"email": self.s.ad_server_email, "password": self.s.ad_server_password}
        r = await self._client.post(f"{self.s.api_base}/auth/login", json=creds)
        if r.status_code == 200:
            self._store_token(r.json())
            return
        if not self.s.auto_register:
            raise AdServerError(
                f"Login failed ({r.status_code}: {r.text[:200]}) and auto_register is disabled."
            )
        logger.info("Login failed (%s); registering sim user %s", r.status_code, self.s.ad_server_email)
        reg = {
            "email": self.s.ad_server_email,
            "name": self.s.ad_server_user_name,
            "password": self.s.ad_server_password,
            "role": self.s.ad_server_user_role,
        }
        rr = await self._client.post(f"{self.s.api_base}/auth/register", json=reg)
        if rr.status_code == 200:
            self._store_token(rr.json())
            return
        r2 = await self._client.post(f"{self.s.api_base}/auth/login", json=creds)
        if r2.status_code == 200:
            self._store_token(r2.json())
            return
        raise AdServerError(
            f"Auth bootstrap failed. login={r.status_code} register={rr.status_code}:{rr.text[:200]}"
        )

    def _store_token(self, payload: Dict[str, Any]) -> None:
        self.token = payload.get("access_token") or payload.get("token")
        self.user = payload.get("user", {}) or {}
        if not self.token:
            raise AdServerError(f"Auth response missing token: {payload}")

    # --------------------------------------------------------------- generic
    async def _send(self, method: str, path: str, *, json: Any = None,
                    params: Any = None, auth: bool = True) -> httpx.Response:
        headers = self._auth_headers() if auth else {}
        url = f"{self.s.api_base}{path}"
        last: Optional[Exception] = None
        for _ in range(2):
            try:
                return await self._client.request(method, url, json=json, params=params, headers=headers)
            except httpx.TransportError as e:
                last = e
        raise AdServerError(f"{method} {path} transport error after retry: {last}")

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._send("POST", path, json=body)
        if r.status_code in (200, 201):
            return r.json() if r.content else {}
        raise AdServerError(f"POST {path} -> {r.status_code}: {r.text[:300]}")

    async def _put(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        r = await self._send("PUT", path, json=body)
        if r.status_code in (200, 201):
            return r.json() if r.content else {}
        raise AdServerError(f"PUT {path} -> {r.status_code}: {r.text[:300]}")

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None, auth: bool = True) -> Any:
        r = await self._send("GET", path, params=params, auth=auth)
        if r.status_code == 200:
            return r.json() if r.content else None
        raise AdServerError(f"GET {path} -> {r.status_code}: {r.text[:200]}")

    async def get_root(self, path: str) -> httpx.Response:
        """GET an absolute (root-relative) path, e.g. /ads.txt or /openapi.json."""
        return await self._client.get(f"{self.s.root_base}{path}")

    # --------------------------------------------------------------- seeding
    async def create_publisher(self, name: str, domain: str = "") -> Dict[str, Any]:
        return await self._post("/publishers", {
            "name": name, "domain": domain or f"{name.lower().replace(' ', '')}.example.com",
            "status": "active", "preferred_currency": "USD",
        })

    async def create_ad_unit(self, publisher_id: str, name: str, ad_format: str,
                             width: int, height: int) -> Dict[str, Any]:
        return await self._post("/ad-units", {
            "publisher_id": publisher_id, "name": name,
            "format": ad_format, "type": ad_format if ad_format != "ctv" else "video",
            "zone_type": "vast", "width": width, "height": height, "status": "active",
        })

    async def create_advertiser(self, name: str, credit_limit: float = 0.0) -> Dict[str, Any]:
        # `credit_limit` is the advertiser's financial cap on the SUT (the only
        # editable financial field on create/update). The seeder sizes it to cover
        # the sum of the advertiser's campaign budgets.
        return await self._post("/advertisers", {
            "name": name, "status": "active",
            "domain": f"{name.lower().replace(' ', '')}.com",
            "credit_limit": round(float(credit_limit), 2),
        })

    async def credit_advertiser(self, advertiser_id: str, amount: float,
                                note: str = "seed: fund available balance") -> Dict[str, Any]:
        # The SUT computes available_balance = SUM(advertiser_ledger.amount); creation
        # seeds it to 0. Posting a credit_adjustment funds the advertiser so its
        # available balance equals its credit limit.
        return await self._post(f"/advertisers/{advertiser_id}/ledger", {
            "event_type": "credit_adjustment", "amount": round(float(amount), 2), "note": note,
        })

    async def advertiser_balance(self, advertiser_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._get(f"/advertisers/{advertiser_id}/balance")
        except AdServerError:
            return None

    async def create_demand_partner(self, name: str, ad_format: str, bid_floor: float,
                                    endpoint_url: str = "") -> Dict[str, Any]:
        return await self._post("/demand-partners", {
            "name": name, "type": "dsp", "status": "active",
            "endpoint_url": endpoint_url, "supported_formats": [ad_format],
            "bid_floor": bid_floor, "timeout_ms": 1000,
        })

    async def create_line_item(self, partner_id: str, name: str, ad_format: str,
                               floor_price: float, geo_targets: List[str],
                               device_targets: List[str]) -> Dict[str, Any]:
        return await self._post(f"/demand-partners/{partner_id}/line-items", {
            "name": name, "ad_format": ad_format, "floor_price": floor_price,
            "geo_targets": geo_targets, "device_targets": device_targets,
            "status": "active", "tag_type": "vast",
        })

    async def create_campaign(self, *, name: str, advertiser_id: str, budget: float,
                              daily_budget: float, cpm: float, ad_format: str,
                              start_date: str, end_date: str,
                              countries: List[str], devices: List[str]) -> Dict[str, Any]:
        """Create a serveable campaign via REST (create + decisioning-field shim).

        SERVER BUG worked around here: the create API persists `format_targets`,
        `cpm_bid`, `cached_spend_*`, but the auction (`decide_vast_ad`) reads
        `ad_format`, ranks by `target_cpm`, and gates on `spent`. We PUT the
        decisioning field names so the campaign is eligible — and report it.
        """
        created = await self._post("/campaigns", {
            "name": name, "advertiser_id": advertiser_id, "status": "active",
            "format_targets": [ad_format], "pricing_model": "cpm",
            "budget": budget, "budget_total": budget,
            "daily_budget": daily_budget, "budget_daily": daily_budget,
            "cpm_bid": cpm, "cpm_rate": cpm,
            "start_date": start_date, "end_date": end_date,
            "geo_targets": countries, "device_targets": devices,
            "targeting": {"countries": countries, "devices": devices},
        })
        cid = created.get("id")
        if not cid:
            return created
        try:
            patched = await self._put(f"/campaigns/{cid}", {
                "ad_format": ad_format, "target_cpm": cpm,
                "spent": 0.0, "daily_spent": 0.0,
            })
            return patched or created
        except AdServerError:
            return created

    async def create_creative(self, *, campaign_id: str, name: str, ad_format: str,
                              width: int, height: int) -> Dict[str, Any]:
        return await self._post("/creatives", {
            "campaign_id": campaign_id, "name": name,
            "format": ad_format, "type": ad_format if ad_format != "ctv" else "video",
            "file_url": f"https://cdn.example.com/sim/{new_id()}.mp4",
            "click_url": f"https://advertiser.example.com/landing?c={campaign_id}",
            "width": width, "height": height, "duration": "00:00:30",
            "status": "approved",
        })

    # --------------------------------------------------------------- serving
    def _classify_vast(self, vr: validators.VastResult, tag_id: str) -> str:
        if vr.ad_type in ("empty",):
            return "no_fill"
        if vr.ad_type in ("unparseable",):
            return "error"
        if not vr.filled:
            return "no_fill"
        # Filler heuristic for the SUT's default "Video Ad".
        title = (vr.ad_title or "").strip()
        media = (vr.media_files[0].get("url") if vr.media_files else "") or ""
        is_filler = (
            title in ("", "Video Ad")
            and (f"/creative/{tag_id}.mp4" in media or "voise.com" in (vr.clickthrough_url or ""))
        )
        return "filler" if is_filler else "real"

    async def request_vast(self, *, tag_id: str, publisher_id: str, device: str,
                           user_id: str, width: int = 640, height: int = 480,
                           country: Optional[str] = None,
                           privacy: Optional[Dict[str, Any]] = None,
                           cap: str = "vast_canonical",
                           follow_wrappers: bool = True) -> AdResult:
        params: Dict[str, Any] = {"pub": publisher_id, "w": width, "h": height, "ifa": user_id}
        if device in ("ctv", "tv"):
            params["devicetype"] = 3
        if country:
            params["country"] = country
        if privacy:  # send privacy signals on the serving path (S12) even if SUT drops them
            for k in ("gdpr", "gdpr_consent", "us_privacy", "gpp", "gpp_sid"):
                if privacy.get(k) is not None:
                    params[k] = privacy[k]
        t0 = time.perf_counter()
        try:
            r = await self._client.get(self._url(cap, tag_id=tag_id), params=params)
        except httpx.HTTPError as e:
            return AdResult(protocol="vast", status_code=0,
                            latency_ms=(time.perf_counter() - t0) * 1000,
                            filled=False, classification="error",
                            no_fill_reason=f"transport_error:{type(e).__name__}")
        latency = (time.perf_counter() - t0) * 1000
        endpoint = self.routes.get(cap, "")
        vr = validators.validate_vast(r.text, endpoint=endpoint)

        if r.status_code == 0 or r.status_code >= 500:
            classification = "error"
        else:
            classification = self._classify_vast(vr, tag_id)

        # Recursive Wrapper following (VASTAdTagURI), accumulating tracking.
        depth = 0
        if follow_wrappers and vr.ad_type == "wrapper" and vr.wrapper_uri:
            inner, depth = await self._follow_wrappers(vr, endpoint)
            if inner is not None:
                # merge child impressions/tracking into the parent view
                vr.impression_urls += inner.impression_urls
                for ev, urls in inner.tracking_events.items():
                    vr.tracking_events.setdefault(ev, []).extend(urls)
                vr.click_tracking_urls += inner.click_tracking_urls
                vr.media_files += inner.media_files
                if inner.clickthrough_url and not vr.clickthrough_url:
                    vr.clickthrough_url = inner.clickthrough_url
                vr.findings += inner.findings
                if inner.ad_type == "inline":
                    classification = self._classify_vast(inner, tag_id)

        real_fill = classification == "real"
        flat_events = [u for urls in vr.tracking_events.values() for u in urls]
        click_urls = ([vr.clickthrough_url] if vr.clickthrough_url else []) + vr.click_tracking_urls
        return AdResult(
            protocol="vast", status_code=r.status_code, latency_ms=latency,
            filled=real_fill, classification=classification,
            campaign=None if classification == "filler" else vr.ad_title,
            creative_id=vr.ad_id,
            impression_urls=vr.impression_urls, click_urls=click_urls,
            event_urls=flat_events, tracking_events=vr.tracking_events,
            error_urls=vr.error_urls, media_urls=[m["url"] for m in vr.media_files if m.get("url")],
            ad_type=vr.ad_type, vast_version=vr.version, has_omid=vr.has_omid, wrapper_depth=depth,
            findings=[f.to_dict() for f in vr.findings],
            no_fill_reason=None if real_fill else (classification if classification != "real" else None),
            trace_id=r.headers.get("X-Request-Id") or r.headers.get("x-request-id"),
            raw=r.text[:2000],
        )

    async def _follow_wrappers(self, vr: validators.VastResult, endpoint: str):
        """Resolve VASTAdTagURI chain until InLine / depth cap / loop. Returns (inner, depth)."""
        visited = set()
        uri = vr.wrapper_uri
        depth = 0
        last: Optional[validators.VastResult] = None
        while uri and depth < WRAPPER_MAX_DEPTH:
            sub, _, note = tracking.normalize_url(uri, self.s)
            if note:
                self.url_rewrite_notes[note] = self.url_rewrite_notes.get(note, 0) + 1
            if sub in visited:
                vr.findings.append(validators.Finding(
                    standard=validators.VAST, spec_section="VAST §3.3.1", check="wrapper_loop",
                    severity=validators.FAIL, expected="no redirect loop in wrapper chain",
                    observed=f"loop detected at {sub}", endpoint=endpoint))
                break
            visited.add(sub)
            depth += 1
            try:
                r = await self._client.get(sub)
            except httpx.HTTPError as e:
                vr.findings.append(validators.Finding(
                    standard=validators.VAST, spec_section="VAST §3.3.1", check="wrapper_fetch",
                    severity=validators.FAIL, expected="VASTAdTagURI resolves",
                    observed=f"fetch error: {type(e).__name__}", endpoint=sub))
                break
            inner = validators.validate_vast(r.text, endpoint=sub)
            last = inner
            if inner.ad_type == "wrapper" and inner.wrapper_uri:
                uri = inner.wrapper_uri
                continue
            break
        if depth >= WRAPPER_MAX_DEPTH and last is not None and last.ad_type == "wrapper":
            vr.findings.append(validators.Finding(
                standard=validators.VAST, spec_section="VAST §3.3.1", check="wrapper_depth",
                severity=validators.WARN, expected=f"wrapper chain resolves within {WRAPPER_MAX_DEPTH} hops",
                observed=f"still a wrapper at depth {depth}", endpoint=endpoint))
        return last, depth

    async def request_ortb(self, *, tag_id: str, publisher_id: str, country: str,
                           device: str, browser: str, user_id: str,
                           width: int = 1920, height: int = 1080,
                           ad_format: str = "video", bidfloor: float = 5.775,
                           privacy: Optional[Dict[str, Any]] = None,
                           pod: Optional[Dict[str, Any]] = None,
                           app_mode: bool = False, ifa: Optional[str] = None) -> AdResult:
        req_id = new_id("bid-")
        privacy = privacy or {}
        body = ortb_mod.build_bid_request(
            request_id=req_id, tag_id=tag_id, publisher_id=publisher_id,
            country=country, device=device, browser=browser, user_id=user_id,
            width=width, height=height, ad_format=ad_format, bidfloor=bidfloor,
            app_mode=app_mode, ifa=ifa,
            gdpr=privacy.get("gdpr"), consent=privacy.get("consent") or privacy.get("gdpr_consent"),
            us_privacy=privacy.get("us_privacy"), gpp=privacy.get("gpp"),
            gpp_sid=privacy.get("gpp_sid"), coppa=privacy.get("coppa"), pod=pod,
        )
        return await self._dispatch_ortb(tag_id=tag_id, publisher_id=publisher_id,
                                         body=body, req_id=req_id)

    async def _dispatch_ortb(self, *, tag_id: str, publisher_id: str,
                             body: Dict[str, Any], req_id: str) -> AdResult:
        """POST a prebuilt OpenRTB bid request, validate the response, normalise to AdResult."""
        endpoint = self.routes.get("ortb_auction", "")
        t0 = time.perf_counter()
        try:
            r = await self._client.post(self._url("ortb_auction", tag_id=tag_id),
                                        params={"pub": publisher_id}, json=body)
        except httpx.HTTPError as e:
            return AdResult(protocol="ortb", status_code=0,
                            latency_ms=(time.perf_counter() - t0) * 1000,
                            filled=False, classification="error",
                            no_fill_reason=f"transport_error:{type(e).__name__}", trace_id=req_id)
        latency = (time.perf_counter() - t0) * 1000
        payload: Any = None
        if r.content:
            try:
                payload = r.json()
            except ValueError:
                payload = None
        parsed = ortb_mod.parse_bid_response(r.status_code, payload)
        vresult = validators.validate_bid_response(r.status_code, payload, request=body, endpoint=endpoint)
        win_urls = [u for u in (parsed.get("nurl"), parsed.get("burl")) if u]
        if r.status_code == 0 or r.status_code >= 500:
            classification = "error"
        elif parsed["filled"]:
            classification = "real"
        else:
            classification = "no_fill"
        return AdResult(
            protocol="ortb", status_code=r.status_code, latency_ms=latency,
            filled=parsed["filled"], classification=classification,
            campaign_id=parsed["campaign_id"], creative_id=parsed["creative_id"],
            price=parsed["price"], win_urls=win_urls,
            findings=[f.to_dict() for f in vresult.findings],
            no_fill_reason=parsed["no_fill_reason"], trace_id=req_id,
            adm=parsed.get("adm"),
            raw=(r.text[:2000] if r.content else ""),
        )

    async def request_ortb_custom(self, *, tag_id: str, publisher_id: str,
                                  body: Dict[str, Any]) -> AdResult:
        """Send a caller-supplied OpenRTB bid request verbatim (e.g. a real publisher
        sample pasted into the UI), validated into the same AdResult shape."""
        req_id = str(body.get("id") or new_id("bid-"))
        return await self._dispatch_ortb(tag_id=tag_id, publisher_id=publisher_id,
                                         body=body, req_id=req_id)

    # -------------------------------------------------------------- tracking
    async def fire(self, url: str, normalize: bool = True, *, errorcode: Optional[int] = None,
                   playhead: str = "00:00:00") -> Dict[str, Any]:
        """GET a tracking URL like a real player would: substitute macros, rewrite
        host/prefix, fire. Never raises. Returns status/ok/final url/note."""
        final, rewritten, note = (url, False, None)
        if normalize:
            final, rewritten, note = tracking.normalize_url(url, self.s)
            if rewritten and note:
                self.url_rewrite_notes[note] = self.url_rewrite_notes.get(note, 0) + 1
        final, replaced, _unresolved = tracking.substitute_macros(final, errorcode=errorcode, playhead=playhead)
        for m in replaced:
            self.macro_counts[m] = self.macro_counts.get(m, 0) + 1
        try:
            r = await self._client.get(final)
            ok = 200 <= r.status_code < 400
            return {"ok": ok, "status_code": r.status_code, "url": final, "note": note,
                    "macros": replaced}
        except httpx.HTTPError as e:
            return {"ok": False, "status_code": 0, "url": final,
                    "note": f"transport_error:{type(e).__name__}", "macros": replaced}

    async def fire_quartiles(self, result: AdResult) -> List[Dict[str, Any]]:
        """Fire start -> firstQuartile -> midpoint -> thirdQuartile -> complete IN ORDER,
        using whatever quartile <Tracking> URLs the VAST carried. Returns per-event fires."""
        from app.adserver.macros import QUARTILE_PLAYHEAD
        out: List[Dict[str, Any]] = []
        for ev in ("start", "firstQuartile", "midpoint", "thirdQuartile", "complete"):
            for url in result.tracking_events.get(ev, []):
                fired = await self.fire(url, playhead=QUARTILE_PLAYHEAD.get(ev, "00:00:00"))
                out.append({"event": ev, **fired})
        return out

    # ------------------------------------------------------- supply chain
    async def fetch_supply_files(self) -> Dict[str, Any]:
        """Fetch + validate ads.txt / app-ads.txt / sellers.json (best-effort)."""
        from app.adserver import supplychain
        out: Dict[str, Any] = {"findings": []}
        ads = await self._safe_text(self.routes.get("ads_txt", "/ads.txt"))
        appads = await self._safe_text(self.routes.get("app_ads_txt", "/app-ads.txt"))
        sellers = await self._safe_json(self.routes.get("sellers_json", "/sellers.json"))

        ads_ids: List[str] = []
        if ads is not None:
            v = supplychain.validate_ads_txt(ads, endpoint=self.routes.get("ads_txt", "/ads.txt"))
            out["ads_txt"] = {"records": len(v["records"]), "seller_ids": v["seller_ids"]}
            out["findings"] += v["findings"]
            ads_ids = v["seller_ids"]
        else:
            out["ads_txt"] = {"error": "unreachable"}
        if appads is not None:
            v = supplychain.validate_ads_txt(appads, endpoint=self.routes.get("app_ads_txt", "/app-ads.txt"), app=True)
            out["app_ads_txt"] = {"records": len(v["records"])}
            out["findings"] += v["findings"]
        if sellers is not None:
            v = supplychain.validate_sellers_json(sellers, endpoint=self.routes.get("sellers_json", "/sellers.json"),
                                                  ads_txt_seller_ids=ads_ids)
            out["sellers_json"] = {"sellers": len(v["seller_ids"])}
            out["findings"] += v["findings"]
        else:
            out["sellers_json"] = {"error": "unreachable"}
        return out

    async def _safe_text(self, path: str) -> Optional[str]:
        try:
            r = await self.get_root(path)
            return r.text if r.status_code == 200 else None
        except httpx.HTTPError:
            return None

    async def _safe_json(self, path: str) -> Optional[Any]:
        try:
            r = await self.get_root(path)
            return r.json() if r.status_code == 200 and r.content else None
        except (httpx.HTTPError, ValueError):
            return None

    # ------------------------------------------------------------- reporting
    async def get_campaign(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._get(f"/campaigns/{campaign_id}")
        except AdServerError:
            return None

    async def campaign_stats(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._get(f"/campaigns/{campaign_id}/stats")
        except AdServerError:
            return None

    async def campaign_spend(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._get(f"/campaigns/{campaign_id}/spend")
        except AdServerError:
            return None

    async def delete_campaign(self, campaign_id: str) -> None:
        try:
            await self._send("DELETE", f"/campaigns/{campaign_id}")
        except AdServerError:
            pass

    async def list_campaigns(self) -> List[Dict[str, Any]]:
        try:
            data = await self._get("/campaigns", params={"limit": 200})
            if isinstance(data, dict):
                return data.get("campaigns") or data.get("items") or data.get("data") or []
            return data or []
        except AdServerError:
            return []
