"""error-browser-lane-unavailable (2026-11-14): the dynamic-lane health
probe must speak HTTP — the WSL bridge accepts TCP connections
unconditionally, so the old bare-TCP probe reported reachable:true while
the engine was dead."""

import socket
import threading

from agentic_rag_mcp.browser_lanes import dynamic_health


def _serve(handler):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    threading.Thread(target=_accept_loop, args=(srv, handler),
                     daemon=True).start()
    return srv.getsockname()[1]


def _accept_loop(srv, handler):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=handler, args=(conn,),
                         daemon=True).start()


class TestBridgeMaskMode:

    def test_accept_then_close_reports_unavailable(self):
        # the exact failure mode: the bridge accepts, its far-side dial
        # fails, the socket closes before any HTTP response
        port = _serve(lambda c: c.close())
        result = dynamic_health.probe_dynamic(host="127.0.0.1", port=port)
        assert result["status"] == "error"
        assert result["dynamic"]["reachable"] is False
        assert "browser-lane-unavailable" in result["reason"]
        assert "playwright-mcp-server" in result["reason"]  # recovery hint

    def test_accept_never_speak_reports_unavailable(self):
        # bridge up, far side hanging: no response, no close — the probe
        # must fall to its timeout and stay honest, never hang
        port = _serve(lambda c: None)
        result = dynamic_health.probe_dynamic(host="127.0.0.1", port=port,
                                               timeout_s=0.3)
        assert result["status"] == "error"
        assert result["dynamic"]["reachable"] is False

    def test_http_responder_reports_ok(self):
        # a live SSE server answers with headers (then holds the stream
        # open — the probe must not wait for the stream to end)
        def respond(conn):
            try:
                conn.recv(1024)
                conn.sendall(b"HTTP/1.1 200 OK\r\n"
                             b"Content-Type: text/event-stream\r\n\r\n"
                             b"event: endpoint\ndata: /message\n\n")
                conn.recv(1024)  # hold open until the probe closes
            except OSError:
                pass
        port = _serve(respond)
        result = dynamic_health.probe_dynamic(host="127.0.0.1", port=port)
        assert result == {"status": "ok",
                          "dynamic": {"reachable": True,
                                      "url": f"http://127.0.0.1:{port}/sse"}}
