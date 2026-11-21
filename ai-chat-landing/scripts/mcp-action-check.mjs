#!/usr/bin/env node
// Spec 047 T032/T045: owner-present printer and Word Chat UI acceptance.
// Default (US1): RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_PRINTER_CHANGE=1
//   node scripts/mcp-action-check.mjs
// Word only (US2): RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_WORD_DUPLEX=1
//   node scripts/mcp-action-check.mjs --word-only
// Chrome CDP :9240 + pnpm dev :3000. No test printing, saved screenshot bytes,
// raw printer setter, or Word save/close/quit is used.

import { execFile } from "node:child_process"
import { argv, env } from "node:process"
import { promisify } from "node:util"
import { fileURLToPath } from "node:url"

const WORD_ONLY = argv.includes("--word-only")
const DEFAULT_ONLY = argv.includes("--default-only")
const DEFAULT_USAGE = "cd ai-chat-landing && RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_PRINTER_CHANGE=1 node scripts/mcp-action-check.mjs"
const WORD_USAGE = "cd ai-chat-landing && RUN_MCP_ACTION_E2E=1 MCP_ACTION_ALLOW_WORD_DUPLEX=1 node scripts/mcp-action-check.mjs --word-only"
const USAGE = WORD_ONLY ? WORD_USAGE : DEFAULT_USAGE
const permitted = env.RUN_MCP_ACTION_E2E === "1" && (WORD_ONLY
  ? env.MCP_ACTION_ALLOW_WORD_DUPLEX === "1"
  : env.MCP_ACTION_ALLOW_PRINTER_CHANGE === "1")
if (!permitted || WORD_ONLY && DEFAULT_ONLY) {
  console.log(JSON.stringify({
    status: "skipped",
    reason: "owner-present opt-in and the selected action's permission are required",
    usage: USAGE,
    effects: "none: no Chrome, Dify, Python, Windows, Office, or printer calls made",
  }))
  process.exit(0)
}
if (argv.includes("--help") || argv.includes("-h")) {
  console.log(JSON.stringify({ status: "skipped", usage: USAGE, wordUsage: WORD_USAGE }))
  process.exit(0)
}

const CDP = "http://localhost:9240"
const APP = "http://localhost:3000"
const PYTHON = fileURLToPath(new URL("../../.venv/bin/python", import.meta.url))
const PRIMARY = (env.MCP_ACTION_TEST_PRINTER || "Microsoft Print to PDF").trim()
const MODIFIED = (env.MCP_ACTION_MODIFIED_PRINTER || "").trim()
const DUPLEX_PRINTER = (env.MCP_ACTION_DUPLEX_PRINTER || "HP LaserJet M610 TCPIP").trim()
const DUPLEX_MODES = { "long-edge": "TwoSidedLongEdge", "short-edge": "TwoSidedShortEdge" }
const OFFER = "Do you want me to do it automatically for you?"
const WAIT_MS = 90_000
const STAMP = Date.now()
const WORD_MARKER = `T045 disposable unsaved marker ${STAMP}`
const execFileAsync = promisify(execFile)
const evidence = {
  status: "running",
  mode: WORD_ONLY ? "word" : "default",
  cases: [],
  restoration: null,
  wordRestoration: null,
}

function require(value, message) {
  if (!value) throw new Error(message)
}
function samePrinter(a, b) {
  return typeof a === "string" && typeof b === "string" && a.toLowerCase() === b.toLowerCase()
}
function safeError(error) {
  return String(error?.message || error)
    .replace(/https?:\/\/\S*\/mcp-action\/screenshots\/[A-Za-z0-9_-]+/g, "[screenshot-url]")
    .replace(/[A-Za-z0-9_-]{43}/g, "[token]")
    .slice(0, 300)
}
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

async function pythonJSON(code, args, label) {
  let stdout
  try {
    ({ stdout } = await execFileAsync(PYTHON, ["-c", code, ...args.map(String)], {
      timeout: WAIT_MS,
      maxBuffer: 1024 * 1024,
      windowsHide: true,
    }))
  } catch {
    throw new Error(`${label} failed or exceeded 90 seconds`)
  }
  try {
    const lines = stdout.trim().split(/\r?\n/).filter(Boolean)
    return JSON.parse(lines[lines.length - 1])
  } catch {
    throw new Error(`${label} returned malformed evidence`)
  }
}

