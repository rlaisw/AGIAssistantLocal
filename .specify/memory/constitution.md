# AgenticRAG Constitution

## Core Principles

### I. Contract Preservation (NON-NEGOTIABLE)
Client-facing tool contracts — the `ask` response field set and MCP tool schemas — must stay backward-compatible: existing contract tests pass unchanged, new fields are additive, and any breaking change requires a spec amendment documenting the migration. Consumers (Dify chatflows, MCP hosts) must never break on a server upgrade.

### II. Tests-First
Every non-trivial behavior lands with its runnable check written before the implementation (unit / integration / contract, per `tests/` layout). The full suite must be green before any task is marked complete. Tests are never weakened to pass — fix the code, or fix a fixture that was genuinely dishonest.

### III. Minimal Dependencies
Reuse the ladder before adding anything: stdlib → platform → already-installed dependency → new dependency. Vendored third-party code carries its license header and a re-vendor upgrade path (see `routing/rl_agent_api.py`). New runtime services are a last resort and must degrade gracefully when absent.

### IV. Honest Answers (NON-NEGOTIABLE)
The system never fabricates. No evidence → "no relevant information was found". Budget exhaustion → low-confidence flag. Disabled features → explicit FeatureDisabled errors. Every routing decision carries provenance (`decision_node` | `fallback`) — there is no third value.

### V. Spec-Driven Replacement
Superseding work retires the old design, it does not deprecate it: old code paths are deleted (no dead code), the spec carries a Supersedes record, and the client contract is preserved field-for-field. Configuration for retired components is removed with them.

## Quality Gates

- 100% of the pytest suite green before commit (currently 1,245 unit/contract tests — count refreshed 2026-11-21 after repairing the stale ANTV/PPT count pins and restoring the research page cap; owner-present integration suites run separately)
- One runnable check per non-trivial behavior; deterministic tests (mocks at trust boundaries, no network in CI paths)
- Performance targets are measured, not assumed; success criteria are hardware-relative when measurement demands it (see SC-001 amendment, spec 002)

## Governance

- This constitution governs all `/speckit.*` commands; violations surface as CRITICAL convergence findings
- Amendments require documented rationale in the amending spec's Clarifications section
- Lazy engineering is the house style: shortest working diff, deletion over addition, YAGNI — never at the expense of Principles I and IV

**Version**: 1.0.2 | **Ratified**: 2026-10-08 | **Last Amended**: 2026-10-24 (Quality Gates test-count refresh only)
