# Data Model: Hermes Program Launch Lane

**Feature**: specs/029-hermes-launch-programs/spec.md · Supersedes 028 US3 for launches · 2026-11-01

## Entities

### LaunchRequest

The user's launch intent after the gate's normalization.

| Field | Type | Rules |
|-------|------|-------|
| target | str | One application name (no extension, no separators) OR one full executable path ending `.exe` (Windows `C:\…` or host `/mnt/c/…` style, both normalized to the host form; mixed separators and drive-letter case tolerated) |
| kind | `name` \| `path` | `path` requires the `.exe` suffix post-normalization |
| sanitized_task | str | The single clean instruction passed downstream ("launch <target>") — never contains arguments or shell text (those force a refusal instead) |

**Validation (gate, in order)**: launch verb present → fillers stripped → target extracted → no target = ask-back; script/shortcut suffix (`.bat/.cmd/.ps1/.lnk/.vbs/.js/.msi/…`) = blocked (executables-only rule); argument patterns (`--x`, `/x`, `k=v`, quoted arg strings, `;`\|`&` chaining) or shell phrasing anywhere = blocked (no-arguments rule); two targets = ask-back (one per request, never both).

### LaunchVerdict

The gate's decision — the only signal that may reach the Hermes client.

| Field | Type | Values |
|-------|------|--------|
| decision | `ok` \| `blocked` | blocked never produces a client call |
| operation | str | `launch-app` (also the audit operation value) |
| target | str \| None | the extracted target (canonical form for paths) |
| kind | `name` \| `path` \| None | |
| reason | str \| None | user-readable, names the violated rule (executables-only / no-arguments / ask-back) and — for ask-backs — asks which application |

### Tool envelope (MCP `hermes_launch_app`)

`{status: ok|blocked|error, decision?: executed|blocked, result?: str, reason?: str, target?: str}` — `result` present iff ok (the agent's report of what it observed: started / already running-activated / details); `reason` present iff blocked/error (names the rule or the failure + recovery hint). `ok` requires the agent's explicit `LAUNCH: SUCCESS` attestation line — a `LAUNCH: FAILED` report or a missing attestation is `error`. Additive to the existing 24-tool surface; no existing schema changes.

### AuditEntry (launch)

One JSONL line per attempted launch via the existing `HermesAudit` writer — fields unchanged:

| Field | Value for launches |
|-------|--------------------|
| ts | UTC ISO-8601 (seconds) |
| decision | `executed` \| `blocked` \| `error` |
| operation | `launch-app` |
| normalized_path | the target (name as-typed, or canonical path) |
| allowed_root | `""` (no containment root applies) |
| outcome \| reason | executed → the agent's report (truncated); blocked/error → the reason |

**Invariants**: exactly one entry per attempt, written at the tool's single verdict point (executed entries post-completion — a mid-launch stop never erases the truth); append-only, never rewritten or pruned by the lane (FR-006, FR-012).

## State transitions

`prompt → LaunchRequest (gate) → LaunchVerdict → [blocked: audit+answer] | [ok: Hermes client → agent observes (started | already-running | failed) → audit executed/error → honest envelope]`

No lane-side state persists between calls — stateless client, `store:false` (FR-007 of 028 holds by construction).