// Only fixed reviewed-action methods are callable; no arbitrary caller script.
const PYTHON_ACTION = `
import asyncio, json, sys
from agentic_rag_mcp.mcp_action.actions import ReviewedActions
method, printer, orientation = sys.argv[1], sys.argv[2], sys.argv[3]
actions = ReviewedActions()
if orientation:
    result = asyncio.run(getattr(actions, method)(printer, orientation))
else:
    result = asyncio.run(getattr(actions, method)(printer))
print(json.dumps(result))
`
async function reviewed(operation, printer, orientation = "") {
  const methods = {
    validate: "validate_default_printer",
    execute: "execute_default_printer",
    "validate-word": "validate_word_printer_duplex",
    "execute-word": "execute_word_printer_duplex",
  }
  require(methods[operation], "Unknown reviewed action operation")
  return pythonJSON(PYTHON_ACTION, [methods[operation], printer, orientation], `Reviewed ${operation}`)
}
async function readDefault() {
  const result = await reviewed("validate", PRIMARY)
  require(result.status === "ok" && result.match_count === 1, "Test printer is not one exact installed printer")
  require(typeof result.printer === "string", "Reviewed validation omitted the canonical printer")
  return { current: result.current_default ?? null, canonical: result.printer }
}

// Independent duplex reads go through ReviewedActions' fixed read-only
// Get-PrintConfiguration path. The second fixed, read-only probe snapshots only
// print-job IDs so the UI journey can prove that Print Preview printed nothing.
const PYTHON_WORD_READ = `
import asyncio, base64, json, re, sys
from agentic_rag_mcp.mcp_action.actions import ReviewedActions
from agentic_rag_mcp.windows_mcp.client import call_tool
JOB_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$requestedName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__NAME__'))
try {
    $jobs = @(Get-PrintJob -PrinterName $requestedName -ErrorAction Stop)
    $payload = @{ status = 'ok'; jobs = @($jobs | ForEach-Object { [string]$_.ID }) }
} catch {
    $payload = @{ status = 'error'; jobs = @() }
}
$json = $payload | ConvertTo-Json -Depth 4 -Compress
Write-Output ('MCP_T045_JOBS:' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
"""
async def main():
    printer, orientation = sys.argv[1], sys.argv[2]
    validation = await ReviewedActions().validate_word_printer_duplex(printer, orientation)
    result = {'validation': validation, 'jobs_status': 'error', 'jobs': []}
    try:
        encoded = base64.b64encode(printer.encode('utf-8')).decode('ascii')
        out = await call_tool('PowerShell', {
            'command': JOB_SCRIPT.replace('__NAME__', encoded), 'timeout': 30,
        }, 't045-read-only-jobs', audit=None)
        if out.get('status') == 'ok' and not out.get('truncated'):
            match = re.search(r'MCP_T045_JOBS:([A-Za-z0-9+/=]+)', out.get('text', ''))
            if match:
                payload = json.loads(base64.b64decode(match.group(1)).decode('utf-8'))
                if payload.get('status') == 'ok' and isinstance(payload.get('jobs'), list):
                    result['jobs_status'] = 'ok'
                    result['jobs'] = [str(value)[:40] for value in payload['jobs']]
    except Exception:
        pass
    print(json.dumps(result))
asyncio.run(main())
`
async function readWordState(orientation = "long-edge") {
  return pythonJSON(PYTHON_WORD_READ, [DUPLEX_PRINTER, orientation], "Read-only duplex/job probe")
}

