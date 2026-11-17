import { describe, expect, it } from "vitest"
import { PREAMBLE_CHAR_CAP, buildPreamble } from "./preamble"

const part = (over: Partial<Parameters<typeof buildPreamble>[0]> = {}) => ({
  name: "report.pdf",
  type: ".pdf",
  chars: 120,
  text: "RELIABILITY_CHECK_42",
  truncated: false,
  ...over,
})

describe("attachment preamble", () => {
  it("carries provenance, content, and the question", () => {
    const out = buildPreamble(part(), "what does it say?")
    expect(out).toContain("[Attached file: report.pdf (.pdf, 120 characters extracted)]")
    expect(out).toContain("RELIABILITY_CHECK_42")
    expect(out).toContain("[End of attached file content]")
    expect(out).toContain("User question: what does it say?")
  })

  it("uses (analyze this file) when the question is empty", () => {
    const out = buildPreamble(part(), "   ")
    expect(out).toContain("User question: (analyze this file)")
  })

  it("carries the extraction note in the header", () => {
    const out = buildPreamble(part({ note: "no readable text (OCR is not enabled)" }), "x")
    expect(out).toContain("[Note about this file: no readable text (OCR is not enabled)]")
  })

  it("does not truncate at exactly the cap", () => {
    const out = buildPreamble(part({ text: "a".repeat(PREAMBLE_CHAR_CAP) }), "q")
    expect(out).not.toContain("content truncated")
    expect(out).toContain("a".repeat(PREAMBLE_CHAR_CAP))
  })

  it("truncates one char past the cap with the marker named", () => {
    const out = buildPreamble(
      part({ text: "a".repeat(PREAMBLE_CHAR_CAP + 1), chars: PREAMBLE_CHAR_CAP + 1 }),
      "q"
    )
    expect(out).toContain("content truncated at 24,000 characters")
    const content = out.split("\n").filter((l) => /^a+$/.test(l)).join("")
    expect(content.length).toBe(PREAMBLE_CHAR_CAP)
  })
})