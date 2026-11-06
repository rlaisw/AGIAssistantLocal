"use client"

import * as React from "react"
import { useTheme } from "next-themes"
import {
  ArrowUp,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  Copy,
  Link2,
  LoaderCircle,
  LogOut,
  Mic,
  Monitor,
  Moon,
  MoreHorizontal,
  Paperclip,
  PanelLeft,
  Plus,
  RefreshCw,
  Search,
  Settings,
  Share2,
  Square,
  Sun,
  ThumbsDown,
  ThumbsUp,
  User,
} from "lucide-react"

import { ChatHistory } from "@/components/chat-history"
import { ModelDropdown } from "@/components/model-dropdown"
import { PdfExportButton } from "@/components/pdf-export-button"
import { createHistoryState } from "@/lib/history/state"
import { filterHistory } from "@/lib/history/search"
import type { ConversationRecord } from "@/lib/history/types"
import { HistoryError } from "@/lib/history/types"
import { badgeModel, badgeNote, type BadgeValue } from "@/lib/models/badge"
import { fetchAvailability } from "@/lib/models/availability"
import { createModelStorage } from "@/lib/models/persistence"
import { DEFAULT_MODEL_ID, isModelId, optionById, type ModelId } from "@/lib/models/options"
import { splitFollowUp } from "@/lib/follow-up"
import {
  composerMode,
  decideStopAction,
  finalizeOnStop,
  shouldCallBackendStop,
} from "@/lib/stop/state"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Markdown } from "@/components/markdown"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"

type Message = {
  id: number
  role: "user" | "assistant"
  text: string
  reasoning?: string
  code?: string
  codeName?: string
  sources?: string[]
  streaming?: boolean
  noBadge?: boolean
  // spec 027: session-only stop marker (survives conversation switching,
  // lost on reload — the partial transcript is the durable record)
  stopped?: boolean
}

type Conversation = {
  id: string
  title: string
  messages: Message[]
  difyId?: string
}

const cannedReplies = [
  {
    text: "Here's how I'd approach it:\n\n1. Start with the smallest working version and ship it behind a flag.\n2. Measure the real bottleneck before optimizing anything.\n3. Roll out gradually, watching error rates at each step.",
    sources: ["engineering-handbook.md"],
  },
  {
    text: "Good question. The short version: it depends on your constraints, but for most teams the pragmatic order is data model first, then API surface, then UI. Each layer should be usable before the next one exists.",
  },
  {
    text: "Here's a compact implementation:",
    code: `export function debounce<T extends (...args: never[]) => void>(
  fn: T,
  wait = 200
) {
  let timer: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), wait)
  }
}`,
    codeName: "debounce.ts",
  },
]

const FEATURE_CARDS = [
  {
    title: "Generate PowerPoint",
    icon: "📊",
    description: "Create professional PowerPoint from text prompts in minutes",
    label: "How to create PPT",
    url: "/example1.html",
  },
  {
    title: "Generate Infographic",
    icon: "🎨",
    description: "Design eye-catching infographics without design skills",
    label: "How to create Infographic",
    url: "/example2.html",
  },
  {
    title: "Draw Chart Diagram",
    icon: "📈",
    description: "Visualize data with interactive charts and flow diagrams",
    label: "How to create chart diagram",
    url: "/example3.html",
  },
  {
    title: "Talk with CorpIT Helpdesk Chatbot",
    icon: "💻",
    description: "Get instant IT support and troubleshooting guidance",
    label: "Chat with CorpIT Support",
    url: "/example4.html",
  },
  {
    title: "Ask Any Question with AI Chatbot",
    icon: "🤖",
    description: "Access knowledge across domains with our intelligent assistant",
    label: "Ask AI Chatbot",
    url: "/example5.html",
  },
  {
    title: "Create Personal Agentic RAG Document DB",
    icon: "💾",
    description: "Build your own searchable knowledge base with AI-powered Agentic RAG",
    label: "Create Self-Hosted Agentic RAG",
    url: "/example6.html",
  },
]

const FLUSH_MS = 100
const WATCHDOG_MS = 120000

function parseAnswer(raw: string): { text: string; reasoning?: string } {
  let reasoning = ""
  const text = raw
    .replace(/<think>([\s\S]*?)(?:<\/think>|$)/g, (_, inner: string) => {
      reasoning += inner
      return ""
    })
    .replace(/<\/?think>$/, "")
    .trim()
  return { text, reasoning: reasoning.trim() || undefined }
}

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 pt-2.5 text-muted-foreground" role="status">
      <LoaderCircle className="size-4 animate-spin text-[#82D2F6]" aria-hidden="true" />
      <span className="text-sm font-semibold">Thinking</span>
    </div>
  )
}

