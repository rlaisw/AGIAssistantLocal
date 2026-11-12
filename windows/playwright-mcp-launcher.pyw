"""playwright-mcp-launcher (2026-11-12): start the Playwright MCP server
with NO console window AND keep its Chromium windows visible/maximized.

Why the watchdog (not just launch flags):
  * Hidden-launch wrappers (conhost --headless, powershell -WindowStyle
    Hidden) set the hidden show-state in STARTUPINFO, which Windows hands
    to the FIRST GUI window a child creates -> Chromium born minimized.
  * The persistent Chromium profile ALSO remembers window state, so a
    once-minimized profile restores minimized on every launch.
A pythonw host has no console and a Win32 watchdog thread restores +
maximizes any 'Chrome for Testing' window within ~2 s; the user's own
Chrome titles (- Google Chrome) are never touched.

Started at logon via a Startup-folder shortcut; replaces the scheduled
task for this service (its hidden launch caused the minimize class).
"""
import ctypes
import subprocess
import time
from ctypes import wintypes

CMD = [
    r"C:\Users\RLWC145\AppData\Roaming\npm\playwright-mcp.cmd",
    "--port", "3002", "--host", "127.0.0.1",
    "--executable-path",
    r"C:\Users\RLWC145\AppData\Local\ms-playwright\chromium-1254\chrome-win64\chrome.exe",
    "--blocked-origins",
    "doubleclick.net,googlesyndication.com,google-analytics.com,"
    "googletagmanager.com,facebook.net,adservice.google.com,"
    "analytics.google.com",
    "--viewport-size", "1920,1080",
]

CREATE_NO_WINDOW = 0x08000000
SW_RESTORE = 9
SW_MAXIMIZE = 3
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
ACTIVE_WINDOW_S = 20  # keep it front this long after each navigation

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                 wintypes.LPARAM)


def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _bring_to_front(hwnd) -> None:
    """Foreground activation. The ALT tap clears Windows' foreground lock
    (needed here because the RDP client commonly holds focus), then
    SetForegroundWindow lands reliably; AttachThreadInput is the fallback."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    if user32.GetForegroundWindow() == hwnd:
        return
    user32.keybd_event(VK_MENU, 0, 0, 0)          # ALT down
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    if user32.SetForegroundWindow(hwnd):
        return
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    t_thread = user32.GetWindowThreadProcessId(hwnd, None)
    attached = False
    if fg_thread and t_thread and fg_thread != t_thread:
        attached = bool(user32.AttachThreadInput(fg_thread, t_thread, True))
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if attached:
        user32.AttachThreadInput(fg_thread, t_thread, False)


def _watch_forever() -> None:
    """Restore+maximize our Chromium windows (title-tagged, ours only), and
    bring them to the FRONT when they first appear or on each navigation
    (title change) — never every cycle, so it does not fight the user."""
    hits: list[int] = []
    seen: dict[int, str] = {}
    changed: dict[int, float] = {}

    def _cb(hwnd, _lparam):
        if "Chrome for Testing" in _title(hwnd):
            hits.append(hwnd)
        return True

    callback = _ENUM_PROC(_cb)
    while True:
        hits.clear()
        user32.EnumWindows(callback, 0)
        for hwnd in hits:
            t = _title(hwnd)
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            if seen.get(hwnd) != t:  # new window or a new page navigation
                changed[hwnd] = time.time()
            # front during active navigation (title changed recently), so
            # the user watches the browsing; never fight them afterwards
            if time.time() - changed.get(hwnd, 0.0) < ACTIVE_WINDOW_S:
                _bring_to_front(hwnd)
            seen[hwnd] = t
        for gone in [h for h in seen if h not in hits]:
            seen.pop(gone, None)
            changed.pop(gone, None)
        time.sleep(2)


if __name__ == "__main__":
    subprocess.Popen(CMD, creationflags=CREATE_NO_WINDOW, close_fds=True,
                     shell=False)
    _watch_forever()
