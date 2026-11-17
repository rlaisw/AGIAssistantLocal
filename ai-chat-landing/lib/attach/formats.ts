/**
 * Spec 043 — the attachment format gate (server-side trust boundary).
 * The picker's `accept` is a convenience; a renamed file or a direct POST
 * must be refused here: size → extension → magic sniff → non-empty.
 */

export const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024 // 20 MB (FR-005)

export const FORMAT_EXTENSIONS = [
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".ppt",
  ".pptx",
  ".txt",
  ".csv",
  ".json",
  ".xml",
] as const

export type AttachmentExt = (typeof FORMAT_EXTENSIONS)[number]

export const ACCEPT_ATTR = FORMAT_EXTENSIONS.join(",")

export const SUPPORTED_LABEL =
  "PDF, Word (.doc/.docx), Excel (.xls/.xlsx), PowerPoint (.ppt/.pptx), TXT, CSV, JSON, XML"

const ZIP_FAMILY: ReadonlySet<AttachmentExt> = new Set([".docx", ".xlsx", ".pptx"])

export type GateResult =
  | { ok: true; ext: AttachmentExt }
  | { ok: false; status: 413 | 415 | 422; error: string }

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".")
  return dot < 0 ? "" : name.slice(dot).toLowerCase()
}

export function humanSize(bytes: number): string {
  const mb = bytes / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** Validates a file against the contract (contracts/attach-api.md). */
export function gate(name: string, bytes: Uint8Array): GateResult {
  if (bytes.length > MAX_ATTACHMENT_BYTES) {
    return {
      ok: false,
      status: 413,
      error: `This file is ${humanSize(bytes.length)} — the maximum attachment size is 20 MB.`,
    }
  }
  const ext = extensionOf(name) as AttachmentExt
  if (!FORMAT_EXTENSIONS.includes(ext)) {
    return {
      ok: false,
      status: 415,
      error: `That file type is not supported — attach ${SUPPORTED_LABEL}.`,
    }
  }
  if (bytes.length === 0) {
    return {
      ok: false,
      status: 422,
      error: "This file is empty — there is nothing to analyze.",
    }
  }
  const head = Buffer.from(bytes.subarray(0, 5)).toString("latin1")
  if (ext === ".pdf" && !head.startsWith("%PDF-")) {
    return {
      ok: false,
      status: 415,
      error: "The file content does not match its .pdf extension.",
    }
  }
  if (ZIP_FAMILY.has(ext) && !head.startsWith("PK")) {
    return {
      ok: false,
      status: 415,
      error: `The file content does not match its ${ext} extension.`,
    }
  }
  return { ok: true, ext }
}