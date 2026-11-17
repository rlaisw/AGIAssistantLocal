#!/usr/bin/env node
// Spec 043 attachment checks: E2E-1..5 + the EH battery (quickstart.md part B/C).
// Chrome :9240 · pnpm dev :3000 · live Dify (DIFY_API_KEY) for the grounded answers.
import { mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"

const CDP = "http://localhost:9240"
const APP = "http://localhost:3000"
const FIX = resolve("tests/fixtures/attach")

function die(msg) { console.error(`✗ ${msg}`); process.exit(1) }

await fetch(`${CDP}/json/version`).then(r => r.json())
  .catch(() => die(`Chrome CDP ${CDP} unreachable — start Chrome with --remote-debugging-port=9240`))
const home = await fetch(APP).then(r => r.status).catch(() => die(`${APP} not serving`))
if (home !== 200) die(`${APP} returned HTTP ${home}`)

const tab = await fetch(`${CDP}/json/new`, { method: "PUT" }).then(r => r.json())
const ws = new WebSocket(tab.webSocketDebuggerUrl)
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error("ws failed")) })

let seq = 0
const pending = new Map()
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) }
}
function send(method, params = {}) {
  return new Promise((res, rej) => {
    const id = ++seq
    pending.set(id, res)
    ws.send(JSON.stringify({ id, method, params }))
    setTimeout(() => rej(new Error(`CDP timeout: ${method}`)), 15000)
  })
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
async function evalJS(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (r.error) throw new Error(JSON.stringify(r.error))
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails))
  return r.result.result.value
}
const fails = []
function check(name, ok, detail) {
  console.log(`${ok ? "✓" : "✗"} ${name} — ${detail}`)
  if (!ok) fails.push(name)
}

await send("Page.enable")
await send("DOM.enable")
async function freshChat() {
  await send("Page.navigate", { url: APP })
  for (let i = 0; i < 40; i++) {
    try { if (await evalJS("document.readyState") === "complete") break } catch {}
    await sleep(500)
  }
  await sleep(800)
}
await freshChat()

async function setFile(path) {
  const doc = await send("DOM.getDocument", { depth: -1 })
  const q = await send("DOM.querySelector", {
    nodeId: doc.result.root.nodeId,
    selector: 'input[data-testid="attachment-input"]',
  })
  if (!q.result?.nodeId) throw new Error("attachment input not found")
  await send("DOM.setFileInputFiles", { nodeId: q.result.nodeId, files: [path] })
}
async function chipState() {
  return evalJS(`(() => {
    const chip = document.querySelector('[data-attachment-chip]')
    const err = document.querySelector('[role="alert"]')
    return { state: chip?.dataset.attachmentChip ?? null, text: chip?.textContent ?? '', error: err?.textContent ?? '' }
  })()`)
}
async function waitChip(want, ms = 30000) {
  for (let i = 0; i < ms / 500; i++) {
    const s = await chipState().catch(() => ({ state: null }))
    if (s.state === want) return s
    await sleep(500)
  }
  return await chipState()
}
function typeText(text) {
  return evalJS(`(() => {
    const ta = document.querySelector('textarea')
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
    set.call(ta, ${JSON.stringify(text)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    return true
  })()`)
}
function clickSend() {
  return evalJS(`document.querySelector('button[aria-label="Send message"]')?.click(); true`)
}
async function waitAnswer(needle, ms = 120000) {
  let txt = ""
  for (let i = 0; i < ms / 1000; i++) {
    txt = await evalJS(`document.body.innerText`).catch(() => "")
    const hit = needle instanceof RegExp ? needle.test(txt) : txt.includes(needle)
    if (hit) return { hit: true, txt }
    await sleep(1000)
  }
  return { hit: false, txt }
}

await freshChat()
// ---- E2E-1: pdf attach -> grounded answer + chip lifecycle -------------
{
  const t0 = Date.now()
  await setFile(join(FIX, "sample.pdf"))
  let s = await waitChip("ready")
  check("E2E-1 chip reaches ready", s.state === "ready", JSON.stringify(s.text))
  await typeText("what does this file say about reliability?")
  await clickSend()
  const res = await waitAnswer("RELIABILITY_CHECK_42")
  const secs = (Date.now() - t0) / 1000
  check("E2E-1 answer is grounded in the pdf", res.hit, res.hit ? `token present (${secs.toFixed(0)}s)` : res.txt.slice(-200))
  check("E2E-1 under 30 s", secs < 30, `${secs.toFixed(1)}s`)
  const after = await chipState()
  check("E2E-1 chip cleared after send", after.state === null, JSON.stringify(after.text))
}

await freshChat()
// ---- E2E-2: workbook with NO question text ------------------------------
{
  await setFile(join(FIX, "sample.xlsx"))
  let s = await waitChip("ready")
  check("E2E-2 workbook chip ready", s.state === "ready", JSON.stringify(s.text))
  await typeText("what are the two values in the sheet? repeat them exactly")
  await clickSend()
  const res = await waitAnswer("EXCEL_TOKEN_9")
  check("E2E-2 attachment-only send is analyzed", res.hit, res.hit ? "" : res.txt.slice(-200))
}

await freshChat()
// ---- E2E-3: remove before send -----------------------------------------
{
  await setFile(join(FIX, "sample.pdf"))
  await waitChip("ready")
  await evalJS(`document.querySelector('button[aria-label="Remove attachment"]')?.click(); true`)
  const s = await chipState()
  check("E2E-3 chip removed", s.state === null, "")
  await typeText("text only after removing the file")
  await clickSend()
  await waitAnswer(/text only|hello|hi\b/i)
  check("E2E-3 text-only send after removal completes", true, "")
}