// Test-only single-attempt OfficeProxy/COM helper. It attaches before starting
// Word, creates only this unique disposable marker, and never saves/closes or
// prints any document. Only metadata is returned; the marker stays open unsaved.
const PYTHON_WORD_MARKER = `
import json, sys
from agentic_rag_mcp.office_lanes.proxy import OfficeProxy
MARKER_SCRIPT = r"""
import json
import subprocess
import ctypes
import pythoncom
import win32com.client
d = json.loads(data)
initialized = False
try:
    pythoncom.CoInitialize()
    initialized = True
    try:
        word = win32com.client.GetActiveObject('Word.Application')
    except Exception:
        processes = subprocess.check_output(['tasklist', '/FO', 'CSV', '/NH'], text=True, timeout=5)
        if 'WINWORD.EXE' in processes.upper():
            raise RuntimeError('Word is running but COM attach failed')
        word = win32com.client.DispatchEx('Word.Application')
    word.Visible = True
    preexisting_count = int(word.Documents.Count)
    preexisting_saved_flags = [bool(word.Documents.Item(index).Saved) for index in range(1, preexisting_count + 1)]
    marker = str(d['marker'])
    matches = []
    for index in range(1, word.Documents.Count + 1):
        candidate = word.Documents.Item(index)
        if marker in str(candidate.Content.Text):
            matches.append(candidate)
    marker_created = False
    if not matches and bool(d['create']):
        document = word.Documents.Add()
        document.Content.Text = marker
        matches = [document]
        marker_created = True
    saved_flags = [bool(word.Documents.Item(index).Saved) for index in range(1, word.Documents.Count + 1)]
    window = word.ActiveWindow
    hwnd = int(window.Hwnd)
    user32 = ctypes.windll.user32
    result = {
        'status': 'ok',
        'document_count': int(word.Documents.Count),
        'saved_flags': saved_flags,
        'preexisting_count': preexisting_count,
        'preexisting_saved_flags': preexisting_saved_flags,
        'marker_created': marker_created,
        'marker_count': len(matches),
        'marker_saved': bool(matches[0].Saved) if len(matches) == 1 else None,
        'marker_text_ok': len(matches) == 1 and marker in str(matches[0].Content.Text),
        'preview': bool(word.PrintPreview),
        'view_type': int(window.View.Type),
        'window_visible': bool(word.Visible) and bool(user32.IsWindowVisible(hwnd)),
        'foreground': user32.GetForegroundWindow() == hwnd,
    }
    output = json.dumps(result)
except Exception as exc:
    output = json.dumps({'status': 'error', 'error_type': type(exc).__name__})
finally:
    if initialized:
        pythoncom.CoUninitialize()
"""
proxy = OfficeProxy(timeout_s=20)
try:
    out = proxy._call_once('RunPython', {
        'code': MARKER_SCRIPT,
        'data': json.dumps({'marker': sys.argv[1], 'create': sys.argv[2] == '1'}),
    }, 30)
    payload = proxy._payload_json(out.get('text', '')) if out.get('status') == 'ok' else None
    print(json.dumps(payload or {'status': 'error', 'error_type': 'Transport'}))
except Exception:
    print(json.dumps({'status': 'error', 'error_type': 'Transport'}))
`
async function wordMarker(create) {
  const result = await pythonJSON(PYTHON_WORD_MARKER, [WORD_MARKER, create ? "1" : "0"], "Bounded Word marker probe")
  require(result.status === "ok", "Word could not create/verify the disposable unsaved marker")
  return result
}

let originalDefault = null
let canonicalPrimary = PRIMARY
let canonicalModified = MODIFIED
let restorationAttempted = false
async function restoreOriginal() {
  restorationAttempted = true
  require(originalDefault, "No original default was captured")
  let current = null
  try { current = (await readDefault()).current } catch { current = null }
  let actionStatus = "not-needed"
  if (!samePrinter(current, originalDefault)) {
    const restored = await reviewed("execute", originalDefault)
    actionStatus = restored.status || "unknown"
  }
  const verified = await readDefault()
  require(samePrinter(verified.current, originalDefault), "RESTORATION FAILED: original default was not read back")
  evidence.restoration = { status: actionStatus === "not-needed" ? "unchanged" : "restored", actionStatus }
  return evidence.restoration
}

