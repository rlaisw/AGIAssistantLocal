#!/usr/bin/env node
// Spec 046 live acceptance: only the infographic notification link is pinned and
// blue; every other rendering path is left alone. Uses deterministic echoes.
import http from "node:http"
import { execFileSync } from "node:child_process"

const APP = process.env.APP_URL || "http://localhost:3000"
const CDP = process.env.CDP_URL || "http://localhost:9240"
const INFO_URL = "http://localhost:28080/infographics/e468aaee5ee3/"
const APPLE_URL = "https://support.apple.com/en-us/HT204204"
const DECK_URL = "http://localhost:28080/decks/deploy_automation_20261119/deploy_automation_20261119_034050/"

function getJSON(path) {
  return new Promise((resolve, reject) => {
    http.get(new URL(path, CDP), (r) => {
      let data = ""
      r.on("data", (c) => (data += c))
      r.on("end", () => resolve(JSON.parse(data)))
    }).on("error", reject)
  })
}

const tabs = await getJSON("/json/list")
const page = tabs.find((t) => t.type === "page")
if (!page) throw new Error("no CDP page target")
const ws = new WebSocket(page.webSocketDebuggerUrl)
const pending = new Map()
let seq = 0
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m)
    pending.delete(m.id)
  }
}
await new Promise((r) => (ws.onopen = r))
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq
    pending.set(id, resolve)
    ws.send(JSON.stringify({ id, method, params }))
    setTimeout(() => reject(new Error(`CDP timeout: ${method}`)), 15000)
  })
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
async function evalJS(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (r.error) throw new Error(JSON.stringify(r.error))
  if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails))
  return r.result.result.value
}
const failures = []
function check(name, ok, detail = "") {
  console.log(`${ok ? "✓" : "✗"} ${name}${detail ? ` — ${detail}` : ""}`)
  if (!ok) failures.push(name)
}

