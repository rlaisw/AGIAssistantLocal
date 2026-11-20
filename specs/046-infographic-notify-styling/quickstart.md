# Quickstart — 046-infographic-notify-styling

Runnable validation plan. Prerequisites: the stack healthy (`./startup.sh`), `pnpm dev` on `:3000`, CDP Chrome on `:9240`. Implement in this order: unit pins red → helper green → renderer branch → V1–V3.

## V0 — Unit pins, red then green

```bash
cd ai-chat-landing
pnpm test -- lib/infographic-link.test.ts
```

Expected:

- Before `lib/infographic-link.ts` exists, the new test fails RED.
- After the helper is implemented, all URL and sanitizer pins pass.
- Do not change tests to make a broken implementation pass.

## V1 — Live notification-link check (SC-001/SC-002)

```bash
node scripts/infographic-link-check.mjs
```

The script asks the model to echo an infographic markdown link, then asserts in the real Chat UI:

- The link exists and its text starts with **📌**.
- The existing label wording is preserved.
- `getComputedStyle(link).color` equals the computed color of a probe with `text-blue-600 dark:text-blue-400`.
- The link retains `target="_blank"` and its original `/infographics/` `href`.
- The styled link appears during streaming and persists after completion (E5).

Expected: all assertions green.

## V2 — Neighbor and error-path checks (SC-003 + E1/E2/E3/E4/E7)

The same script checks:

- A plain Apple support link has **no** 📌 and no infographic class (E1).
- An old-wording infographic link is still 📌 + blue (E4).
- A nested markdown label renders as content, not `[object Object]` (E2).
- A model-emitted leading 📌 does not produce `📌📌` (E3, also unit-pinned).
- Multiple infographic links each receive exactly one renderer-owned pin (E7).
- Inline images and the deck action bar still render normally; the follow-up line keeps 💡 + blue.

## V3 — Stored-text/export and full-suite gates

- Check the Dify message row for the probe answer: the answer text contains no renderer-added 📌 (E8).
- Run:

```bash
pnpm typecheck
pnpm lint
pnpm test
```

Expected: typecheck clean, lint has no new errors, and the full vitest suite remains green (175+ tests).

## Notes

- The color assertion deliberately compares against the follow-up token pair rather than an `rgb()` literal because current Chrome may serialize colors as `lab()`.
- No Dify app or prompt change is part of validation; if one is needed, the implementation is out of scope.
