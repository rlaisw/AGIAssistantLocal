// spec 027 (contracts §2): same-origin stop proxy — the Dify service API key
// stays server-side; the browser only ever sees this route.
export const runtime = "nodejs"

const DIFY_USER = "ai-chat-ui-user" // must match the chat proxy's end-user id

const SIDECAR_MCP =
  (process.env.SIDECAR_MCP_URL ?? "http://localhost:28080") + "/mcp"

// 3-step stateless streamable-HTTP MCP dance (same envelope the battery's
// probes use): initialize -> initialized -> tools/call hermes_cancel_turn.
async function cancelSidecarTurn(conversationId: string): Promise<void> {
  const post = (payload: unknown) =>
    fetch(SIDECAR_MCP, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5_000),
    })
  await post({
    jsonrpc: "2.0", id: 1, method: "initialize",
    params: { protocolVersion: "2024-11-05", capabilities: {},
             clientInfo: { name: "chat-stop", version: "0" } },
  })
  await post({ jsonrpc: "2.0", method: "notifications/initialized" })
  await post({
    jsonrpc: "2.0", id: 2, method: "tools/call",
    params: { name: "hermes_cancel_turn",
              arguments: { conversation_id: conversationId } },
  })
}

export async function POST(req: Request) {
  const { taskId, conversationId } = (await req.json().catch(() => ({}))) as {
    taskId?: unknown
    conversationId?: unknown
  }
  if (typeof taskId !== "string" || !taskId.trim() || taskId.length > 128) {
    return Response.json({ error: "taskId is required" }, { status: 400 })
  }

  // repeated-show-AI-is-controlling-… (2026-11-09): Dify's stop halts the
  // workflow but the gateway agent keeps running (measured: minutes of
  // continued desktop control after Stop). If the caller passes the Dify
  // conversation id, also cancel the sidecar's in-flight gateway call for
  // that conversation (hermes_cancel_turn) — the gateway's SSE branch then
  // interrupts the agent. Fire-and-forget with a short timeout: the chat's
  // own stop must never block on the sidecar.
  if (typeof conversationId === "string" && conversationId.trim()) {
    void cancelSidecarTurn(conversationId).catch(() => {})
  }

  const apiKey = process.env.DIFY_API_KEY
  if (!apiKey) {
    return Response.json({ error: "DIFY_API_KEY is not configured" }, { status: 503 })
  }
  const apiBase = (
    process.env.DIFY_API_BASE_URL ?? "http://localhost/v1"
  ).replace(/\/+$/, "")

  try {
    const upstream = await fetch(
      `${apiBase}/chat-messages/${encodeURIComponent(taskId)}/stop`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ user: DIFY_USER }),
        signal: AbortSignal.timeout(10_000),
      }
    )
    // completion race: the backend reports nothing to stop — client treats
    // this as success, never an error (contracts §2)
    if (upstream.status === 404) {
      return Response.json({ result: "no-task" })
    }
    if (!upstream.ok) {
      const detail = (await upstream.text().catch(() => "")).slice(0, 200)
      return Response.json({ error: `stop failed: ${detail}` }, { status: 502 })
    }
    return Response.json({ result: "ok" })
  } catch (error) {
    const message = error instanceof Error ? error.message : "stop request failed"
    return Response.json({ error: `stop failed: ${message.slice(0, 200)}` }, { status: 502 })
  }
}