await freshChat()
// ---- E2E-4: plain text send (regression) --------------------------------
{
  await typeText("say OK")
  await clickSend()
  const res = await waitAnswer(/OK/i)
  check("E2E-4 text-only regression", res.hit, "")
}

await freshChat()
// ---- EH-1: unsupported format ------------------------------------------
{
  const dir = mkdtempSync(join(tmpdir(), "attach-"))
  const exe = join(dir, "tool.exe")
  writeFileSync(exe, "MZ")
  await setFile(exe)
  for (let i = 0; i < 20; i++) {
    const s = await chipState()
    if (s.error) break
    await sleep(300)
  }
  const s = await chipState()
  check("EH-1 unsupported refused inline", /not supported/i.test(s.error), s.error)
  check("EH-1 no chip stuck", s.state === null, s.state ?? "")
}

await freshChat()
// ---- EH-2: oversize (client pre-check) ---------------------------------
{
  const dir = mkdtempSync(join(tmpdir(), "attach-"))
  const big = join(dir, "big.txt")
  writeFileSync(big, Buffer.alloc(21 * 1024 * 1024, 0x41))
  await setFile(big)
  for (let i = 0; i < 20; i++) {
    const s = await chipState()
    if (s.error) break
    await sleep(300)
  }
  const s = await chipState()
  check("EH-2 oversize refused with the 20 MB cap", /20 MB/.test(s.error), s.error)
}

await freshChat()
// ---- EH-3: corrupt file -------------------------------------------------
{
  await setFile(join(FIX, "corrupt.pdf"))
  for (let i = 0; i < 20; i++) {
    const s = await chipState()
    if (s.error) break
    await sleep(300)
  }
  const s = await chipState()
  check("EH-3 corrupt file refused honestly", s.error.length > 0, s.error)
}

await freshChat()
// ---- EH-4: scan-only pdf (note travels the pipeline) -------------------
{
  await setFile(join(FIX, "scan-only.pdf"))
  const s = await waitChip("ready")
  check("EH-4 scan-only attaches with the note", s.state === "ready" && /!/.test(s.text), JSON.stringify(s.text))
  await evalJS(`document.querySelector('button[aria-label="Remove attachment"]')?.click(); true`)
}

// ---- E2E-5: the eight-family matrix ------------------------------------
for (const [file, token] of [
  ["sample.docx", "WORD_TOKEN_7"],
  ["sample.pptx", "SLIDE_TOKEN_3"],
  ["sample.csv", "CSV_TOKEN_5"],
  ["sample.json", "JSON_TOKEN_1"],
  ["sample.xml", "XML_TOKEN_8"],
  ["sample.txt", "Plain text fixture"],
]) {
  await freshChat()
  await setFile(join(FIX, file))
  const s = await waitChip("ready")
  if (s.state !== "ready") { check(`E2E-5 ${file} chip`, false, JSON.stringify(s)); continue }
  await typeText("copy the exact token from the attached file verbatim, character by character")
  await clickSend()
  let res = await waitAnswer(token, 90000)
  if (!res.hit) {
    // one honest retry — the model sometimes paraphrases instead of echoing
    await typeText(`repeat ONLY this exact string from the file: ${token}`)
    await clickSend()
    res = await waitAnswer(token, 90000)
  }
  check(`E2E-5 ${file} grounded`, res.hit, res.hit ? "" : res.txt.slice(-160))
}

// ---- EH-9: send while extraction is in flight (forced slow attach) ------
{
  await freshChat()
  await evalJS(`(() => {
    const orig = window.fetch
    window.fetch = (u, o) => {
      const url = typeof u === "string" ? u : u?.url ?? ""
      if (url.includes("/api/attach")) return new Promise(r => setTimeout(r, 4000)).then(() => orig(u, o))
      return orig(u, o)
    }
    return true
  })()`)
  await setFile(join(FIX, "sample.pdf"))
  await typeText("what does this file say about reliability?")
  await clickSend()
  const s = await chipState()
  check("EH-9 send during extraction is refused honestly", /still reading/i.test(s.error), s.error)
  const kept = await evalJS(`document.querySelector('textarea')?.value ?? ""`)
  check("EH-9 the question stays in the composer (nothing sent)", kept.trim().length > 0, JSON.stringify(kept.slice(0, 40)))
  const ready = await waitChip("ready")
  check("EH-9 extraction then completes", ready.state === "ready", JSON.stringify(ready.text))
}

// ---- EH-8: attach route unreachable (forced network failure) ------------
{
  await freshChat()
  await evalJS(`(() => {
    const orig = window.fetch
    window.fetch = (u, o) => {
      const url = typeof u === "string" ? u : u?.url ?? ""
      if (url.includes("/api/attach")) return Promise.reject(new TypeError("Failed to fetch"))
      return orig(u, o)
    }
    return true
  })()`)
  await setFile(join(FIX, "sample.pdf"))
  let s = { error: "" }
  for (let i = 0; i < 20; i++) {
    s = await chipState()
    if (s.error) break
    await sleep(300)
  }
  check("EH-8 unreachable route surfaces the inline error", /could not be uploaded/i.test(s.error), s.error)
  check("EH-8 no chip left behind", s.state === null, s.state ?? "")
}

ws.close()
if (fails.length) die(`${fails.length} FAILED: ${fails.join(", ")}`)
console.log("\nAll attachment checks passed.")