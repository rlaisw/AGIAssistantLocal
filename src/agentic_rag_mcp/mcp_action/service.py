"""Draft, consent, and serialized execution for reviewed MCP-Action proposals."""

from __future__ import annotations

import asyncio
import time

from ..office_lanes.proxy import OfficeProxy
from ..windows_mcp.client import CapturedImage, call_tool
from ..windows_mcp.open import open_settings
from .actions import parse_marked_json
from .screenshots import get_screenshot_store
from .state import ProposalStore

_OFFER = "Do you want me to do it automatically for you?"
_EXPIRES_IN_S = 900
_ACTION_PARAMETERS = {
    "windows_default_printer": frozenset({"printer"}),
    "word_printer_duplex": frozenset({"printer", "orientation"}),
}
_INTERNAL_ERROR = "Internal MCP-Action error; no automatic action was performed."
_EXECUTION_ERROR = (
    "The reviewed action failed; the mutation outcome is unknown and was not retried."
)
_DEFAULT_PRINTER = "windows_default_printer"
_WORD_DUPLEX = "word_printer_duplex"
_TOTAL_BUDGET_S = 240.0
_DEFAULT_ACTION_BUDGET_S = 60.0
_WORD_ACTION_BUDGET_S = 90.0
_DISPLAY_STATUSES = frozenset(
    {"displayed", "partial", "unverified", "attempted-but-failed", "skipped"}
)
_SCREENSHOT_STATUSES = frozenset(
    {"captured", "attempted-but-failed", "skipped-display-unverified", "skipped"}
)
_FOREGROUND_RECT_SCRIPT = r"""
Add-Type -AssemblyName UIAutomationClient
$focused = [System.Windows.Automation.AutomationElement]::FocusedElement
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
$window = $focused
while ($window -and
    $window.Current.ControlType -ne [System.Windows.Automation.ControlType]::Window) {
    $window = $walker.GetParent($window)
}
if ($window) {
    $rect = $window.Current.BoundingRectangle
    $region = @(
        [int]$rect.X,
        [int]$rect.Y,
        [int]($rect.X + $rect.Width),
        [int]($rect.Y + $rect.Height)
    )
    $json = @{ region = $region } | ConvertTo-Json -Compress
    Write-Output ('MCP_ACTION_JSON:' +
        [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
}
"""
_ACTION_RESULT_KEYS = (
    "changed",
    "before",
    "after",
    "verification",
    "caveats",
    "match_count",
    "managed_default",
    "printer",
    "orientation",
    "requested_duplex",
    "reason",
)
_WORD_DISPLAY_KEYS = (
    "preview_ok",
    "view_type",
    "visible",
    "foreground",
    "blank_created",
    "document_count",
    "count_ok",
    "saved_ok",
    "documents_preserved",
)


def _word_display_envelope(value) -> dict:
    """Map Office evidence without relaying proxy text or document metadata."""
    if not isinstance(value, dict):
        status = "attempted-but-failed"
        evidence = {}
    else:
        evidence = {key: value[key] for key in _WORD_DISPLAY_KEYS if key in value}
        proxy_status = value.get("status")
        preview = value.get("preview_ok") is True
        foreground = value.get("foreground") is True
        preserved = value.get("documents_preserved") is True
        if proxy_status in _DISPLAY_STATUSES - {"partial"}:
            status = proxy_status
        elif proxy_status == "ok" and preview and foreground and preserved:
            status = "displayed"
        elif proxy_status in {"ok", "partial"} and preview and preserved:
            status = "partial"
        elif proxy_status in {"ok", "partial"}:
            status = "unverified"
        else:
            status = "attempted-but-failed"
    result = {"status": status, **evidence}
    if status == "partial":
        result["reason"] = "Word Print Preview could not be brought to the foreground."
    elif status == "unverified":
        result["reason"] = "Word Print Preview could not be verified."
    elif status == "attempted-but-failed":
        result["reason"] = "Word Print Preview could not be displayed safely."
    return result