let canonicalDuplex = DUPLEX_PRINTER
let originalDuplex = null
let originalOrientation = null
let wordRestorationFailed = false
let baselineWord = null
let baselineJobs = null
async function readDuplex() {
  const state = await readWordState(originalOrientation || "long-edge")
  const validation = state.validation || {}
  require(validation.status === "ok" && validation.match_count === 1,
    "Duplex printer is not one exact readable Get-PrintConfiguration target")
  require(state.jobs_status === "ok", "Get-PrintJob cannot prove the no-print-job invariant")
  return {
    current: validation.current_duplex ?? null,
    canonical: validation.printer,
    jobs: state.jobs,
  }
}
function assertNoNewJobs(state) {
  if (!baselineJobs) return
  const before = new Set(baselineJobs)
  require(state.jobs.every(id => before.has(id)), "A new print-job ID appeared during the preview journey")
}
function assertWordPreserved(preview) {
  return wordMarker(false).then(word => {
    require(baselineWord, "Word marker baseline is unavailable")
    require(word.document_count === baselineWord.document_count, "Word document count changed")
    require(JSON.stringify(word.saved_flags) === JSON.stringify(baselineWord.saved_flags),
      "A Word document Saved flag changed")
    require(word.marker_count === 1 && word.marker_text_ok === true, "Disposable marker content was not preserved")
    require(word.marker_saved === false, "Disposable marker was saved")
    if (preview) {
      require(word.preview === true && word.view_type === 4, "Word Print Preview/View.Type=4 is unverified")
      require(word.window_visible === true, "Word Print Preview is not visible")
      require(word.foreground === true, "Word Print Preview is not foreground")
    }
    return { preserved: true, saved: false, preview: word.preview }
  })
}
async function wordProof(expectedDuplex, preview) {
  const state = await readDuplex()
  assertNoNewJobs(state)
  if (expectedDuplex) require(state.current === expectedDuplex, "Independent Get-PrintConfiguration read mismatched")
  const word = await assertWordPreserved(preview)
  return { duplex: state.current, word, printJobs: "unchanged" }
}
async function restoreDuplex() {
  require(originalDuplex && originalOrientation, "No original duplex/orientation was captured")
  let current = null
  try { current = (await readDuplex()).current } catch { current = null }
  let actionStatus = "not-needed"
  if (current !== originalDuplex) {
    const restored = await reviewed("execute-word", canonicalDuplex, originalOrientation)
    actionStatus = restored.status || "unknown"
  }
  const verified = await readDuplex()
  assertNoNewJobs(verified)
  require(verified.current === originalDuplex, "WORD DUPLEX RESTORATION FAILED: original mode was not read back")
  if (baselineWord) await assertWordPreserved(false)
  evidence.wordRestoration = { status: actionStatus === "not-needed" ? "unchanged" : "restored", actionStatus }
  return evidence.wordRestoration
}

