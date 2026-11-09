export const runtime = "nodejs"

type StreamEvent = {
  // spec 027: additive "task" event — consumers must tolerate unknown types
  type: "chunk" | "reasoning" | "replace" | "sources" | "done" | "error" | "ping" | "task"
  text?: string
  sources?: string[]
  message?: string
  conversationId?: string
  taskId?: string
}

export async function POST(req: Request) {
  const { query, conversationId, aiModel } = await req.json()
  if (!query || typeof query !== "string") {
    return Response.json({ error: "query is required" }, { status: 400 })
  }

  const apiKey = process.env.DIFY_API_KEY
  if (!apiKey) {
    return Response.json({ error: "DIFY_API_KEY is not configured" }, { status: 503 })
  }

  const apiBase = (
    process.env.DIFY_API_BASE_URL ?? "http://localhost/v1"
  ).replace(/\/+$/, "")

  const upstream = await fetch(`${apiBase}/chat-messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      // spec 026: cloud selection is global (the published app is patched);
      // sends carry only the local switch. Absent input = cloud (else branch),
      // battery and legacy callers stay byte-identical when aiModel is omitted.
      inputs:
        aiModel === "local"
          ? { ai_model: "local" }
          : aiModel
            ? { ai_model: "cloud" }
            : {},
      query,
      response_mode: "streaming",
      conversation_id: conversationId ?? "",
      user: "ai-chat-ui-user",
    }),
  })

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "")
    return Response.json(
      { error: `Dify error (${upstream.status}): ${detail.slice(0, 200)}` },
      { status: 502 }
    )
  }

  const encoder = new TextEncoder()
  const decoder = new TextDecoder()
  const reader = upstream.body.getReader()
  // spec 027: once the client cancels (user stop), the loop's pending read
  // rejects — don't report that as a stream error to a stopping client
  let cancelled = false

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: StreamEvent) =>
        controller.enqueue(encoder.encode(JSON.stringify(event) + "\n"))
      let buffer = ""
      let difyConversationId: string | undefined
      let taskIdSent = false
      // true once we've closed our stream ourselves (message_end path) — the
      // finally must not close the controller twice
      let finalized = false

      try {
        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          let boundary = buffer.indexOf("\n\n")
          while (boundary >= 0) {
            const block = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            boundary = buffer.indexOf("\n\n")
            for (const line of block.split("\n")) {
              if (!line.startsWith("data:")) {
                if (
                  line.startsWith("event:") &&
                  line.slice(6).trim() === "ping"
                ) {
                  send({ type: "ping" })
                }
                continue
              }
              let event: Record<string, unknown>
              try {
                event = JSON.parse(line.slice(5).trim())
              } catch {
                continue
              }
              if (
                typeof event.conversation_id === "string" &&
                !difyConversationId
              ) {
                difyConversationId = event.conversation_id
              }
              // spec 027 (contracts §1): forward the generation ids once — the
              // task id lets the client halt the backend via /api/chat/stop,
              // and the early conversation_id lets a stopped FIRST turn still
              // register its conversation in history (done never arrives)
              if (typeof event.task_id === "string" && !taskIdSent && event.task_id) {
                taskIdSent = true
                send({
                  type: "task",
                  taskId: event.task_id,
                  conversationId: difyConversationId,
                })
              }
              switch (event.event) {
                case "message":
                case "agent_message":
                  if (event.answer) send({ type: "chunk", text: String(event.answer) })
                  break
                case "reasoning_chunk": {
                  const data = event.data as { reasoning?: string } | undefined
                  if (data?.reasoning) send({ type: "reasoning", text: data.reasoning })
                  break
                }
                case "message_replace":
                  if (event.answer) send({ type: "replace", text: String(event.answer) })
                  break
                case "message_end": {
                  const metadata = event.metadata as
                    | { retriever_resources?: { document_name?: string }[] }
                    | undefined
                  const names = (metadata?.retriever_resources ?? [])
                    .map((r) => r.document_name)
                    .filter((n): n is string => Boolean(n))
                  const sources = [...new Set(names)]
                  if (sources.length) send({ type: "sources", sources })
                  // wait-long-time-show-output-result (2026-11-09): message_end
                  // is Dify's terminal answer-complete event — finalize the UI
                  // now instead of waiting for the upstream body to close, which
                  // can lag indefinitely (plugin-daemon holds, tool-time cuts).
                  finalized = true
                  send({ type: "done", conversationId: difyConversationId })
                  controller.close()
                  reader.cancel().catch(() => {})
                  return
                }
                case "error":
                  send({
                    type: "error",
                    message: typeof event.message === "string" ? event.message : "Dify stream error",
                  })
                  break
              }
            }
          }
        }
        send({ type: "done", conversationId: difyConversationId })
      } catch (error) {
        if (!cancelled)
          send({
            type: "error",
            message: error instanceof Error ? error.message : "stream error",
          })
      } finally {
        if (!finalized) controller.close()
      }
    },
    cancel() {
      cancelled = true
      reader.cancel().catch(() => {})
    },
  })

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache",
    },
  })
}
