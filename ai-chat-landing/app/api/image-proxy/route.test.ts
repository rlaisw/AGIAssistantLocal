import { NextRequest } from "next/server"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GET } from "./route"

afterEach(() => {
  vi.unstubAllGlobals()
})

async function proxyImage(cacheControl: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response("image bytes", {
        status: 200,
        headers: {
          "content-type": "image/png",
          "cache-control": cacheControl,
        },
      })
    )
  )
  const upstream = "https://images.example.test/screenshot.png"
  const request = new NextRequest(
    `http://localhost/api/image-proxy?url=${encodeURIComponent(upstream)}`
  )
  return GET(request)
}

describe("GET /api/image-proxy cache policy (spec 047)", () => {
  it("preserves the upstream no-store policy exactly", async () => {
    const response = await proxyImage("no-store, max-age=0")

    expect(response.status).toBe(200)
    expect(response.headers.get("cache-control")).toBe("no-store, max-age=0")
  })

  it("retains one-hour public caching for an ordinary cacheable image", async () => {
    const response = await proxyImage("public, max-age=86400")

    expect(response.status).toBe(200)
    expect(response.headers.get("cache-control")).toBe("public, max-age=3600")
  })
})