let tab = null
let ws = null
let seq = 0
const pending = new Map()
async function connectCDP() {
  await fetch(`${CDP}/json/version`, { signal: AbortSignal.timeout(WAIT_MS) })
    .then(r => r.json())
    .catch(() => { throw new Error("Chrome CDP :9240 is unreachable") })
  const home = await fetch(APP, { signal: AbortSignal.timeout(WAIT_MS) })
    .then(r => r.status).catch(() => 0)
  require(home === 200, "Chat UI :3000 is not serving HTTP 200")

  tab = await fetch(`${CDP}/json/new`, {
    method: "PUT",
    signal: AbortSignal.timeout(WAIT_MS),
  }).then(r => r.json())
  ws = new WebSocket(tab.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("CDP websocket timed out")), WAIT_MS)
    ws.onopen = () => { clearTimeout(timer); resolve() }
    ws.onerror = () => { clearTimeout(timer); reject(new Error("CDP websocket connection failed")) }
  })
  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    const waiter = pending.get(message.id)
    if (waiter) {
      clearTimeout(waiter.timer)
      pending.delete(message.id)
      waiter.resolve(message)
    }
  }
}
function sendCDP(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq
    const timer = setTimeout(() => {
      pending.delete(id)
      reject(new Error(`CDP timeout: ${method}`))
    }, 20_000)
    pending.set(id, { resolve, timer })
    ws.send(JSON.stringify({ id, method, params }))
  })
}
async function evalJS(expression) {
  const result = await sendCDP("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  })
  if (result.error || result.exceptionDetails) throw new Error("Browser evaluation failed")
  return result.result.result.value
}

const SEL_COLUMN = `[class*="space-y-6"][class*="p-4"]`
async function freshChat() {
  await sendCDP("Page.navigate", { url: APP })
  const deadline = Date.now() + WAIT_MS
  for (;;) {
    const ready = await evalJS(`(() => {
      const ta = document.querySelector('textarea')
      const col = document.querySelector('${SEL_COLUMN}')
      return document.readyState === 'complete' && !!ta && !col
        && document.body.textContent.includes('How can I help you today?')
    })()`).catch(() => false)
    if (ready) return
    require(Date.now() < deadline, "Fresh chat did not reach the empty state within 90 seconds")
    await sleep(400)
  }
}
async function typeAndSend(text) {
  const sent = await evalJS(`(() => {
    const ta = document.querySelector('textarea')
    if (!ta) return false
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
    set.call(ta, ${JSON.stringify(text)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    return true
  })()`)
  require(sent, "Composer textarea was not found")
}
async function assistantState() {
  return evalJS(`(() => {
    const col = document.querySelector('${SEL_COLUMN}')
    if (!col) return { count: 0, totalScreenshots: 0, lastScreenshots: [] }
    const blocks = [...col.children].filter(el => el.classList.contains('gap-3'))
    const last = blocks[blocks.length - 1]
    const answer = last?.querySelector('[data-answer-text]')
    const body = answer?.cloneNode(true)
    body?.querySelector('[data-follow-up]')?.remove()
    const images = [...(last?.querySelectorAll("img[src*='/mcp-action/screenshots/']") || [])]
    return {
      count: blocks.length,
      text: answer?.innerText || '',
      manual: body?.innerText || '',
      followUp: answer?.querySelector('[data-follow-up]')?.innerText || '',
      totalScreenshots: col.querySelectorAll("img[src*='/mcp-action/screenshots/']").length,
      lastScreenshots: images.map(img => ({ src: img.src, naturalWidth: img.naturalWidth, complete: img.complete })),
    }
  })()`)
}
async function composerMode() {
  return evalJS(`document.querySelector('button[data-composer-mode]')?.getAttribute('data-composer-mode') || ''`)
}
async function waitTurn(count) {
  const deadline = Date.now() + WAIT_MS
  for (;;) {
    const state = await assistantState()
    if (state.count >= count && state.text.trim() && await composerMode() === "send") return state
    require(Date.now() < deadline, `Assistant turn ${count} did not finish within 90 seconds`)
    await sleep(400)
  }
}
function assertNoScreenshot(state) {
  require(state.totalScreenshots === 0, "Unexpected MCP-action screenshot was rendered")
}
function assertDraft(state, printer, manualRequired = true) {
  const followUp = state.followUp.replace(/^💡\s*/, "").trim()
  require(followUp === OFFER, `Exact automatic-action offer was not the final follow-up: ${state.text.slice(-1600)}`)
  require(state.text.includes(printer), "Draft answer did not name the reviewed target")
  if (manualRequired) {
    const actionCount = (state.manual.match(/\b(?:click|select|open|choose|set|turn|expand|right-click)\b/gi) || []).length
    require(actionCount >= 2 && /\b(?:first|then|next|after|step)\b/i.test(state.manual), `Manual steps did not precede the offer: ${state.manual.slice(0, 2000)}`)
    require(/printer/i.test(state.manual), "Manual printer guidance was missing")
  }
  assertNoScreenshot(state)
}
function assertBlocked(state) {
  require(/blocked|no (?:eligible |pending )?(?:action|proposal)|nothing to confirm|cannot confirm|can't confirm|unable to confirm|nothing (?:was )?(?:changed|executed)|(?:not|don't) have.*(?:action|proposal)|already (?:completed|resolved|confirmed)/i.test(state.text),
    `Orphan/repeated confirmation was not reported as blocked or already resolved: ${state.text.slice(-1800)}`)
}
async function screenshotEvidence() {
  const deadline = Date.now() + WAIT_MS
  let state
  for (;;) {
    state = await assistantState()
    const image = state.lastScreenshots[0]
    if (state.lastScreenshots.length === 1 && image?.complete && image.naturalWidth > 0) break
    require(Date.now() < deadline, "Inline screenshot did not load with naturalWidth > 0 within 90 seconds")
    await sleep(400)
  }
  const image = state.lastScreenshots[0]
  const response = await fetch(image.src, {
    cache: "no-store",
    signal: AbortSignal.timeout(WAIT_MS),
  })
  require(response.status === 200, "Screenshot URL did not return HTTP 200")
  require((response.headers.get("cache-control") || "").split(/\s*,\s*/).includes("no-store"),
    "Screenshot URL did not return Cache-Control: no-store")
  const bytes = (await response.arrayBuffer()).byteLength
  require(bytes > 8, "Screenshot URL returned empty bytes")
  return { status: response.status, noStore: true, bytes, naturalWidth: image.naturalWidth }
}
function draftQuery(caseName) {
  const marker = `T032-${caseName}-${STAMP}`
  return `${marker} For a written Windows how-to answer, not a PowerShell, file, launch, or Office task: the exact target printer is ${canonicalPrimary}. Give tailored manual steps for making it the default printer, then create the reviewed mcp_action draft for windows_default_printer. The request is complete; do not ask for more context, and do not confirm, open Settings, capture, or execute anything.`
}
async function assertCurrent(printer) {
  const current = (await readDefault()).current
  require(samePrinter(current, printer), "Independent reviewed validation observed an unexpected default printer")
  return current
}

