import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { extractText } from "./extract"
import { extensionOf } from "./formats"

const fixtures = join(__dirname, "../../tests/fixtures/attach")

async function run(name: string) {
  const bytes = readFileSync(join(fixtures, name))
  return extractText({ name, ext: extensionOf(name), bytes })
}

describe("per-format extraction (real fixture files)", () => {
  it.each([
    ["sample.pdf", "RELIABILITY_CHECK_42"],
    ["sample.docx", "WORD_TOKEN_7"],
    ["sample.xlsx", "EXCEL_TOKEN_9"],
    ["sample.pptx", "SLIDE_TOKEN_3"],
    ["sample.csv", "CSV_TOKEN_5"],
    ["sample.json", "JSON_TOKEN_1"],
    ["sample.xml", "XML_TOKEN_8"],
  ])("%s extracts its unique token", async (name, token) => {
    const res = await run(name)
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toContain(token)
  })

  it("plain text extracts", async () => {
    const res = await run("sample.txt")
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toContain("Plain text fixture")
  })
})

describe("extraction edge cases (honest outcomes)", () => {
  it("scan-only PDF yields empty text with the no-readable-text note", async () => {
    const res = await run("scan-only.pdf")
    expect(res.ok).toBe(true)
    if (res.ok) {
      expect(res.text).toBe("")
      expect(res.note ?? "").toContain("no readable text")
    }
  })

  it("corrupt PDF fails honestly", async () => {
    const res = await run("corrupt.pdf")
    expect(res.ok).toBe(false)
  })

  it("legacy .ppt is refused with the save-as remedy", async () => {
    const res = await run("legacy.ppt")
    expect(res.ok).toBe(false)
    if (!res.ok) expect(res.error).toContain("save it as .pptx")
  })

  it("broken JSON fails honestly", async () => {
    const res = await run("broken.json")
    expect(res.ok).toBe(false)
    if (!res.ok) expect(res.error).toContain("not valid JSON")
  })

  it("broken XML fails honestly", async () => {
    const res = await run("broken.xml")
    expect(res.ok).toBe(false)
    if (!res.ok) expect(res.error).toContain("well-formed")
  })

  it("empty text yields the empty extraction (gate refuses before this in the route)", async () => {
    const res = await run("empty.txt")
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toBe("")
  })
})