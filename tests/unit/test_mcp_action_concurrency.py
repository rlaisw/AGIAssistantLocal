"""T014 async orchestration contract for spec 047 (U18/U19).

The injected doubles pin a minimal evidence API: display provides
``show_default_printer(conversation_id)`` and screenshots provides the generic
``capture(conversation_id)`` entry point.  No action-specific capture alias is
required.  Draft validation may be read-only; ``execute_default_printer`` is the
post-confirmation before-read/mutation/after-read boundary and returns a mapping
with ``changed``, ``before``, ``after``, and ``verification`` fields.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from agentic_rag_mcp.mcp_action.service import McpActionService
from agentic_rag_mcp.mcp_action.state import ProposalStore

ACTION_ID = "windows_default_printer"
PRINTER_A = "Test Printer A"
PRINTER_B = "Test Printer B"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeActions:
    def __init__(self) -> None:
        self.trace: list[str] = []
        self.validate_calls: list[str] = []
        self.execute_calls: list[str] = []
        self.errors: dict[str, BaseException] = {}
        self.started: dict[str, asyncio.Event] = {}
        self.releases: dict[str, asyncio.Event] = {}
        self.active = 0
        self.max_active = 0

    def gate(self, printer: str) -> tuple[asyncio.Event, asyncio.Event]:
        started = asyncio.Event()
        release = asyncio.Event()
        self.started[printer] = started
        self.releases[printer] = release
        return started, release

    async def validate_default_printer(self, printer: str) -> dict:
        self.validate_calls.append(printer)
        return {
            "status": "ok",
            "printer": printer,
            "current_default": "Old Printer",
            "match_count": 1,
            "managed_default": False,
            "caveats": [],
        }

    async def execute_default_printer(self, printer: str) -> dict:
        self.execute_calls.append(printer)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.trace.append(f"before:{printer}")
        try:
            if printer in self.started:
                self.started[printer].set()
            if printer in self.releases:
                await self.releases[printer].wait()
            if printer in self.errors:
                raise self.errors[printer]
            self.trace.append(f"after:{printer}")
            return {
                "status": "ok",
                "action_id": ACTION_ID,
                "changed": True,
                "before": {"default_printer": "Old Printer"},
                "after": {"default_printer": printer},
                "verification": "verified",
                "caveats": [],
            }
        finally:
            self.active -= 1
            self.trace.append(f"settled:{printer}")


class FakeDisplay:
    def __init__(self, clock: FakeClock, trace: list[str]) -> None:
        self.clock = clock
        self.trace = trace
        self.calls: list[str] = []
        self.outcomes: dict[str, dict] = {}
        self.durations: dict[str, float] = {}

    async def show_default_printer(self, conversation_id: str) -> dict:
        self.calls.append(conversation_id)
        self.trace.append(f"display:{conversation_id}")
        self.clock.advance(self.durations.get(conversation_id, 0.0))
        return deepcopy(self.outcomes.get(conversation_id, {"status": "displayed"}))


class FakeScreenshots:
    def __init__(self, clock: FakeClock, trace: list[str]) -> None:
        self.clock = clock
        self.trace = trace
        self.calls: list[str] = []
        self.outcomes: dict[str, dict] = {}
        self.durations: dict[str, float] = {}

    async def capture(self, conversation_id: str) -> dict:
        self.calls.append(conversation_id)
        self.trace.append(f"capture:{conversation_id}")
        self.clock.advance(self.durations.get(conversation_id, 0.0))
        return deepcopy(
            self.outcomes.get(
                conversation_id,
                {
                    "status": "captured",
                    "image_url": "https://example.test/mcp-action/screenshot.png",
                    "expires_in_s": 900,
                },
            )
        )


def _make_service(
    actions: FakeActions,
    clock: FakeClock,
    display: FakeDisplay | None = None,
    screenshots: FakeScreenshots | None = None,
) -> tuple[McpActionService, FakeDisplay, FakeScreenshots]:
    display = display or FakeDisplay(clock, actions.trace)
    screenshots = screenshots or FakeScreenshots(clock, actions.trace)
    service = McpActionService(
        store=ProposalStore(clock=clock),
        actions=actions,
        display=display,
        screenshots=screenshots,
        audit=None,
        clock=clock,
    )
    return service, display, screenshots


async def _draft(
    service: McpActionService,
    conversation_id: str,
    printer: str = PRINTER_A,
) -> dict:
    result = await service.handle(
        phase="draft",
        conversation_id=conversation_id,
        dialogue_count=4,
        action_id=ACTION_ID,
        parameters={"printer": printer},
    )
    assert result["status"] == "pending-confirmation"
    return result


async def _confirm(service: McpActionService, conversation_id: str) -> dict:
    return await service.handle(
        phase="confirm",
        conversation_id=conversation_id,
        dialogue_count=5,
        query="yes",
    )


async def _cancel(service: McpActionService, conversation_id: str) -> dict:
    return await service.handle(
        phase="cancel",
        conversation_id=conversation_id,
        dialogue_count=5,
        query="no",
    )


async def _wait(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), timeout=1)


def _assert_sanitized_error(result: dict, *secrets: str) -> None:
    assert result["status"] == "error"
    reason = result.get("reason", result.get("error"))
    assert isinstance(reason, str) and reason
    assert len(reason) <= 500
    serialized = json.dumps(result)
    for secret in secrets:
        assert secret not in serialized


@pytest.mark.asyncio
async def test_event_gated_executor_is_desktop_serialized_with_separate_timings():
    clock = FakeClock()
    actions = FakeActions()
    display = FakeDisplay(clock, actions.trace)
    screenshots = FakeScreenshots(clock, actions.trace)
    display.durations["c2"] = 2.0
    screenshots.durations["c2"] = 3.0
    service, _, _ = _make_service(actions, clock, display, screenshots)
    await _draft(service, "c1", PRINTER_A)
    await _draft(service, "c2", PRINTER_B)
    a_started, a_release = actions.gate(PRINTER_A)
    b_started, b_release = actions.gate(PRINTER_B)

    first = asyncio.create_task(_confirm(service, "c1"))
    await _wait(a_started)
    second = asyncio.create_task(_confirm(service, "c2"))
    await asyncio.sleep(0)  # Schedule the queued task without advancing fake time.
    assert not second.done()

    clock.advance(10.0)
    a_release.set()
    first_result = await asyncio.wait_for(first, timeout=1)
    await _wait(b_started)
    clock.advance(5.0)
    b_release.set()
    second_result = await asyncio.wait_for(second, timeout=1)

    assert first_result["status"] == "ok"
    assert second_result["status"] == "ok"
    assert actions.max_active == 1
    assert actions.execute_calls == [PRINTER_A, PRINTER_B]
    assert second_result["timing"] == {
        "queue_wait_s": 10.0,
        "execution_s": 10.0,
        "total_s": 20.0,
        "display_s": 2.0,
        "screenshot_s": 3.0,
    }
    assert actions.trace == [
        f"before:{PRINTER_A}",
        f"after:{PRINTER_A}",
        f"settled:{PRINTER_A}",
        "display:c1",
        "capture:c1",
        f"before:{PRINTER_B}",
        f"after:{PRINTER_B}",
        f"settled:{PRINTER_B}",
        "display:c2",
        "capture:c2",
    ]


@pytest.mark.parametrize(
    ("queued_seconds", "expected_status"),
    [(180.0, "ok"), (180.01, "queued-timeout")],
)
@pytest.mark.asyncio
async def test_full_60_second_action_budget_must_fit_inside_240_second_total(
    queued_seconds, expected_status
):
    clock = FakeClock()
    actions = FakeActions()
    service, display, screenshots = _make_service(actions, clock)
    await _draft(service, "c1", PRINTER_A)
    await _draft(service, "c2", PRINTER_B)
    a_started, a_release = actions.gate(PRINTER_A)
    _b_started, b_release = actions.gate(PRINTER_B)

    first = asyncio.create_task(_confirm(service, "c1"))
    await _wait(a_started)
    second = asyncio.create_task(_confirm(service, "c2"))
    await asyncio.sleep(0)
    clock.advance(queued_seconds)
    a_release.set()
    b_release.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )

    assert first_result["status"] != "queued-timeout"
    assert second_result["status"] == expected_status
    assert second_result["timing"]["queue_wait_s"] == pytest.approx(queued_seconds)
    assert second_result["timing"]["execution_s"] == 0.0
    assert second_result["timing"]["total_s"] == pytest.approx(queued_seconds)

    if expected_status == "ok":
        assert actions.execute_calls == [PRINTER_A, PRINTER_B]
        return

    assert actions.execute_calls == [PRINTER_A]
    assert display.calls == ["c1"]
    assert screenshots.calls == ["c1"]
    repeated = await _confirm(service, "c2")
    assert repeated["status"] == "blocked"
    assert actions.execute_calls == [PRINTER_A]


@pytest.mark.asyncio
async def test_duplicate_confirms_execute_once_and_block_the_other():
    clock = FakeClock()
    actions = FakeActions()
    service, display, screenshots = _make_service(actions, clock)
    await _draft(service, "c1")
    started, release = actions.gate(PRINTER_A)

    first = asyncio.create_task(_confirm(service, "c1"))
    await _wait(started)
    duplicate = asyncio.create_task(_confirm(service, "c1"))
    duplicate_result = await asyncio.wait_for(duplicate, timeout=1)

    assert duplicate_result["status"] == "blocked"
    assert actions.execute_calls == [PRINTER_A]
    release.set()
    first_result = await asyncio.wait_for(first, timeout=1)
    assert first_result["status"] == "ok"
    assert actions.execute_calls == [PRINTER_A]
    assert display.calls == ["c1"]
    assert screenshots.calls == ["c1"]


@pytest.mark.asyncio
async def test_draft_and_cancel_never_acquire_busy_desktop_lock_or_mutate():
    clock = FakeClock()
    actions = FakeActions()
    service, display, screenshots = _make_service(actions, clock)
    await _draft(service, "c1", PRINTER_A)
    started, release = actions.gate(PRINTER_A)
    confirmed = asyncio.create_task(_confirm(service, "c1"))
    await _wait(started)

    try:
        drafted = await asyncio.wait_for(
            _draft(service, "c2", PRINTER_B), timeout=1
        )
        cancelled = await asyncio.wait_for(_cancel(service, "c2"), timeout=1)

        assert drafted["status"] == "pending-confirmation"
        assert cancelled["status"] == "cancelled"
        # Read-only validation is allowed; every mutating/evidence stage is not.
        assert actions.execute_calls == [PRINTER_A]
        assert display.calls == []
        assert screenshots.calls == []
    finally:
        release.set()

    confirmed_result = await asyncio.wait_for(confirmed, timeout=1)
    assert confirmed_result["status"] == "ok"
    assert actions.execute_calls == [PRINTER_A]
    assert display.calls == ["c1"]
    assert screenshots.calls == ["c1"]


@pytest.mark.asyncio
async def test_executor_exception_is_sanitized_and_released_after_host_settles():
    clock = FakeClock()
    actions = FakeActions()
    actions.errors[PRINTER_A] = RuntimeError(
        r"C:\Users\alice\secret.ps1 --token super-secret"
    )
    service, display, screenshots = _make_service(actions, clock)
    await _draft(service, "c1", PRINTER_A)
    await _draft(service, "c2", PRINTER_B)
    started, release = actions.gate(PRINTER_A)

    first = asyncio.create_task(_confirm(service, "c1"))
    await _wait(started)
    second = asyncio.create_task(_confirm(service, "c2"))
    await asyncio.sleep(0)
    assert not second.done()
    assert actions.execute_calls == [PRINTER_A]

    release.set()
    first_result, second_result = await asyncio.wait_for(
        asyncio.gather(first, second), timeout=1
    )

    _assert_sanitized_error(
        first_result, "super-secret", "secret.ps1", r"C:\Users"
    )
    assert first_result.get("changed") is not True
    assert second_result["status"] == "ok"
    assert actions.execute_calls == [PRINTER_A, PRINTER_B]
    assert actions.trace.index(f"settled:{PRINTER_A}") < actions.trace.index(
        f"before:{PRINTER_B}"
    )
    assert display.calls == ["c2"]
    assert screenshots.calls == ["c2"]


@pytest.mark.asyncio
async def test_unknown_transport_outcome_is_not_blind_retried():
    clock = FakeClock()
    actions = FakeActions()
    actions.errors[PRINTER_A] = TimeoutError(
        "Transport vanished after mutation; token=do-not-leak"
    )
    service, display, screenshots = _make_service(actions, clock)
    await _draft(service, "c1")

    result = await _confirm(service, "c1")

    _assert_sanitized_error(result, "do-not-leak", "Transport vanished")
    assert result.get("changed") is not True
    assert result["verification"] == "unavailable"
    assert actions.execute_calls == [PRINTER_A]
    assert display.calls == []
    assert screenshots.calls == []

    repeated = await _confirm(service, "c1")
    assert repeated["status"] == "blocked"
    assert actions.execute_calls == [PRINTER_A]


@pytest.mark.parametrize("failure_stage", ["display", "screenshot"])
@pytest.mark.asyncio
async def test_verified_setting_with_display_or_screenshot_failure_is_partial(
    failure_stage,
):
    clock = FakeClock()
    actions = FakeActions()
    service, display, screenshots = _make_service(actions, clock)
    if failure_stage == "display":
        display.outcomes["c1"] = {
            "status": "attempted-but-failed",
            "reason": "Settings page was not verified.",
        }
    else:
        screenshots.outcomes["c1"] = {
            "status": "attempted-but-failed",
            "reason": "No valid image was returned.",
        }
    await _draft(service, "c1")

    result = await _confirm(service, "c1")

    assert result["status"] == "partial"
    assert result["changed"] is True
    assert result["before"] == {"default_printer": "Old Printer"}
    assert result["after"] == {"default_printer": PRINTER_A}
    assert result["verification"] == "verified"
    assert actions.execute_calls == [PRINTER_A]
    if failure_stage == "display":
        assert result["display"]["status"] == "attempted-but-failed"
        assert result["screenshot"]["status"] == "skipped-display-unverified"
        assert screenshots.calls == []
    else:
        assert result["display"]["status"] == "displayed"
        assert result["screenshot"]["status"] == "attempted-but-failed"
        assert screenshots.calls == ["c1"]
    assert "image_url" not in result["screenshot"]


@pytest.mark.asyncio
async def test_orphan_and_wrong_conversation_confirmations_are_blocked():
    clock = FakeClock()
    actions = FakeActions()
    service, display, screenshots = _make_service(actions, clock)

    orphan = await _confirm(service, "orphan")
    assert orphan["status"] == "blocked"
    await _draft(service, "c1")
    wrong_conversation = await _confirm(service, "c2")

    assert wrong_conversation["status"] == "blocked"
    assert actions.execute_calls == []
    assert display.calls == []
    assert screenshots.calls == []

    # The failed cross-conversation attempt must not consume c1's proposal.
    confirmed = await _confirm(service, "c1")
    assert confirmed["status"] == "ok"
    assert actions.execute_calls == [PRINTER_A]