// follow-up prompts (2026-10-28): the trailing "Want me to…?" paragraph of a
// finished answer renders as blue text with a 💡; mid-stream it stays inline
function AssistantText({ message }: { message: Message }) {
  if (!message.text) return <ThinkingIndicator />
  const { body, followUp } = message.streaming
    ? { body: message.text, followUp: undefined }
    : splitFollowUp(message.text)
  return (
    <>
      <div data-answer-text>
        <Markdown>{body}</Markdown>
        {followUp && (
          <div className="mt-3 text-blue-600 dark:text-blue-400" data-follow-up>
            <Markdown>{`💡 ${followUp}`}</Markdown>
          </div>
        )}
      </div>
      {message.streaming && <ThinkingIndicator />}
    </>
  )
}

export default function Page() {
  const [conversations, setConversations] = React.useState<Conversation[]>([
    { id: "c-0", title: "New chat", messages: [] },
  ])
  const [activeId, setActiveId] = React.useState("c-0")
  const [input, setInput] = React.useState("")
  const [sidebarOpen, setSidebarOpen] = React.useState(true)
  const [busy, setBusy] = React.useState(false)
  const [copiedId, setCopiedId] = React.useState<number | null>(null)
  const modelStorage = React.useMemo(
    () => createModelStorage(typeof window === "undefined" ? null : window.localStorage),
    []
  )
  const [selectionByConv, setSelectionByConv] = React.useState<Record<string, ModelId>>({})
  const [localAvailable, setLocalAvailable] = React.useState(false)
  // spec 026: the configured cloud model is server truth (the published app);
  // applyingModel blocks sends while a reconfiguration cycle runs (FR-003).
  const [configuredCloud, setConfiguredCloud] = React.useState<ModelId>(DEFAULT_MODEL_ID)
  const [applyingModel, setApplyingModel] = React.useState<ModelId | null>(null)
  const [applyError, setApplyError] = React.useState<string | null>(null)
  const { theme, setTheme } = useTheme()
  const history = React.useMemo(
    () =>
      createHistoryState({
        fetchPage: async (cursor?: string) => {
          const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""
          const res = await fetch(`/api/conversations${q}`)
          if (!res.ok) {
            const detail = (await res.json().catch(() => null)) as
              | { error?: string }
              | null
            throw new HistoryError("history_unavailable", detail?.error)
          }
          return (await res.json()) as Awaited<
            ReturnType<typeof import("@/lib/history/mappers")["mapConversationPage"]>
          >
        },
      }),
    []
  )
  const [historyRecords, setHistoryRecords] = React.useState<
    import("@/lib/history/types").ConversationRecord[]
  >([])
  const [loadingMore, setLoadingMore] = React.useState(false)

  const syncHistory = React.useCallback(() => {
    setHistoryRecords([...history.records])
  }, [history])
  const [searchQuery, setSearchQuery] = React.useState("")
  const [debouncedQuery, setDebouncedQuery] = React.useState("")
  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(searchQuery), 200)
    return () => clearTimeout(t)
  }, [searchQuery])
  const contentMap = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const c of conversations) {
      if (c.difyId) m.set(c.difyId, c.messages.map((msg) => msg.text).join("\n"))
    }
    return m
  }, [conversations])
  const filteredRecords = React.useMemo(
    () => filterHistory(historyRecords, (id) => contentMap.get(id), debouncedQuery),
    [historyRecords, contentMap, debouncedQuery]
  )

  React.useEffect(() => {
    void history.load().then(syncHistory)
  }, [history, syncHistory])

  const streamRef = React.useRef<ReturnType<typeof setInterval> | null>(null)
  const abortRef = React.useRef<AbortController | null>(null)
  const replyRef = React.useRef(0)
  const idRef = React.useRef(3)
  const scrollRef = React.useRef<HTMLDivElement>(null)
  // spec 027: the in-flight generation (single-flight app-wide, research R5)
  // and the one-way stop latch (FR-009). genRef survives conversation switches
  // so the generation keeps updating its own conversation (FR-010).
  const genRef = React.useRef<{
    convId: string
    assistantId: number
    title: string
    model: ModelId
    taskId: string | null
    isDemo: boolean
  } | null>(null)
  const stopRequestedRef = React.useRef(false)

  const active =
    conversations.find((c) => c.id === activeId) ?? conversations[0]
  // spec 026: local selection stays per-conversation; a cloud selection means
  // "the globally configured model" (server truth supersedes stored choices).
  const storedSelection = selectionByConv[activeId]
  const activeModel: ModelId = storedSelection === "local" ? "local" : configuredCloud
  // spec 027 (FR-001/FR-010): Stop replaces Send only while the viewed
  // conversation is the one generating; re-renders on busy/activeId changes
  // cover every transition of genRef this depends on
  const stopMode = composerMode({
    busy,
    viewingGeneratingConversation: genRef.current?.convId === activeId,
  })

  const refreshAvailability = React.useCallback(() => {
    void fetchAvailability().then(setLocalAvailable)
  }, [])
  React.useEffect(() => {
    refreshAvailability()
  }, [refreshAvailability])
  const refreshConfiguredModel = React.useCallback(() => {
    void fetch("/api/models/current")
      .then((r) => (r.ok ? r.json() : null))
      .then((body: { model?: string } | null) => {
        if (body?.model && isModelId(body.model)) setConfiguredCloud(body.model)
      })
      .catch(() => {})
  }, [])
  React.useEffect(() => {
    refreshConfiguredModel()
  }, [refreshConfiguredModel])
  // close-excel-wait-long-time (2026-11-06): a long-lived tab kept the
  // mount-time model badge forever (it showed Deepseek long after the lane
  // was pinned to kimi-k3) — re-sync after every completed turn.
  const prevBusyRef = React.useRef(false)
  React.useEffect(() => {
    if (prevBusyRef.current && !busy) refreshConfiguredModel()
    prevBusyRef.current = busy
  }, [busy, refreshConfiguredModel])

  async function applyCloudModel(id: ModelId) {
    setApplyError(null)
    setApplyingModel(id)
    try {
      const res = await fetch("/api/models/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: id }),
      })
      const body = (await res.json().catch(() => ({}))) as { error?: string }
      if (!res.ok) throw new Error(body.error ?? `apply failed (${res.status})`)
      setConfiguredCloud(id)
      setSelectionByConv((prev) => ({ ...prev, [activeId]: id }))
      if (active?.difyId) modelStorage.setSelection(active.difyId, id)
    } catch (err) {
      // FR-004: honest error, the visible selection reverts to what still runs
      setApplyError(err instanceof Error ? err.message : String(err))
    } finally {
      setApplyingModel(null)
    }
  }

  function selectModel(id: ModelId) {
    setApplyError(null)
    if (id === "local") {
      setSelectionByConv((prev) => ({ ...prev, [activeId]: id }))
      if (active?.difyId) modelStorage.setSelection(active.difyId, id)
      return
    }
    if (id === configuredCloud || applyingModel) return // same-model no-op / single cycle
    void applyCloudModel(id)
  }

  function resetSelectionToCloud(convId: string, difyId: string | undefined) {
    // spec 026: the fallback/reset target is the globally configured cloud
    // model, not a hardcoded default (research D6).
    setSelectionByConv((prev) => ({ ...prev, [convId]: configuredCloud }))
    if (difyId) modelStorage.setSelection(difyId, configuredCloud)
  }

  React.useEffect(() => {
    return () => {
      if (streamRef.current) clearInterval(streamRef.current)
      abortRef.current?.abort()
    }
  }, [])

  // Mobile drawer (spec 019): start closed below md, Escape closes
  React.useEffect(() => {
    const t = setTimeout(() => {
      if (window.innerWidth < 768) setSidebarOpen(false)
    }, 0)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && window.innerWidth < 768) setSidebarOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => {
      clearTimeout(t)
      window.removeEventListener("keydown", onKey)
    }
  }, [])

  React.useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [active?.messages])

  function updateConversation(
    id: string,
    updater: (c: Conversation) => Conversation
  ) {
    setConversations((prev) => prev.map((c) => (c.id === id ? updater(c) : c)))
  }

  function updateMessage(id: number, patch: Partial<Message>, convId: string = activeId) {
    updateConversation(convId, (c) => ({
      ...c,
      messages: c.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    }))
  }

  // spec 027: every generation end (complete, error, stop) funnels through
  // here — clears the single-flight refs and frees the composer (FR-002/005)
  function finishGeneration() {
    genRef.current = null
    stopRequestedRef.current = false
    setBusy(false)
  }

  function demoStream(assistantId: number, convId: string = activeId) {
    const reply = cannedReplies[replyRef.current % cannedReplies.length]
    replyRef.current += 1
    if (genRef.current) genRef.current.isDemo = true
    const words = reply.text.split(" ")
    let i = 0
    streamRef.current = setInterval(() => {
      i += 3
      const done = i >= words.length
      updateMessage(
        assistantId,
        {
          text: words.slice(0, Math.min(i, words.length)).join(" "),
          streaming: !done,
          sources: done ? reply.sources : undefined,
          code: done ? reply.code : undefined,
          codeName: done ? reply.codeName : undefined,
        },
        convId
      )
      if (done && streamRef.current) {
        clearInterval(streamRef.current)
        streamRef.current = null
        finishGeneration()
      }
    }, 60)
  }

  // FR-007 vs error-matrix row 8: a local selection only counts as failed when
  // Local is actually down — a Dify-side error (e.g. a stale published app)
  // surfaces as a normal send error and keeps the selection visible.
  async function localModelFailed(): Promise<boolean> {
    const localOk = await fetchAvailability()
    setLocalAvailable(localOk)
    return !localOk
  }

  async function send(text = input) {
    const value = text.trim()
    if (!value || busy || applyingModel) return
    if (active?.difyId) {
      history.touch(active.difyId)
      syncHistory()
    }
    setInput("")
    setBusy(true)
    const userMessage: Message = {
      id: (idRef.current += 1),
      role: "user",
      text: value,
    }
    const assistantId = (idRef.current += 1)
    const difyId = active?.difyId
    const sendConvId = activeId
    const requested = activeModel
    const assistantIndex = (active?.messages.length ?? 0) + 1

    // spec 025 FR-002/FR-004: the selection applies to this send; a local
    // selection that cannot serve falls back to cloud with a persistent
    // badge note and resets the stored selection (never auto-resume).
    let serving = requested
    let badgeValue: BadgeValue = requested
    if (requested === "local") {
      const localOk = await fetchAvailability()
      setLocalAvailable(localOk)
      if (!localOk) {
        serving = configuredCloud
        badgeValue = `${configuredCloud}|fallback`
        resetSelectionToCloud(sendConvId, difyId)
      }
    }

    updateConversation(activeId, (c) => ({
      ...c,
      title: c.title === "New chat" ? value.slice(0, 42) : c.title,
      messages: [
        ...c.messages,
        userMessage,
        { id: assistantId, role: "assistant", text: "", streaming: true },
      ],
    }))

    // spec 027: single-flight generation record + stop latch reset (FR-009)
    stopRequestedRef.current = false
    genRef.current = {
      convId: sendConvId,
      assistantId,
      title: value.slice(0, 60),
      model: serving,
      taskId: null,
      isDemo: false,
    }

    const controller = new AbortController()
    abortRef.current = controller
    let answer = ""
    let reasoning = ""
    let flushTimer: ReturnType<typeof setTimeout> | null = null
    let timedOut = false
    let watchdog: ReturnType<typeof setTimeout> | null = null

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: value, conversationId: difyId ?? null, aiModel: serving }),
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        const detail = (await res.json().catch(() => null)) as
          | { error?: string }
          | null
        throw new Error(detail?.error ?? `Request failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ""

      const armWatchdog = () => {
        if (watchdog) clearTimeout(watchdog)
        watchdog = setTimeout(() => {
          timedOut = true
          controller.abort()
        }, WATCHDOG_MS)
      }
      armWatchdog()

      const flush = () => {
        flushTimer = null
        const parsed = parseAnswer(answer)
        updateMessage(
          assistantId,
          {
            text: parsed.text,
            reasoning: reasoning || parsed.reasoning,
          },
          sendConvId
        )
      }
      const scheduleFlush = () => {
        if (flushTimer) return
        flushTimer = setTimeout(flush, FLUSH_MS)
      }

      for (;;) {
        const { done, value: chunk } = await reader.read()
        if (done) break
        buffer += decoder.decode(chunk, { stream: true })
        let idx = buffer.indexOf("\n")
        while (idx >= 0) {
          const line = buffer.slice(0, idx).trim()
          buffer = buffer.slice(idx + 1)
          idx = buffer.indexOf("\n")
          if (!line) continue
          let msg: {
            type: string
            text?: string
            sources?: string[]
            message?: string
            conversationId?: string
            taskId?: string
          }
          try {
            msg = JSON.parse(line)
          } catch {
            continue
          }
          armWatchdog()
          switch (msg.type) {
            case "chunk":
              answer += msg.text ?? ""
              scheduleFlush()
              break
            case "reasoning":
              reasoning += msg.text ?? ""
              scheduleFlush()
              break
            case "replace":
              answer = msg.text ?? ""
              scheduleFlush()
              break
            case "sources":
              updateMessage(assistantId, { sources: msg.sources }, sendConvId)
              break
            case "task":
              // spec 027: generation ids from the stream — taskId for the
              // backend halt; the conversation registers NOW (not at done)
              // so it is reachable and stoppable in the sidebar mid-stream,
              // and a stopped first turn still resumes from history (FR-010)
              if (genRef.current) genRef.current.taskId = msg.taskId ?? null
              if (msg.conversationId) {
                updateConversation(sendConvId, (c) =>
                  c.difyId ? c : { ...c, difyId: msg.conversationId }
                )
                history.upsert({
                  difyId: msg.conversationId,
                  title: value.slice(0, 60),
                  lastActivityAt: Date.now(),
                })
                modelStorage.setSelection(msg.conversationId, serving)
                syncHistory()
              }
              break
            case "error":
              throw new Error(msg.message ?? "Stream error")
            case "done":
              if (msg.conversationId) {
                updateConversation(sendConvId, (c) => ({
                  ...c,
                  difyId: msg.conversationId,
                }))
                history.upsert({
                  difyId: msg.conversationId,
                  title: value.slice(0, 60),
                  lastActivityAt: Date.now(),
                })
                syncHistory()
                modelStorage.setSelection(msg.conversationId, serving)
                modelStorage.setBadge(msg.conversationId, assistantIndex, badgeValue)
              }
              break
          }
        }
      }
      if (flushTimer) clearTimeout(flushTimer)
      if (watchdog) clearTimeout(watchdog)
      // spec 025 FR-007: a mid-generation local failure can close the Dify
      // stream without an error event (empty reply) — treat that as failure
      // when Local is actually down (reset per FR-004); a Dify-side empty
      // reply keeps the selection (error-matrix row 8). Never a silent bubble.
      if (!answer.trim() && requested === "local") {
        const localFailed = await localModelFailed()
        if (localFailed) resetSelectionToCloud(sendConvId, difyId)
        updateMessage(
          assistantId,
          {
            text: localFailed
              ? "The local model could not answer this message and the selection was reset to DeepSeek. Please send again."
              : "Something went wrong sending this message. The selection stays on Qwen3 8B — please send again.",
            streaming: false,
            noBadge: true,
          },
          sendConvId
        )
        finishGeneration()
        return
      }
      flush()
      updateMessage(assistantId, { streaming: false }, sendConvId)
      finishGeneration()
    } catch (error) {
      if (flushTimer) clearTimeout(flushTimer)
      if (watchdog) clearTimeout(watchdog)
      // spec 027: once a user stop is latched, the turn is already finalized —
      // any stream remnant (abort, error event racing the abort) is ignored
      if (stopRequestedRef.current) return
      if (
        error instanceof DOMException &&
        error.name === "AbortError" &&
        !timedOut
      ) {
        // spec 027 (research R3, supersedes the old silent return that left
        // streaming + busy stuck): other aborts (delete, unmount) end quietly
        finishGeneration()
        return
      }
      // spec 025 FR-007 / error-matrix row 8: reset only when Local is
      // actually down; a Dify-side error keeps the selection and never falls
      // back to canned demo replies for a local-requested send.
      const localFailed = await localModelFailed()
      if (localFailed) resetSelectionToCloud(sendConvId, difyId)
      if (!answer) {
        if (timedOut || localFailed) {
          updateMessage(
            assistantId,
            {
              text: localFailed
                ? "The local model could not answer this message and the selection was reset to DeepSeek. Please send again."
                : "Connection lost — the assistant may still be working on it. Please send your question again.",
              streaming: false,
              noBadge: localFailed,
            },
            sendConvId
          )
          finishGeneration()
        } else if (requested === "local") {
          updateMessage(
            assistantId,
            {
              text: "Something went wrong sending this message. The selection stays on Qwen3 8B — please send again.",
              streaming: false,
              noBadge: true,
            },
            sendConvId
          )
          finishGeneration()
        } else {
          demoStream(assistantId, sendConvId)
        }
      } else {
        const parsed = parseAnswer(answer)
        updateMessage(
          assistantId,
          {
            text: `${parsed.text}\n\nSomething went wrong while streaming the response.`,
            reasoning: reasoning || parsed.reasoning,
            streaming: false,
          },
          sendConvId
        )
        finishGeneration()
      }
    }
  }

  // spec 027 (FR-001/003/004/006/009): user Stop — halt the backend, abort the
  // stream, finalize the turn honestly, free the composer in under 1 second
  function stopGeneration() {
    const gen = genRef.current
    if (!gen || stopRequestedRef.current) return // nothing running / double-click (FR-009)
    stopRequestedRef.current = true

    const conv = conversations.find((c) => c.id === gen.convId)
    const message = conv?.messages.find((m) => m.id === gen.assistantId)
    const hasAnswerText = Boolean(message?.text?.trim())
    const action = decideStopAction({
      busy: true,
      stopRequested: false,
      hasAnswerText,
      hasReasoning: Boolean(message?.reasoning?.trim()),
      generationPhase: hasAnswerText ? "streaming" : "thinking",
    })

    // FR-006: halt the backend generation too — fire-and-forget; the client
    // stops cleanly regardless, failures warn here and surface in the battery
    if (
      shouldCallBackendStop({
        taskId: gen.taskId ?? undefined,
        demoMode: gen.isDemo,
      })
    ) {
      void fetch("/api/chat/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId: gen.taskId }),
      }).catch((err) =>
        console.warn("[stop] backend halt failed (client stopped anyway):", err)
      )
    }

    if (gen.isDemo) {
      if (streamRef.current) {
        clearInterval(streamRef.current)
        streamRef.current = null
      }
    } else {
      abortRef.current?.abort()
    }

    if (action === "remove-empty-turn") {
      updateConversation(gen.convId, (c) => ({
        ...c,
        messages: c.messages.filter((m) => m.id !== gen.assistantId),
      }))
    } else if (action === "finalize-stopped") {
      const patch = finalizeOnStop({
        text: message?.text ?? "",
        reasoning: message?.reasoning,
        streaming: true,
      })
      if (!("remove" in patch)) updateMessage(gen.assistantId, patch, gen.convId)
    }
    finishGeneration()
  }

  async function openConversation(record: ConversationRecord) {
    const existing = conversations.find((c) => c.difyId === record.difyId)
    if (existing) {
      setActiveId(existing.id)
      // spec 025 FR-003/SC-003: resume re-hydrates the stored selection
      setSelectionByConv((prev) => ({
        ...prev,
        [existing.id]: modelStorage.getSelection(record.difyId),
      }))
      return
    }
    try {
      const res = await fetch(
        `/api/conversations/${encodeURIComponent(record.difyId)}/messages?limit=100`
      )
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as
          | { error?: string }
          | null
        throw new HistoryError("messages_unavailable", detail?.error)
      }
      const { messages } = (await res.json()) as {
        messages: Message[]
        hasMore: boolean
      }
      const id = `h-${record.difyId}`
      setConversations((prev) => [
        { id, title: record.title, messages, difyId: record.difyId },
        ...prev,
      ])
      setActiveId(id)
      // spec 025 FR-003/SC-003: the choice sticks across reload/resume
      setSelectionByConv((prev) => ({
        ...prev,
        [id]: modelStorage.getSelection(record.difyId),
      }))
    } catch (err) {
      const e = err as HistoryError
      const id = `h-${record.difyId}`
      setConversations((prev) => [
        {
          id,
          title: record.title,
          messages: [
            {
              id: (idRef.current += 1),
              role: "assistant",
              text: `Could not load this conversation${e.message ? `: ${e.message}` : "."} Please try again.`,
              streaming: false,
            },
          ],
          difyId: record.difyId,
        },
        ...prev,
      ])
      setActiveId(id)
    }
  }

  async function deleteConversation(record: ConversationRecord) {
    const res = await fetch(
      `/api/conversations/${encodeURIComponent(record.difyId)}`,
      { method: "DELETE" }
    )
    if (!res.ok) {
      const detail = (await res.json().catch(() => null)) as
        | { error?: string }
        | null
      throw new HistoryError("delete_failed", detail?.error)
    }
    if (active?.difyId === record.difyId) {
      abortRef.current?.abort()
      if (streamRef.current) {
        clearInterval(streamRef.current)
        streamRef.current = null
      }
      genRef.current = null
      stopRequestedRef.current = false
      setBusy(false)
      newChat()
    }
    history.remove(record.difyId)
    // spec 025 (FR-005 interplay): purging the model keys on delete —
    // no orphaned selection or badge data for a removed conversation.
    modelStorage.purgeConversation(record.difyId)
    setSelectionByConv((prev) => {
      const next = { ...prev }
      delete next[`h-${record.difyId}`]
      return next
    })
    syncHistory()
  }

  function newChat() {
    const id = `c-${(idRef.current += 1)}`
    setConversations((prev) => [
      { id, title: "New chat", messages: [] },
      ...prev,
    ])
    setActiveId(id)
  }

  function copyMessage(message: Message) {
    navigator.clipboard?.writeText(message.text)
    setCopiedId(message.id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  return (
    <div className="flex h-svh overflow-hidden">
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <aside className="fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r bg-background md:static md:z-auto md:bg-muted/30">
          <div className="flex h-13 shrink-0 items-center gap-2 border-b px-3">
            <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Bot className="size-4" />
            </span>
            <span className="font-heading text-sm font-semibold">AGI Chat</span>
          </div>
          <div className="space-y-3 p-3">
            <Button className="w-full" onClick={() => {
              newChat()
              if (window.innerWidth < 768) setSidebarOpen(false)
            }}>
              <Plus />
              New chat
            </Button>
            <div className="relative">
              <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setSearchQuery("")
                }}
                placeholder="Search chats"
                className="h-8 rounded-lg pr-7 pl-9"
              />
              {searchQuery && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setSearchQuery("")}
                  className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  ×
                </button>
              )}
            </div>
          </div>
          <nav className="flex-1 space-y-1 overflow-y-auto px-1 pb-4" aria-label="Chat history">
            {history.status === "ready" && debouncedQuery.trim() && filteredRecords.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                No conversations match “{debouncedQuery}”
              </div>
            ) : (
            <ChatHistory
              records={filteredRecords}
              status={history.status}
              hasMore={history.hasMore}
              loadingMore={loadingMore}
              activeDifyId={active?.difyId}
              onOpen={(record) => {
                if (window.innerWidth < 768) setSidebarOpen(false)
                void openConversation(record)
              }}
              onRetry={() => { void history.load().then(syncHistory) }}
              onLoadMore={() => { setLoadingMore(true); void history.loadMore().then(syncHistory).finally(() => setLoadingMore(false)) }}
              onDelete={deleteConversation}
            />
            )}
          </nav>
          <div className="flex items-center gap-2 border-t p-3">
            <Avatar size="sm">
              <AvatarFallback>AD</AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">Alex Doe</div>
              <div className="truncate text-xs text-muted-foreground">
                alex@acme.com
              </div>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Account options"
                  />
                }
              >
                <MoreHorizontal />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="top" className="w-44">
                <DropdownMenuItem>
                  <User />
                  Profile
                </DropdownMenuItem>
                <DropdownMenuItem>
                  <Settings />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive">
                  <LogOut />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          </aside>
        </>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-13 shrink-0 items-center gap-2 border-b px-3">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Toggle sidebar"
            onClick={() => setSidebarOpen((o) => !o)}
          >
            <PanelLeft />
          </Button>
          <span className="truncate text-sm font-medium">{active.title}</span>
          <div className="ml-auto flex items-center gap-1.5">
            <Badge variant="secondary" className="gap-1.5 font-medium">
              <Bot className="size-3.5" />
              AGI Chat
            </Badge>
            <PdfExportButton messages={active.messages} />
            <Button variant="outline" size="sm">
              <Share2 />
              Share
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Toggle theme"
                  />
                }
              >
                <Sun className="dark:hidden" />
                <Moon className="hidden dark:block" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-36">
                <DropdownMenuItem onClick={() => setTheme("light")}>
                  <Sun />
                  Light
                  {theme === "light" && <Check className="ml-auto" />}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("dark")}>
                  <Moon />
                  Dark
                  {theme === "dark" && <Check className="ml-auto" />}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => setTheme("system")}>
                  <Monitor />
                  System
                  {theme === "system" && <Check className="ml-auto" />}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {active.messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
              <Bot className="size-6" />
            </div>
            <h1 className="font-heading mt-6 text-2xl font-semibold">
              How can I help you today?
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Ask anything, or start from a suggestion.
            </p>
            <div className="mt-8 grid w-full max-w-4xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURE_CARDS.map((c) => (
                <div
                  key={c.title}
                  className="rounded-2xl border bg-card p-4 text-left transition-colors hover:bg-muted"
                >
                  <button className="block w-full text-left" onClick={() => send(c.label)}>
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <span className="text-base" aria-hidden="true">
                        {c.icon}
                      </span>
                      {c.title}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{c.description}</p>
                  </button>
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs text-primary underline-offset-2 hover:underline"
                  >
                    {c.label} →
                  </a>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl xl:max-w-[min(90%,1400px)] space-y-6 p-4 py-6 sm:p-6">
              {active.messages.map((m, index) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[85%] lg:max-w-2xl rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={m.id} className="flex gap-3">
                    <Avatar size="sm" className="mt-0.5">
                      <AvatarFallback>
                        <Bot className="size-4 text-muted-foreground" />
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1 space-y-3">
                      {m.reasoning && (
                        <div className="rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1.5 font-medium text-foreground">
                            <BrainCircuit className="size-3.5" />
                            Reasoning
                            <ChevronDown className="size-3" />
                          </span>
                          <p className="mt-1.5 leading-relaxed">{m.reasoning}</p>
                        </div>
                      )}
                      <AssistantText message={m} />
                      {m.code && (
                        <div className="overflow-hidden rounded-lg border">
                          <div className="flex items-center justify-between border-b bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
                            <span className="font-mono">{m.codeName}</span>
                            <span className="flex items-center gap-1">
                              <Copy className="size-3" />
                              Copy
                            </span>
                          </div>
                          <pre className="overflow-x-auto bg-muted/20 p-3 font-mono text-xs leading-relaxed">
                            <code>{m.code}</code>
                          </pre>
                        </div>
                      )}
                      {m.sources && (
                        <div className="flex flex-wrap gap-1.5">
                          {m.sources.map((source) => (
                            <Badge
                              key={source}
                              variant="outline"
                              className="gap-1 text-xs font-normal"
                            >
                              <Link2 className="size-3" />
                              {source}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {m.stopped && (
                        <p
                          className="text-xs italic text-muted-foreground"
                          data-stopped-caption
                        >
                          Stopped
                        </p>
                      )}
                      {!m.streaming &&
                        badgeNote(
                          active.difyId
                            ? modelStorage.getBadge(active.difyId, index)
                            : "cloud"
                        ) && (
                          <p
                            className="text-xs italic text-muted-foreground"
                            data-fallback-note
                          >
                            {badgeNote(
                              active.difyId
                                ? modelStorage.getBadge(active.difyId, index)
                                : "cloud"
                            )}
                          </p>
                        )}
                      {!m.streaming && (
                        <div className="flex items-center gap-1 text-muted-foreground">
                          {!m.noBadge && (
                            <span
                              className="text-xs"
                              data-model-badge={badgeModel(
                                active.difyId
                                  ? modelStorage.getBadge(active.difyId, index)
                                  : "cloud"
                              )}
                            >
                              {optionById(
                                badgeModel(
                                  active.difyId
                                    ? modelStorage.getBadge(active.difyId, index)
                                    : "cloud"
                                )
                              ).displayName}
                            </span>
                          )}
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label="Copy response"
                            onClick={() => copyMessage(m)}
                          >
                            {copiedId === m.id ? <Check /> : <Copy />}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label="Good response"
                          >
                            <ThumbsUp />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label="Bad response"
                          >
                            <ThumbsDown />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            aria-label="Regenerate response"
                          >
                            <RefreshCw />
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        )}

        <div className="shrink-0 border-t">
          <div className="mx-auto w-full max-w-3xl xl:max-w-[min(90%,1400px)] p-3 sm:p-4">
            <div className="rounded-3xl border bg-muted/30 p-2 shadow-sm">
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder="Message AGI Chat…"
                rows={1}
                className="min-h-8 border-transparent bg-transparent px-3 py-2 focus-visible:border-transparent focus-visible:ring-0"
              />
              <div className="flex items-center gap-1 px-1 pt-1">
                <Button variant="ghost" size="icon-sm" aria-label="Attach files">
                  <Paperclip />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="Voice input">
                  <Mic />
                </Button>
                <div className="ml-auto flex items-center gap-2">
                  {applyingModel ? (
                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <LoaderCircle
                        className="size-3.5 animate-spin text-[#82D2F6]"
                        aria-hidden="true"
                      />
                      Applying {optionById(applyingModel).displayName}…
                    </span>
                  ) : (
                    <ModelDropdown
                      value={activeModel}
                      localAvailable={localAvailable}
                      onValueChange={selectModel}
                      onOpen={refreshAvailability}
                    />
                  )}
                  {applyError && !applyingModel && (
                    <span
                      className="max-w-56 truncate text-xs text-destructive"
                      title={applyError}
                    >
                      {applyError}
                    </span>
                  )}
                  {stopMode === "stop" ? (
                    <Button
                      size="icon-sm"
                      className="rounded-full"
                      aria-label="Stop generation"
                      data-composer-mode="stop"
                      onClick={() => stopGeneration()}
                    >
                      <Square className="size-3.5 fill-current" />
                    </Button>
                  ) : (
                    <Button
                      size="icon-sm"
                      className="rounded-full"
                      aria-label="Send message"
                      data-composer-mode="send"
                      disabled={!input.trim() || busy || !!applyingModel}
                      onClick={() => send()}
                    >
                      <ArrowUp />
                    </Button>
                  )}
                </div>
              </div>
            </div>
            <p className="pt-2 text-center text-xs text-muted-foreground">
              AGI Chat can make mistakes. Check important info.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
