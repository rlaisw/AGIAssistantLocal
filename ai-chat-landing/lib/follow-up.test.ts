import { describe, expect, it } from "vitest"

import { splitFollowUp } from "./follow-up"

describe("splitFollowUp", () => {
  it("splits a trailing question paragraph off the answer", () => {
    const r = splitFollowUp("Install SQL Server from setup.exe.\n\nFollow the wizard.\n\nWant me to tailor this for a silent install?")
    expect(r.body).toBe("Install SQL Server from setup.exe.\n\nFollow the wizard.")
    expect(r.followUp).toBe("Want me to tailor this for a silent install?")
  })

  it("leaves answers whose last paragraph is not a question untouched", () => {
    const text = "Step one.\n\nStep two ends with a period."
    expect(splitFollowUp(text)).toEqual({ body: text })
  })

  it("does not treat a single-paragraph answer as a follow-up", () => {
    const text = "Want me to just do it?"
    expect(splitFollowUp(text)).toEqual({ body: text })
  })

  it("takes only the last question when several paragraphs end with ?", () => {
    const r = splitFollowUp("What is a backup?\n\nWhy back up nightly?\n\nWant me to write the cron job?")
    expect(r.followUp).toBe("Want me to write the cron job?")
    expect(r.body).toBe("What is a backup?\n\nWhy back up nightly?")
  })

  it("preserves markdown inside the follow-up", () => {
    const r = splitFollowUp("Body text.\n\nWant me to [open the guide](http://x/y)?")
    expect(r.followUp).toBe("Want me to [open the guide](http://x/y)?")
  })

  it("ignores trailing whitespace after the question mark", () => {
    const r = splitFollowUp("Body.\n\nWant me to continue?  ")
    expect(r.followUp).toBe("Want me to continue?")
  })

  it("catches a multi-line follow-up that ends with a period (real case 2026-10-28)", () => {
    const r = splitFollowUp(
      "Summary of the BMI data.\n\nDetails here.\n\nWant me to add any of these next?\nA radar or box-plot comparing BMI spread\nA histogram of BMI distribution\nJust tell me which and I'll generate it."
    )
    expect(r.body).toBe("Summary of the BMI data.\n\nDetails here.")
    expect(r.followUp).toContain("Want me to add any of these next?")
    expect(r.followUp).toContain("Just tell me which and I'll generate it.")
  })

  it("captures the whole block when options sit in their own paragraphs (live case 2026-10-28)", () => {
    const r = splitFollowUp(
      "The watch-list is the 14 employees at BMI 25+.\n\nWant me to add any of these next?\n\nA radar or box-plot comparing BMI spread by group\nA histogram of BMI distribution\nAn Excel-style pivot or a chart in a different style (bar, treemap, dual-axis)\n\nJust tell me which and I'll generate it."
    )
    expect(r.body).toBe("The watch-list is the 14 employees at BMI 25+.")
    expect(r.followUp).toContain("Want me to add any of these next?")
    expect(r.followUp).toContain("A radar or box-plot")
    expect(r.followUp).toContain("Just tell me which and I'll generate it.")
  })

  it("styles a single-paragraph 'Want a …?' opener ending with a bang (Kimi case 2026-10-28)", () => {
    const r = splitFollowUp(
      "Answer content here.\n\nWant a different view — e.g., a sorted BMI ranking, a histogram of height/weight distribution, or a dual-axis chart? Just let me know!"
    )
    expect(r.body).toBe("Answer content here.")
    expect(r.followUp).toBe("Want a different view — e.g., a sorted BMI ranking, a histogram of height/weight distribution, or a dual-axis chart? Just let me know!")
  })

  it("captures opener + options + a 'Just say' closer (Qwen case 2026-10-28)", () => {
    const r = splitFollowUp(
      "What the scatter shows: weight rises with height overall.\n\nWant a different cut?\n\nI can regenerate any of these as:\nSorted column chart (BMI high → low) for a ranked watch list\nDual-axes (BMI bars + height line) per employee\nBox plot of BMI spread, or a treemap/sankey grouping\nAn infographic summary card for a slide/report\n\nJust say which one. I spot-checked your BMI column and the values are consistent."
    )
    expect(r.body).toBe("What the scatter shows: weight rises with height overall.")
    expect(r.followUp).toContain("Want a different cut?")
    expect(r.followUp).toContain("Dual-axes")
    expect(r.followUp).toContain("Just say which one.")
  })

  it("does not match plain 'just' sentences as closers", () => {
    const text = "Analysis.\n\nJust because the data says so, it is fine."
    expect(splitFollowUp(text)).toEqual({ body: text })
  })

  it("styles only the closer when no opener precedes the options (options belong to their question)", () => {
    const r = splitFollowUp(
      "This is a long and detailed analysis paragraph explaining the full BMI breakdown of the entire employee dataset with many numbers in it, far beyond one line of text, so it must stay in the body.\n\nA radar or box-plot\nA histogram\n\nJust tell me which and I'll generate it."
    )
    expect(r.body).toContain("long and detailed analysis")
    expect(r.body).toContain("A radar or box-plot")
    expect(r.followUp).toBe("Just tell me which and I'll generate it.")
  })

  it("does not style a last paragraph that merely mentions wanting something", () => {
    const text = "Analysis.\n\nThe team wanted me to check twice, so I did."
    expect(splitFollowUp(text)).toEqual({ body: text })
  })

  it("re-adds a follow-up question that sits immediately before an infographic link", () => {
    const link = "[Open the step-by-step infographic](http://localhost:28080/infographics/e468aaee5ee3/)"
    const r = splitFollowUp(`Answer body.\n\nWant me to tailor the steps?\n\n${link}`)
    expect(r.body).toBe(`Answer body.\n\n${link}`)
    expect(r.followUp).toBe("Want me to tailor the steps?")
  })

  it("keeps an opener + options + closer follow-up block before an infographic link", () => {
    const link = "[Open the step-by-step infographic](http://localhost:28080/infographics/e468aaee5ee3/)"
    const text = `Summary.\n\nWant me to add a visual?\nA roadmap\nA timeline\n\nJust tell me which one.\n\n${link}`
    const r = splitFollowUp(text)
    expect(r.body).toBe(`Summary.\n\n${link}`)
    expect(r.followUp).toContain("Want me to add a visual?")
    expect(r.followUp).toContain("A roadmap")
    expect(r.followUp).toContain("Just tell me which one.")
  })

  it("does not invent a follow-up when an infographic link follows plain body text", () => {
    const link = "[Open the step-by-step infographic](http://localhost:28080/infographics/e468aaee5ee3/)"
    const text = `Answer body without any follow-up question.\n\n${link}`
    expect(splitFollowUp(text)).toEqual({ body: text })
  })

  it("splits the exact MCP-action offer after manual instruction paragraphs", () => {
    const manualSteps = "1. Open Settings and select Printers & scanners.\n\n2. Select Microsoft Print to PDF and choose Set as default."
    const offer = "Do you want me to do it automatically for you?"

    expect(splitFollowUp(`${manualSteps}\n\n${offer}`)).toEqual({
      body: manualSteps,
      followUp: offer,
    })
  })
})