class WindowsDisplay:
    """Open and independently verify only the reviewed printer Settings page."""

    def __init__(self, audit=None, office_proxy=None) -> None:
        self.audit = audit
        # Resolve lazily: constructing the display must not open an OfficeMCP session.
        self.office_proxy = office_proxy if office_proxy is not None else OfficeProxy

    async def show_default_printer(self, conversation_id: str) -> dict:
        try:
            opened = await open_settings("printers", conversation_id, self.audit)
            if not isinstance(opened, dict) or opened.get("status") != "ok":
                return {
                    "status": "attempted-but-failed",
                    "reason": "Windows printer settings could not be opened.",
                }
            verified = await call_tool(
                "WaitFor",
                {
                    "condition": "text",
                    "text": "Printers & scanners",
                    "window_name": "Settings",
                    "timeout": 30,
                    "interval": 0.5,
                    "use_dom": False,
                },
                conversation_id,
                self.audit,
            )
            text = verified.get("text", "") if isinstance(verified, dict) else ""
            if (
                not isinstance(verified, dict)
                or verified.get("status") != "ok"
                or "printers & scanners" not in text.casefold()
            ):
                return {
                    "status": "unverified",
                    "reason": "The Windows printer settings page could not be verified.",
                }
            return {"status": "displayed"}
        except Exception:  # noqa: BLE001 - never expose host or desktop details
            return {
                "status": "attempted-but-failed",
                "reason": "Windows printer settings could not be displayed.",
            }

    def show_word_print(self) -> dict:
        """Map bounded OfficeProxy evidence without exposing COM/transport text."""
        try:
            proxy = self.office_proxy
            if isinstance(proxy, type) or not hasattr(proxy, "show_word_print"):
                proxy = proxy()
            return _word_display_envelope(proxy.show_word_print())
        except Exception:  # noqa: BLE001 - COM/transport details stay out of chat/audit
            return _word_display_envelope(None)


class ScreenshotCapture:
    """Store one validated host image and return only its public evidence metadata."""

    def __init__(self, store=None, audit=None) -> None:
        self.store = store if store is not None else get_screenshot_store()
        self.audit = audit

    @staticmethod
    def _valid_region(value) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 4
            and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
            and value[2] > value[0]
            and value[3] > value[1]
        )

    async def _foreground_region(self, conversation_id: str) -> list[int] | None:
        try:
            result = await call_tool(
                "PowerShell",
                {"command": _FOREGROUND_RECT_SCRIPT, "timeout": 10},
                conversation_id,
                self.audit,
            )
            if not isinstance(result, dict) or result.get("status") != "ok":
                return None
            if result.get("truncated"):
                return None
            region = parse_marked_json(result.get("text", "")).get("region")
            return region if self._valid_region(region) else None
        except Exception:  # noqa: BLE001 - full-display fallback is the honest default
            return None

    async def _capture_image(self, conversation_id: str, region: list[int] | None):
        arguments = {} if region is None else {"region": region}
        result = await call_tool(
            "Screenshot",
            arguments,
            conversation_id,
            self.audit,
            include_images=True,
            consent_attempts=4,
        )
        images = result.get("images") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("status") != "ok"
            or not isinstance(images, list)
            or len(images) != 1
            or not isinstance(images[0], CapturedImage)
        ):
            raise ValueError("one captured image is required")
        return images[0]

    async def capture(self, conversation_id: str) -> dict:
        scope = "full-display"
        region_fallback = None
        try:
            image = None
            region = await self._foreground_region(conversation_id)
            if region is not None:
                try:
                    image = await self._capture_image(conversation_id, region)
                    scope = "foreground-window"
                except Exception:  # noqa: BLE001 - retry only the non-mutating capture
                    region_fallback = "region-capture-failed"
            if image is None:
                scope = "full-display"
                image = await self._capture_image(conversation_id, None)
            artifact = self.store.save(image.data, image.mime_type)
            result = {
                "status": "captured",
                "capture_scope": scope,
                "image_url": artifact.image_url,
                "expires_in_s": _EXPIRES_IN_S,
                "usage": (
                    "Inline this temporary image once as "
                    "![Verification screenshot](<image_url>)."
                ),
            }
            if region_fallback is not None:
                result["region_fallback"] = region_fallback
            return result
        except Exception:  # noqa: BLE001 - no desktop text/path/Base64 crosses here
            result = {
                "status": "attempted-but-failed",
                "capture_scope": scope,
                "reason": "Screenshot capture or storage failed.",
            }
            if region_fallback is not None:
                result["region_fallback"] = region_fallback
            return result


