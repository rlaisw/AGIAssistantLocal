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

  it("UTF-16LE XML with BOM (the Windows RelMon export family) extracts", async () => {
    const xml = '<?xml version="1.0" encoding="utf-16" ?><r><v>UTF16_XML_TOKEN_4</v></r>'
    const bytes = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(xml, "utf16le")])
    const res = await extractText({ name: "relmon.xml", ext: ".xml", bytes })
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toContain("UTF16_XML_TOKEN_4")
  })

  it("UTF-16LE text and JSON with BOM decode correctly", async () => {
    const text = "UTF16_TEXT_TOKEN_6"
    const json = JSON.stringify({ k: "UTF16_JSON_TOKEN_2" })
    for (const [name, ext, content, token] of [
      ["relmon.txt", ".txt", text, "UTF16_TEXT_TOKEN_6"],
      ["relmon.json", ".json", json, "UTF16_JSON_TOKEN_2"],
    ] as const) {
      const bytes = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from(content, "utf16le")])
      const res = await extractText({ name, ext, bytes })
      expect(res.ok).toBe(true)
      if (res.ok) expect(res.text).toContain(token)
    }
  })

  it("UTF-16BE XML with BOM extracts", async () => {
    const xml = '<?xml version="1.0" encoding="utf-16" ?><r><v>UTF16BE_TOKEN_3</v></r>'
    const bytes = Buffer.concat([Buffer.from([0xfe, 0xff]), Buffer.from(xml, "utf16le").swap16()])
    const res = await extractText({ name: "relmon-be.xml", ext: ".xml", bytes })
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toContain("UTF16BE_TOKEN_3")
  })

  it("UTF-8 BOM is stripped before parsing", async () => {
    const bytes = Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from("<r><v>BOM_TOKEN_9</v></r>")])
    const res = await extractText({ name: "bom.xml", ext: ".xml", bytes })
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toContain("BOM_TOKEN_9")
  })

  it("empty text yields the empty extraction (gate refuses before this in the route)", async () => {
    const res = await run("empty.txt")
    expect(res.ok).toBe(true)
    if (res.ok) expect(res.text).toBe("")
  })
})