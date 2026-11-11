"""Spec 038 — the sidecar→gateway HTTP client (research R5): the 035-R5
endpoint shapes with honest envelopes on every path — outage, malformed
upstream, clean — never parsed console soup, never a fabricated verdict."""

from __future__ import annotations

import json

import httpx

from .neverlist import scan

# spec 038 R5: the recovery text named in every unavailable envelope
RECOVERY_TEXT = "start the Scheduled Task: schtasks /run /tn task-gateway-service"




class TaskGatewayClient:
    def __init__(self, base_url: str, connect_timeout_s: float = 5.0,
                 read_timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        # tests inject a mock transport via client._client
        # NOTE: no base_url here — tests inject MockTransport clients that
        # serve relative paths; production joins via _full()
        self._client = httpx.Client(
            timeout=httpx.Timeout(read_timeout_s,
                                   connect=connect_timeout_s))

    # -- envelopes --------------------------------------------------------

    def _unavailable(self, exc: Exception) -> dict:
        return {"status": "error",
                "reason": (f"error:task-gateway-unavailable — the task-gateway "
                           f"service at {self.base_url} is unreachable "
                           f"({exc.__class__.__name__}); recover with "
                           f"{RECOVERY_TEXT}")}

    @staticmethod
    def _malformed(exc: Exception, which: str) -> dict:
        return {"status": "error",
                "reason": (f"error:task-gateway-malformed-response — the "
                           f"{which} response was not the structured JSON "
                           f"the contract promises ({exc}); no verdict is "
                           f"fabricated from upstream noise")}

    def _call(self, method: str, path: str, payload: dict | None,
              which: str, cid: str) -> dict:
        """One request → honest envelope. JSON-only: a non-JSON body or an
        unknown recommendation value is malformed, never content (FR-009)."""
        try:
            url = self.base_url + path
            r = (self._client.post(url, json=payload)
                 if method == "POST" else self._client.get(url))
        except httpx.HTTPError as exc:
            return self._unavailable(exc)
        if r.status_code == 404:
            return {"status": "error",
                    "reason": f"error:not-found — {which}: {r.text[:200]}"}
        try:
            body = r.json()
        except (json.JSONDecodeError, ValueError) as exc:
            return self._malformed(exc, which)
        if not isinstance(body, dict):
            return self._malformed(ValueError("non-object body"), which)
        return body

    # -- the four endpoint shapes (contracts) -----------------------------

    def tier1(self, issue_type: str, issue_text: str, cid: str) -> dict:
        out = self._call("POST", "/api/helpdesk/tier1",
                        {"issue_type": issue_type, "issue_text": issue_text},
                        "tier-1", cid)
        if out.get("status") == "error":
            return out
        rec = out.get("recommendation")
        if rec not in ("none", "tier2"):
            return self._malformed(
                ValueError(f"recommendation {rec!r} not in none|tier2"),
                "tier-1")
        return {"status": "ok", **out}

    def tier2(self, issue_type: str, cid: str) -> dict:
        return self._call("POST", "/api/helpdesk/tier2",
                          {"issue_type": issue_type}, "tier-2", cid)

    def install(self, version: str, channel: str, cid: str) -> dict:
        return self._call("POST", "/api/office/install",
                          {"version": version, "channel": channel},
                          "office-install", cid)

    def job_status(self, job_id: str, cid: str) -> dict:
        out = self._call("GET", f"/api/helpdesk/job/{job_id}",
                         None, f"job {job_id}", cid)
        if out.get("status") == "error":
            return out
        return {"status": "ok", "job": out}

    def healthz(self) -> dict:
        return self._call("GET", "/api/healthz", None, "healthz", "probe")


__all__ = ["RECOVERY_TEXT", "TaskGatewayClient", "scan"]