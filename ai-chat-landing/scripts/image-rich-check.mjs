#!/usr/bin/env node
// Spec 050 acceptance: image-rich chat answers on the live Chat UI.
// Fresh conversation per case; counts rendered <img> inside the assistant
// answer, requires non-empty alt/src, enforces the 10-image cap, and checks
// grouping (not a trailing gallery) for overview answers.
//
// Usage:
//   node ai-chat-landing/scripts/image-rich-check.mjs            # all cases
//   node ai-chat-landing/scripts/image-rich-check.mjs --smoke    # text-only only
//   node ai-chat-landing/scripts/image-rich-check.mjs --only=howto
//   PROMPT="..." MIN_IMAGES=3 node .../image-rich-check.mjs      # one ad-hoc case
//
// Env: APP_URL (default http://localhost:3000), CDP_URL (default http://localhost:9240),
//      TIMEOUT_MS (default 180000 per answer).
// Requires Chrome with --remote-debugging-port=9240 and `pnpm dev` running.

import { argv } from "node:process"

const APP = process.env.APP_URL || "http://localhost:3000"
const CDP = process.env.CDP_URL || "http://localhost:9240"
const TIMEOUT = Number(process.env.TIMEOUT_MS || 180000)
const SMOKE = argv.includes("--smoke")
const ONLY = argv.find(a => a.startsWith("--only="))?.slice(7) ?? null
const AD_HOC = process.env.PROMPT || null

const CASES = [
  {
    name: "howto",
    prompt: "Show me the step-by-step instructions for pairing a standard Bluetooth mouse on Windows 11.",
    followUp: "It's a generic Bluetooth mouse on Windows 11 — please show me the steps with the images from the source pages.",
    min: Number(process.env.MIN_IMAGES || 3),
    max: 10, grouping: true,
  },
  {
    name: "overview",
    prompt: "Show me examples of mechanical keyboards and what makes each one different.",
    followUp: "Just give me the overview with example images from the sources.",
    min: 2, max: 10, spread: true,
  },
  {
    name: "gallery",
    prompt: "Show me a big gallery of mechanical keyboard examples — as many as you can find, with images from the sources.",
    followUp: "Just show me the gallery with images from the sources, no more questions.",
    min: 1, max: 10,
  },
  {
    name: "chart",
    prompt: "Compare the battery life of the five most popular wireless mice in a chart, and also show me product images from the sources.",
    followUp: "Yes — include the chart and the product images from the sources.",
    min: 1, max: 10,
  },
  {
    name: "textonly",
    prompt: "What is the capital of France?",
    min: 0, max: 0,
  },
]

function die(msg) { console.error(`✗ ${msg}`); process.exit(1) }

const version = await fetch(`${CDP}/json/version`).then(r => r.json())
  .catch(() => die(`Chrome CDP ${CDP} unreachable — start Chrome with --remote-debugging-port=9240`))
if ((await fetch(APP).catch(() => ({ status: 0 }))).status !== 200) die(`${APP} not serving — start pnpm dev in ai-chat-landing/`)

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
    setTimeout(() => rej(new Error(`CDP timeout: ${method}`)), 30000)
  })
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
async function evalJS(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (r.error) throw new Error(`Runtime.evaluate: ${JSON.stringify(r.error)}`)
  if (r.exceptionDetails) throw new Error(`page exception: ${r.exceptionDetails.exception?.description ?? "unknown"}`)
  return r.result.result.value
}

const COLUMN = `[class*="space-y-6"][class*="p-4"]`

async function navigate() {
  await send("Page.navigate", { url: APP })
  for (let i = 0; i < 60; i++) {
    if (await evalJS("document.readyState").catch(() => "") === "complete") break
    await sleep(500)
  }
  await sleep(800)
}

async function newChat() {
  await evalJS(`document.querySelector('aside button.w-full')?.click(); true`)
  await sleep(700)
}

async function typeAndSend(text) {
  const ok = await evalJS(`(() => {
    const ta = document.querySelector('textarea')
    if (!ta) return false
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
    set.call(ta, ${JSON.stringify(text)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    return true
  })()`)
  if (!ok) die("composer textarea not found")
}

