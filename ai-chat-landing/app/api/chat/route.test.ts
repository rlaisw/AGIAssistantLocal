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
