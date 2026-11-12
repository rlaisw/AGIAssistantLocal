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

user32 = ctypes.WinDLL("user32", use_last_error=True)

_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                 wintypes.LPARAM)


def _title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _watch_forever() -> None:
    """Restore+maximize our Chromium windows (title-tagged, ours only)."""
    hits: list[int] = []

    def _cb(hwnd, _lparam):
        if "Chrome for Testing" in _title(hwnd):
            hits.append(hwnd)
        return True

    callback = _ENUM_PROC(_cb)
    while True:
        hits.clear()
        user32.EnumWindows(callback, 0)
        for hwnd in hits:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
        time.sleep(2)


if __name__ == "__main__":
    subprocess.Popen(CMD, creationflags=CREATE_NO_WINDOW, close_fds=True,
                     shell=False)
    _watch_forever()
