# safe-shutdown.ps1 - safely shut down the WSL Ubuntu stack ONLY.
# Windows keeps running: no service tasks are ended, no Office apps are
# closed, no Windows shutdown is issued - the script does exactly one
# thing: a clean `wsl --shutdown`, so systemd stops Dify Postgres, the
# sidecar container, and the port bridge (avoiding dirty-kill recovery
# prompts). Everything comes back on the next WSL shell - the container's
# restart policy is "always".
#
# Usage (from Windows PowerShell; elevated NOT required):
#   powershell -ExecutionPolicy Bypass -File C:\temp\safe-shutdown.ps1
# One-liner equivalent:  wsl --shutdown
#
# One-time copy from the repo (run inside WSL):
#   cp /kilocode/AGIAssistantLocal/windows/safe-shutdown.ps1 /mnt/c/temp/
# (or run straight from the repo via its WSL UNC path:
#   \\wsl.localhost\Ubuntu-24.04\kilocode\AGIAssistantLocal\windows\safe-shutdown.ps1 )
#
# After the next WSL boot, the one thing worth verifying (inside WSL):
#   systemctl --user is-active wsl-port-bridge.service   # expect: active
# and if the WSL user session failed to start (the boot warning):
#   systemctl --user start wsl-port-bridge
#   sudo loginctl enable-linger administrator   # once: boot-proof, warning gone

$ErrorActionPreference = 'Continue'

Write-Host '==> Shutting down WSL (wsl --shutdown) - Windows keeps running'
& wsl --shutdown
Start-Sleep -Seconds 3
Write-Host '==> Done. Open a WSL shell to boot the stack back (sidecar + Dify + bridge return automatically).'
