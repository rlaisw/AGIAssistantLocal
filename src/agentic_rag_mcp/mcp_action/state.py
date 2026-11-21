"""In-memory MCP-Action proposals and fail-closed consent resolution."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

_ACTION_PARAMETERS = {
    "windows_default_printer": frozenset({"printer"}),
    "word_printer_duplex": frozenset({"printer", "orientation"}),
}
_AFFIRMATIVE = frozenset(
    {"yes", "yeah", "yep", "ok", "okay", "confirm", "proceed", "go ahead"}
)
_NEGATIVE = frozenset({"no", "nope", "cancel", "stop", "never mind"})
_AFFIRMATIVE_PHRASE = re.compile(
    r"^(?:yes|yeah|yep|ok|okay|sure)"
    r"(?:,?\s+(?:please\s+)?(?:help\s+(?:me\s+)?)?(?:to\s+)?"
    r"(?:do\s+(?:it|that|so)|go\s+ahead|proceed))$"
)
_NEGATIVE_PHRASE = re.compile(r"^(?:no|nope)(?:,?\s+(?:thanks|thank\s+you))?$")
_ORIENTATIONS = frozenset({"long-edge", "short-edge"})
_TTL_SECONDS = 900.0
_MAX_PRINTER_LENGTH = 256


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_id: str
    conversation_id: str
    action_id: str
    parameters: dict[str, str]
    effect: str
    caveats: list[str]
    created_dialogue_count: int
    created_at_utc: datetime
    expires_at_monotonic: float


@dataclass(frozen=True, slots=True)
class Decision:
    status: Literal["reserved", "cancelled", "blocked"]
    proposal: Proposal | None
    reason: str


class ProposalStore:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._pending: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def create(
        self,
        conversation_id: str,
        action_id: str,
        parameters: dict[str, str],
        effect: str,
        dialogue_count: int,
        caveats: list[str] | None = None,
    ) -> Proposal:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be a non-empty string")
        if not self._valid_dialogue_count(dialogue_count):
            raise ValueError("dialogue_count must be an integer >= 0")
        validated = self._validate_parameters(action_id, parameters)
        now = self._clock()
        proposal = Proposal(
            proposal_id=uuid4().hex,
            conversation_id=conversation_id,
            action_id=action_id,
            parameters=validated,
            effect=effect,
            caveats=list(caveats) if caveats is not None else [],
            created_dialogue_count=dialogue_count,
            created_at_utc=datetime.now(UTC),
            expires_at_monotonic=now + _TTL_SECONDS,
        )
        with self._lock:
            self._remove_expired_locked(now)
            self._pending[conversation_id] = proposal
        return proposal

    def peek(self, conversation_id: str) -> Proposal | None:
        """Return an active proposal without consuming or superseding it."""
        with self._lock:
            now = self._clock()
            self._remove_expired_locked(now)
            proposal = self._pending.get(conversation_id)
            if proposal is None or now >= proposal.expires_at_monotonic:
                return None
            return proposal

    @staticmethod
    def is_affirmative(query: str) -> bool:
        return ProposalStore._classify_response(query) == "confirm"

    def resolve(
        self,
        conversation_id: str,
        dialogue_count: int,
        query: str,
        phase: Literal["confirm", "cancel"] = "confirm",
    ) -> Decision:
        with self._lock:
            self._remove_expired_locked(self._clock())
            proposal = self._pending.get(conversation_id)
            if proposal is None:
                return Decision("blocked", None, "No eligible proposal is pending.")

            if (
                not self._valid_dialogue_count(dialogue_count)
                or dialogue_count != proposal.created_dialogue_count + 1
            ):
                del self._pending[conversation_id]
                return Decision(
                    "blocked", None, "Confirmation requires the immediately following turn."
                )

            response = self._classify_response(query)
            if response != phase:
                del self._pending[conversation_id]
                return Decision(
                    "blocked", None, "The raw response does not match the resolution phase."
                )

            del self._pending[conversation_id]
            if phase == "cancel":
                return Decision("cancelled", proposal, "No automatic action was performed.")
            return Decision("reserved", proposal, "Proposal reserved for execution.")

    @staticmethod
    def _valid_dialogue_count(value: object) -> bool:
        return type(value) is int and value >= 0

    @staticmethod
    def _validate_parameters(action_id: str, parameters: dict[str, str]) -> dict[str, str]:
        if not isinstance(action_id, str) or action_id not in _ACTION_PARAMETERS:
            raise ValueError("Unsupported action_id")
        expected = _ACTION_PARAMETERS[action_id]
        if not isinstance(parameters, dict) or set(parameters) != expected:
            raise ValueError("Parameters do not match the action's closed schema")

        printer = parameters.get("printer")
        if not isinstance(printer, str):
            raise ValueError("printer must be a string")  # noqa: TRY004 - uniform validation errors
        printer = printer.strip()
        if (
            not printer
            or len(printer) > _MAX_PRINTER_LENGTH
            or any(character in printer for character in ("\0", "\r", "\n"))
        ):
            raise ValueError("printer is empty, too long, or contains a control character")
        validated = {"printer": printer}

        if action_id == "word_printer_duplex":
            orientation = parameters.get("orientation")
            if not isinstance(orientation, str) or orientation not in _ORIENTATIONS:
                raise ValueError("orientation must be long-edge or short-edge")
            validated["orientation"] = orientation
        return validated

    @staticmethod
    def _classify_response(query: str) -> Literal["confirm", "cancel"] | None:
        if not isinstance(query, str):
            return None
        normalized = query.strip(" \t\r\n.!?").casefold()
        if normalized in _AFFIRMATIVE or _AFFIRMATIVE_PHRASE.fullmatch(normalized):
            return "confirm"
        if normalized in _NEGATIVE or _NEGATIVE_PHRASE.fullmatch(normalized):
            return "cancel"
        return None

    def _remove_expired_locked(self, now: float) -> None:
        expired = [
            conversation_id
            for conversation_id, proposal in self._pending.items()
            if now >= proposal.expires_at_monotonic
        ]
        for conversation_id in expired:
            del self._pending[conversation_id]