class _EvidenceUnavailable:
    """Safe construction default; the production server wires real adapters."""

    async def show_default_printer(self, conversation_id: str) -> dict:
        return {
            "status": "attempted-but-failed",
            "reason": "Desktop display integration is not configured.",
        }

    def show_word_print(self) -> dict:
        return {"status": "error"}

    async def capture(self, conversation_id: str) -> dict:
        return {
            "status": "attempted-but-failed",
            "reason": "Screenshot capture integration is not configured.",
        }


def _effect(action_id: str, parameters: dict) -> str:
    printer = parameters["printer"].strip()
    if action_id == _DEFAULT_PRINTER:
        return (
            f"Change your default printer to {printer}, "
            "then open Windows printer settings to show the result."
        )
    orientation = parameters["orientation"]
    return (
        f"Set {orientation} duplex for Word printing on {printer}. "
        "This changes the printer-wide configuration and may affect printing outside "
        "the current Word document. Word Print Preview will then open to show the result; "
        "a blank unsaved document may be created solely to show Print Preview."
    )


def _bounded(value: object, fallback: str) -> str:
    return value[:450] if isinstance(value, str) and value else fallback


def _caveats(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item[:450] for item in value if isinstance(item, str) and item]


def _timing(
    queued_at: float,
    execution_started: float,
    finished: float,
    display_s: float | None = None,
    screenshot_s: float | None = None,
) -> dict:
    return {
        "queue_wait_s": max(0.0, execution_started - queued_at),
        "execution_s": max(0.0, finished - execution_started),
        "total_s": max(0.0, finished - queued_at),
        "display_s": display_s,
        "screenshot_s": screenshot_s,
    }


