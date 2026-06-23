"""HTTP client for the target ad server.

Responsibilities:
  * auth bootstrap (login, with open-registration fallback for local dev)
  * entity creation for seeding (publishers, ad units, advertisers, DSPs,
    line items, campaigns, creatives)
  * ad requests over VAST and OpenRTB, returning a normalised AdResult
  * firing tracking pixels (impression / click / event / win)
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
from app.adserver.result import AdResult
from app.adserver.vast import parse_vast
from app.config import Settings
from app.util import new_id

logger = logging.getLogger("adsim.client")


class AdServerError(RuntimeError):
    pass


class AdServerClient:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.token: Optional[str] = None
        self.user: Dict[str, Any] = {}
        self._client = httpx.AsyncClient(
            timeout=settings.http_timeout,
            verify=settings.verify_tls,
            follow_redirects=False,
        )
        # rewrites observed while normalising embedded tracking URLs (findings)
        self.url_rewrite_notes: Dict[str, int] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AdServerClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ auth
    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def ping(self) -> bool:
        try:
            r = await self._client.get(f"{self.s.api_base}/ping")
            return r.status_code == 200
        except httpx.HTTPError:
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
        # Someone may have registered between our login and register attempts.
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
        """Issue a request, retrying once on transport errors.

        The ad server resets the keep-alive connection after a 500 (e.g. the
        publisher-insert bug), which surfaces as a ReadError on the NEXT request
        that reuses the socket. A single retry picks up a fresh connection.
        """
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

    async def create_advertiser(self, name: str) -> Dict[str, Any]:
        return await self._post("/advertisers", {
            "name": name, "status": "active",
            "domain": f"{name.lower().replace(' ', '')}.com",
        })

    async def create_demand_partner(self, name: str, ad_format: str, bid_floor: float) -> Dict[str, Any]:
        return await self._post("/demand-partners", {
            "name": name, "type": "dsp", "status": "active",
            "endpoint_url": "", "supported_formats": [ad_format],
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
        """Create a serveable campaign via REST (create + decisioning shim).

        SERVER BUG worked around here: the create API persists `format_targets`,
        `cpm_bid`, `cached_spend_*`, but the internal auction (`decide_vast_ad`)
        queries `ad_format`, ranks by `target_cpm`, and gates on `spent`/
        `daily_spent`. A freshly created campaign therefore matches NO decisioning
        query (verified: `decisioning match count: 0`). `update_campaign` does a
        raw `$set`, so we PUT the decisioning field names — over REST — to make
        the campaign eligible. We set spent=0 (correct initial state), never a
        value that pre-decides a scenario.
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
    async def request_vast(self, *, tag_id: str, publisher_id: str, device: str,
                           user_id: str, width: int = 640, height: int = 480) -> AdResult:
        params = {"pub": publisher_id, "w": width, "h": height, "ifa": user_id}
        if device in ("ctv", "tv"):
            params["devicetype"] = 3
        t0 = time.perf_counter()
        try:
            r = await self._client.get(f"{self.s.api_base}/v/{tag_id}", params=params)
        except httpx.HTTPError as e:
            return AdResult(protocol="vast", status_code=0,
                            latency_ms=(time.perf_counter() - t0) * 1000,
                            filled=False, no_fill_reason=f"transport_error:{type(e).__name__}")
        latency = (time.perf_counter() - t0) * 1000
        parsed = parse_vast(r.text)
        # `decide_vast_ad` ALWAYS returns a VAST; when no real campaign is selected
        # it emits a default "Video Ad" filler (AdTitle="Video Ad", Ad id=tag_id).
        # Treat that as a no-fill in campaign terms so fill-rate/win-distribution
        # reflect REAL campaign serving, not the filler.
        is_filler = parsed["filled"] and (
            parsed["campaign"] in (None, "Video Ad")
            and (not parsed["creative_id"] or parsed["creative_id"] == str(tag_id))
        )
        real_fill = parsed["filled"] and not is_filler
        no_fill = parsed["no_fill_reason"] or r.headers.get("X-No-Fill-Reason")
        if is_filler:
            no_fill = "default_filler_no_campaign"
        return AdResult(
            protocol="vast", status_code=r.status_code, latency_ms=latency,
            filled=real_fill, campaign=None if is_filler else parsed["campaign"],
            creative_id=parsed["creative_id"], impression_urls=parsed["impression_urls"],
            click_urls=([parsed["clickthrough_url"]] if parsed["clickthrough_url"] else [])
                       + parsed["click_tracking_urls"],
            event_urls=parsed["tracking_event_urls"],
            no_fill_reason=None if real_fill else no_fill,
            trace_id=r.headers.get("X-Request-Id"),
            raw=r.text[:2000],
        )

    async def request_ortb(self, *, tag_id: str, publisher_id: str, country: str,
                           device: str, browser: str, user_id: str,
                           width: int = 640, height: int = 480,
                           ad_format: str = "video") -> AdResult:
        req_id = new_id("bid-")
        body = ortb_mod.build_bid_request(
            request_id=req_id, tag_id=tag_id, publisher_id=publisher_id,
            country=country, device=device, browser=browser, user_id=user_id,
            width=width, height=height, ad_format=ad_format,
        )
        t0 = time.perf_counter()
        try:
            r = await self._client.post(f"{self.s.api_base}/b/{tag_id}",
                                        params={"pub": publisher_id}, json=body)
        except httpx.HTTPError as e:
            return AdResult(protocol="ortb", status_code=0,
                            latency_ms=(time.perf_counter() - t0) * 1000,
                            filled=False, no_fill_reason=f"transport_error:{type(e).__name__}",
                            trace_id=req_id)
        latency = (time.perf_counter() - t0) * 1000
        payload: Any = None
        if r.content:
            try:
                payload = r.json()
            except ValueError:
                payload = None
        parsed = ortb_mod.parse_bid_response(r.status_code, payload)
        win_urls = [u for u in (parsed.get("nurl"), parsed.get("burl")) if u]
        return AdResult(
            protocol="ortb", status_code=r.status_code, latency_ms=latency,
            filled=parsed["filled"], campaign_id=parsed["campaign_id"],
            creative_id=parsed["creative_id"], price=parsed["price"],
            win_urls=win_urls, no_fill_reason=parsed["no_fill_reason"],
            trace_id=req_id, raw=(r.text[:2000] if r.content else ""),
        )

    # -------------------------------------------------------------- tracking
    async def fire(self, url: str, normalize: bool = True) -> Dict[str, Any]:
        """GET a tracking URL. Never raises. Returns status/ok/final url/note."""
        final, rewritten, note = (url, False, None)
        if normalize:
            final, rewritten, note = tracking.normalize_url(url, self.s)
            if rewritten and note:
                self.url_rewrite_notes[note] = self.url_rewrite_notes.get(note, 0) + 1
        try:
            r = await self._client.get(final)
            # 2xx and 3xx (click endpoints answer 302) both count as recorded.
            ok = 200 <= r.status_code < 400
            return {"ok": ok, "status_code": r.status_code, "url": final, "note": note}
        except httpx.HTTPError as e:
            return {"ok": False, "status_code": 0, "url": final, "note": f"transport_error:{type(e).__name__}"}

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
        """Soft-delete (status->completed). Best-effort; used by scenarios to clean
        up the campaigns they create so they don't accumulate / ratchet CPMs."""
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
