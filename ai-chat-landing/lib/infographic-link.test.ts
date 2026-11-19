import { describe, expect, it } from "vitest"

import {
  infographicDisplayLabel,
  isInfographicLink,
} from "@/lib/infographic-link"

describe("isInfographicLink (spec 046 — target-based detection)", () => {
  it("accepts the sidecar's absolute infographic page URLs", () => {
    expect(isInfographicLink("http://localhost:28080/infographics/e468aaee5ee3/")).toBe(true)
  })

  it("accepts relative infographic URLs", () => {
    expect(isInfographicLink("/infographics/0f9a5e920f00/")).toBe(true)
  })

  it("accepts infographic URLs carrying query strings", () => {
    expect(isInfographicLink("http://localhost:28080/infographics/abc123/?x=1")).toBe(true)
  })

  it("rejects deck download links", () => {
    expect(isInfographicLink("http://localhost:28080/exports/deck.pptx")).toBe(false)
  })

  it("rejects deck page links", () => {
    expect(isInfographicLink("http://localhost:28080/decks/mydeck/mydeck_1/")).toBe(false)
  })

  it("rejects external web links", () => {
    expect(isInfographicLink("https://support.apple.com/en-us/HT204204")).toBe(false)
  })

  it("rejects empty and undefined hrefs", () => {
    expect(isInfographicLink("")).toBe(false)
    expect(isInfographicLink(undefined)).toBe(false)
  })
})

describe("infographicDisplayLabel (spec 046 — double-emoji guard, E5)", () => {
  it("passes the canonical label through unchanged", () => {
    expect(infographicDisplayLabel("Open the step-by-step infographic")).toBe(
      "Open the step-by-step infographic"
    )
  })

  it("strips one leading model-emitted pin with surrounding whitespace", () => {
    expect(infographicDisplayLabel(" 📌 Open the step-by-step infographic")).toBe(
      "Open the step-by-step infographic"
    )
  })

  it("leaves a pin mid-text untouched (it is data)", () => {
    expect(infographicDisplayLabel("Open the 📌 infographic")).toBe("Open the 📌 infographic")
  })
})
