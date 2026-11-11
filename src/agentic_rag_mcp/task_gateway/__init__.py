"""Spec 038 — Task Gateway: the gated sidecar lane over the 035-R5
endpoint shapes (tier-1/tier-2/install/job), the conversation-scoped
Tier-2 state, and the shared never-list module."""

from .neverlist import NEVER_PATTERNS, scan  # noqa: F401
from .tier2_state import Tier2State  # noqa: F401