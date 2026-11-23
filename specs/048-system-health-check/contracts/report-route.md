# Contract: Temporary Health Report Route

## `GET /mcp-action/reports/{token}`

Returns one temporary HTML system-health report.

### Path

- `token` is exactly 43 characters matching `[A-Za-z0-9_-]{43}` from 256 random bits.
- URL contains no conversation ID, computer name, user/email/IP, timestamp, local path, or report metadata.
- This is an unauthenticated capability URL for the current single-user local-trust deployment. Anyone with it can read the report until expiry.

### `200 OK`

- Body is the exact stored self-contained HTML bytes; no wrapper/conversion.
- `Content-Type: text/html; charset=utf-8`.
- Required headers:

```text
Cache-Control: no-store, max-age=0
Pragma: no-cache
Expires: 0
Content-Disposition: inline; filename="system-health-report.html"
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
X-Frame-Options: DENY
Cross-Origin-Resource-Policy: same-origin
X-Robots-Tag: noindex, nofollow, noarchive
Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:; script-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox
```

Do **not** send `Access-Control-Allow-Origin`, `Last-Modified`, `ETag`, `Accept-Ranges`, or other cache validators.

### `404 Not Found`

Malformed, unknown, expired, and wrong tokens return indistinguishable 404s with `Cache-Control: no-store`. Expired access deletes the owned file when present. No token/path/report content is echoed.

### Other methods

`405 Method Not Allowed` with `Allow: GET` and `Cache-Control: no-store`.

## Content rules

- Exactly one HTML document, UTF-8 (optional BOM), maximum 5 MiB.
- Must contain a complete `<html>…</html>` document; reject NULs and truncated content.
- Reject `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<base>`, `<link>`, `on*=` attributes, `javascript:`, `data:text/html`, and meta refresh.
- Inline `<style>`, inline `style=` attributes, inline SVG, and data-URI images are allowed. No external scripts/styles/fonts/resources.
- Every host-provided value is HTML-escaped by the generator.
- The report may display owner-approved login, email, IP, hardware/serial, password-expiry, event, and crash/reliability fields. These fields are not redacted from the report.
- Passwords, MFA codes, tokens, client secrets, and credentials are never included.

## Storage and lifetime

- Dedicated container temporary directory `/tmp/agentic-rag-mcp-reports`, mode `0700`; files `0600`.
- Absolute 900-second TTL from wall-clock creation; GET does not renew.
- 30-second janitor plus startup and shutdown cleanup; expired/future-skewed files removed; no symlink following.
- No metadata database. Sidecar restart may remove the report early; recreate by rerunning the health action.
- Host source JSON/HTML run artifacts are transient and are cleaned after the report is copied. Only tool-owned `health-<runId>` artifacts may be removed.

## Privacy and logging

- The report may contain PII by explicit owner approval; do not log or audit its content.
- Report tokens are redacted in logs alongside screenshot tokens.
- The URL remains in Dify chat history even after expiry; the server cannot erase already-delivered chat text or rendered browser pages.
- Do not proxy HTML through the image proxy. The existing Markdown renderer opens it as a normal new-tab link.
