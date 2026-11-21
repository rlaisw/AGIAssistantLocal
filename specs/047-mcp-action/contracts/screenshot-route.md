# Contract: Temporary MCP-Action Screenshot Route

## `GET /mcp-action/screenshots/{token}`

Returns one temporary verification screenshot captured after a confirmed action.

### Path

- `token` is exactly 43 characters matching `[A-Za-z0-9_-]{43}` and is generated with 256 random bits.
- The URL contains no conversation ID, printer/document name, timestamp, local path, or other metadata.
- This is an unauthenticated capability URL for the current single-user local deployment. Anyone possessing it can retrieve the image until expiry.

### `200 OK`

- Body is the original decoded PNG or JPEG bytes; no base64 wrapper.
- `Content-Type`: validated `image/png` or `image/jpeg`.
- Required headers:

```text
Cache-Control: no-store, max-age=0
Pragma: no-cache
Expires: 0
Access-Control-Allow-Origin: *
Cross-Origin-Resource-Policy: cross-origin
X-Content-Type-Options: nosniff
Content-Disposition: inline
```

Repeated immediate GETs are allowed because chat rerenders and PDF export may fetch the same URL. GET does not renew expiry or trigger deletion after first read.

### `404 Not Found`

Returned identically for malformed, unknown, wrong, and expired tokens, with `Cache-Control: no-store`. Expired access deletes the owned file if it still exists. No tombstone or metadata is exposed.

### Other methods

Return `405 Method Not Allowed` with `Allow: GET` and `Cache-Control: no-store`.

## Storage and expiry

- Exactly one valid PNG/JPEG image, magic-byte checked, decoded size ≤10 MiB.
- Dedicated container-local temporary directory, mode `0700`; files mode `0600`.
- Absolute TTL is 900 seconds from capture; janitor interval is 30 seconds.
- Startup and shutdown sweep leftovers; container recreation leaves no mounted screenshot copy.
- No sidecar metadata/expiry database is required.
- The chat image proxy preserves upstream `no-store`; its existing one-hour public caching remains only for ordinary remote images.

## Privacy and audit

- Tool results contain only the temporary URL and expiry, never Base64 or a local path.
- Persistent application/access logs redact the token.
- Audit records capture/delivery outcome only, never token, URL, path, image bytes, or desktop text.
- If display is not verified, capture is skipped rather than returning an unrelated window.
- Already-rendered browser pixels and a PDF explicitly exported by the user cannot be recalled; the server copy and cached proxy response still follow this temporary-retention contract.