function wordDraftQuery(caseName, orientation) {
  return `T045-${caseName}-${STAMP} For a written Word duplex how-to answer, not an Office file task: the exact printer is ${canonicalDuplex} and orientation is ${orientation}. Give tailored manual steps, then create the reviewed mcp_action draft for word_printer_duplex with parameters printer and orientation. Explain the printer-wide effect beyond the current Word document and that a blank unsaved document is used only after confirmation for Print Preview. The request is complete; do not ask for context, confirm, execute, capture, save, close, or print anything.`
}
function hasPrinterWideDisclosure(text) {
  const scope = /printer-wide|printer-level|printer queue|printer itself|on the printer/i.test(text)
  const beyond = /outside|beyond|other (?:applications|apps|Word files|documents)|not (?:just|only)[^.]*(?:document|Word)|not (?:the|inside the|in the) file/i.test(text)
  return scope && beyond
}
function assertWordDraft(state, orientation, manualRequired = true) {
  assertDraft(state, canonicalDuplex, manualRequired)
  require(state.text.toLowerCase().includes(orientation), "Word draft omitted the stored orientation")
  require(hasPrinterWideDisclosure(state.text),
    `Word draft omitted printer-wide scope beyond the document: ${state.text.slice(-1800)}`)
}
function accessDenied(text) {
  return /access denied|unauthorized|permission|administrator|elevation/i.test(text)
}
async function runWordYes(orientation, { alreadyActive = false, repeated = false, modifiedFrom = null } = {}) {
  const before = await readDuplex()
  const draftOrientation = modifiedFrom || orientation
  await freshChat()
  await typeAndSend(wordDraftQuery(`yes-${draftOrientation}`, draftOrientation))
  assertWordDraft(await waitTurn(1), draftOrientation)
  const draftProof = await wordProof(before.current, false)
  let executed
  if (modifiedFrom) {
    await typeAndSend(`yes, but use ${orientation}`)
    const revised = await waitTurn(2)
    assertWordDraft(revised, orientation, false)
    await wordProof(before.current, false)
    await typeAndSend("yes")
    executed = await waitTurn(3)
  } else {
    await typeAndSend("yes")
    executed = await waitTurn(2)
  }
  const target = DUPLEX_MODES[orientation]
  const normalizedResult = executed.text.toLowerCase().replace(/[\s_-]+/g, "")
  const normalizedOrientation = orientation.toLowerCase().replace(/[\s_-]+/g, "")
  require(executed.text.includes(canonicalDuplex) && normalizedResult.includes(normalizedOrientation),
    `Word result omitted the stored printer/orientation: ${executed.text.slice(-1800)}`)

  if (accessDenied(executed.text)) {
    assertNoScreenshot(executed)
    const proof = await wordProof(null, false)
    require(proof.word.preview === draftProof.word.preview,
      "Access-denied Word action opened Print Preview despite the failed mutation")
    return {
      status: "environment-blocked",
      reason: "Set-PrintConfiguration access denied; administrator permission is required",
      before: before.current,
      after: proof.duplex,
      screenshot: false,
      word: proof.word,
      printJobs: proof.printJobs,
    }
  }

  require(executed.text.includes(before.current) && executed.text.includes(target),
    "Word execution did not report actual before/after duplex values")
  require(hasPrinterWideDisclosure(executed.text),
    `Word result omitted printer-wide scope: ${executed.text.slice(-1800)}`)
  if (alreadyActive) require(/already|no change|unchanged/i.test(executed.text),
    "Already-active Word action did not report changed:false/no change")
  const proof = await wordProof(target, true)
  const screenshot = await screenshotEvidence()
  const result = {
    before: before.current,
    after: proof.duplex,
    changed: before.current !== target,
    word: proof.word,
    printJobs: proof.printJobs,
    screenshot,
  }
  if (repeated) {
    await typeAndSend("yes")
    const repeat = await waitTurn(3)
    assertBlocked(repeat)
    require(repeat.totalScreenshots === 1 && repeat.lastScreenshots.length === 0,
      "Repeated Word yes produced duplicate execution evidence")
    await wordProof(target, false)
    result.duplicateExecution = false
  }
  return result
}
async function runWordSuite() {
  const initial = await readDuplex()
  canonicalDuplex = initial.canonical
  originalOrientation = Object.keys(DUPLEX_MODES).find(key => DUPLEX_MODES[key] === initial.current)
  require(originalOrientation, "Original duplex is not restorable through the two reviewed orientations")
  originalDuplex = initial.current
  baselineJobs = initial.jobs
  baselineWord = await wordMarker(true)
  require(baselineWord.marker_count === 1 && baselineWord.marker_text_ok === true,
    "Disposable Word marker was not created and verified")
  require(baselineWord.marker_saved === false, "Disposable Word marker did not remain Saved=false")
  require(baselineWord.document_count === baselineWord.preexisting_count + (baselineWord.marker_created ? 1 : 0),
    "Word marker creation changed an unexpected document count")
  const remainingSavedFlags = [...baselineWord.saved_flags]
  const markerFlagIndex = remainingSavedFlags.indexOf(baselineWord.marker_saved)
  if (markerFlagIndex >= 0) remainingSavedFlags.splice(markerFlagIndex, 1)
  require(JSON.stringify(remainingSavedFlags.sort()) === JSON.stringify([...baselineWord.preexisting_saved_flags].sort()),
    "Creating the disposable marker changed a pre-existing document Saved flag")

  await runCase("word-no", async () => {
    await freshChat()
    await typeAndSend(wordDraftQuery("no", "long-edge"))
    assertWordDraft(await waitTurn(1), "long-edge")
    await wordProof(originalDuplex, false)
    await typeAndSend("no")
    const cancelled = await waitTurn(2)
    assertNoScreenshot(cancelled)
    require(!cancelled.text.includes(OFFER), "Word decline repeated the automatic-action offer")
    const proof = await wordProof(originalDuplex, false)
    return { duplex: proof.duplex, screenshot: false, word: proof.word, printJobs: proof.printJobs }
  })

  await runCase("word-long-edge", () => runWordYes("long-edge"), { mutating: true })
  await runCase("word-short-edge", () => runWordYes("short-edge"), { mutating: true })
  await runCase("word-modified-long-to-short", () => runWordYes("short-edge", {
    modifiedFrom: "long-edge",
  }), { mutating: true })
  await runCase(`word-already-active-${originalOrientation}`, () => runWordYes(originalOrientation, {
    alreadyActive: true,
    repeated: true,
  }), { mutating: true })

  await runCase("unsupported-office-procedure", async () => {
    await freshChat()
    await typeAndSend(`T045-unsupported-${STAMP} For a written Excel how-to answer only, explain how to freeze panes. This is not a Word duplex request; do not execute or offer an automatic desktop action, open Print Preview, capture, save, close, or print.`)
    const answer = await waitTurn(1)
    require(answer.text.trim() && !answer.text.includes(OFFER),
      "Unsupported Office procedure produced an MCP-action offer or no manual answer")
    assertNoScreenshot(answer)
    const proof = await wordProof(originalDuplex, false)
    return { offer: false, duplex: proof.duplex, word: proof.word, printJobs: proof.printJobs }
  })
}

