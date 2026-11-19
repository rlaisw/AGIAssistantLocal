#!/usr/bin/env node
// Spec 046 acceptance: the infographic notify line renders as 📌 + blue with a
// working link; neighbors (deck bar, plain links, follow-up line) unchanged;
// --loop N runs the SC-001 battery (N differently-phrased asks).
const APP = process.env.APP_URL || "http://localhost:3000"
const CDP = process.env.CDP_URL || "http://localhost:9240"
const LOOP = Number.parseInt(process.argv.find(a => a === "--loop" ? a : "") ? process.argv[process.argv.indexOf("--loop") + 1] : "1", 10)

import http from "node:http"
function getJSON(path) {
  return new Promise((res, rej) => {
    http.get(new URL(path, CDP), r => {
      let d = ""; r.on("data", c => d += c); r.on("end", () => res(JSON.parse(d)))
    }).on("error", rej)
  })
}
const tabs = await getJSON("/json/list")
const page = tabs.find(t => t.type === "page")
if (!page) throw new Error("no CDP page target")
const ws = new WebSocket(page.webSocketDebuggerUrl)
const pending = new Map()
let seq = 0
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } }
await new Promise(r => ws.onopen = r)
function send(method, params = {}) {
  return new Promise((res, rej) => {
    const id = ++seq
    pending.set(id, res)
    ws.send(JSON.stringify({ id, method, params }))
    setTimeout(() => rej(new Error(`CDP timeout: ${method}`)), 120000)
  })
}
const sleep = ms => new Promise(r => setTimeout(r, ms))
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
async function freshChat() {
  await send("Page.navigate", { url: APP })
  for (let i = 0; i < 60; i++) {
    try { if (await evalJS("document.readyState") === "complete") break } catch {}
    await sleep(500)
  }
  await sleep(1200)
}
async function typeText(text) {
  await evalJS(`(() => {
    const ta = document.querySelector('textarea')
    if (!ta) throw new Error('no composer textarea')
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
    setter.call(ta, ${JSON.stringify(text)})
    ta.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)
}
async function clickSend() {
  await evalJS(`(() => {
    const btn = document.querySelector('button[data-composer-mode="send"]:not([disabled])')
    if (!btn) throw new Error('send button not found or disabled')
    btn.click()
  })()`)
}
const ANSWER_DONE = `(() => {
  const sel = '[data-follow-up], [data-infographic-link]'
  const asst = [...document.querySelectorAll('main div')].filter(d => d.querySelector('[data-infographic-link], a, p'))
  return {
    styled: !!document.querySelector('[data-infographic-link]'),
    followUp: !!document.querySelector('[data-follow-up]'),
    thinking: !!document.querySelector('[data-streaming], .animate-pulse'),
    text: document.body.innerText.length,
  }
})()`
async function waitAnswerDone(timeoutMs = 240000) {
  let last = null
  const start = Date.now()
  for (;;) {
    last = await evalJS(ANSWER_DONE)
    if (last.styled && !last.thinking) return last
    if (Date.now() - start > timeoutMs) return last
    await sleep(3000)
  }
}

const ASKS = [
  "Explain how to set up a Wi-Fi router, step by step, and also create an infographic summary of the steps",
  "Summarize the steps to configure a new phone, and also create an infographic summary of the steps",
  "Give me the process for a monthly computer maintenance routine, and also create an infographic summary of the steps",
]

const blue = () => evalJS(`(() => {
  const a = document.querySelector('[data-infographic-link]')
  if (!a) return null
  const cs = getComputedStyle(a)
  return { text: a.textContent.trim(), color: cs.color, target: a.target, href: a.href,
           classes: a.className, followUp: !!document.querySelector('[data-follow-up]') }
})()`)

let styled = 0
for (let i = 0; i < LOOP; i++) {
  await freshChat()
  await typeText(ASKS[i % ASKS.length])
  await clickSend()
  let done = await waitAnswerDone(180000)
  // spec 045 ask-first: a how-to ask may answer with context questions first —
  // answer them, then the tailored reply carries the infographic link
  if (!done.styled) {
    const asked = await evalJS("document.body.innerText.includes('?')")
    if (asked) {
      await typeText("A standard home setup, latest model, over Wi-Fi — please give the steps and the infographic summary.")
      await clickSend()
      done = await waitAnswerDone(240000)
    }
  }
  check(`V1 ask ${i + 1}: styled infographic link rendered`, done.styled, JSON.stringify(done))
  const info = await blue()
  check(`V1 ask ${i + 1}: label carries 📌 and the canonical wording`, info?.text?.startsWith("📌") && /Open the step-by-step infographic/i.test(info?.text ?? ""), info?.text ?? "missing")
  const refBlue = await evalJS(`(() => {
    const probe = document.createElement("div")
    probe.className = "text-blue-600 dark:text-blue-400"
    document.body.appendChild(probe)
    const c = getComputedStyle(probe).color
    probe.remove()
    return c
  })()`)
  check(`V1 ask ${i + 1}: computed color equals the blue token (theme-aware)`, !!info?.color && info.color === refBlue, `${info?.color} vs ${refBlue}`)
  check(`V1 ask ${i + 1}: link opens in a new tab with the infographic href`, info?.target === "_blank" && (info?.href ?? "").includes("/infographics/"), info?.href ?? "missing")
  if (done.styled) styled++
  const dark = await evalJS(`(() => document.querySelector('[data-infographic-link]')?.className.includes('dark:text-blue-400') ?? false)()`)
  check(`V1 ask ${i + 1}: dark-theme token present`, dark, String(dark))
}
check(`SC-001 battery ${styled}/${LOOP} styled`, styled === LOOP, `${styled}/${LOOP}`)

// E6 — old wording still styles (URL-based detection): ask the model to echo the old label
await freshChat()
await typeText("Reply with exactly this markdown line and nothing else: [open the infographic](http://localhost:28080/infographics/e468aaee5ee3/)")
await clickSend()
const e6done = await waitAnswerDone()
check("E6 old-wording link still styled (URL-based)", e6done.styled, JSON.stringify(e6done))

// ---------------------------------------------------------------------------
// V2 (US2 / SC-003): neighbors keep today's appearance — three probes:
//   A) a deck link renders the action bar (two-turn-safe); its reply's
//      follow-up line keeps 💡+blue when present;
//   B) a plain external link (exact-echo, deterministic) stays unstyled.
// ---------------------------------------------------------------------------
{
  await freshChat()
  await typeText("Create a one-page PowerPoint deck named v2check with the title 'Q4 Review'.")
  await clickSend()
  let nb = await waitAnswerDone(240000)
  for (let turn = 0; turn < 3 && !(await evalJS("!!document.querySelector('[data-deck-actions], a[href*='.pptx']')")); turn++) {
    if (!(await evalJS("document.body.innerText.includes('?')"))) break
    await typeText("Just one page: title 'Q4 Review'. No extra pages.")
    await clickSend()
    nb = await waitAnswerDone(240000)
  }
  const deck = await evalJS(`(() => !!document.querySelector('[data-deck-actions], a[href*="/exports/"], a[href*=".pptx"]'))()`)
  check("V2 deck link renders the deck action bar (not infographic styling)", deck, String(deck))
  const fu = await evalJS(`(() => {
    const el = document.querySelector('[data-follow-up]')
    if (!el) return null
    return { hasBulb: el.textContent.includes('💡'), color: getComputedStyle(el).color }
  })()`)
  if (fu) {
    check("V2 follow-up line keeps 💡", fu.hasBulb, JSON.stringify(fu))
    const blueRef = await evalJS(`(() => {
      const probe = document.createElement("div")
      probe.className = "text-blue-600 dark:text-blue-400"
      document.body.appendChild(probe)
      const c = getComputedStyle(probe).color
      probe.remove()
      return c
    })()`)
    check("V2 follow-up line keeps its blue", fu.color === blueRef, `${fu.color} vs ${blueRef}`)
  } else {
    check("V2 follow-up line keeps 💡 (skipped: no follow-up in this reply)", true, "no follow-up paragraph — allowed")
  }

  await freshChat()
  await typeText("Reply with exactly this markdown line and nothing else: [Apple support article](https://support.apple.com/en-us/HT204204)")
  await clickSend()
  await waitAnswerDone(180000)
  const plain = await evalJS(`(() => {
    const links = [...document.querySelectorAll('a')].filter(a => a.href.includes('support.apple.com'))
    return links.map(a => ({ styled: a.hasAttribute('data-infographic-link'), emoji: a.textContent.includes('📌'), text: a.textContent.trim() }))
  })()`)
  check("V2 plain external link is unstyled (no 📌, no infographic styling)", plain.length > 0 && plain.every(l => !l.styled && !l.emoji), JSON.stringify(plain))
}

console.log(fails.length ? `FAILED: ${fails.join("; ")}` : "All infographic notify-line checks passed")
process.exit(fails.length ? 1 : 0)
