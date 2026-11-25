"""Spec 050: the deterministic 10-image cap inside the honesty_check JS node.

Executes the checked-in node code with node (same pattern as
test_mcp_action_dsl.py) — red before the cap exists, green after.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import yaml

_DSL = pathlib.Path(__file__).resolve().parents[2] / "dify" / "AGIAssistant" / "AGI_Assistant.yml"


def _honesty_code() -> str:
    dsl = yaml.safe_load(_DSL.read_text(encoding="utf-8"))
    code = None

    def walk(node) -> None:
        nonlocal code
        if isinstance(node, dict):
            if isinstance(node.get("code"), str) and "Honesty check" in node["code"]:
                code = node["code"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(dsl)
    assert code, "honesty_check code node not found"
    assert "IMAGE_CAP = 10" in code, "spec 050: deterministic cap missing from node"
    return code


def _cap_code() -> str:
    code = _honesty_code()
    i = code.index("var IMAGE_CAP")
    j = code.index("\n  }\n", i) + len("\n  }\n")
    return code[i:j]


def _run_cap(text: str) -> str:
    runner = (
        "const fs=require('fs');"
        "const p=JSON.parse(fs.readFileSync(0,'utf8'));"
        "eval(p.code);process.stdout.write(JSON.stringify({r: capInlineImages(p.text)}));"
    )
    run = subprocess.run(["node", "-e", runner],
                         input=json.dumps({"code": _cap_code(), "text": text}),
                         text=True, capture_output=True, timeout=10, check=False)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)["r"]


def _run(code: str, text: str) -> str:
    inputs = {"answer": "", "items": [], "general_answer": text, "general_items": []}
    runner = (
        "const fs=require('fs');"
        "const p=JSON.parse(fs.readFileSync(0,'utf8'));"
        "eval(p.code);process.stdout.write(JSON.stringify(main(p.inputs)));"
    )
    run = subprocess.run(["node", "-e", runner],
                         input=json.dumps({"code": code, "inputs": inputs}),
                         text=True, capture_output=True, timeout=10, check=False)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)["result"]


def _images(n: int, prefix="https://img.example") -> str:
    return "\n".join(f"![Step {i}]({prefix}/{i}.png)" for i in range(1, n + 1))


def test_cap_keeps_first_ten_visible_images():
    out = _run(_honesty_code(), "Steps:\n" + _images(12))
    assert out.count("![") == 10
    assert "![Step 10]" in out and "![Step 11]" not in out and "![Step 12]" not in out


def test_think_block_images_not_counted_or_stripped():
    think = "<" + "think> Plan:\n" + _images(8, "https://img.example/plan") + "\n<" + "/think>"
    body = "Steps:\n" + _images(3)
    out = _run(_honesty_code(), think + body)
    assert think.strip() in out                       # reasoning preserved verbatim
    assert out.count("img.example/plan/") == 8         # reasoning kept verbatim
    assert "](https://img.example/3.png)" in out       # 3 visible fit under the cap


def test_screenshot_urls_exempt():
    shots = _images(12, "http://sidecar:8080/mcp-action/screenshots")
    out = _run_cap("Evidence:\n" + shots)
    assert out.count("/mcp-action/screenshots/") == 12


def test_unbalanced_think_tags_clamp_at_zero():
    out = _run(_honesty_code(), "</think>\n" + _images(12))
    assert out.count("![") == 10


def test_answer_without_images_unchanged():
    text = "The capital of France is Paris.\n\nSources: [example](https://example.com)"
    assert _run(_honesty_code(), text) == text


def test_cleanup_does_not_leave_triple_newlines():
    out = _run(_honesty_code(), _images(12))
    assert "\n\n\n" not in out