async function runCase(name, fn, { mutating = false } = {}) {
  const record = { name, status: "running" }
  evidence.cases.push(record)
  const started = Date.now()
  try {
    Object.assign(record, await fn())
    if (record.status === "running") record.status = "passed"
  } catch (error) {
    record.status = "failed"
    record.error = safeError(error)
    throw error
  } finally {
    if (mutating) {
      try { await (WORD_ONLY ? restoreDuplex() : restoreOriginal()) }
      catch (error) {
        record.status = "failed"
        record.restoration = "failed"
        record.error = safeError(error)
        evidence.status = "failed"
        if (WORD_ONLY) wordRestorationFailed = true
        console.error("RESTORATION FAILED: owner attention is required")
        throw error
      }
    }
    record.durationMs = Date.now() - started
  }
}

try {
  await connectCDP()
  if (WORD_ONLY) {
    await runWordSuite()
  } else {
  const initial = await readDefault()
  canonicalPrimary = initial.canonical
  originalDefault = initial.current
  require(originalDefault, "An existing per-user default printer is required for restoration")

  let modifiedAvailable = false
  if (MODIFIED && !samePrinter(MODIFIED, canonicalPrimary)) {
    try {
      const validation = await reviewed("validate", MODIFIED)
      canonicalModified = validation.printer || MODIFIED
      modifiedAvailable = validation.status === "ok" && validation.match_count === 1
    } catch { modifiedAvailable = false }
  }

  await runCase("default-printer-no", async () => {
    await freshChat()
    await typeAndSend(draftQuery("no"))
    assertDraft(await waitTurn(1), canonicalPrimary)
    await assertCurrent(originalDefault)
    await typeAndSend("no")
    const cancelled = await waitTurn(2)
    assertNoScreenshot(cancelled)
    require(!cancelled.text.includes(OFFER), "Decline unexpectedly repeated the automatic-action offer")
    await assertCurrent(originalDefault)
    return { defaultAfter: originalDefault, screenshot: false }
  })

  await runCase("orphan-yes", async () => {
    await freshChat()
    await typeAndSend("yes")
    const orphan = await waitTurn(1)
    assertBlocked(orphan)
    assertNoScreenshot(orphan)
    await assertCurrent(originalDefault)
    return { blocked: true, defaultAfter: originalDefault, screenshot: false }
  })

  await runCase("generic-follow-up", async () => {
    await freshChat()
    await typeAndSend("Without using tools, explain in two sentences why the sky is blue. End with the standalone ordinary follow-up question: Want me to explain Rayleigh scattering in more detail?")
    const first = await waitTurn(1)
    require(first.text.includes("Want me to explain Rayleigh scattering in more detail?"),
      "Ordinary follow-up was not preserved")
    require(!first.text.includes(OFFER), "Generic answer used the MCP-action offer")
    assertNoScreenshot(first)
    await typeAndSend("yes")
    const second = await waitTurn(2)
    require(/scatter/i.test(second.text), "Generic yes did not continue the ordinary topic")
    require(!second.text.includes(OFFER), "Generic yes was hijacked by MCP-action")
    assertNoScreenshot(second)
    await assertCurrent(originalDefault)
    return { ordinaryYes: true, defaultAfter: originalDefault, screenshot: false }
  })

  await runCase("default-printer-yes-and-repeated-yes", async () => {
    await freshChat()
    await typeAndSend(draftQuery("yes"))
    assertDraft(await waitTurn(1), canonicalPrimary)
    await assertCurrent(originalDefault)
    await typeAndSend("yes")
    const executed = await waitTurn(2)
    require(executed.text.includes(originalDefault) && executed.text.includes(canonicalPrimary),
      "Execution answer did not report the actual before/after printers")
    await assertCurrent(canonicalPrimary)
    const screenshot = await screenshotEvidence()

    await typeAndSend("yes")
    const repeated = await waitTurn(3)
    assertBlocked(repeated)
    require(repeated.totalScreenshots === 1 && repeated.lastScreenshots.length === 0,
      "Repeated yes produced duplicate execution evidence")
    await assertCurrent(canonicalPrimary)
    return {
      before: originalDefault,
      after: canonicalPrimary,
      changed: !samePrinter(originalDefault, canonicalPrimary),
      screenshot,
      duplicateExecution: false,
    }
  }, { mutating: true })

  if (!MODIFIED || !modifiedAvailable) {
    evidence.cases.push({
      name: "modified-yes-but-other",
      status: "skipped",
      reason: "MCP_ACTION_MODIFIED_PRINTER is absent, not installed, or duplicates the primary target",
    })
  } else {
    await runCase("modified-yes-but-other", async () => {
      await freshChat()
      await typeAndSend(draftQuery("modified"))
      assertDraft(await waitTurn(1), canonicalPrimary)
      await typeAndSend(`yes, but use ${canonicalModified}`)
      const revised = await waitTurn(2)
      assertDraft(revised, canonicalModified, false)
      await assertCurrent(originalDefault)

      await typeAndSend("yes")
      const executed = await waitTurn(3)
      require(executed.text.includes(canonicalModified), "Fresh confirmation did not report the revised target")
      await assertCurrent(canonicalModified)
      const screenshot = await screenshotEvidence()
      return { before: originalDefault, after: canonicalModified, oldProposalExecuted: false, screenshot }
    }, { mutating: true })
  }
  }

  evidence.status = evidence.cases.some(record => record.status === "environment-blocked")
    ? "completed-with-environment-blocked"
    : "passed"
} catch (error) {
  evidence.status = "failed"
  evidence.error = safeError(error)
  process.exitCode = 1
} finally {
  if (WORD_ONLY && originalDuplex && !wordRestorationFailed) {
    try { await restoreDuplex() }
    catch (error) {
      evidence.status = "failed"
      evidence.wordRestoration = { status: "failed" }
      wordRestorationFailed = true
      evidence.error = safeError(error)
      process.exitCode = 1
      console.error("WORD DUPLEX RESTORATION FAILED: owner attention is required")
    }
  } else if (!WORD_ONLY && originalDefault && !restorationAttempted) {
    try { await restoreOriginal() }
    catch (error) {
      evidence.status = "failed"
      evidence.restoration = { status: "failed" }
      evidence.error = safeError(error)
      process.exitCode = 1
      console.error("RESTORATION FAILED: owner attention is required")
    }
  }
  try { ws?.close() } catch {}
  if (tab?.id) await fetch(`${CDP}/json/close/${tab.id}`, {
    signal: AbortSignal.timeout(5000),
  }).catch(() => {})
  console.log(JSON.stringify(evidence))
}
