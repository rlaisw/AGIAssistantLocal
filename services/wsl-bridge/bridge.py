"""chrome-not-desktop-automation (2026-11-11): the WSL docker0 port bridge.

The sidecar container cannot reach Windows services bound to 127.0.0.1
(mirrored networking exposes them on WSL loopback ONLY — not on docker0).
The Hermes agent runs on the host, so its direct connections are fine; the
SIDECAR's probes/clients (browser lane health, task-gateway) are not.

This bridge listens on docker0 (172.17.0.1 — container-reachable, never
LAN-routed) and forwards to WSL loopback, which mirrored networking maps
to the Windows services. Windows bindings stay on 127.0.0.1: zero new
exposure on the Windows side; the only new listener is on the container
network.

Systemd user unit (no sudo): ~/.config/systemd/user/wsl-port-bridge.service
Default ports: 3002 (Playwright MCP probe) + 8080 (task-gateway client).
"""

from __future__ import annotations

import asyncio
import sys

DOCKER0 = "172.17.0.1"
# NOTE: WSL mirrored networking makes Windows-held ports UNBINDABLE in WSL
# on any interface — so the bridge listens on SHIFTED ports (13002/18080,
# held by nobody) and forwards to the mirrored-loopback originals.
FORWARDS = [
    (DOCKER0, 13002, "127.0.0.1", 3002),  # playwright-mcp (spec 037 probe)
    (DOCKER0, 18080, "127.0.0.1", 8080),  # task-gateway (spec 038 client)
    # desktop v2 (2026-11-12): WindowsMCP — single-hop desktop primitives
    (DOCKER0, 18800, "127.0.0.1", 8800),  # windows-mcp (launch/focus/type)
]


async def _pump(reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except Exception:  # noqa: BLE001 — best-effort close on teardown
            pass


async def _handle(down_reader: asyncio.StreamReader,
                  down_writer: asyncio.StreamWriter,
                  up_host: str, up_port: int) -> None:
    try:
        up_reader, up_writer = await asyncio.open_connection(up_host, up_port)
    except (ConnectionError, OSError):
        # upstream down: close the container side so the caller sees EOF
        down_writer.close()
        return
    await asyncio.gather(_pump(down_reader, up_writer),
                          _pump(up_reader, down_writer))


async def serve(bind_host: str, bind_port: int, up_host: str, up_port: int):
    async def handler(r, w):
        await _handle(r, w, up_host, up_port)

    server = await asyncio.start_server(handler, bind_host, bind_port)
    async with server:
        await server.serve_forever()


async def main() -> None:
    await asyncio.gather(*(serve(b, bp, u, up)
                           for b, bp, u, up in FORWARDS))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)