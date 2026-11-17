import { afterEach, describe, expect, it, vi } from "vitest"
import { POST } from "./route"

// wait-long-time-show-output-result (2026-11-09): message_end must finalize
// the UI stream (done + close) without waiting for the upstream body to close —
// Dify can hold the body open long after the answer is complete.

function sse(event: Record<string, unknown>): Uint8Array {
  return new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`)
}

afterEach(() => {
  vi.unstubAllGlobals()
  delete process.env.DIFY_API_KEY
})

describe("chat route finalization", () => {
  it("emits done at message_end even when the upstream body never closes", async () => {
    process.env.DIFY_API_KEY = "k"
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(sse({ event: "agent_message", answer: "OK", conversation_id: "c1", task_id: "t1" }))
          controller.enqueue(sse({ event: "message_end", conversation_id: "c1", metadata: { retriever_resources: [{ document_name: "doc.md" }] } }))
          // deliberately never closes — simulates a held upstream stream
        },
      }),
      { status: 200 },
    )))

    const res = await POST(new Request("http://x/api/chat", {
      method: "POST",
      body: JSON.stringify({ query: "hi" }),
    }))
    const body = await res.text()
    const types = body.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l).type)
    expect(types).toContain("chunk")
    expect(types).toContain("sources")
    expect(types).toContain("task")
    expect(types[types.length - 1]).toBe("done")
  })

  it("still relays done on upstream close without message_end (cut streams)", async () => {
    process.env.DIFY_API_KEY = "k"
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      new ReadableStream({
        start(controller) {
          controller.enqueue(sse({ event: "message", answer: "OK", conversation_id: "c2", task_id: "t2" }))
          controller.close()
        },
      }),
      { status: 200 },
    )))

    const res = await POST(new Request("http://x/api/chat", {
      method: "POST",
      body: JSON.stringify({ query: "hi" }),
    }))
    const body = await res.text()
    const types = body.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l).type)
    expect(types[types.length - 1]).toBe("done")
  })
})

// spec 043: attachments ride the query as a preamble; without one the
// upstream body must stay byte-identical to the pre-attachment shape.
describe("attachment preamble injection", () => {
  async function capturedBody(payload: Record<string, unknown>) {
    process.env.DIFY_API_KEY = "k"
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new ReadableStream({ start(c) { c.close() } }), { status: 200 })
    )
    vi.stubGlobal("fetch", fetchMock)
    const req = new Request("http://local/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    })
    await POST(req)
    const init = fetchMock.mock.calls[0][1] as RequestInit
    return JSON.parse(String(init.body))
  }

  it("no attachment: query unchanged and body shape identical", async () => {
    const body = await capturedBody({ query: "hello", conversationId: null })
    expect(body.query).toBe("hello")
    expect(Object.keys(body)).toEqual(["inputs", "query", "response_mode", "conversation_id", "user"])
    expect(body).toEqual({
      inputs: {},
      query: "hello",
      response_mode: "streaming",
      conversation_id: "",
      user: "ai-chat-ui-user",
    })
  })

  it("with attachment: the preamble carries the file and the question", async () => {
    const body = await capturedBody({
      query: "what does it say?",
      conversationId: "c1",
      attachments: [{ name: "r.pdf", type: ".pdf", chars: 9, text: "TOKEN_42", truncated: false }],
    })
    expect(body.query).toContain("[Attached file: r.pdf (.pdf, 9 characters extracted)]")
    expect(body.query).toContain("TOKEN_42")
    expect(body.query).toContain("User question: what does it say?")
    expect(body.conversation_id).toBe("c1")
  })
})
