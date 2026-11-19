# Feature Specification: Ask before answering — request critical missing information

**Feature Branch**: `045-ask-before-answering`

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: 'add System Prompt — "Before answering the user''s question, ask for any critical missing information." (intent confirmed in conversation, 2026-11-19)'

## Clarifications

### Session 2026-11-19

- Q: Where does the rule live and what does it cover? → A: the **AGI Chat's system prompt** (the chatflow's steering text, the same surface family as spec 044's infographic default): before answering, the assistant must ask for any **critical** missing information instead of guessing. It generalizes ask-back behavior to the whole chat — including the General/knowledge lane, which today answers directly.
- Q: How does it relate to the existing lane ask-backs? → A: it **complements** them. The lane-specific gates (ambiguous program-launch target, Office unsaved-changes, email compose confirmation) remain authoritative in their domains — the general rule must not weaken, duplicate, or double-ask on top of them.
- The **"critical" qualifier is central** (owner's own wording): only information that materially changes the answer, or that gates a safe/meaningful action, is worth a question. Without it the chat would interrogate on every simple question.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Underspecified requests get a targeted question, not a guess (Priority: P1)

The owner sends an actionable request with a critical gap: "back up my files", "email John about the meeting", "what's the error in my log?". Instead of acting on an assumption or fabricating the missing piece, the assistant's **first response asks for exactly the missing information** — which files and where to, which John and what the draft should say, which log and timeframe — and nothing else happens until the owner answers.

**Why this priority**: This is the entire directive — the guess-free first turn.

**Independent Test**: an underspecified actionable ask; assert the first response contains a targeted question and performs no action/answer.

**Acceptance Scenarios**:

1. **Given** an actionable request with a critical gap, **When** sent, **Then** the first response asks for the missing piece (targeted, minimal — not an interrogation) and does not act or answer on an assumption.
2. **Given** the owner's answer to the ask-back, **When** received, **Then** the next response answers or acts immediately — no second round of questions unless a genuinely new critical gap opens.

---

### User Story 2 - Complete questions still answer directly (Priority: P2)

Fully-specified questions and requests answer in one turn with **zero clarifying questions**: "what is the capital of France", "back up C:\temp\reports to C:\temp\backup", "summarize this file: [attached]". The rule never fires when nothing critical is missing — over-asking is treated as a defect of the rule, not a feature.

**Why this priority**: A clarifying-question rule without a strict "critical" gate makes the chat exhausting; the owner's wording pins the qualifier and this story enforces it.

**Independent Test**: a battery of complete questions; assert one-turn direct answers with no clarifying question.

**Acceptance Scenarios**:

1. **Given** a complete, self-sufficient question, **When** sent, **Then** the answer arrives directly — no clarifying question precedes it.
2. **Given** a request where the chat can act safely with stated context already known (including earlier turns of the same conversation), **When** sent, **Then** it does not re-ask what the conversation already established.

---

### User Story 3 - The rule coexists with the existing gates, honestly (Priority: P3)

Where a lane already asks back through its own gate — an ambiguous launch target, unsaved Office changes, an email draft awaiting confirmation — the flows stand unchanged: no double-ask, no weakened gate. And the rule never invites fabrication: the assistant asks rather than inventing the missing information, consistent with the anti-fabrication law that already governs the chat.

**Why this priority**: The chat has audited, established ask-back behavior; the new rule must integrate without regressing it.

**Independent Test**: re-run the existing lane acceptance probes (launch ambiguity, office ask-backs) and one fabrication-prone ask; assert gates intact, no double-asks, no invented details.

**Acceptance Scenarios**:

1. **Given** a prompt that a lane gate already handles with its own ask-back, **When** sent, **Then** the lane's ask-back appears as designed — the general rule adds nothing on top.
2. **Given** a request whose missing info the assistant cannot know, **When** answering, **Then** it asks — it never presents invented details as if known.

---

### Edge Cases

- Ambiguity with a reasonable, low-stakes default: the assistant may answer while naming the assumption in one sentence — only a *materially changing* gap triggers the question (the "critical" test).
- Multi-part requests with one missing piece: ask only about that piece, not about every part.
- Several distinct critical gaps at once (target AND content): a minimal set of questions in one response is acceptable — never a long interrogation.
- Information present in earlier conversation turns is not missing — the chat uses it without re-asking.
- The ask-back itself must be answerable by the owner: no requests for credentials, secrets, or private keys as "missing information" (operationally required details only; secrets stay in their configured places).
- Attachment-bearing requests follow spec-043 rules unchanged (the attached content is context; missing-critical-info questions can still occur around it).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Before answering or acting, the assistant MUST evaluate whether any **critical** information is missing — critical being information without which the answer or action materially changes, becomes unsafe, or is meaningless.
- **FR-002**: When critical information is missing, the first response MUST ask a targeted, minimal question (or minimal set) for exactly that information — before any answer or action — and MUST NOT invent, assume silently, or fabricate the missing information (anti-fabrication law).
- **FR-003**: When no critical information is missing, the assistant MUST answer or act directly in the same turn, with no clarifying question; systematic over-asking is a violation of this requirement, not an acceptable reading of the rule.
- **FR-004**: Information already present in the conversation (including earlier turns and attached-file content) MUST be treated as known and MUST NOT be re-asked.
- **FR-005**: The rule MUST NOT weaken, duplicate, or conflict with the existing lane-specific ask-back gates (program-launch ambiguity, Office unsaved-changes, email compose confirmation, never-list refusals); those flows remain authoritative and unchanged.
- **FR-006**: The rule lives in the chatflow's steering surface (system prompt) as an additive directive — no tool schema, code, or contract change (Constitution I).

### Key Entities

- **Critical missing information**: the test in FR-001 — materially changes the answer/action, gates safety, or makes the request meaningless. Judgment is the assistant's, guided by this definition; acceptance is measured by behavior.
- **Targeted ask-back**: the first response's minimal question set for exactly the missing pieces — distinct from the existing lane gates, which keep their own authoritative ask-back forms.
- **The existing lane gates** (unchanged): launch-target ambiguity, Office unsaved-changes, email confirmation — the rule complements, never overrides.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Underspecified actionable asks ("back up my files") yield a targeted clarifying question in the first response with no action or guessed answer — 10/10 over a probe battery of distinct phrasings.
- **SC-002**: Complete, self-sufficient questions answer directly with zero clarifying questions — 10/10 over a probe battery (including knowledge questions and fully-specified actions).
- **SC-003**: The existing lane acceptance battery (Hermes launch ask-backs, Office ask-backs, email confirmation) stays green with no double-asks introduced — 0 regressions.
- **SC-004**: Multi-turn coherence: after the owner supplies the missing information, the next response answers or acts without re-asking — verified on at least three probe threads.

## Assumptions

- The rule is steering-text-only in the chatflow's system prompt (both agent prompt surfaces, both nodes — the spec-044 pattern), published via the established `deploy chatflow` path, verified against the served DSL.
- "Critical" is the assistant's judgment guided by FR-001's definition; acceptance is measured behaviorally via probes (SC-001/SC-002), not by inspecting internal reasoning.
- The rule's wording keeps the owner's sentence as the headline directive, with the critical-qualifier definition and the no-over-asking clause as supporting sentences.
- No Supersedes — additive over the existing chat behavior; the anti-fabrication law and honesty nodes are untouched and reinforced by FR-002.
