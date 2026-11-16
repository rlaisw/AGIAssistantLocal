---
description: "Task list for the Reliability Monitor applet (042)"
---

# Tasks: Reliability Monitor applet (042-reliability-monitor-applet)

**Input**: Design documents from `specs/042-reliability-monitor-applet/` (plan.md, spec.md, research.md, data-model.md, contracts/reliability-target.md, quickstart.md)

**Tests**: INCLUDED — the house tests-first pattern (quickstart.md part A); written red before implementation.

**Organization**: One user story (US1: open Reliability Monitor by name) — the smallest lifecycle in the project, on a lane proven across 34 surfaces and two bug fixes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependencies)
- Exact file paths in every description

---

## Phase 1: Setup

- [X] T001 Add the reliability-monitor entry to the reviewed inventory in `src/agentic_rag_mcp/windows_mcp/targets.py` — key "reliability monitor" with synonyms "reliability history" and "stability monitor" (all resolve to the same entry; natural-phrasing aliases follow the installed-programs precedent, 2026-11-16)

---

## Phase 2: US1 - Open Reliability Monitor by name (Priority: P1) 🎯 MVP

**Goal**: "open the reliability monitor" opens the Reliability Monitor window on the owner's desktop via the live-verified launch form.

**Independent Test**: quickstart.md — resolution pins green; the live E2E shows a "Performance Monitor" mmc window in the interactive session < 15 s desktop-quiet; the 34 existing targets keep resolving (regression).

### Tests for US1 (write first, expect red)

- [X] T002 [P] [US1] Unit pins in `tests/unit/test_windows_mcp_applets.py`: "reliability monitor", "reliability history", and "stability monitor" all resolve to the one target; the launcher pins the mmc-hosted form `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` (the regression pin: the plain `perfmon /rel` form silently exits from the service's context — research R1 — and must never return)

### Implementation for US1

- [X] T003 [US1] Add the per-host launch branch in `src/agentic_rag_mcp/windows_mcp/open.py` — the reliability-monitor target launches via the live-verified `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'` form, alongside the existing `.msc`-direct, `.cpl`, and Settings-page forms (T002 goes green)
- [X] T004 [US1] Live E2E per quickstart.md: "open the reliability monitor" through the chat tool path → `{status: ok}` < 15 s desktop-quiet, a "Performance Monitor" mmc window confirmed in the interactive session, the `windows-mcp-open` executed audit row present; plus one ask-back check ("open the reliability thingamajig" → the 35-surface list) and one regression spot-check (an existing target still opens)

**Checkpoint**: the 35th surface works end-to-end.

---

## Phase 3: Polish & Cross-Cutting Concerns

- [X] T005 Full battery: `pytest tests/unit` green (715+), `ruff check` clean on touched files, `deploy redeploy` (the entry ships in the image; no tool-count change, no DSL publish needed)
- [X] T006 Commit and push the feature (lifecycle-style message; working tree clean)

---

## Dependencies & Execution Order

- **T001 → T002 → T003 → T004** sequential (the pins reference the entry; the E2E needs the implementation); **T005 → T006** after T004.
- No parallel opportunities inside the story (single-file, three-line-scale changes); T002 is marked [P] only because the test file is disjoint from the implementation file once the entry exists.

---

## Implementation Strategy

### MVP First

1. T001 (the entry) → T002 red → T003 green → T004 live — the whole feature; STOP and VALIDATE: the window opens, the pins hold, the 34-target regression is clean.

---

## Notes

- The launch form is decided (research R1, live-A/B): `Start-Process mmc.exe -ArgumentList 'perfmon.msc','/rel'`. Do not re-litigate; do not use plain `perfmon /rel` — it silently exits from the service's context on this build (verified: `HasExited: True`, no crash event).
- The window titles as "Performance Monitor" (Reliability is the `/rel` view) — the E2E window check matches the title, and the relay claims the window opened, never the chart's readiness.
- No DSL publish: the tier-1 rule covers any name on the reviewed list by construction.
- The desktop-activity deferral (hands-off ~10 s) applies to the live E2E as to every target.