function lastAnswer() {
  return evalJS(`(() => {
    const col = document.querySelector('${COLUMN}')
    if (!col) return { missing: true }
    const blocks = [...col.children].filter(el => el.classList.contains('gap-3'))
    if (!blocks.length) return { count: 0 }
    const last = blocks[blocks.length - 1]
    const answer = last.querySelector('[data-answer-text]')
    if (!answer) return { count: blocks.length, len: 0, streaming: true }
    return {
      count: blocks.length,
      len: answer.innerText.length,
      streaming: !!last.querySelector('[role="status"]'),
      text: answer.innerText,
      images: [...answer.querySelectorAll('img')].map(img => ({
        src: img.currentSrc || img.src || "",
        alt: img.getAttribute('alt') || "",
        before: (() => {                       // text chars before this image
          let n = 0
          const w = document.createTreeWalker(answer, NodeFilter.SHOW_TEXT)
          let node
          while ((node = w.nextNode())) {
            if (img.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_PRECEDING) n += node.textContent.length
          }
          return n
        })(),
      })),
    }
  })()`)
}

async function waitAnswer() {
  const t0 = Date.now()
  let stable = 0, prev = -1
  for (;;) {
    const m = await lastAnswer().catch(() => ({ missing: true }))
    if (!m.missing && m.count > 0 && !m.streaming && m.len > 0) {
      if (m.len === prev) stable++
      else { stable = 0; prev = m.len }
      if (stable >= 2) return m
    }
    if (Date.now() - t0 > TIMEOUT) return null
    await sleep(1000)
  }
}

async function askWithFollowUp(c) {
  await typeAndSend(c.prompt)
  let m = await waitAnswer()
  if (!m) return null
  // The ask-first rule may produce a question-only first turn: answer it once.
  const asked = (m.text.match(/\?/g) || []).length > 0 && m.images.length === 0
  if (c.followUp && asked) {
    await typeAndSend(c.followUp)
    m = await waitAnswer()
  }
  return m
}

function evaluate(c, m) {
  const images = m?.images || []
  const problems = []
  const visible = images.length
  if (visible < c.min) problems.push(`only ${visible} images (min ${c.min})`)
  if (visible > c.max) problems.push(`${visible} images exceeds max ${c.max}`)
  const emptyAlt = images.filter(i => !i.alt.trim()).length
  const emptySrc = images.filter(i => !i.src.trim() || i.src.startsWith("data:")).length
  if (emptyAlt) problems.push(`${emptyAlt} image(s) without alt text`)
  if (emptySrc) problems.push(`${emptySrc} image(s) without a usable src`)
  if (c.grouping && visible >= 1) {
    const total = Math.max(m.len, 1)
    const first = Math.min(...images.map(i => i.before))
    if (first > total * 0.7) problems.push("first image sits below the last 30% of the answer (not grouped with steps)")
  }
  if (c.spread && visible >= 2) {
    const total = Math.max(m.len, 1)
    const trailing = images.filter(i => i.before > total * 0.75).length
    if (trailing === visible) problems.push("all images clustered at the end")
  }
  return { case: c.name, visible, with_alt: visible - emptyAlt, empty_src: emptySrc, pass: problems.length === 0, problems }
}

await navigate()
const cases = AD_HOC
  ? [{ name: "ad-hoc", prompt: AD_HOC, min: Number(process.env.MIN_IMAGES || 1), max: 10 }]
  : SMOKE ? CASES.filter(c => c.name === "textonly")
  : ONLY ? CASES.filter(c => c.name === ONLY) : CASES

let failed = 0
for (const c of cases) {
  await newChat()
  const m = await askWithFollowUp(c)
  const result = m ? evaluate(c, m) : { case: c.name, visible: 0, pass: false, problems: ["no answer within timeout"] }
  console.log(JSON.stringify(result))
  if (!result.pass) failed++
}
console.log(`\n${failed === 0 ? "PASS" : "FAIL"} — ${cases.length - failed}/${cases.length} cases`)
process.exit(failed === 0 ? 0 : 1)
