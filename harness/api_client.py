"""Live driver over the Resonate backend API.

Auth: X-Dev-User-Email against a NON-PROD backend. A prod hostname is refused
unless an explicit bearer token is supplied.

Schemas below match the running backend's /openapi.json (verified 2026-05-30).
"""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass

from .schemas import SimResult

_PROD_HOSTS = ("resonate-hq.vercel.app",)
_TRANSIENT = {408, 429, 500, 502, 503, 504}

# Harness channel → backend output_family (matches the platform's own
# draftOutputFamilyForChannel; values must satisfy the messages.output_family check).
OUTPUT_FAMILY = {
    "email": "direct_voter_outreach", "sms": "direct_voter_outreach",
    "mail": "press_release", "speech": "press_release",
    "radio": "paid_ad", "tv": "paid_ad", "social": "social_post",
}

# UI channel → backend channel path segment. The backend calls speeches "press".
# Valid backend channels: canvass, email, mail, press, radio, sms, social, tv.
CHANNEL_PATH = {"speech": "press", "speeches / docs": "press", "docs": "press"}


def _channel(ch: str) -> str:
    return CHANNEL_PATH.get((ch or "").strip().lower(), (ch or "").strip().lower())


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status, self.body = status, body


@dataclass
class ResonateClient:
    base_url: str = "http://localhost:8000"
    dev_email: str = "harness-operator@example.com"
    bearer_token: str = ""
    timeout: float = 180.0

    def __post_init__(self) -> None:
        if any(h in self.base_url for h in _PROD_HOSTS) and not self.bearer_token:
            raise RuntimeError(
                "Refusing to drive a production host with dev-auth. Point at a test/staging "
                "backend, or set RESONATE_BEARER_TOKEN for an intentional prod target."
            )

    def _client(self):
        import httpx

        headers = {"X-Dev-User-Email": self.dev_email}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=self.timeout)

    async def _req(self, method: str, path: str, *, json_body=None, attempts: int = 3):
        import httpx

        last: Exception | None = None
        for i in range(attempts):
            try:
                async with self._client() as c:
                    r = await c.request(method, path, json=json_body)
                if r.status_code in _TRANSIENT and i < attempts - 1:
                    await asyncio.sleep(0.4 * (i + 1))
                    continue
                if r.status_code >= 400:
                    raise ApiError(r.status_code, r.text)
                return r.json() if r.content else {}
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                await asyncio.sleep(0.4 * (i + 1))
        raise last or RuntimeError("request failed")

    @staticmethod
    def _find_id(obj) -> str | None:
        if isinstance(obj, list):
            return ResonateClient._find_id(obj[0]) if obj else None
        if isinstance(obj, dict):
            for k in ("id", "organization_id", "org_id", "project_id"):
                if obj.get(k):
                    return str(obj[k])
        return None

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def health(self) -> dict:
        return await self._req("GET", "/health")

    async def bootstrap(self, org_name: str = "Harness Test Org") -> tuple[str, str]:
        """Resolve (or auto-provision) the org via dev-auth, create a throwaway
        sandbox project. Returns (org_id, project_id)."""
        org_id = None
        try:
            org_id = self._find_id(await self._req("GET", "/api/v1/orgs/me"))
        except ApiError:
            pass
        if not org_id:
            org_id = self._find_id(await self._req("POST", "/api/v1/orgs", json_body={"name": org_name}))
        if not org_id:
            raise RuntimeError("could not resolve org_id from /orgs")

        slug = f"harness-{secrets.token_hex(3)}"
        proj = await self._req(
            "POST", f"/api/v1/orgs/{org_id}/projects",
            json_body={"name": "Harness Sim Sandbox", "slug": slug, "project_type_key": "politics_playground"},
        )
        project_id = self._find_id(proj)
        if not project_id:
            raise RuntimeError(f"could not resolve project_id from {proj}")
        return org_id, project_id

    # ── language / drafting ──────────────────────────────────────────────────
    async def preflight(self, project_id: str, intent: str, channel: str,
                        output_family: str | None = None, max_questions: int = 5,
                        voice_mode: str = "light") -> dict:
        return await self._req(
            "POST", f"/api/v1/projects/{project_id}/language/preflight-questions",
            json_body={"intent": intent, "channel": _channel(channel),
                       "output_family": output_family or OUTPUT_FAMILY.get(channel, channel),
                       "max_questions": max_questions, "voice_mode": voice_mode},
        )

    async def draft_batch(self, project_id: str, channel: str, intent: str, *,
                         output_family: str | None = None, scope: str = "single",
                         segment_keys: list[str] | None = None, voice_mode: str = "light",
                         project_category: str = "*", verbatim_request: str | None = None) -> dict:
        body = {
            "intent": intent,
            "output_family": output_family or OUTPUT_FAMILY.get(channel, channel),
            "scope": scope,
            "segment_keys": segment_keys or [],
            "voice_mode": voice_mode,
            "project_category": project_category,
        }
        if verbatim_request:
            body["verbatim_request"] = verbatim_request
        return await self._req("POST", f"/api/v1/projects/{project_id}/language/draft-batch/{_channel(channel)}", json_body=body)

    async def draft_batch_stream(self, project_id: str, channel: str, intent: str, **kw):
        """SSE variant. Yields (event_type, data_dict). Terminal events: 'draft', 'error'."""
        import httpx

        body = {"intent": intent, "output_family": kw.get("output_family") or OUTPUT_FAMILY.get(channel, channel),
                "scope": kw.get("scope", "single"), "segment_keys": kw.get("segment_keys") or [],
                "voice_mode": kw.get("voice_mode", "light"), "project_category": kw.get("project_category", "*")}
        async with self._client() as c:
            async with c.stream("POST", f"/api/v1/projects/{project_id}/language/draft-batch/{_channel(channel)}/stream",
                                json=body) as r:
                if r.status_code >= 400:
                    raise ApiError(r.status_code, await r.aread() and (await r.aread()).decode("utf-8", "ignore"))
                event = None
                async for line in r.aiter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        try:
                            yield event or "message", json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            pass

    @staticmethod
    def to_sim_result(sim_id: str, channel: str, intent_type: str, brief_intent: str,
                     brief_context: str, draft_resp: dict, model: str = "", persona: str = "",
                     surface: str = "", preflight_qa: list | None = None) -> SimResult:
        """Build a SimResult from a draft-batch response's first draft."""
        drafts = draft_resp.get("drafts") or []
        d = drafts[0] if drafts else {}
        return SimResult(
            id=sim_id, channel=channel, intent_type=intent_type, model=model, persona=persona,
            surface=surface, preflight_qa=preflight_qa or [],
            content_text=d.get("content_text", ""), subject=d.get("subject"),
            brief_intent=brief_intent, brief_context=brief_context,
            refused=bool(d.get("refused", False)),
            advisory_flags=list(d.get("advisory_flags") or []),
            stance_drift_score=d.get("stance_drift_score"),
            stance_drift_method=d.get("stance_drift_method"),
            messenger_recommendation=list(d.get("messenger_recommendation") or []),
        )
