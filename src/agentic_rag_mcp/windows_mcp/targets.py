"""Spec 041 — the reviewed settings-target inventory (tier 1).

The bounded list the launcher accepts: classic Control Panel applets
(launchable via `control <id>`) and modern Settings pages
(launchable via `start ms-settings:<page>`). Additions to this list are a
deliberate future edit (spec Assumptions); anything not here asks back."""

from __future__ import annotations

TARGETS: dict[str, dict] = {
    # -- classic applets (control <identifier>) --------------------------
    "system properties": {"kind": "cpl", "identifier": "sysdm.cpl"},
    "mouse settings": {"kind": "cpl", "identifier": "main.cpl"},
    "keyboard properties": {"kind": "cpl", "identifier": "keyboard.cpl"},
    "game controllers": {"kind": "cpl", "identifier": "joy.cpl"},
    "add hardware wizard": {"kind": "cpl", "identifier": "hdwwiz.cpl"},
    "device manager": {"kind": "cpl", "identifier": "devmgmt.msc"},
    "network connections": {"kind": "cpl", "identifier": "ncpa.cpl"},
    "internet options": {"kind": "cpl", "identifier": "inetcpl.cpl"},
    "windows firewall advanced": {"kind": "cpl", "identifier": "wf.cpl"},
    "programs and features": {"kind": "cpl", "identifier": "appwiz.cpl"},
    "uninstall programs": {"kind": "cpl", "identifier": "appwiz.cpl"},
    # open-the-installed-programs-applet (2026-11-16): the owner's natural
    # phrasing — map it to the same applet instead of asking back
    "installed programs": {"kind": "cpl", "identifier": "appwiz.cpl"},
    "installed programs applet": {"kind": "cpl", "identifier": "appwiz.cpl"},
    "installed apps applet": {"kind": "cpl", "identifier": "appwiz.cpl"},
    "sound settings": {"kind": "cpl", "identifier": "mmsys.cpl"},
    "speech recognition": {"kind": "cpl", "identifier": "speech.cpl"},
    "power options": {"kind": "cpl", "identifier": "powercfg.cpl"},
    "user accounts": {"kind": "cpl", "identifier": "nusrmgr.cpl"},
    "credential manager": {"kind": "cpl", "identifier": "credwiz.cpl"},
    "security center": {"kind": "cpl", "identifier": "wscui.cpl"},
    "display settings": {"kind": "cpl", "identifier": "desk.cpl"},
    "themes": {"kind": "cpl", "identifier": "themes.cpl"},
    "date and time": {"kind": "cpl", "identifier": "timedate.cpl"},
    "ease of access": {"kind": "cpl", "identifier": "access.cpl"},
    "utility manager": {"kind": "cpl", "identifier": "utilman.cpl"},
    "region and language": {"kind": "cpl", "identifier": "intl.cpl"},
    "odbc data sources": {"kind": "cpl", "identifier": "odbccp32.cpl"},
    "phone and modem": {"kind": "cpl", "identifier": "telephon.cpl"},
    "scanners and cameras": {"kind": "cpl", "identifier": "sticpl.cpl"},
    # spec 042 (2026-11-16): the Reliability Monitor — perfmon.msc's /rel
    # view; synonyms all resolve to the one entry (the installed-programs
    # alias precedent). Launches via the mmc-hosted form (research R1):
    # plain perfmon /rel silently exits from the service's context.
    "reliability monitor": {"kind": "perfmon_rel", "identifier": "perfmon.msc"},
    "reliability history": {"kind": "perfmon_rel", "identifier": "perfmon.msc"},
    "stability monitor": {"kind": "perfmon_rel", "identifier": "perfmon.msc"},
    "bluetooth devices": {"kind": "cpl", "identifier": "bthprops.cpl"},
    # -- modern Settings pages (start ms-settings:<page>) ----------------
    "settings home": {"kind": "settings_page", "identifier": ""},
    "bluetooth settings": {"kind": "settings_page",
                            "identifier": "bluetooth"},
    "windows update": {"kind": "settings_page", "identifier": "windowsupdate"},
    "apps and features": {"kind": "settings_page", "identifier": "appsfeatures"},
    "accounts settings": {"kind": "settings_page", "identifier": "accounts"},
    "privacy settings": {"kind": "settings_page", "identifier": "privacy"},
    "about this pc": {"kind": "settings_page", "identifier": "about"},
    "personalization": {"kind": "settings_page",
                         "identifier": "personalization"},
    "devices settings": {"kind": "settings_page", "identifier": "devices"},
}

_ASK_BACK = ("blocked: I did not recognize that settings surface. "
             "Known surfaces: " + ", ".join(sorted(TARGETS))
             + " — name one and I will open it")


def resolve_target(text: str) -> dict:
    """Resolve a natural-language target to one inventory entry.

    Returns {status: ok, target} on an exact/unambiguous match, or
    {status: ask-back, reason} naming the full list — never a guess."""
    low = (text or "").strip().lower()
    if not low:
        return {"status": "ask-back", "reason": _ASK_BACK}
    hits = [k for k in TARGETS if k == low or low in k or k in low]
    # exact match first; a single fuzzy hit is unambiguous; more ask back
    if low in TARGETS:
        hits = [low]
    if len(hits) == 1:
        return {"status": "ok", "target": TARGETS[hits[0]],
                "display_name": hits[0]}
    return {"status": "ask-back",
            "reason": _ASK_BACK if not hits
            else ("blocked: ambiguous — which of these: " + ", ".join(sorted(hits))
                  + "?")}