await send("Page.enable")
async function freshChat() {
  await send("Page.navigate", { url: APP })
  for (let i = 0; i < 40; i++) {
    try {
      if ((await evalJS("document.readyState")) === "complete") break
    } catch {}
    await sleep(500)
  }
  await sleep(900)
}
async function typeText(text) {
  await evalJS(`(() => {
    const ta = document.querySelector('textarea')
    if (!ta) throw new Error('composer textarea not found')
    const set = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    set.call(ta, ${JSON.stringify(text)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)
}
async function clickSend() {
  await evalJS(`(() => {
    const b = document.querySelector('button[data-composer-mode="send"]:not([disabled])')
    if (!b) throw new Error('send button unavailable')
    b.click()
  })()`)
}
async function waitFor(expression, timeout = 90000) {
  const started = Date.now()
  for (;;) {
    const value = await evalJS(`(() => !!(${expression}))()`)
    if (value) return true
    if (Date.now() - started > timeout) return false
    await sleep(1500)
  }
}
async function refBlue() {
  return evalJS(`(() => {
    const p = document.createElement('div')
    p.className = 'text-blue-600 dark:text-blue-400'
    document.body.appendChild(p)
    const c = getComputedStyle(p).color
    p.remove()
    return c
  })()`)
}

async function mainEcho() {
  const query = `Reply with exactly this markdown line and nothing else: [Open the step-by-step infographic](${INFO_URL})`
  await freshChat()
  await typeText(query)
  await clickSend()
  check("V1 infographic link appears during streaming (E5)", await waitFor(`document.querySelector('[data-infographic-link]')`), "styled link present")
  await waitFor(`!document.querySelector('[data-composer-mode="stop"]') && document.querySelector('[data-infographic-link]')`, 180000)
  const info = await evalJS(`(() => {
    const a = document.querySelector('[data-infographic-link]')
    if (!a) return null
    return { text: a.textContent.trim(), color: getComputedStyle(a).color,
      target: a.target, href: a.href, cls: a.className }
  })()`)
  check("V1 label begins with one 📌", !!info?.text?.startsWith("📌"), info?.text)
  check("V1 existing label wording is preserved", /Open the step-by-step infographic/i.test(info?.text || ""), info?.text)
  const blue = await refBlue()
  check("V1 computed color equals follow-up blue", info?.color === blue, `${info?.color} vs ${blue}`)
  check("V1 href and new-tab behavior unchanged", info?.target === "_blank" && info?.href === INFO_URL, info?.href)
  check("V1 dark-theme token present", info?.cls?.includes("dark:text-blue-400"), info?.cls)
}

async function oldWording() {
  await freshChat()
  await typeText(`Reply with exactly this markdown line and nothing else: [open the infographic](${INFO_URL})`)
  await clickSend()
  check("E4 old wording still gets 📌 (URL-based)", await waitFor(`document.querySelector('[data-infographic-link]')`), "old label styled")
}

async function nestedLabel() {
  await freshChat()
  await typeText(`Reply with exactly this markdown line and nothing else: [**Open** the step-by-step infographic](${INFO_URL})`)
  await clickSend()
  await waitFor(`document.querySelector('[data-infographic-link]')`)
  const ok = await evalJS(`(() => {
    const a = document.querySelector('[data-infographic-link]')
    return a && !a.textContent.includes('[object Object]') && !!a.querySelector('strong')
  })()`)
  check("E2 nested markdown label renders as nodes, not [object Object]", !!ok, "strong node present")
}

async function duplicatePin() {
  await freshChat()
  await typeText(`Reply with exactly this markdown line and nothing else: [📌 Open the step-by-step infographic](${INFO_URL})`)
  await clickSend()
  await waitFor(`document.querySelector('[data-infographic-link]')`)
  const text = await evalJS(`document.querySelector('[data-infographic-link]').textContent.trim()`)
  const count = (text.match(/📌/g) || []).length
  check("E3 model-emitted pin is not duplicated", count === 1, text)
}

async function multipleLinks() {
  await freshChat()
  await typeText(`Reply with exactly this markdown text and nothing else: [Open the step-by-step infographic](${INFO_URL}) and [More infographics](${INFO_URL})`)
  await clickSend()
  await waitFor(`document.querySelectorAll('[data-infographic-link]').length === 2`)
  const info = await evalJS(`[...document.querySelectorAll('[data-infographic-link]')].map(a => a.textContent.trim())`)
  check("E7 each infographic link gets exactly one renderer pin", info.length === 2 && info.every(t => t.startsWith("📌") && (t.match(/📌/g) || []).length === 1), JSON.stringify(info))
}

async function plainAndDeck() {
  await freshChat()
  await typeText(`Reply with exactly this markdown line and nothing else: [Apple support article](${APPLE_URL})`)
  await clickSend()
  await waitFor(`[...document.querySelectorAll('a')].some(a => a.href === '${APPLE_URL}')`)
  const plain = await evalJS(`(() => {
    const a = [...document.querySelectorAll('a')].find(a => a.href === '${APPLE_URL}')
    return { styled: a.hasAttribute('data-infographic-link'), pin: a.textContent.includes('📌'), cls: a.className }
  })()`)
  check("E1 plain external link has no pin or infographic styling", plain && !plain.styled && !plain.pin, JSON.stringify(plain))

  await freshChat()
  await typeText(`Reply with exactly this markdown line and nothing else: [open the deck](${DECK_URL})`)
  await clickSend()
  await waitFor(`document.body.innerText.toLowerCase().includes('download') || document.body.innerText.toLowerCase().includes('preview')`)
  const deck = await evalJS(`(() => {
    const a = [...document.querySelectorAll('a')].find(a => a.href === '${DECK_URL}')
    return { inf: a ? a.hasAttribute('data-infographic-link') : false,
      action: document.body.innerText.toLowerCase().includes('download') || document.body.innerText.toLowerCase().includes('preview') }
  })()`)
  check("V2 deck keeps its action bar and no infographic styling", deck?.action && !deck.inf, JSON.stringify(deck))
}

async function imageAndFollowUp() {
  await freshChat()
  await typeText("Reply with exactly this markdown and nothing else: ![AGI sample](https://example.com/sample.png)")
  await clickSend()
  await waitFor(`document.querySelector('img')`)
  const img = await evalJS(`(() => {
    const i = document.querySelector('img')
    return { src: i.src, hasInf: i.hasAttribute('data-infographic-link') }
  })()`)
  check("V2 inline image rendering unchanged", img?.src === "https://example.com/sample.png" && !img.hasInf, img?.src)

  await freshChat()
  await typeText("Reply with exactly these two paragraphs and nothing else: This is a sample answer.\n\nWant me to show an example?")
  await clickSend()
  await waitFor(`document.querySelector('[data-follow-up]')`)
  const fu = await evalJS(`(() => {
    const el = document.querySelector('[data-follow-up]')
    return { bulb: el.textContent.includes('💡'), color: getComputedStyle(el).color }
  })()`)
  const blue = await refBlue()
  check("V2 follow-up keeps 💡 and its blue token", fu?.bulb && fu.color === blue, JSON.stringify(fu))
}

async function followUpBeforeLink() {
  await freshChat()
  await typeText(`Reply with exactly these three paragraphs and nothing else: This is the answer body.\n\nWant me to tailor the steps?\n\n[Open the step-by-step infographic](${INFO_URL})`)
  await clickSend()
  await waitFor(`document.querySelector('[data-follow-up]') && document.querySelector('[data-infographic-link]')`, 120000)
  const result = await evalJS(`(() => {
    const fu = document.querySelector('[data-follow-up]')
    const link = document.querySelector('[data-infographic-link]')
    return {
      text: fu?.textContent ?? '',
      color: fu ? getComputedStyle(fu).color : '',
      hasBulb: fu?.textContent.includes('💡') ?? false,
      link: link?.href ?? ''
    }
  })()`)
  const blue = await refBlue()
  check(
    "Follow-up before infographic link is re-added with 💡 + blue",
    result.text.includes("Want me to tailor the steps?") && result.hasBulb && result.color === blue && result.link === INFO_URL,
    JSON.stringify(result)
  )
}

async function generationFollowUp() {
  await freshChat()
  await typeText("Explain how to back up a phone in 3 steps, and also create an infographic summary of the steps.")
  await clickSend()
  for (let turn = 0; turn < 3; turn++) {
    const hasFollowUp = await waitFor(`document.querySelector('[data-follow-up]')`, 180000)
    if (hasFollowUp) break
    // A how-to can trigger spec 045's ask-first turn; answer its context question
    // so the next turn must produce the infographic plus the follow-up.
    await typeText("iPhone 13 on iOS 17, over Wi-Fi to iCloud, please give the steps and the infographic summary.")
    await clickSend()
  }
  const result = await evalJS(`(() => {
    const fu = document.querySelector('[data-follow-up]')
    const link = document.querySelector('[data-infographic-link]')
    return { followUp: fu?.textContent ?? '', link: link?.href ?? '' }
  })()`)
  check(
    "Generated answer ends with a follow-up after the infographic link",
    /want me to|would you like|should i|shall i/i.test(result.followUp) && result.link.includes('/infographics/'),
    JSON.stringify(result)
  )
}

async function storedTextCheck() {
  const query = `Reply with exactly this markdown line and nothing else: [Open the step-by-step infographic](${INFO_URL})`
  const sql = `select coalesce(answer,'') from messages where query = '${query.replaceAll("'", "''")}' order by created_at desc limit 1`
  const answer = execFileSync("docker", ["exec", "docker-db_postgres-1", "psql", "-U", "postgres", "-d", "dify", "-t", "-A", "-c", sql], { encoding: "utf8", maxBuffer: 4 * 1024 * 1024 })
  check("E8 stored answer contains no renderer-added 📌", answer.length > 0 && !answer.includes("📌"), `stored answer length=${answer.length}`)
}

await mainEcho()
await oldWording()
await nestedLabel()
await duplicatePin()
await multipleLinks()
await plainAndDeck()
await imageAndFollowUp()
await followUpBeforeLink()
await generationFollowUp()
await storedTextCheck()

console.log(failures.length ? `FAILED: ${failures.join("; ")}` : "All infographic notification-link checks passed")
process.exit(failures.length ? 1 : 0)
