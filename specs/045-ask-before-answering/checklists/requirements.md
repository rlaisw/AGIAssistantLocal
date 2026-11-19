# Specification Quality Checklist: Ask before answering — request critical missing information

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-19
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — steering surface named only as the feature's location (same as spec 044's pattern); no code/schema language
- [x] Focused on user value and business needs — guess-free first turns without over-asking
- [x] Written for non-technical stakeholders — ask/answer/gate language throughout
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain — the two decisive questions (where the rule lives; relation to lane gates) were answered in conversation before drafting; the critical-qualifier semantics come from the owner's own wording
- [x] Requirements are testable and unambiguous — each FR maps to a behavioral probe (first-response question, direct answer, no re-ask, gates green)
- [x] Success criteria are measurable — 10/10 probe batteries, 0 regressions, 3-thread multi-turn check
- [x] Success criteria are technology-agnostic — phrased as chat behavior, no stack names
- [x] All acceptance scenarios are defined — three stories, each independently testable
- [x] Edge cases are identified — low-stakes defaults, multi-part, multi-gap, conversation memory, secrets exclusion, attachments
- [x] Scope is clearly bounded — additive steering only; existing gates authoritative; attachments/lane flows unchanged
- [x] Dependencies and assumptions identified — steering-only placement, judgment-vs-behavior measurement, publish path, no Supersedes

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows — ask-first, no-over-ask, gate coexistence
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- FR-003 makes over-asking a violation (not just an unmet nicety) — the owner's "critical" qualifier is the load-bearing word; implementation probes must include an over-asking battery (SC-002).
- Items marked incomplete require spec updates before `/speckit.clarify` or `/speckit.plan`
