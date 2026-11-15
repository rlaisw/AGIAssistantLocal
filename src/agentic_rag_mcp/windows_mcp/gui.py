"""Spec 041 — the tier-4 GUI gate (FR-006): the click/type sequence runs
ONLY after a plain-word confirmation naming each control and its effect.

Contracts (the four honest stop conditions, all audited):
- credential/password fields are refused BEFORE any service call — the
  typed value never reaches the audit row (the sensitive rule);
- an elevation (UAC / secure-desktop) barrier stops the sequence with
  the completed steps named — never a success claim for the rest;
- a dialog beyond the described sequence stops and re-confirms;
- a never-list action inside a dialog is refused exactly like a typed
  command (the shared never-list binds here too).
Day-one scope: the safe starter set (uninstall, power options, display,
sound, date/time) — enforced by the routing layer, not here."""

from __future__ import annotations

import re

from ..task_gateway.neverlist import scan as _neverlist_scan
from .client import call_tool

_CREDENTIAL_RE = re.compile(
    r"password|credential|passphrase|\bpin\b|otp|2fa|secret", re.IGNORECASE)
_VALID_ACTIONS = {"click", "type", "wait"}


class GuiState:
    """The conversation-scoped pending-sequence store (mirrors the
    tier-3 PowerShell draft store: what was confirmed is structurally
    what runs — a confirm carries no step text)."""

    _pending: dict[str, list] = {}  # noqa: RUF012

    def set_pending(self, conversation_id: str, steps: list) -> None:
        self._pending[conversation_id] = steps

    def pending(self, conversation_id: str) -> list | None:
        return self._pending.get(conversation_id)

    def clear(self, conversation_id: str) -> None:
        self._pending.pop(conversation_id, None)


def _validate_steps(steps: list,
                    description: str = "") -> tuple[bool, str | None, list | None]:
    """Shape + gate validation BEFORE any store write or call: actions
    bounded, credential fields refused pre-call (the value never enters
    any record), the never-list scans the plain words of every step."""
    if not isinstance(steps, list) or not steps:
        return False, "rejected: a sequence needs at least one step", None
    clean = []
    for step in steps:
        if not isinstance(step, dict):
            return False, "rejected: each step is an object", None
        action = str(step.get("action", "")).lower()
        if action not in _VALID_ACTIONS:
            return False, (f"rejected: unknown action {action!r} "
                           f"(allowed: click, type, wait)"), None
        if action in ("click", "type") and not step.get("target"):
            return False, "rejected: click/type steps need a target", None
        if action == "type" and not step.get("value"):
            return False, "rejected: type steps need a value", None
        if action == "type" and _CREDENTIAL_RE.search(str(step.get("target", ""))):
            return False, ("blocked: a credential/password field is never "
                           "typed by automation — enter secrets by hand; "
                           "nothing was sent to the machine"), None
        never = _neverlist_scan(
            f"{step.get('target', '')} {step.get('expect', '')} {description}")
        if never:
            return False, never, None
        clean.append({"action": action, "target": step.get("target"),
                      "value": step.get("value"),
                      "expect": step.get("expect")})
    return True, None, clean


def _sequence_text(steps: list, description: str) -> str:
    parts = []
    for i, step in enumerate(steps, 1):
        base = (f"{i}. click {step['target']}"
                if step["action"] == "click"
                else (f"{i}. type into {step['target']}"
                      if step["action"] == "type"
                      else f"{i}. wait {step.get('value')} seconds"))
        if step.get("expect"):
            base += f" (expect: {step['expect']})"
        parts.append(base)
    return (f"I will {'; then '.join(parts)} — for: {description}. "
            f"Reply yes to run this exactly, or describe a change.")


def draft_sequence(steps: list, description: str, conversation_id: str,
                   audit=None) -> dict:
    """Draft the sequence for a plain-word confirmation. The stored steps
    are what run; the draft text is what the owner sees."""
    ok, reason, clean = _validate_steps(steps, description or "")
    if not ok:
        if audit and reason.startswith("blocked"):
            audit.write_attempt(decision="blocked",
                                operation="windows-mcp-gui",
                                normalized_path=None, allowed_root="",
                                reason=reason,
                                conversation_id=conversation_id,
                                duration_s=0.0)
        return {"status": "blocked", "reason": reason}
    text = _sequence_text(clean, description or "the requested flow")
    GuiState().set_pending(conversation_id, clean)
    return {"status": "pending-confirmation", "sequence_text": text}


async def confirm_sequence(conversation_id: str,
                           conversation_id2: str | None = None) -> dict:
    """Execute the STORED sequence step by step (a confirm carries no
    step text). Every stop condition is honest and names the completed
    steps; per-step outcomes are audited by the underlying calls."""
    cid = conversation_id2 or conversation_id
    steps = GuiState().pending(conversation_id)
    if steps is None:
        return {"status": "blocked",
                "reason": "no pending sequence for this conversation — "
                          "draft it first and confirm after reading it"}
    completed = 0
    for step in steps:
        action = step["action"]
        if action == "click":
            out = await call_tool("Click",
                                 {"label": step["target"], "clicks": 1},
                                 cid, audit=None)
        elif action == "type":
            out = await call_tool("Type",
                                 {"text": step["value"],
                                  "label": step["target"]},
                                 cid, audit=None)
        else:
            out = await call_tool("Wait", {"duration": step["value"]},
                                  cid, audit=None)
        if out.get("status") != "ok":
            reason = out.get("reason", "")
            low = reason.lower()
            if "secure desktop" in low or "user_control" in low:
                # elevation (UAC) or desktop-deferral barrier: stop honestly
                GuiState().clear(conversation_id)
                if "user_control" in low or "deferred" in low:
                    return {"status": "blocked", "completed_steps": completed,
                            "reason": ("blocked: the Windows-MCP service "
                                       "deferred the call while the desktop "
                                       "user is active — the sequence stopped "
                                       f"after {completed} step(s); ask "
                                       "again in a few seconds")}
                return {"status": "blocked", "completed_steps": completed,
                        "reason": ("blocked: an elevation (UAC) prompt or "
                                   "secure-desktop barrier appeared — the "
                                   "sequence stopped after "
                                   f"{completed} step(s); approve the prompt "
                                   "by hand and ask again, or cancel")}
            GuiState().clear(conversation_id)
            return {"status": "blocked", "completed_steps": completed,
                    "reason": reason}
        if step.get("expect"):
            snap = await call_tool("Snapshot", {"use_dom": True},
                                   cid, audit=None)
            if snap.get("status") == "ok" and \
                    str(step["expect"]) not in (snap.get("text") or ""):
                # a dialog/state beyond the described sequence: stop and
                # re-confirm (the cascade rule)
                GuiState().clear(conversation_id)
                excerpt = (snap.get("text") or "")[:150]
                return {"status": "blocked", "completed_steps": completed,
                        "reason": ("blocked: an unexpected dialog/state "
                                   f"appeared beyond the described sequence "
                                   f"('{excerpt}') — stop and re-confirm "
                                   "before continuing")}
        completed += 1
    GuiState().clear(conversation_id)
    return {"status": "ok", "completed_steps": completed}
