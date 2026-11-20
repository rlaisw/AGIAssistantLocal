// Infographic notification-link styling (spec 046): target-based detection and
// a single renderer-owned pin. The label itself is never rewritten.
const INFOGRAPHIC_URL = "/infographics/"
const PIN = "📌"

export function isInfographicLink(href: string | undefined): boolean {
  return typeof href === "string" && href.includes(INFOGRAPHIC_URL)
}

// E3: if the model emits its own leading pin, remove it once so the renderer's
// pin is the only one. A pin anywhere else in the label is content, not a prefix.
export function infographicDisplayLabel(text: string): string {
  return text.replace(new RegExp(`^\\s*${PIN}\\s*`), "")
}