class McpActionService:
    def __init__(
        self,
        store=None,
        actions=None,
        display=None,
        screenshots=None,
        audit=None,
        clock=None,
    ):
        self.store = store if store is not None else ProposalStore()
        self.actions = actions
        self.display = display if display is not None else _EvidenceUnavailable()
        self.screenshots = (
            screenshots if screenshots is not None else _EvidenceUnavailable()
        )
        self.audit = audit
        self._clock = clock if clock is not None else time.monotonic
        self._desktop_lock = asyncio.Lock()

    async def handle(
        self,
        phase,
        conversation_id,
        dialogue_count,
        query="",
        action_id="",
        parameters=None,
    ) -> dict:
        """Prepare, cancel, or execute a proposal; audit never changes the outcome."""
        started = self._clock()
        try:
            result = await self._handle(
                phase,
                conversation_id,
                dialogue_count,
                query,
                action_id,
                parameters,
            )
        except ValueError:
            result = {"status": "error", "reason": "The action or parameters are invalid."}
        except Exception:  # noqa: BLE001 - public tool boundary must sanitize every failure
            result = {"status": "error", "reason": _INTERNAL_ERROR}
        self._write_audit(phase, conversation_id, result, started)
        return result

    async def _handle(
        self,
        phase,
        conversation_id,
        dialogue_count,
        query,
        action_id,
        parameters,
    ) -> dict:
        if phase not in {"draft", "confirm", "cancel"}:
            return {"status": "error", "reason": "phase must be draft, confirm, or cancel."}
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return {
                "status": "error",
                "reason": "conversation_id must be a non-empty string.",
            }
        if type(dialogue_count) is not int or dialogue_count < 0:
            return {"status": "error", "reason": "dialogue_count must be an integer >= 0."}

        if phase in {"confirm", "cancel"}:
            return await self._resolve(
                phase,
                conversation_id,
                dialogue_count,
                query,
                action_id,
                parameters,
            )
        return await self._draft(
            conversation_id,
            dialogue_count,
            action_id,
            parameters,
            query,
        )

    async def _resolve(
        self,
        phase,
        conversation_id,
        dialogue_count,
        query,
        action_id,
        parameters,
    ) -> dict:
        if action_id != "":
            return {
                "status": "error",
                "reason": f"{phase} must not carry action_id.",
            }
        if parameters is not None:
            return {
                "status": "error",
                "reason": f"{phase} must not carry parameters.",
            }
        queued_at = self._clock()
        decision = self.store.resolve(
            conversation_id, dialogue_count, query, phase=phase
        )
        if phase == "cancel" and decision.status == "cancelled":
            return {
                "status": "cancelled",
                "reason": "No automatic action was performed.",
            }
        if decision.status == "blocked":
            return {"status": "blocked", "reason": decision.reason}
        if self.actions is None or decision.proposal.action_id not in _ACTION_PARAMETERS:
            return {
                "status": "blocked",
                "reason": "Execution is blocked until the live execution gate is approved.",
            }
        return await self._execute(
            decision.proposal,
            conversation_id,
            queued_at,
        )

    async def _draft(
        self,
        conversation_id,
        dialogue_count,
        action_id,
        parameters,
        query="",
    ) -> dict:
        pending = self.store.peek(conversation_id)
        if (
            pending is not None
            and dialogue_count == pending.created_dialogue_count + 1
            and self.store.is_affirmative(query)
        ):
            return {
                "status": "blocked",
                "reason": (
                    "A proposal is pending. Call mcp_action with phase='confirm' "
                    "and no action_id or parameters to execute the stored proposal."
                ),
            }
        if not isinstance(action_id, str) or not action_id.strip():
            return {"status": "ask-back", "reason": "Choose a supported action first."}
        if action_id not in _ACTION_PARAMETERS:
            return {
                "status": "unsupported",
                "reason": "No reviewed automatic action exists for action_id.",
            }
        if parameters is None:
            return {"status": "ask-back", "reason": "Missing required parameter: printer."}
        if not isinstance(parameters, dict):
            return {"status": "error", "reason": "parameters must be an object."}

        expected = _ACTION_PARAMETERS[action_id]
        if set(parameters) != expected and set(parameters) - expected:
            return {
                "status": "error",
                "reason": "parameters must match the action's closed schema.",
            }
        missing = sorted(expected - set(parameters))
        if missing:
            return {
                "status": "ask-back",
                "reason": f"Missing required parameter: {', '.join(missing)}.",
            }
        if parameters["printer"] is None or (
            isinstance(parameters["printer"], str) and not parameters["printer"].strip()
        ):
            return {"status": "ask-back", "reason": "Missing required parameter: printer."}
        if action_id == "word_printer_duplex" and (
            parameters["orientation"] is None
            or (
                isinstance(parameters["orientation"], str)
                and not parameters["orientation"].strip()
            )
        ):
            return {"status": "ask-back", "reason": "Missing required parameter: orientation."}

        parameters = dict(parameters)
        caveats = []
        if self.actions is not None:
            if action_id == _DEFAULT_PRINTER:
                validation = await self.actions.validate_default_printer(
                    parameters["printer"]
                )
            else:
                validation = await self.actions.validate_word_printer_duplex(
                    parameters["printer"], parameters["orientation"]
                )
            if not isinstance(validation, dict) or validation.get("status") != "ok":
                reason = (
                    validation.get("reason") if isinstance(validation, dict) else None
                )
                return {
                    "status": "error",
                    "action_id": action_id,
                    "reason": _bounded(
                        reason,
                        "The requested printer could not be validated safely.",
                    ),
                }
            if isinstance(validation.get("printer"), str):
                parameters["printer"] = validation["printer"]
            caveats = _caveats(validation.get("caveats"))

        proposal = self.store.create(
            conversation_id,
            action_id,
            parameters,
            _effect(action_id, parameters),
            dialogue_count,
            caveats=caveats,
        )
        return {
            "status": "pending-confirmation",
            "action_id": proposal.action_id,
            "effect": proposal.effect,
            "offer": _OFFER,
            "expires_in_s": _EXPIRES_IN_S,
            "caveats": proposal.caveats,
        }

    async def _execute(self, proposal, conversation_id: str, queued_at: float) -> dict:
        async with self._desktop_lock:
            execution_started = self._clock()
            queue_wait_s = execution_started - queued_at
            action_budget_s = (
                _DEFAULT_ACTION_BUDGET_S
                if proposal.action_id == _DEFAULT_PRINTER
                else _WORD_ACTION_BUDGET_S
            )
            if queue_wait_s > _TOTAL_BUDGET_S - action_budget_s:
                finished = self._clock()
                return {
                    "status": "queued-timeout",
                    "action_id": proposal.action_id,
                    "changed": False,
                    "verification": "not-run",
                    "display": {"status": "skipped"},
                    "screenshot": {"status": "skipped"},
                    "reason": "The full action budget was no longer available; nothing executed.",
                    "timing": _timing(queued_at, execution_started, finished),
                }

            try:
                if proposal.action_id == _DEFAULT_PRINTER:
                    raw_result = await self.actions.execute_default_printer(
                        proposal.parameters["printer"]
                    )
                else:
                    raw_result = await self.actions.execute_word_printer_duplex(
                        proposal.parameters["printer"],
                        proposal.parameters["orientation"],
                    )
            except Exception:  # noqa: BLE001 - host details never cross the tool boundary
                raw_result = None

            result = self._action_envelope(raw_result, proposal.action_id)
            stage_times = {"display_s": None, "screenshot_s": None}
            if result["status"] == "ok" and result["verification"] == "verified":
                evidence, stage_times = await self._evidence(
                    conversation_id, proposal.action_id
                )
                result.update(evidence)
            else:
                result["status"] = "error"
                result["display"] = {"status": "skipped"}
                result["screenshot"] = {"status": "skipped"}
                result.setdefault("reason", _EXECUTION_ERROR)

            finished = self._clock()
            result["timing"] = _timing(
                queued_at, execution_started, finished, **stage_times
            )
            return result

    def _action_envelope(self, raw_result, action_id: str) -> dict:
        empty_state = (
            {"default_printer": None}
            if action_id == _DEFAULT_PRINTER
            else {"duplex": None}
        )
        if not isinstance(raw_result, dict):
            return {
                "status": "error",
                "action_id": action_id,
                "changed": False,
                "before": empty_state,
                "after": dict(empty_state),
                "verification": "unavailable",
                "reason": _EXECUTION_ERROR,
            }
        result = {key: raw_result[key] for key in _ACTION_RESULT_KEYS if key in raw_result}
        result["action_id"] = action_id
        result["status"] = "ok" if raw_result.get("status") == "ok" else "error"
        result["changed"] = result.get("changed") is True
        result.setdefault("before", empty_state)
        result.setdefault("after", dict(empty_state))
        if result.get("verification") not in {"verified", "mismatch", "unavailable", "not-run"}:
            result["verification"] = "unavailable"
        result["caveats"] = _caveats(result.get("caveats"))
        if "reason" in result:
            result["reason"] = _bounded(result["reason"], _EXECUTION_ERROR)
        return result

    async def _ensure_word_foreground(self, display: dict, conversation_id: str) -> dict:
        """Use the supported App switch only after preview evidence exists."""
        if display.get("preview_ok") is not True or display.get("foreground") is not False:
            return display
        try:
            switched = await call_tool(
                "App",
                {"mode": "switch", "name": "WINWORD.EXE"},
                conversation_id,
                self.audit,
            )
            if not isinstance(switched, dict) or switched.get("status") != "ok":
                return display
            retried = await asyncio.to_thread(self.display.show_word_print)
            if isinstance(retried, dict):
                mapped = _word_display_envelope(retried)
                if mapped.get("status") == "displayed":
                    return mapped
        except Exception:  # noqa: BLE001 - retain the original honest partial outcome
            return display
        return display

    async def _evidence(
        self, conversation_id: str, action_id: str = _DEFAULT_PRINTER
    ) -> tuple[dict, dict]:
        display_started = self._clock()
        try:
            if action_id == _WORD_DUPLEX:
                display = await asyncio.to_thread(self.display.show_word_print)
                display = await self._ensure_word_foreground(display, conversation_id)
            else:
                display = await self.display.show_default_printer(conversation_id)
        except Exception:  # noqa: BLE001 - preserve the independently verified setting
            display = None
        display = (
            _word_display_envelope(display)
            if action_id == _WORD_DUPLEX
            else self._display_envelope(display)
        )
        display_s = max(0.0, self._clock() - display_started)
        if display["status"] != "displayed":
            return (
                {
                    "status": "partial",
                    "display": display,
                    "screenshot": {"status": "skipped-display-unverified"},
                },
                {"display_s": display_s, "screenshot_s": None},
            )

        screenshot_started = self._clock()
        try:
            screenshot = await self.screenshots.capture(conversation_id)
        except Exception:  # noqa: BLE001 - preserve the independently verified setting
            screenshot = None
        screenshot_s = max(0.0, self._clock() - screenshot_started)
        screenshot = self._screenshot_envelope(screenshot)
        if action_id == _WORD_DUPLEX and screenshot["status"] != "captured":
            screenshot["reason"] = "The verified Word result could not be captured."
        return (
            {
                "status": "ok" if screenshot["status"] == "captured" else "partial",
                "display": display,
                "screenshot": screenshot,
            },
            {"display_s": display_s, "screenshot_s": screenshot_s},
        )

    @staticmethod
    def _display_envelope(value) -> dict:
        if not isinstance(value, dict) or value.get("status") not in _DISPLAY_STATUSES:
            return {
                "status": "attempted-but-failed",
                "reason": "The verified setting could not be displayed.",
            }
        result = dict(value)
        if "reason" in result:
            result["reason"] = _bounded(
                result["reason"], "The verified setting could not be displayed."
            )
        return result

    @staticmethod
    def _screenshot_envelope(value) -> dict:
        if not isinstance(value, dict) or value.get("status") not in _SCREENSHOT_STATUSES:
            value = None
        result = dict(value) if isinstance(value, dict) else {}
        image_url = result.get("image_url")
        if result.get("status") == "captured" and not (
            isinstance(image_url, str)
            and image_url.startswith(("http://", "https://"))
        ):
            result = {"status": "attempted-but-failed"}
        if result.get("status") != "captured":
            result.pop("image_url", None)
            result.pop("expires_in_s", None)
            result.pop("usage", None)
            result.setdefault("status", "attempted-but-failed")
            result["reason"] = _bounded(
                result.get("reason"), "The verified result could not be captured."
            )
        return result

    def _write_audit(self, phase, conversation_id, result: dict, started: float) -> None:
        if self.audit is None:
            return
        try:
            status = result.get("status", "error")
            action_id = result.get("action_id")
            if action_id not in _ACTION_PARAMETERS:
                action_id = ""
            if status in {"pending-confirmation", "cancelled", "ok", "partial"}:
                decision = "executed"
            elif status in {"blocked", "queued-timeout", "ask-back", "unsupported"}:
                decision = "blocked"
            else:
                decision = "error"
            label = f"{action_id}:{status}" if action_id else status
            display = result.get("display")
            screenshot = result.get("screenshot")
            display_status = (
                display.get("status", "not-attempted")
                if isinstance(display, dict)
                else "not-attempted"
            )
            screenshot_status = (
                screenshot.get("status", "not-attempted")
                if isinstance(screenshot, dict)
                else "not-attempted"
            )
            verification = result.get("verification", "not-attempted")
            outcome = (
                f"{label}:verification={verification}:display={display_status}"
                f":screenshot={screenshot_status}"
            )
            kwargs = {"outcome": outcome}
            if decision != "executed":
                kwargs["reason"] = (
                    f"{label}: reviewed MCP-Action request was not executed."
                )
            timing = result.get("timing")
            self.audit.write_attempt(
                decision=decision,
                operation="mcp-action",
                normalized_path=None,
                allowed_root="windows-desktop",
                conversation_id=(
                    conversation_id
                    if isinstance(conversation_id, str) and conversation_id.strip()
                    else None
                ),
                duration_s=max(0.0, self._clock() - started),
                timing=timing if isinstance(timing, dict) else None,
                **kwargs,
            )
        except Exception:  # noqa: BLE001 - persistence failure cannot rewrite host truth
            return
