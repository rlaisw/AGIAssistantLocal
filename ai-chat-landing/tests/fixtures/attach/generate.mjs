// Generates the tiny attachment fixtures (committed, re-runnable).
// Run: node tests/fixtures/attach/generate.mjs
import { writeFileSync, mkdirSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import JSZip from "jszip"
import * as XLSX from "xlsx"

const dir = dirname(fileURLToPath(import.meta.url))
mkdirSync(dir, { recursive: true })

// ---- a minimal, structurally valid PDF (correct xref) -------------------
function makePdf(text) {
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    null, // contents stream filled below
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ]
  const content = `BT /F1 24 Tf 72 720 Td (${text}) Tj ET`
  objs[3] = `<< /Length ${content.length} >>\nstream\n${content}\nendstream`

  let out = "%PDF-1.4\n"
  const offsets = []
  objs.forEach((body, i) => {
    offsets.push(out.length)
    out += `${i + 1} 0 obj\n${body}\nendobj\n`
  })
  const xrefAt = out.length
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`
  for (const off of offsets) {
    out += `${String(off).padStart(10, "0")} 00000 n \n`
  }
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xrefAt}\n%%EOF\n`
  return Buffer.from(out, "latin1")
}

writeFileSync(join(dir, "sample.pdf"), makePdf("RELIABILITY_CHECK_42"))
// a valid, readable-structure PDF with NO text layer (scan-only simulation)
writeFileSync(join(dir, "scan-only.pdf"), makePdf(""))
writeFileSync(join(dir, "corrupt.pdf"), Buffer.from("%PDF-broken", "latin1"))

// ---- docx (zip: [Content_Types].xml, _rels, word/document.xml) ----------
const docx = new JSZip()
docx.file(
  "[Content_Types].xml",
  `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`
)
docx.file(
  "_rels/.rels",
  `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`
)
docx.file(
  "word/document.xml",
  `<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>WORD_TOKEN_7</w:t></w:r></w:p></w:body></w:document>`
)
const docxBuf = await docx.generateAsync({ type: "nodebuffer" })
writeFileSync(join(dir, "sample.docx"), docxBuf)
// a zip payload renamed as .pdf (content/extension mismatch)
writeFileSync(join(dir, "renamed-docx-as-pdf.pdf"), docxBuf)

// ---- xlsx via SheetJS ---------------------------------------------------
const wb = XLSX.utils.book_new()
const ws = XLSX.utils.aoa_to_sheet([
  ["name", "value"],
  ["EXCEL_TOKEN_9", 42],
])
XLSX.utils.book_append_sheet(wb, ws, "Sheet1")
XLSX.writeFile(wb, join(dir, "sample.xlsx"))
const csvWs = XLSX.utils.aoa_to_sheet([["id", "note"], ["1", "CSV_TOKEN_5"]])
const csvWb = XLSX.utils.book_new()
XLSX.utils.book_append_sheet(csvWb, csvWs, "Sheet1")
writeFileSync(join(dir, "sample.csv"), XLSX.utils.sheet_to_csv(csvWs))

// ---- pptx (zip: presentation.xml + slide1.xml with an a:t run) ----------
const pptx = new JSZip()
pptx.file(
  "[Content_Types].xml",
  `<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>`
)
pptx.file(
  "_rels/.rels",
  `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>`
)
pptx.file(
  "ppt/presentation.xml",
  `<?xml version="1.0" encoding="UTF-8"?><p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId2"/></p:sldIdLst></p:presentation>`
)
pptx.file(
  "ppt/_rels/presentation.xml.rels",
  `<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/></Relationships>`
)
pptx.file(
  "ppt/slides/slide1.xml",
  `<?xml version="1.0" encoding="UTF-8"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>SLIDE_TOKEN_3</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>`
)
writeFileSync(join(dir, "sample.pptx"), await pptx.generateAsync({ type: "nodebuffer" }))

// ---- plain-text family --------------------------------------------------
writeFileSync(join(dir, "sample.txt"), "Plain text fixture.\nTXT line two.\n")
writeFileSync(join(dir, "sample.json"), '{"token": "JSON_TOKEN_1", "n": 1}\n')
writeFileSync(join(dir, "sample.xml"), '<?xml version="1.0"?><root><token>XML_TOKEN_8</token></root>\n')
writeFileSync(join(dir, "broken.json"), '{"token": "JSON_TOKEN_1", \n')
writeFileSync(join(dir, "broken.xml"), "<root><token>unclosed\n")
writeFileSync(join(dir, "empty.txt"), "")
// legacy .ppt: CFB magic stub — the extractor refuses it before parsing
writeFileSync(join(dir, "legacy.ppt"), Buffer.from("D0CF11E0A1B11AE1", "hex"))

console.log("fixtures written to", dir)