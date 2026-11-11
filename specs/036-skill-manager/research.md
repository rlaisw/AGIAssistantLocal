# Research: Skill Manager (spec 036)

**Spec**: 036 | **Date**: 2026-11-11 | **Status**: resolved (inherits 035 R1–R3; this file adds the component-specific decisions)

## R1: Where the search index lives (inherits 035 R1, now concrete)

- **Decision**: `Embedder` (`search/embeddings.py`, sentence-transformers) embeds `"{name}\n{description}"` per skill; vectors indexed in a dedicated LanceDB table (`skills`) beside the knowledge-base store; `skill_search` = embed(intent) → ANN top-k → SQLite trust join. Re-embed on save/update only (v1: brute-force scan acceptable at <10k skills; ANN via LanceDB is free since the wrapper exists).
- **Rationale**: zero new dependencies (Constitution III), one embedding path for the whole system, and the intent→skill match is exactly the same shape as the existing vector search.
- **Alternatives considered**: Chroma as proposed in the original diagram (rejected: second vector store beside LanceDB buys nothing); keyword FTS (rejected in 035 R1: intent vocabulary drift).

## R2: The store — SQLite shapes (inherits 035 data model)

- **Decision**: Two tables. `skills(name TEXT PRIMARY KEY, description TEXT NOT NULL, tier INTEGER NOT NULL CHECK(tier IN (1,2)), workflow_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, created_at TEXT, updated_at TEXT)`. `skill_feedback(skill_name TEXT, outcome TEXT CHECK(outcome IN ('success','failure')), error_context TEXT, ts TEXT, PRIMARY KEY(skill_name, ts))` — rowid ordering for append semantics. WAL mode; the DB file lives beside the audit log (`~/.config/agentic-rag-mcp/hermes-mcp/`) so the existing bind-mount persists it.
- **Rationale**: same-name update is a PK upsert (FR-006/036), trust is two integers and a WHERE clause, feedback is append-only with a composite key. No ORM (Constitution III).
- **Alternatives considered**: JSON file store (rejected: no transactional upsert, corruptible mid-save); LanceDB for everything (rejected: it is a vector store, not a source of record).

## R3: Workflow template grammar (inherits 035 R2)

- **Decision**: `workflow_json` is `[{step, tool, service, params_template, expect}]`; `params_template` values carry `{{snake_case}}` slots; a save-time validator rejects (a) machine-specific literals matching `C:\Users\`, hostnames, `/mnt/c/...`-style absolute host paths, (b) steps missing `expect`, (c) non-snake-case names, (d) empty descriptions. Substitution at replay: `{name → value}` map built from the user's live request by the executor (the agent fills it from the request text; an unfilled slot is an honest ask-back).
- **Rationale**: validation at the boundary makes SC-005/FR-005 testable table-driven; `{{}}` is the least grammar that round-trips.
- **Alternatives considered**: JSON Schema per step (deferred: the 4-field shape is closed for v1); free text (rejected in 035 R2).

## R4: Replay executor vs the gates (035 FR-020 made mechanical)

- **Decision**: `executor.py` walks steps; for each step it resolves the service the same way the lanes do and calls the **existing** tool handlers (`hermes_run_powershell` draft→confirm, office task, run_command…). A step whose target tool is confirm-gated pauses the walk (returns `pending-confirmation`), and the confirm resumes at the next step — the pending draft rides the **existing** `hermes_powershell_state` (conversation-scoped), NOT a new state store. A cancelled confirm clears the draft (existing rules) and aborts the walk without marking feedback failure for the skill.
- **Rationale**: reusing the live gates means FR-020 is true *by construction* — there is no code path that executes a gated step without the live confirm, so A3 is a structural test, not a behavioral hope. Reusing the pending-draft state avoids a second source of confirm truth.
- **Alternatives considered**: executor-side confirm state (rejected: two pending-draft stores would drift); snapshot-and-replay the confirmed skill step (rejected: that IS the pre-confirmation FR-020 forbids).

## R5: The four tools and the Dify wiring

- **Decision**: MCP tools `skill_search(intent, conversation_id)` → `{found, skills:[{name, description, success_rate, sample, reusable}]}` (reusable pre-computed so the lane decision is mechanical); `skill_get(name)` → full record or explicit not-found; `skill_save(skill)` → validated, upserted, `{name, version}`; `skill_feedback(skill_name, outcome, error_context?)` → `{acknowledged}`. All four require `conversation_id` (house pattern), audit as `operation=skill-{search|get|save|feedback|replay-start|replay-abort}`, and carry the timing profile. The DSL gains the skill-loop rules in the Hermes lane instructions + a General-lane exclusion (questions never search).
- **Rationale**: trust pre-computation keeps FR-002 decisions out of the model; `reusable` is data, not vibes (Constitution IV). The Dify `tool_mcp_providers` rebuild + api/worker restart applies to all four.
- **Alternatives considered**: `skill_replay` as a 5th tool (rejected: replay is the lane's existing tool sequence driven by the executor through normal handlers — a dedicated tool would duplicate the gates); two-phase for `skill_save` (rejected: saves create data, they don't mutate machines).

## R6: Degradation and the "unavailable" boundary

- **Decision**: every store call is try/except → honest `error:skill-store-unavailable` envelope naming the outage; the lane instructions then route manually and say so in the answer. Search miss is `{found:false, skills:[]}` — distinguishable from outage by envelope, never a fabricated "found nothing" that masks a down store.
- **Rationale**: FR-013/036 requires the split; collapsing outage into miss would violate Honest Answers (Constitution IV).
- **Alternatives considered**: retry-with-backoff inside the tool (rejected: one honest error up front beats a hung turn; the agent retries naturally).

**All NEEDS CLARIFICATION resolved; none remain.**