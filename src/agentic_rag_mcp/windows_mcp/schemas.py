"""Spec 041 — the live-captured schemas of the Windows-MCP tools the
applet tiers drive (probed from the running service, 2026-11-15;
research.md R1/R3). Merged into the lane's TOOL_SCHEMAS by client.py so
args are validated before dispatch."""

from __future__ import annotations

GUI_TOOL_SCHEMAS: dict[str, dict] = {
    "PowerShell": {"args": {"command", "timeout"},
                   "required": {"command"}},
    "App": {"args": {"mode", "name", "window_loc", "window_size",
                     "executable", "args", "cwd"},
            "required": set()},
    "Snapshot": {"args": {"use_vision", "use_dom", "use_annotation",
                          "use_ui_tree", "width_reference_line",
                          "height_reference_line", "display", "region"},
                 "required": set()},
    "Screenshot": {"args": {"use_annotation", "width_reference_line",
                            "height_reference_line", "display", "region"},
                   "required": set()},
    "Click": {"args": {"loc", "label", "button", "clicks"},
              "required": set()},
    "Type": {"args": {"text", "loc", "label", "clear", "caret_position",
                      "press_enter"},
             "required": {"text"}},
    "Wait": {"args": {"duration"}, "required": {"duration"}},
    "WaitFor": {"args": {"condition", "text", "window_name", "timeout",
                          "interval", "use_dom"},
                "required": {"condition"}},
}
