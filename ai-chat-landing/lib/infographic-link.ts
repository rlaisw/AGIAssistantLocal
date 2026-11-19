// Infographic notify-line styling (spec 046): the markdown link whose target is
// an infographic page renders as a call-out — 📌 prefix + blue label, matching
// the follow-up line's treatment. Detection is URL-based (FR-004) so label
// rewording never un-styles the line; the renderer owns the emoji (research R4).

const INFOGRAPHIC_URL = "/infographics/"
const PIN = "📌"

export function isInfographicLink(href: string | undefined): boolean {
  return typeof href === "string" && href.includes(INFOGRAPHIC_URL)
}

// E5 guard: if the model ever emits its own leading pin, strip it once so the
// renderer's pin is the only one.
export function infographicDisplayLabel(text: string): string {
  return text.replace(new RegExp(`^\\s*${PIN}\\s*`), "")
}
