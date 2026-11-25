# Phase 0 Research — Image-Rich Chat Answers

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-25

All decisions below are grounded in the checked-in codebase; the owner-supplied TRANSFER reference is treated as evidence of what worked elsewhere, not as a specification to copy.

## D1 — Where the image data lives: additive projection, not a new tool

- **Decision**: Extend `web_research` hits with `images: [{url, alt, heading}]`; keep `fetch_url.images` as `list[str]`.
- **Rationale**: Hits already carry `scrape.sections`; a projection keeps one source of truth and cannot drift in position. Existing fields stay untouched (constitution I). A new dedicated tool would add a call, latency, and a second extraction path.
- **Alternatives**: (a) tell the model to parse `render_html` — token-expensive and error-prone; (b) return only section blocks — the model must then walk nested structures; (c) new `web_images` tool — rejected: extra round trip, duplicate fetch.

## D2 — Alt text is captured at extraction, never synthesized

- **Decision**: `extract_sections` adds `alt: (img.get("alt") or "").strip()` to each `{"type": "img"}` block; `flatten_images` copies it. Empty when the source has none.
- **Rationale**: The source's own description is the only non-fabricated description; the model derives a visible alt from surrounding text when the source is silent (FR-010, constitution IV).
- **Alternatives**: OCR/captioning (new dependency, out of scope), alt from surrounding paragraph (changes the source's claim — rejected), omitting alt (fails accessibility and SC-006).

## D3 — One shared noise list, one ordering rule

- **Decision**: Share the tracker/noise substring list between `_fetch_url` (server.py) and the new `flatten_images` (research.py): `pixel, tracker, beacon, spacer, 1x1, blank.gif`. Dedupe by absolute URL while iterating sections in document order; cap at 40.
- **Rationale**: Two divergent noise lists would let the same page produce different image sets through different tools (inconsistent model behavior, worse tests).
- **Alternatives**: Per-tool lists (drift), regex classification (overkill), no cap (payload/log blow-through on gallery pages).

## D4 — Prompt placement and scope

- **Decision**: One binding block replaces the current soft `ANSWER FORMAT — IMAGES (default)` after `Never invent facts.` and immediately before `ANSWER FORMAT — CITATIONS:`, in `Agentic Strategy` and `Agentic Strategy (Local)` only. Hermes and both PPT-Master prompts unchanged (clarified: general lanes only).
- **Rationale**: The prompts are duplicated per lane inside the DSL; editing one copy is a known silent-divergence bug (spec 045 precedent). The policy must precede citations so the model plans images before formatting sources.
- **Alternatives**: Post-answer reminder (too late), tool description wording (weaker than instruction), editing only the cloud lane (fails FR-016).

## D5 — Deterministic cap placement

- **Decision**: Add `capInlineImages` inside the existing `honesty_check` code node and apply it on the node's normal answer returns. It counts only images outside `…` blocks and skips `/mcp-action/screenshots/` URLs; it trims the 11th+ image markdown and collapses the resulting blank-line debris.
- **Rationale**: The node already owns the user-visible answer (`visible`) and final text mutation; a second node would add graph complexity. The chat UI hides think blocks, so reasoning images must be invisible to the counter as well (FR-011, FR-017).
- **Alternatives**: New code node (more edges, more publish surface), prompt-only cap (model-enforced, drifts), server-side rewrite (server cannot see the model's answer without new plumbing; also out of scope).

## D6 — Error handling decided up front

- **Decision**: Every image-related failure degrades to an explicit empty/honest state:
  - extraction: malformed/`data:`/non-http src skipped; unparseable page ⇒ `sections: []` (existing, no exception);
  - projection: any non-`ok` scrape ⇒ `images: []` (present, never `null`);
  - payload: 40-image cap, document order;
  - answer: no source images ⇒ text-only + explicit statement; dead URL ⇒ alt still describes the image;
  - finalizer: unbalanced think tags clamp depth at 0; screenshot routes exempt; text preserved.
- **Rationale**: The constitution forbids fabrication and silent omission; an empty list with a reason is honest, a missing field is a contract break.
- **Alternatives**: Raising on bad pages (breaks multi-page research), omitting the field when empty (contract break, model cannot distinguish "none" from "old payload"), counting screenshots (would delete health-check evidence).

## D7 — Verification strategy

- **Decision**: Three layers — (1) pytest unit/contract pins incl. executing the finalizer's JS with the existing `node -e` pattern; (2) a new CDP acceptance script that counts rendered `<img>` elements per answer and asserts alt presence/cap/no-image cases; (3) the four owner-facing live prompts from the handoff (how-to ≥3, overview ≥2 not clustered, gallery 1–10, capital-of-France 0) run in fresh conversations on both apps.
- **Rationale**: Unit pins catch payload/prompt/finalizer regressions; CDP proves the user-visible result; live prompts prove model behavior, which no static test can.
- **Alternatives**: Prompt-text assertions only (does not prove behavior), snapshot tests of HTML (brittle), manual-only checks (not repeatable).

## D8 — Deployment and publish safety

- **Decision**: Rebuild the sidecar (`redeploy`) for the payload change, then `deploy chatflow` publishes the prompt graph; verify both apps by explicit ID and confirm the new prompt marker in Postgres per app. The mirrored twin must be verified separately because name-based publish is nondeterministic.
- **Rationale**: Existing repo knowledge: identically named apps + name-based publish = silent wrong-target deploys; the `images` field only exists in the rebuilt container.
- **Alternatives**: Name-based `deploy all` (known unsafe here), hand-editing the console (repo has been reverted by console edits before).

## D9 — Out of scope (kept)

Knowledge-base document answers, chat attachments, server-side captioning/vision, a UI fallback for dead images, and any change to Hermes/PPT-Master answer policy (clarified).
