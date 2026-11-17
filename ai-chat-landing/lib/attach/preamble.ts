/**
 * Spec 043 — the attachment preamble injected into the Dify query.
 * The model sees provenance, the extraction note, the truncation marker,
 * and the owner's question — so it cannot imply coverage it does not have.
 */

export const PREAMBLE_CHAR_CAP = 24_000

export type AttachmentPart = {
  name: string
  type: string
  chars: number
  text: string
  truncated?: boolean
  note?: string
}

export function buildPreamble(
  attachment: AttachmentPart,
  question: string
): string {
  const { name, type, chars, text, note } = attachment
  const clipped = text.slice(0, PREAMBLE_CHAR_CAP)
  const capped = text.length > PREAMBLE_CHAR_CAP

  const header = [
    `[Attached file: ${name} (${type}, ${chars} characters extracted)]`,
    ...(note ? [`[Note about this file: ${note}]`] : []),
    ...(capped
      ? [
          `[content truncated at ${PREAMBLE_CHAR_CAP.toLocaleString("en-US")} characters — the file is longer]`,
        ]
      : []),
  ].join("\n")

  const footer = [
    "[End of attached file content]",
    "---",
    `User question: ${question.trim() || "(analyze this file)"}`,
  ].join("\n")

  return `${header}\n${clipped}\n${footer}`
}