"""Spec 036 — SQLite skill store: upsert-versioned skills + append-only
feedback (data-model.md). Trust is two counters; decay is feedback-driven,
never time-based (FR-003). No delete operation exists (FR-009)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SLOT_RE = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
# machine-specific literals never enter the store (SC-005): Windows profile
# paths, env-var indirections, POSIX home dirs. Drives/roots are defaults,
# not identities — only user/host-scoped paths are rejected.
_MACHINE_LITERALS = (
    re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    re.compile(r"%(USERPROFILE|APPDATA|LOCALAPPDATA)%", re.IGNORECASE),
    re.compile(r"/home/[a-z]", re.IGNORECASE),
    re.compile(r"/Users/", re.IGNORECASE),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier IN (1, 2)),
    workflow_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skill_feedback (
    skill_name TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
    error_context TEXT,
    ts TEXT NOT NULL,
    PRIMARY KEY (skill_name, ts)
);
"""


class SkillNotFound(LookupError):
    """Explicit missing skill — never an empty record (contract)."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _param_strings(params) -> list[str]:
    """Raw string values from a params template — scanned pre-JSON so
    backslash escaping cannot hide a machine literal."""
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for item in v.values():
                walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(params or {})
    return out


def validate_skill(skill: dict) -> str | None:
    """Boundary validation (FR-004/005/006): returns ONE rejection message
    naming EVERY violated field (aggregated — no-reusable-skill-on-file-do-
    not-open-word, 2026-11-12: first-fail-only drip-fed the agent one field
    per retry, costing 4 extra LLM rounds per save), or None when storable."""
    problems: list[str] = []
    name = skill.get("name") or ""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        problems.append(
            f"name — must be snake_case (^[a-z][a-z0-9_]*$), got {name!r}")
    description = (skill.get("description") or "").strip()
    if not description:
        problems.append(
            "description — must be a non-empty trigger-keyword description")
    tier = skill.get("tier")
    if tier not in (1, 2):
        problems.append(f"tier — must be 1 or 2, got {tier!r}")
    workflow = skill.get("workflow")
    if not isinstance(workflow, list) or not workflow:
        problems.append("workflow — must be a non-empty list of steps")
        workflow = []  # per-step checks are moot without steps
    for i, step in enumerate(workflow):
        if not isinstance(step, dict):
            problems.append(f"workflow step {i + 1} — must be an object")
            continue
        for key in ("tool", "service"):
            if not str(step.get(key) or "").strip():
                problems.append(f"workflow step {i + 1} — missing '{key}'")
        if not str(step.get("expect") or "").strip():
            problems.append(f"workflow step {i + 1} — every step must carry "
                            "an 'expect' field (FR-006)")
        for value in _param_strings(step.get("params_template")):
            for lit in _MACHINE_LITERALS:
                if lit.search(value):
                    problems.append(
                        f"workflow step {i + 1} params_template — "
                        f"machine-specific literal {lit.pattern!r} found in "
                        f"{value!r}; use {{placeholders}} (SC-005)")
    if tier == 2 and workflow and \
            "tier1" not in str(workflow[0].get("tool", "")).lower():
        problems.append("tier-2 skills must include a Tier-1 pre-check as "
                        "workflow step 1 (FR-006)")
    if problems:
        return "rejected: " + "; ".join(problems[:6])
    return None


def reusable(counts: tuple[int, int], min_rate: float = 0.80,
             min_successes: int = 3) -> bool:
    """FR-002: auto-reuse iff rate > min_rate AND successes >= min_successes
    — strictly greater, so exactly 80% is NOT trusted."""
    success, failure = counts
    total = success + failure
    return total > 0 and success / total > min_rate and success >= min_successes


class SkillStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _row_to_skill(self, row: sqlite3.Row) -> dict:
        return {
            "name": row["name"],
            "description": row["description"],
            "tier": row["tier"],
            "workflow": json.loads(row["workflow_json"]),
            "version": row["version"],
            "success_count": row["success_count"],
            "failure_count": row["failure_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def save(self, skill: dict) -> tuple[str, int]:
        """Validate, then upsert: same name -> version+1 with counters
        preserved (FR-004); a fresh name starts at version 1."""
        reason = validate_skill(skill)
        if reason:
            raise ValueError(reason)
        now = _now()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE skills SET description=?, tier=?, workflow_json=?, "
                "version=version+1, updated_at=? WHERE name=?",
                (skill["description"], skill["tier"],
                 json.dumps(skill["workflow"], ensure_ascii=False), now,
                 skill["name"]))
            if cur.rowcount == 0:
                self._conn.execute(
                    "INSERT INTO skills (name, description, tier, workflow_json,"
                    " version, created_at, updated_at) VALUES (?,?,?,?,1,?,?)",
                    (skill["name"], skill["description"], skill["tier"],
                     json.dumps(skill["workflow"], ensure_ascii=False),
                     now, now))
            self._conn.commit()
        row = self._conn.execute("SELECT version FROM skills WHERE name=?",
                                 (skill["name"],)).fetchone()
        return skill["name"], row["version"]

    def get(self, name: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM skills WHERE name=?",
                                 (name,)).fetchone()
        return self._row_to_skill(row) if row else None

    def counts(self, name: str) -> tuple[int, int] | None:
        row = self._conn.execute(
            "SELECT success_count, failure_count FROM skills WHERE name=?",
            (name,)).fetchone()
        return (row["success_count"], row["failure_count"]) if row else None

    def record_feedback(self, name: str, outcome: str,
                        error_context: str | None = None) -> None:
        """Append one feedback row and move the counter in the SAME
        transaction (FR-008). Missing skill -> SkillNotFound, never an
        orphan row."""
        if outcome not in ("success", "failure"):
            raise ValueError(f"outcome must be success|failure, got {outcome!r}")
        with self._lock:
            if self._conn.execute("SELECT 1 FROM skills WHERE name=?",
                                  (name,)).fetchone() is None:
                raise SkillNotFound(name)
            self._conn.execute(
                "INSERT INTO skill_feedback (skill_name, outcome, error_context, ts)"
                " VALUES (?,?,?,?)", (name, outcome, error_context, _now()))
            column = "success_count" if outcome == "success" else "failure_count"
            self._conn.execute(
                f"UPDATE skills SET {column}={column}+1 WHERE name=?", (name,))
            self._conn.commit()

    def feedback_rows(self, name: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT outcome, error_context, ts FROM skill_feedback"
            " WHERE skill_name=? ORDER BY ts", (name,)).fetchall()
        return [dict(r) for r in rows]

    def consecutive_failures(self, name: str) -> int:
        """Current failure streak (newest last) — the escalation counter."""
        streak = 0
        for row in reversed(self.feedback_rows(name)):
            if row["outcome"] != "failure":
                break
            streak += 1
        return streak

    def slots_in(self, name: str) -> list[str]:
        """All {{placeholders}} a replay of this skill must fill."""
        skill = self.get(name)
        if not skill:
            return []
        found: list[str] = []
        for step in skill["workflow"]:
            text = json.dumps(step.get("params_template") or {},
                              ensure_ascii=False)
            for m in _SLOT_RE.finditer(text):
                if m.group(1) not in found:
                    found.append(m.group(1))
        return found
