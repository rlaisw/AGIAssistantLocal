"""Spec 037 — the scripted lane: script registry + args validation + the
run executor + per-step checkpoint verification (research R1/R2).

Scripts are FILES (scripts/browser/<name>.py) carrying data headers
(# name/version/params/expect) + a Playwright body. Data is validated at
registry load; bodies never carry credentials or machine-specific paths.
Execution runs Windows-side via the existing hermes channel; the script
emits one JSON line per step, verified against `expect` in order."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_HEADER_RE = re.compile(r"^#\s*(name|version|params|expect)\s*:\s*(.+)$")
# credential-looking literals never enter a script body (FR-006)
_CRED_LITERALS = (
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[=:]\s*['\"][^'\"]{4,}"),
)
# machine-specific paths never enter a body (SC-005 discipline, 036 regexes)
_MACHINE_LITERALS = (
    re.compile(r"[A-Za-z]:[\\\\]+Users[\\\\]+"),
    re.compile(r"%(USERPROFILE|APPDATA|LOCALAPPDATA)%", re.IGNORECASE),
    re.compile(r"/home/[a-z]"),
    re.compile(r"/Users/"),
)


class ScriptNotFound(LookupError):
    """Explicit missing script — never a fabricated run."""


@dataclass
class _Script:
    name: str
    version: int
    params: dict
    expect: list
    path: Path


def validate_script_file(path: Path) -> dict:
    """Registry-boundary validation (data-model rules). Raises ValueError
    naming the offending field; returns the parsed script record."""
    text = path.read_text(encoding="utf-8")
    headers: dict[str, str] = {}
    body_lines: list[str] = []
    for line in text.splitlines():
        m = _HEADER_RE.match(line.strip()) if line.strip().startswith("#") else None
        if m:
            headers[m.group(1).lower()] = m.group(2).strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines)
    name = path.stem
    if not _NAME_RE.match(name) or headers.get("name") != name:
        raise ValueError(
            f"rejected: name — file {path.name} must carry '# name: {name}' "
            f"(snake_case, matching the filename); got {headers.get('name')!r}")
    try:
        version = int(headers.get("version", ""))
    except ValueError:
        raise ValueError(f"rejected: version — {path.name} needs an int '# version:'")
    try:
        params = json.loads(headers.get("params") or "null")
        expect = json.loads(headers.get("expect") or "null")
    except json.JSONDecodeError as exc:
        raise ValueError(f"rejected: params/expect — {path.name}: {exc}")
    if not isinstance(params, dict) or not params:
        raise ValueError(f"rejected: params — {path.name} needs a non-empty "
                          "JSON object of {{slot: description}}")
    if not isinstance(expect, list) or not expect or \
            not all(isinstance(e, str) and e.strip() for e in expect):
        raise ValueError(f"rejected: expect — {path.name} needs a non-empty "
                          "JSON list of per-step checkpoints (FR-005)")
    for lit in _CRED_LITERALS:
        if lit.search(body):
            raise ValueError(f"rejected: credential-looking literal in "
                             f"{path.name} body ({lit.pattern!r}) — pass "
                             "credentials as run args, never baked in (FR-006)")
    for lit in _MACHINE_LITERALS:
        if lit.search(body):
            raise ValueError(f"rejected: machine-specific literal in "
                             f"{path.name} body ({lit.pattern!r}) — use "
                              "{{placeholder}} args (SC-005 discipline)")
    return {"name": name, "version": version, "params": params,
            "expect": expect, "path": path}


class ScriptRegistry:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._scripts: dict[str, _Script] = {}
        for path in sorted(self.root.glob("*.py")):
            try:
                rec = validate_script_file(path)
            except ValueError:
                continue  # invalid scripts never enter the routing surface
            self._scripts[rec["name"]] = _Script(**{
                **rec, "path": rec["path"]})

    def names(self) -> list[str]:
        return list(self._scripts)

    def get(self, name: str) -> _Script:
        if name not in self._scripts:
            raise ScriptNotFound(name)
        return self._scripts[name]

    def resolve_args(self, name: str, args: dict) -> dict:
        """Validate args against the script's params schema: missing slot ->
        ask-back naming {{slots}}; extra arg -> named rejection (FR-004/006)."""
        script = self.get(name)
        declared = set(script.params)
        given = set(args or {})
        missing = declared - given
        extra = given - declared
        if missing:
            return {"status": "ask-back",
                    "reason": ("missing values for: "
                               + ", ".join(f"{{{{{k}}}}}" for k in sorted(missing))
                               + " — ask the user; never guess a substitution")}
        if extra:
            return {"status": "ask-back",
                    "reason": ("extra values not in this script's params ("
                               + ", ".join(sorted(extra))
                               + "); pass only the declared slots")}
        return {"status": "ok", "args": dict(args)}


def verify_steps(steps: list[dict], expect: list[str]) -> dict:
    """Per-step checkpoint verification (FR-005): each emitted step must be
    ok AND its summary must mention the ordered checkpoint; the first
    failure aborts naming the step — never a fabricated completion."""
    for i, (step, checkpoint) in enumerate(zip(steps, expect), start=1):
        summary = str(step.get("summary", ""))
        ok = bool(step.get("ok")) and \
            " ".join(checkpoint.lower().split()) in \
            " ".join(summary.lower().split())
        if not ok:
            return {"status": "aborted",
                    "reason": (f"checkpoint mismatch at step {i}: expected "
                               f"'{checkpoint}' — got '{summary[:200]}'; the "
                               f"run stops honestly (no forcing the script)"),
                    "completed_steps": i - 1}
    if len(steps) != len(expect):
        return {"status": "aborted",
                "reason": (f"the script emitted {len(steps)} steps but "
                           f"{len(expect)} checkpoints were declared — the "
                           "run stops honestly"),
                "completed_steps": min(len(steps), len(expect))}
    return {"status": "completed", "completed_steps": len(steps),
            "steps": steps}


def parse_step_lines(output: str) -> list[dict]:
    """Structured stdout discipline: one JSON object per line (research R2);
    non-JSON lines are ignored, never parsed as console soup."""
    steps = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            steps.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return steps