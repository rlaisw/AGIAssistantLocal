"""playwright-mcp-launcher (2026-11-12): start the Playwright MCP server
with NO console window while letting its browser windows show NORMALLY.

The minimize/ghost-window class: hidden-launch wrappers (conhost
--headless, powershell -WindowStyle Hidden) set the hidden show-state
in STARTUPINFO, which Windows propagates to the FIRST GUI window the
child process creates -> Chromium is born minimized. A pythonw host
(no console at all) + CREATE_NO_WINDOW for node avoids setting any
show-state: the browser window comes up normal.

Started at logon via a Startup-folder shortcut; replaces the scheduled
task for this service (the task's hidden launch was the culprit).
"""
import subprocess
import sys

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

if __name__ == "__main__":
    subprocess.Popen(CMD, creationflags=CREATE_NO_WINDOW, close_fds=True,
                     shell=False)
