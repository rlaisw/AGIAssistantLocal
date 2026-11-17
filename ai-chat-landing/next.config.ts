import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // Dev-server cross-origin allowlist: the host's LAN IP so the app can be
  // used from remote machines (e.g. http://10.161.92.34:3000). Next dev
  // blocks cross-origin HMR/chunk requests otherwise (page loads, nothing
  // interactive works).
  allowedDevOrigins: ["10.161.92.34", "http://10.161.92.34:3000"],
  // spec 043: pdf-parse v2 (pdfjs) loads a worker module at runtime — Next
  // must not bundle it into the server chunk graph (the dev-bundled worker
  // path fails: "Cannot find module …/pdf.worker.mjs")
  serverExternalPackages: ["pdf-parse", "pdfjs-dist"],
}

export default nextConfig
