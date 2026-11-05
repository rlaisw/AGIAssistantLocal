#!/usr/bin/env bash
# Post-reboot restart script for the AGI Assistant stack (specs 028-031).
# Auto-starts: Docker containers (sidecar, Dify) — no action needed.
# This script starts the three manual components and runs a health check.

set -euo pipefail

echo "=== AGI Assistant post-reboot restart ==="

echo "[1/5] Starting OfficeMCP (Windows-side MCP server)..."
/mnt/c/Users/RLWC145/.local/bin/officemcp.exe sse --port 8888 --host 127.0.0.1 --folder "C:/OfficeMCP" &
OFFICEMCP_PID=$!
sleep 5
if curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8888/sse 2>/dev/null | grep -q "200"; then
    echo "  OfficeMCP: up on :8888"
else
    echo "  ERROR: OfficeMCP not responding — check the process"
    exit 1
fi

echo "[2/5] Restarting Hermes gateway..."
hermes gateway restart -y --detach
sleep 10
if curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://172.17.0.1:8642/v1/models \
    -H "Authorization: Bearer $(grep api_key /home/administrator/.config/agentic-rag-mcp/config.toml | head -1 | cut -d'"' -f2)" 2>/dev/null | grep -q "200"; then
    echo "  Gateway: up on :8642"
else
    echo "  Gateway not responding yet (may need a moment or manual restart)"
fi

echo "[3/5] Re-registering MCP connection..."
hermes mcp remove OfficeMCP 2>/dev/null || true
yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse 2>&1 | grep -q "Saved" && echo "  MCP registered" || echo "  MCP registration may have failed"
hermes gateway restart -y --detach 2>&1 | tail -1
sleep 10

echo "[4/5] Starting Chat UI..."
if [ -d "$(dirname "$0")/ai-chat-landing" ]; then
    cd "$(dirname "$0")/ai-chat-landing" && pnpm dev &
    sleep 8
    if curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/ 2>/dev/null | grep -q "200"; then
        echo "  Chat UI: up on :3000"
    else
        echo "  Chat UI not responding (still booting?)"
    fi
else
    echo "  ai-chat-landing/ not found — skipping Chat UI"
fi

echo "[5/5] Health check..."
echo "---"
printf "%-25s" "Docker containers:"; docker ps --format '{{.Names}}' 2>/dev/null | wc -l | awk '{print $1 " running"}'
printf "%-25s" "Sidecar :28080:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:28080/ 2>/dev/null | awk '{print ($1 >= 200 && $1 < 500) ? "ok" : "FAIL"}'
printf "%-25s" "OfficeMCP :8888:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:8888/sse 2>/dev/null | awk '{print $1 == 200 ? "ok" : "FAIL"}'
printf "%-25s" "Chat UI :3000:"; curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://localhost:3000/ 2>/dev/null | awk '{print $1 == 200 ? "ok" : "FAIL"}'
printf "%-25s" "MCP tools:"; hermes mcp test OfficeMCP 2>&1 | grep -c "RunPython\|Launch" | awk '{print $1 > 0 ? "ok" : "FAIL"}'
echo "---"

echo ""
echo "=== Done. Stack is ready. ==="
echo "Chat UI: http://localhost:3000"
echo ""
echo "If an Office task fails with 'session stale', run:"
echo "  hermes mcp remove OfficeMCP && yes | hermes mcp add OfficeMCP --url http://127.0.0.1:8888/sse && hermes gateway restart -y --detach"
