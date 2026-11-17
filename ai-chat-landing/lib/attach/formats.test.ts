import { describe, expect, it } from "vitest"
import {
  ACCEPT_ATTR,
  FORMAT_EXTENSIONS,
  MAX_ATTACHMENT_BYTES,
  SUPPORTED_LABEL,
  gate,
  humanSize,
} from "./formats"

const bytes = (n: number, fill = 0x41) => new Uint8Array(n).fill(fill)
const pdf = (n: number) => {
  const b = new Uint8Array(n).fill(0x41)
  b.set(Buffer.from("%PDF-"), 0)
  return b
}
const zip = (n: number) => {
  const b = new Uint8Array(n).fill(0x41)
  b.set(Buffer.from("PK\u0003\u0004"), 0)
  return b
}

describe("attachment format gate", () => {
  it("accepts all eight families", () => {
    for (const ext of [
      ".pdf",
      ".docx",
      ".xlsx",
      ".pptx",
      ".txt",
      ".csv",
      ".json",
      ".xml",
    ]) {
      const content =
        ext === ".pdf" ? pdf(64) : ext === ".docx" || ext === ".xlsx" || ext === ".pptx" ? zip(64) : bytes(64)
      expect(gate(`file${ext}`, content).ok).toBe(true)
    }
  })

  it("keeps the picker accept attr in sync with the allowlist", () => {
    expect(ACCEPT_ATTR).toBe(FORMAT_EXTENSIONS.join(","))
    for (const ext of FORMAT_EXTENSIONS) expect(ACCEPT_ATTR).toContain(ext)
  })

  it("refuses exactly 20 MB + 1 byte with the measured size named", () => {
    const over = gate("big.txt", bytes(MAX_ATTACHMENT_BYTES + 1))
    expect(over.ok).toBe(false)
    if (!over.ok) {
      expect(over.status).toBe(413)
      expect(over.error).toContain("20 MB")
      expect(over.error).toContain(humanSize(MAX_ATTACHMENT_BYTES + 1))
    }
  })

  it("accepts exactly 20 MB", () => {
    expect(gate("edge.txt", bytes(MAX_ATTACHMENT_BYTES)).ok).toBe(true)
  })

  it("refuses unsupported extensions naming the list", () => {
    const r = gate("tool.exe", bytes(10))
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.status).toBe(415)
      expect(r.error).toContain(SUPPORTED_LABEL)
    }
  })

  it("refuses a renamed zip payload with a .pdf name (sniff mismatch)", () => {
    const r = gate("renamed.pdf", zip(64))
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.status).toBe(415)
      expect(r.error).toContain("does not match")
    }
  })

  it("refuses an empty file", () => {
    const r = gate("empty.txt", bytes(0))
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.status).toBe(422)
  })
})