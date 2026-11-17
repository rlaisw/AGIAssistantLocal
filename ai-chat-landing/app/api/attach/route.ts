export const runtime = "nodejs"

import { MAX_ATTACHMENT_BYTES, gate } from "@/lib/attach/formats"
import { extractText } from "@/lib/attach/extract"

/**
 * Spec 043 — attachment extraction endpoint.
 * In-memory only: the file is read, validated (trust boundary), extracted,
 * and never written anywhere. Honest JSON errors per contracts/attach-api.md.
 */
export async function POST(req: Request) {
  let form: FormData | null = null
  try {
    form = await req.formData()
  } catch {
    form = null
  }
  const file = form?.get("file")
  if (!(file instanceof File)) {
    return Response.json({ error: "Attach a file to upload." }, { status: 400 })
  }
  // early size refusal before buffering a large body
  if (file.size > MAX_ATTACHMENT_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(1)
    return Response.json(
      { error: `This file is ${mb} MB — the maximum attachment size is 20 MB.` },
      { status: 413 }
    )
  }
  const bytes = new Uint8Array(await file.arrayBuffer())
  const gated = gate(file.name, bytes)
  if (!gated.ok) {
    return Response.json({ error: gated.error }, { status: gated.status })
  }
  const extracted = await extractText({
    name: file.name,
    ext: gated.ext,
    bytes,
  })
  if (!extracted.ok) {
    return Response.json({ error: extracted.error }, { status: 422 })
  }
  return Response.json({
    ok: true,
    filename: file.name,
    type: gated.ext,
    chars: extracted.text.length,
    text: extracted.text,
    truncated: false,
    ...(extracted.note ? { note: extracted.note } : {}),
  })
}