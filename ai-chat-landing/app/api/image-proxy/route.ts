import type { NextRequest } from "next/server"

const MAX_BYTES = 10 * 1024 * 1024
const FETCH_TIMEOUT_MS = 10_000

// shortcut: single-user self-hosted deployment — any http(s) host is allowed
// (loopback included: sidecar images live on localhost:28080) except the
// cloud-metadata address; add an allowlist if the UI is ever exposed.
const BLOCKED_HOSTS = new Set(["169.254.169.254"])

/**
 * PDF-export image proxy: html2canvas-pro rasterizes with useCORS, and most
 * answer-image hosts (learn.microsoft.com, …) send no ACAO header, so their
 * pixels drop out of the PDF. Fetching same-origin through here avoids the
 * browser CORS check entirely (the server has no such restriction).
 */
export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("url")
  if (!raw) return new Response("missing url", { status: 400 })
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return new Response("invalid url", { status: 400 })
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return new Response("unsupported scheme", { status: 400 })
  }
  if (url.username || url.password || BLOCKED_HOSTS.has(url.hostname)) {
    return new Response("forbidden host", { status: 403 })
  }

  let upstream: Response
  try {
    upstream = await fetch(url, {
      redirect: "follow",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { "user-agent": "agi-chat-pdf-export/1.0" },
    })
  } catch {
    return new Response("fetch failed", { status: 502 })
  }
  const type = upstream.headers.get("content-type") ?? ""
  if (!upstream.ok || !type.startsWith("image/")) {
    return new Response("not an image", { status: 415 })
  }
  const declared = Number(upstream.headers.get("content-length") ?? 0)
  if (declared > MAX_BYTES) return new Response("too large", { status: 413 })
  const buf = await upstream.arrayBuffer()
  if (buf.byteLength > MAX_BYTES) return new Response("too large", { status: 413 })
  const cacheControl = upstream.headers.get("cache-control")

  return new Response(buf, {
    headers: {
      "content-type": type,
      "cache-control":
        cacheControl && /\bno-store\b/i.test(cacheControl)
          ? cacheControl
          : "public, max-age=3600",
    },
  })
}
