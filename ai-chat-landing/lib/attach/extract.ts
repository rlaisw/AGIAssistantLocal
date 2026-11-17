/**
 * Spec 043 — per-format text extraction (server-side, in-memory).
 * Each format uses its standard library; the only hand-rolled walk is the
 * pptx slide-text read. Every edge returns an honest note or error — a
 * scanned PDF is "no readable text", never a fabricated summary.
 */

import { PDFParse } from "pdf-parse"
import mammoth from "mammoth"
import WordExtractor from "word-extractor"
import * as XLSX from "xlsx"
import JSZip from "jszip"
import { XMLValidator, XMLParser } from "fast-xml-parser"

export type ExtractResult =
  | { ok: true; text: string; note?: string }
  | { ok: false; error: string }

export type ExtractInput = {
  name: string
  ext: string
  bytes: Uint8Array
}

const NO_TEXT_NOTE =
  "no readable text (scanned/image-only PDF — OCR is not enabled)"

export async function extractText({
  ext,
  bytes,
}: ExtractInput): Promise<ExtractResult> {
  const buf = Buffer.from(bytes)
  try {
    switch (ext) {
      case ".pdf":
        return await extractPdf(buf)
      case ".docx":
        return await extractDocx(buf)
      case ".doc":
        return await extractDoc(buf)
      case ".xlsx":
      case ".xls":
        return extractWorkbook(buf)
      case ".csv":
        return { ok: true, text: buf.toString("utf-8") }
      case ".pptx":
        return await extractPptx(buf)
      case ".ppt":
        return {
          ok: false,
          error:
            "Legacy PowerPoint (.ppt) text cannot be extracted — save it as .pptx and attach that.",
        }
      case ".txt":
        return { ok: true, text: buf.toString("utf-8") }
      case ".json":
        return extractJson(buf)
      case ".xml":
        return extractXml(buf)
      default:
        return { ok: false, error: `Unsupported format: ${ext}` }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    return {
      ok: false,
      error: `The file could not be read (${message.slice(0, 160)}).`,
    }
  }
}

async function extractPdf(buf: Buffer): Promise<ExtractResult> {
  const parser = new PDFParse({ data: new Uint8Array(buf) })
  try {
    const parsed = await parser.getText()
    // pdf-parse v2 appends page markers ("-- 1 of 3 --"); they are noise
    const text = (parsed.text ?? "")
      .replace(/^-- \d+ of \d+ --$/gm, "")
      .trim()
    if (!text) {
      return { ok: true, text: "", note: NO_TEXT_NOTE }
    }
    return { ok: true, text }
  } finally {
    await parser.destroy().catch(() => {})
  }
}

async function extractDocx(buf: Buffer): Promise<ExtractResult> {
  const result = await mammoth.extractRawText({ buffer: buf })
  const text = (result.value ?? "").trim()
  if (!text) return { ok: true, text: "", note: "no readable text in this .docx" }
  return { ok: true, text }
}

async function extractDoc(buf: Buffer): Promise<ExtractResult> {
  const extractor = new WordExtractor()
  const doc = await extractor.extract(buf)
  const text = (doc.getBody() ?? "").trim()
  if (!text) return { ok: true, text: "", note: "no readable text in this .doc" }
  return { ok: true, text }
}

function extractWorkbook(buf: Buffer): ExtractResult {
  const wb = XLSX.read(buf, { type: "buffer" })
  const parts: string[] = []
  for (const sheetName of wb.SheetNames) {
    const csv = XLSX.utils.sheet_to_csv(wb.Sheets[sheetName])
    if (csv.trim()) parts.push(`# Sheet: ${sheetName}\n${csv.trim()}`)
  }
  const text = parts.join("\n\n")
  if (!text) return { ok: true, text: "", note: "the workbook has no cell data" }
  return { ok: true, text }
}

async function extractPptx(buf: Buffer): Promise<ExtractResult> {
  const zip = await JSZip.loadAsync(buf)
  const slideFiles = Object.keys(zip.files)
    .filter((p) => /^ppt\/slides\/slide\d+\.xml$/.test(p))
    .sort((a, b) => {
      const n = (s: string) => Number(s.match(/slide(\d+)\.xml$/)?.[1] ?? 0)
      return n(a) - n(b)
    })
  const runs: string[] = []
  for (const [index, file] of slideFiles.entries()) {
    const xml = await zip.files[file].async("text")
    const texts = Array.from(xml.matchAll(/<a:t>([^<]*)<\/a:t>/g)).map(
      (m) => m[1]
    )
    if (texts.length) runs.push(`# Slide ${index + 1}\n${texts.join("\n")}`)
  }
  const text = runs.join("\n\n")
  if (!text)
    return { ok: true, text: "", note: "the presentation has no slide text" }
  return { ok: true, text }
}

function extractJson(buf: Buffer): ExtractResult {
  const raw = buf.toString("utf-8")
  try {
    const parsed = JSON.parse(raw)
    return { ok: true, text: JSON.stringify(parsed, null, 2) }
  } catch {
    return { ok: false, error: "The file is not valid JSON." }
  }
}

function extractXml(buf: Buffer): ExtractResult {
  const raw = buf.toString("utf-8")
  const valid = XMLValidator.validate(raw)
  if (valid !== true) {
    return { ok: false, error: "The file is not well-formed XML." }
  }
  const parser = new XMLParser({ ignoreAttributes: false })
  try {
    return { ok: true, text: JSON.stringify(parser.parse(raw), null, 2) }
  } catch {
    return { ok: true, text: raw }
  }
}