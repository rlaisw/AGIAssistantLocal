#!/usr/bin/env bash
# Post-reboot restart script for the AGI Assistant stack (specs 028-031).
# Auto-starts: Docker containers (sidecar, Dify) — no action needed.
# This script starts the four manual components and runs a health check.

set -euo pipefail

echo "=== AGI Assistant post-reboot restart ==="

# shortcut: /sse is a never-ending stream — curl -w never fires; sniff bytes instead
sse_up() {
    # shellcheck disable=SC2016
    [ -n "$(curl -sN --max-time 2 "$1" 2>/dev/null | head -c 64)" ]
}

echo "[1/6] OfficeMCP (Windows-side MCP server)..."
if sse_up http://127.0.0.1:8888/sse; then
    echo "  OfficeMCP: already up on :8888"
else
    /mnt/c/Users/RLWC145/.local/bin/officemcp.exe sse --port 8888 --host 127.0.0.1 --folder "C:/OfficeMCP" > /tmp/agi-assistant-officemcp.log 2>&1 &
    sleep 5
    if sse_up http://127.0.0.1:8888/sse; then
        echo "  OfficeMCP: up on :8888"
    else
        echo "  ERROR: OfficeMCP not responding — check the process"
        exit 1
    fi
fi

# the gateway on :8642 authenticates with the [hermes] api_key (not [dify] —
# a bare `grep api_key | head -1` grabs the wrong section and 401s)
GATEWAY_KEY=$(sed -n '/^\[hermes\]/,/^\[/p' ~/.config/agentic-rag-mcp/config.toml | grep '^api_key' | cut -d'"' -f2)
gateway_up() {
    # shellcheck disable=SC2016
    [ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        -H "Authorization: Bearer $GATEWAY_KEY" http://172.17.0.1:8642/v1/models)" = "200" ]
}

echo "[2/6] Restarting Hermes gateway..."
hermes gateway restart -y --detach >/dev/null 2>&1
sleep 10
if gateway_up; then
    echo "  Gateway: up on :8642"
else
    echo "  Gateway not responding yet (may need a moment or manual restart)"
fi

echo "[3/6] Re-registering MCP connection..."
yes | hermes mcp remove OfficeMCP >/dev/null 2>&1 || true
yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse >/dev/null 2>&1 || true
sleep 1
hermes mcp list 2>/dev/null | grep -q "OfficeMCP" && echo "  MCP registered" || echo "  MCP registration may have failed"
hermes gateway restart -y --detach >/dev/null 2>&1
sleep 10

echo "[4/6] Starting WSL Ollama server (local-model lane)..."
# Windows Ollama app must NOT run: in mirrored networking it steals port 11434
# from the WSL server that Dify and the Chat UI probe actually use (its
# Startup shortcut is renamed Ollama.lnk.disabled — keep it that way).
systemctl --user start ollama 2>/dev/null || true
sleep 2
if curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "200"; then
    echo "  Ollama: up on :11434 ($(ollama list 2>/dev/null | tail -n +2 | wc -l | tr -d ' ') models)"
else
    echo "  ERROR: Ollama not responding — check: journalctl --user -u ollama"
    echo "  (if a Windows Ollama app is running, quit it — it steals port 11434)"
fi

echo "[5/6] Chat UI..."
if [ -d "$(dirname "$0")/ai-chat-landing" ]; then
    if [ "$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/ 2>/dev/null)" = "200" ]; then
        echo "  Chat UI: already up on :3000"
    else
        (cd "$(dirname "$0")/ai-chat-landing" && exec pnpm dev) > /tmp/agi-assistant-chatui.log 2>&1 &
        sleep 8
    fi
    if curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/ 2>/dev/null | grep -q "200"; then
        echo "  Chat UI: up on :3000"
    else
        echo "  Chat UI not responding (still booting?)"
    fi
else
    echo "  ai-chat-landing/ not found — skipping Chat UI"
fi

echo "[6/6] Health check..."
echo "---"
printf "%-25s" "Docker containers:"; docker ps --format '{{.Names}}' 2>/dev/null | wc -l | awk '{print $1 " running"}'
printf "%-25s" "Sidecar :28080:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:28080/ 2>/dev/null | awk '{print ($1 >= 200 && $1 < 500) ? "ok" : "FAIL"}'
printf "%-25s" "OfficeMCP :8888:"; sse_up http://127.0.0.1:8888/sse && echo "ok" || echo "FAIL"
printf "%-25s" "Dify :80:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1/ 2>/dev/null | awk '{print ($1 >= 200 && $1 < 500) ? "ok" : "FAIL"}'
printf "%-25s" "Chat UI :3000:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/ 2>/dev/null | awk '{print $1 == 200 ? "ok" : "FAIL"}'
printf "%-25s" "Ollama :11434:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null | awk '{print $1 == 200 ? "ok" : "FAIL"}'
printf "%-25s" "Gateway :8642:"; gateway_up && echo "ok" || echo "FAIL"
printf "%-25s" "MCP tools:"; hermes mcp test OfficeMCP 2>&1 | grep -c "RunPython\|Launch" | awk '{print ($1 > 0) ? "ok" : "FAIL"}'
echo "---"

echo ""
echo "=== Done. Stack is ready. ==="
echo "Chat UI: http://localhost:3000"
echo ""
echo "If an Office task fails with 'session stale', run:"
echo "  yes | hermes mcp remove OfficeMCP; yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse; hermes gateway restart -y --detach"
