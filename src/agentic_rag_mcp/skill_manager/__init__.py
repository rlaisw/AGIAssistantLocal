"""Spec 036 — Skill Manager: shared skill store, semantic search, executor
helpers. First component of spec 035 (AI Helpdesk Architecture)."""

from .store import SkillNotFound, SkillStore, reusable, validate_skill  # noqa: F401
