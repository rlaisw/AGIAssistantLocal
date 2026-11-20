import { describe, expect, it } from "vitest"

import { infographicDisplayLabel, isInfographicLink } from "@/lib/infographic-link"

describe("isInfographicLink (spec 046)", () => {
  it("accepts absolute sidecar infographic URLs", () => {
    expect(isInfographicLink("http://localhost:28080/infographics/e468aaee5ee3/")).toBe(true)
  })

  it("accepts relative infographic URLs and query strings", () => {
    expect(isInfographicLink("/infographics/abc123/")).toBe(true)
    expect(isInfographicLink("http://localhost:28080/infographics/abc123/?x=1")).toBe(true)
  })

  it("rejects deck download and page links", () => {
    expect(isInfographicLink("http://localhost:28080/exports/deck.pptx")).toBe(false)
    expect(isInfographicLink("http://localhost:28080/decks/demo/demo_1/")).toBe(false)
  })

  it("rejects external, empty, and undefined hrefs", () => {
    expect(isInfographicLink("https://support.apple.com/en-us/HT204204")).toBe(false)
    expect(isInfographicLink("")).toBe(false)
    expect(isInfographicLink(undefined)).toBe(false)
  })
})

describe("infographicDisplayLabel (spec 046, E3)", () => {
  it("passes the existing label through unchanged", () => {
    expect(infographicDisplayLabel("Open the step-by-step infographic")).toBe("Open the step-by-step infographic")
  })

  it("strips exactly one model-emitted leading pin and whitespace", () => {
    expect(infographicDisplayLabel(" 📌 Open the step-by-step infographic")).toBe("Open the step-by-step infographic")
  })

  it("leaves a pin in the middle of the label untouched", () => {
    expect(infographicDisplayLabel("Open the 📌 infographic")).toBe("Open the 📌 infographic")
  })
})
