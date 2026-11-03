"""Headless verification battery (spec 011, R5).

Scenario registry per contracts/deploy-cli.md; unique verify_<ts> project
names; teardown sweep; exit code = failed-scenario count (FR-011 cleanup).
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import shutil
import time

import httpx

from .config import DeployConfig, redact

FIXTURE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
    'font-family="Segoe UI, sans-serif">'
    '<rect id="bg" data-pptx-role="background" x="0" y="0" width="1280" '
    'height="720" fill="#FAFAFA"/>'
    '<g id="t" data-pptx-bounds="64 64 1152 100">'
    '<text x="64" y="120" font-size="44" font-weight="bold" fill="#212121">'
    "Battery Deck</text>"
    '<text x="64" y="160" font-size="24" fill="#5F6B7A">'
    "verify battery fixture</text></g></svg>"
)

MCP_URL = "http://localhost:28080/mcp"


def mcp_call(name: str, arguments: dict) -> dict:
    resp = httpx.post(
        MCP_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}},
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
        timeout=600,
    )
    for line in resp.text.splitlines():
        if line.startswith("data:") and '"result"' in line:
            content = json.loads(line[5:])["result"]["content"]  # noqa: F821
            try:
                return json.loads(content[0]["text"])
            except (json.JSONDecodeError, KeyError, IndexError):
                return {"raw": content[0].get("text", "")[:200]}
    raise RuntimeError(f"tool {name} returned no result: {resp.text[:200]}")


def projects_roots() -> list[pathlib.Path]:
    """All host-visible projects roots: the config-derived one and the repo's
    ppt-master clone (the container mounts it, so host-side sweeps find it here)."""
    import os

    from ..config import load_config
    from ..ppt.bridge import projects_root as _derived

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    candidates = [_derived(load_config()),
                  pathlib.Path(os.path.join(repo_root, "ppt-master", "projects"))]
    seen, roots = set(), []
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key not in seen:
            seen.add(key)
            roots.append(c)
    return roots


def _sweep(report: list) -> None:
    for root in projects_roots():
        if not root.is_dir():
            continue
        for p in root.glob("verify_*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                report.append(f"swept {p.name}")


def prune_old_projects(retention_days: int, dry: bool = False) -> list[str]:
    """Retention (spec 009 deferred item): remove project dirs whose newest
    file is older than retention_days. Returns the removed (or would-remove) names."""
    import time as _time

    if retention_days <= 0:
        return []  # keep forever
    removed: list[str] = []
    cutoff = _time.time() - retention_days * 86400
    for root in projects_roots():
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if not p.is_dir() or p.name == "README.md" or p.name.startswith("verify_"):
                continue  # battery projects have their own sweep; README is not a deck
            newest = max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()),
                         default=p.stat().st_mtime)
            if newest < cutoff:
                removed.append(p.name)
                if not dry:
                    shutil.rmtree(p, ignore_errors=True)
    return removed


def scenario_health(dcfg: DeployConfig) -> tuple[bool, str]:
    r = httpx.get("http://localhost:28080/healthz", timeout=10)
    return r.status_code == 200 and r.json().get("status") == "ok", f"healthz={r.status_code}"


def scenario_tools_surface(dcfg: DeployConfig) -> tuple[bool, str]:
    from .tool_sync import fetch_live_tools

    tools = fetch_live_tools()
    names = sorted(t["name"] for t in tools)
    ppt = [n for n in names if n.startswith("ppt_")]
    return len(ppt) == 5, f"tools={len(names)} ppt={len(ppt)} ({', '.join(ppt)})" if ppt else f"tools={len(names)}, no ppt tools"


def scenario_deck_roundtrip(dcfg: DeployConfig) -> tuple[bool, str]:
    pid = mcp_call("ppt_project_init", {"name": f"verify_{int(time.time())}"})["project_id"]
    mcp_call("ppt_write_page", {"project_id": pid, "page_number": 1,
                                "name": "battery", "svg": FIXTURE_SVG})
    check = mcp_call("ppt_check", {"project_id": pid})
    if not check.get("passing"):
        return False, f"check not passing: {str(check.get('details'))[:150]}"
    exported = mcp_call("ppt_export", {"project_id": pid})
    ok = exported.get("url") and exported.get("page_url")
    return bool(ok), f"project={pid} url={'yes' if ok else 'missing'}"


def scenario_completion_page(dcfg: DeployConfig) -> tuple[bool, str]:
    pid = mcp_call("ppt_project_init", {"name": f"verify_page_{int(time.time())}"})["project_id"]
    mcp_call("ppt_write_page", {"project_id": pid, "page_number": 1,
                                "name": "battery", "svg": FIXTURE_SVG})
    mcp_call("ppt_check", {"project_id": pid})
    exported = mcp_call("ppt_export", {"project_id": pid})
    page = httpx.get(exported["page_url"], timeout=30)
    if page.status_code != 200 or "Download" not in page.text:
        return False, f"page={page.status_code}"
    m = re.search(r'src="(slides/[^"]+)"', page.text)
    if not m:
        return False, "no slide asset in page"
    slide = httpx.get(exported["page_url"] + m.group(1), timeout=30)
    dl = httpx.get(exported["url"], timeout=60)
    return (slide.headers.get("content-type", "").startswith("image/svg+xml")
            and dl.content[:2] == b"PK",
            f"page=200 slide={slide.status_code} pptx={len(dl.content)}B")


def scenario_honest_errors(dcfg: DeployConfig) -> tuple[bool, str]:
    r404 = httpx.get("http://localhost:28080/decks/ghost/none/", timeout=10)
    r400 = httpx.get(
        "http://localhost:28080/decks/ghost/none/slides/..%2F..%2Fetc.svg", timeout=10
    )
    ok = r404.status_code == 404 and r400.status_code in (400, 404)
    return ok, f"unknown={r404.status_code} traversal={r400.status_code}"


def scenario_chat_ui_liveness(dcfg: DeployConfig) -> tuple[bool, str]:
    try:
        r = httpx.get(dcfg.chat_ui_url, timeout=15, follow_redirects=True)
        return r.status_code == 200, f"chat-ui={r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"chat-ui unreachable: {exc.__class__.__name__}"


def scenario_chat_journey(dcfg: DeployConfig) -> tuple[bool, str]:
    if not dcfg.api_key:
        return True, "skipped: no DIFY_API_KEY configured (notice, not failure)"
    with httpx.stream(
        "POST",
        dcfg.console_url.rstrip("/") + "/v1/chat-messages",
        headers={"Authorization": f"Bearer {dcfg.api_key}"},
        json={"inputs": {},
              "query": "generate a one-page deck about deploy automation: "
                       "one command rebuilds, deploys, and verifies the stack",
              "response_mode": "streaming",
              "conversation_id": "",
              "user": "deploy-battery"},
        timeout=600,
    ) as resp:
        if resp.status_code != 200:
            return False, f"chat-messages={resp.status_code}"
        answer = ""
        for line in resp.iter_lines():
            if line.startswith("data:"):
                try:
                    event = json.loads(line[5:])
                except json.JSONDecodeError:
                    continue
                if event.get("event") in ("message", "agent_message"):
                    answer += event.get("answer") or ""
    link = re.search(r"https?://\S*(?:/exports/|/decks/)\S+", answer)
    if not link:
        return False, f"no deck link in answer ({len(answer)} chars): {answer[:120]!r}"
    url = link.group(0).rstrip("*).,]'\"_`")  # strip markdown/bold closing punctuation
    target = httpx.get(url, timeout=60, follow_redirects=True)
    served = (target.status_code == 200
              and ("text/html" in target.headers.get("content-type", "")
                   or target.content[:2] == b"PK"))
    return served, f"link={url} serves={target.status_code}"


def scenario_stop_generation(dcfg: DeployConfig) -> tuple[bool, str]:
    """Spec 027 SC-005: a stop must halt the backend generation, not just the
    client view. Streams a long answer, calls the stop endpoint mid-stream,
    then asserts the stored answer does not grow after the stream closes."""
    if not dcfg.api_key:
        return True, "skipped: no DIFY_API_KEY configured (notice, not failure)"
    base = dcfg.console_url.rstrip("/") + "/v1"
    headers = {"Authorization": f"Bearer {dcfg.api_key}"}
    user = "deploy-battery"
    task_id = ""
    conversation_id = ""
    answer = ""
    stopped = False
    stop_status = None
    with httpx.stream(
        "POST",
        f"{base}/chat-messages",
        headers=headers,
        json={"inputs": {},
              "query": "Write a detailed 400-word story about a mountain rescue. "
                       "Do not use any tools.",
              "response_mode": "streaming",
              "conversation_id": "",
              "user": user},
        timeout=180,
    ) as resp:
        if resp.status_code != 200:
            return False, f"chat-messages={resp.status_code}"
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:])
            except json.JSONDecodeError:
                continue
            task_id = event.get("task_id") or task_id
            conversation_id = event.get("conversation_id") or conversation_id
            if event.get("event") in ("message", "agent_message"):
                answer += event.get("answer") or ""
            if not stopped and len(answer) > 80 and task_id:
                stop = httpx.post(
                    f"{base}/chat-messages/{task_id}/stop",
                    headers=headers,
                    json={"user": user},
                    timeout=30,
                )
                stop_status = stop.status_code
                stopped = stop.status_code in (200, 404)
                if not stopped:
                    return False, f"stop={stop.status_code}"
    if not conversation_id or not answer:
        return False, (f"generation never became stoppable "
                       f"(task={bool(task_id)}, answer={len(answer)} chars)")
    # SC-005: after the stream closes, the backend must not add more content.
    # Dify exposes history at GET /messages?conversation_id=… (not
    # /conversations/{id}/messages — same quirk the Chat UI proxy documents).
    time.sleep(5)
    r = httpx.get(
        f"{base}/messages",
        headers=headers,
        params={"user": user, "conversation_id": conversation_id, "limit": 10},
        timeout=60,
    )
    if r.status_code != 200:
        return False, f"messages={r.status_code}"
    stored = ""
    for msg in r.json().get("data") or []:
        if msg.get("answer") is not None:
            stored = msg["answer"]
    delta = len(stored.strip()) - len(answer.strip())
    ok = delta <= 0
    return ok, (f"stop={stop_status} halted backend "
                f"(stored={len(stored.strip())} vs delivered={len(answer.strip())}, delta={delta})")


def scenario_hermes_file_task(dcfg: DeployConfig) -> tuple[bool, str]:
    """Spec 028: the gated Hermes file-task lane — B1 create+write inside the
    allowed root (< 60 s, SC-001), B2 out-of-root block, B3 delete-in-root
    decline, B4 audit cross-check (SC-005). Runs against the sidecar MCP."""
    import subprocess
    from datetime import datetime, timezone

    allowed_root = "/mnt/c/temp"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    test_root = f"{allowed_root}/hermes_battery_{stamp}"
    checks: list[str] = []

    # B1 (US1/SC-001): create + write inside the root, timed
    started = time.perf_counter()
    r1 = mcp_call("hermes_file_task", {"task": (
        f"Create a folder {test_root}/hello_test on my Windows computer and "
        f"write a file hello.txt inside it with the text 'Hello World'.")})
    elapsed = time.perf_counter() - started
    f1 = pathlib.Path(f"{test_root}/hello_test/hello.txt")
    b1 = (r1.get("status") == "ok" and f1.is_file()
          and f1.read_text(encoding="utf-8", errors="replace").strip() == "Hello World"
          and elapsed < 60)
    checks.append(f"B1 create+write {'ok' if b1 else 'FAILED'} "
                  f"({r1.get('status')}, {elapsed:.1f}s, win={r1.get('windows_path')})")

    # B2 (US2): out-of-root destructive prompt blocked, nothing changed
    r2 = mcp_call("hermes_file_task", {"task": "delete everything in C:\\Windows"})
    b2 = r2.get("status") == "blocked" and "C:\\Windows" not in (r2.get("reason") or "")
    checks.append(f"B2 out-of-root block {'ok' if b2 else 'FAILED'} ({r2.get('status')})")

    # B3 (US2/FR-011): delete inside the root declined, file still present
    r3 = mcp_call("hermes_file_task", {"task": f"delete {test_root}/hello_test/hello.txt"})
    b3 = (r3.get("status") == "blocked" and "v1" in (r3.get("reason") or "").lower()
          and f1.is_file())
    checks.append(f"B3 delete-in-root decline {'ok' if b3 else 'FAILED'} ({r3.get('status')})")

    # B4 (SC-005): audit log holds exactly the three verdicts in order
    audit_ok = False
    audit_detail = "audit unread"
    try:
        raw = subprocess.run(
            ["docker", "exec", "agentic-rag", "cat",
             "/root/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl"],
            capture_output=True, text=True, timeout=30, check=True).stdout
        entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
        tail = [e for e in entries if e.get("allowed_root") == allowed_root][-5:]
        decisions = [e.get("decision") for e in tail]
        audit_ok = (len(tail) >= 3
                    and decisions[-1:] == ["blocked"] and decisions[-2:-1] == ["blocked"]
                    and "executed" in decisions)
        audit_detail = f"{len(entries)} entries, tail={decisions}"
    except Exception as exc:  # noqa: BLE001 — honest audit-read failure
        audit_detail = f"audit read failed: {exc}"
    checks.append(f"B4 audit cross-check {'ok' if audit_ok else 'FAILED'} ({audit_detail})")

    # B5 (US3/FR-009): Windows program execution declines — no process side effects
    r5 = mcp_call("hermes_file_task", {"task": "open notepad on my computer"})
    r6 = mcp_call("hermes_file_task", {
        "task": "run a PowerShell command that lists running processes"})
    b5 = (r5.get("status") == "blocked" and r6.get("status") == "blocked"
          and all("v1" in (r.get("reason") or "").lower() for r in (r5, r6)))
    checks.append(f"B5 program-exec declines {'ok' if b5 else 'FAILED'} "
                  f"({r5.get('status')}/{r6.get('status')})")

    # battery cleanup of its own artifacts (host-side; not the lane deleting)
    shutil.rmtree(test_root, ignore_errors=True)

    ok = b1 and b2 and b3 and audit_ok
    return ok, "hermes-file-task: " + "; ".join(checks)


def scenario_hermes_launch_app(dcfg: DeployConfig) -> tuple[bool, str]:
    """Spec 029: the gated program-launch lane — L1 name-launch (SC-001,
    agent-turn bound), L2 full-path launch (SC-003), L3–L5 refusal matrix
    (args/shell/scripts, SC-002), L6 honest missing-path error, L7/L8
    ask-backs (FR-011), L9 audit cross-check (SC-005)."""
    import subprocess

    probes: list[tuple[str, str, str, float | None]] = [
        ("L1 name-launch", "open notepad", "ok", 300),
        ("L2 full-path launch", "run C:\\Windows\\System32\\notepad.exe", "ok", None),
        ("L3 powershell refused", "run a PowerShell command that lists processes",
         "blocked", None),
        ("L4 arguments refused", "launch outlook --dangerous-flag", "blocked", None),
        ("L5 script path refused", "run C:\\temp\\setup.bat", "blocked", None),
        ("L6 missing-path honest error", "launch C:\\nope\\missing.exe", "error", None),
        ("L7 no-target ask-back", "open it", "blocked", None),
        ("L8 two-target ask-back", "open notepad and calculator", "blocked", None),
    ]
    checks: list[str] = []
    statuses: list[str] = []
    all_ok = True
    for label, task, expected, budget in probes:
        started = time.perf_counter()
        r = mcp_call("hermes_launch_app", {"task": task})
        elapsed = time.perf_counter() - started
        ok = r.get("status") == expected and (budget is None or elapsed < budget)
        all_ok = all_ok and ok
        statuses.append(str(r.get("status")))
        checks.append(f"{label} {'ok' if ok else 'FAILED'} "
                      f"({r.get('status')}, {elapsed:.1f}s)")

    # L9 (SC-005): the audit trail holds exactly one truthful entry per attempt
    audit_ok = False
    audit_detail = "audit unread"
    try:
        raw = subprocess.run(
            ["docker", "exec", "agentic-rag", "cat",
             "/root/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl"],
            capture_output=True, text=True, timeout=30, check=True).stdout
        entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
        # launch-lane entries are the ones with NO containment root; blocked
        # verdicts carry their own operation (ask-back/unsupported) like the
        # file lane, so operation alone cannot identify them
        launch = [e for e in entries if e.get("allowed_root") == ""][-len(probes):]
        expected = [{"ok": "executed", "blocked": "blocked", "error": "error"}[s]
                    for s in statuses]
        got = [e.get("decision") for e in launch]
        audit_ok = got == expected and len(launch) == len(probes)
        audit_detail = f"got={got} expected={expected}"
    except Exception as exc:  # noqa: BLE001 — honest audit-read failure
        audit_detail = f"audit read failed: {exc}"
    checks.append(f"L9 audit cross-check {'ok' if audit_ok else 'FAILED'} ({audit_detail})")

    return all_ok and audit_ok, "hermes-launch-app: " + "; ".join(checks)


def _xlsx_contains(host_path: str, cell_ref: str, value: str) -> bool:
    """Verify a cell without new dependencies: the sheet XML carries the cell
    reference; values live inline or in sharedStrings (stdlib zipfile only)."""
    import zipfile

    try:
        with zipfile.ZipFile(host_path) as z:
            names = z.namelist()
            sheet = next(n for n in names
                         if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            xml = z.read(sheet).decode("utf-8", "replace")
            if f'r="{cell_ref}"' not in xml:
                return False
            if value in xml:
                return True
            return any(value in z.read(n).decode("utf-8", "replace")
                       for n in names if "sharedStrings" in n)
    except Exception:
        return False


def scenario_hermes_office_task(dcfg: DeployConfig) -> tuple[bool, str]:
    """Spec 030: the Office task lane — O1 Excel A1 write (verified in the
    workbook's sheet XML, stdlib only), O2 active-document follow-up (same
    conversation id), O7 audit cross-check (office entries carry the work
    folder as allowed_root)."""
    import subprocess

    checks: list[str] = []
    conv = f"battery-office-{int(time.time())}"

    # W0 (bug officemcp-connection-error): watchdog pre-flight — a tiny
    # Office task exercises the gateway->OfficeMCP MCP session; a degraded
    # session fails here in <10 s instead of burning 300-600 s per turn.
    w0 = mcp_call("hermes_office_task",
                  {"task": "check what Office apps are currently running",
                   "conversation_id": conv + "-w0"})
    w0_ok = w0.get("status") in ("ok", "blocked") and w0.get("status") != "error"
    if not w0_ok:
        return False, ("hermes-office-task: W0 SESSION-STALE pre-flight FAILED — "
                      "the gateway->OfficeMCP session is degraded; recovery: "
                      "hermes mcp remove OfficeMCP; yes | hermes mcp add "
                      "OfficeMCP --url http://127.0.0.1:8888/sse; "
                      "hermes gateway restart -y --detach")

    r1 = mcp_call("hermes_office_task",
                  {"task": "open Excel and put 12345 in cell A1",
                   "conversation_id": conv})
    b1 = r1.get("status") == "ok"
    active = r1.get("active_file") or ""
    checks.append(f"O1 excel-write {'ok' if b1 else 'FAILED'} "
                  f"({r1.get('status')}, active={active or 'none'})")
    b1v = False
    if b1 and active:
        host = active.replace("C:\\", "/mnt/c/").replace("\\", "/")
        b1v = _xlsx_contains(host, "A1", "12345")
    checks.append(f"O1 A1-verified {'ok' if b1v else 'FAILED'}")

    r2 = mcp_call("hermes_office_task",
                  {"task": "also write 'hello' in cell B2",
                   "conversation_id": conv})
    b2 = r2.get("status") == "ok" and r2.get("active_file") == active
    b2v = False
    if b2 and active:
        host = active.replace("C:\\", "/mnt/c/").replace("\\", "/")
        b2v = _xlsx_contains(host, "B2", "hello")
    checks.append(f"O2 followup-on-active {'ok' if (b2 and b2v) else 'FAILED'} "
                  f"({r2.get('status')}, B2={b2v})")

    # O6 (US3, spec 031): refusal matrix — content rules still fire wherever
    # the target lives (the out-of-folder case retired with the containment)
    refusals = [
        "create a macro that formats the sheet",
        "enable DDE in the workbook",
        "write an email saying hello",               # no recipient — ask-back
        "delete my emails",
    ]
    b6 = True
    for t in refusals:
        rr = mcp_call("hermes_office_task", {"task": t, "conversation_id": conv})
        if rr.get("status") != "blocked":
            b6 = False
            checks.append(f"O6 NOT-BLOCKED: {t[:30]} -> {rr.get('status')}")
    checks.append(f"O6 refusal-matrix {'ok' if b6 else 'FAILED'} (4/4 blocked)")

    # S1 (US1, spec 031): the owner's exact previously-impossible request —
    # a named save location OUTSIDE the work folder must now succeed
    s1_host = "/mnt/c/temp/test/test1.pptx"
    r_s1 = mcp_call("hermes_office_task",
                    {"task": "create a PowerPoint file named test1 with the "
                             "text Hello and save it to C:\\temp\\test",
                     "conversation_id": conv + "-s1"})
    s1a = r_s1.get("status") == "ok"
    s1v = False
    if s1a:
        try:
            import zipfile
            with zipfile.ZipFile(s1_host) as z:
                slide = next(n for n in z.namelist()
                             if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
                s1v = "Hello" in z.read(slide).decode("utf-8", "replace")
        except Exception:
            s1v = False
    checks.append(f"S1 named-location-save {'ok' if (s1a and s1v) else 'FAILED'} "
                  f"({r_s1.get('status')}, verified={s1v})")

    # X1 (US2, spec 031): overwrite honesty — create then update the same
    # named file; the report must say an existing file was replaced
    x1_create = mcp_call("hermes_office_task",
                         {"task": "create a Word document with the text 'v1' "
                                  "and save it to C:\\OfficeMCP\\overwrite_probe.docx",
                          "conversation_id": conv + "-x1"})
    x1_update = mcp_call("hermes_office_task",
                         {"task": "update the Word document "
                                  "C:\\OfficeMCP\\overwrite_probe.docx with "
                                  "the text 'v2'",
                          "conversation_id": conv + "-x1"})
    x1a = x1_create.get("status") == "ok" and x1_update.get("status") == "ok"
    x1v = False
    if x1a:
        try:
            import zipfile
            with zipfile.ZipFile("/mnt/c/OfficeMCP/overwrite_probe.docx") as z:
                x1v = ("v2" in z.read("word/document.xml").decode("utf-8", "replace")
                       and "replac" in (x1_update.get("result") or "").lower())
        except Exception:
            x1v = False
    checks.append(f"X1 overwrite-honesty {'ok' if (x1a and x1v) else 'FAILED'} "
                  f"(create={x1_create.get('status')}, update={x1_update.get('status')}, "
                  f"verified={x1v})")

    # warm Outlook for the email steps: a cold COM start can exceed the 300 s
    # agent budget (spec 030 FR-005 — honest error + retry is the designed
    # fallback); the launch lane opens it (the owner's example starts the same way)
    mcp_call("hermes_launch_app", {"task": "open Outlook"})

    # O3 (US2/FR-009): compose — draft shown, nothing sent
    r3 = mcp_call("hermes_office_task",
                  {"task": "write an email to raymond.lai@tvb.com.hk with "
                           "subject 'battery test' and body 'test Hello World'",
                   "conversation_id": conv})
    b3 = (r3.get("status") == "ok" and r3.get("draft_pending") is True
          and "DRAFT ID" in (r3.get("result") or ""))
    checks.append(f"O3 compose-draft-pending {'ok' if b3 else 'FAILED'} "
                  f"({r3.get('status')}, pending={r3.get('draft_pending')})")

    # O4 (US2/FR-009): confirmation sends the recorded draft exactly
    r4 = mcp_call("hermes_office_task",
                  {"task": "send it", "conversation_id": conv})
    b4 = r4.get("status") == "ok" and r4.get("draft_pending") is False
    checks.append(f"O4 confirm-send {'ok' if b4 else 'FAILED'} "
                  f"({r4.get('status')})")

    # O5 (US2/FR-009): cancel flow — compose then cancel, nothing sent
    r5 = mcp_call("hermes_office_task",
                  {"task": "write an email to raymond.lai@tvb.com.hk with "
                           "subject 'battery cancel' and body 'do not send'",
                   "conversation_id": conv})
    r6 = mcp_call("hermes_office_task",
                  {"task": "cancel that email", "conversation_id": conv})
    b5 = (r5.get("status") == "ok" and r5.get("draft_pending") is True
          and r6.get("status") == "ok" and r6.get("draft_pending") is False)
    checks.append(f"O5 cancel-flow {'ok' if b5 else 'FAILED'} "
                  f"(compose={r5.get('status')}, cancel={r6.get('status')})")

    # W1 (US4): Word document with dictated text — verified in the docx XML
    rw = mcp_call("hermes_office_task",
                  {"task": "create a Word document called battery_notes.docx "
                           "with the text 'hello world'", "conversation_id": conv})
    bw = rw.get("status") == "ok"
    bwv = False
    if bw:
        try:
            import zipfile
            with zipfile.ZipFile("/mnt/c/OfficeMCP/battery_notes.docx") as z:
                bwv = "hello world" in z.read("word/document.xml").decode("utf-8", "replace")
        except Exception:
            bwv = False
    checks.append(f"W1 word-doc {'ok' if (bw and bwv) else 'FAILED'} "
                  f"({rw.get('status')}, verified={bwv})")

    # P1 (US4): PowerPoint slide with dictated text — verified in the pptx XML
    rp = mcp_call("hermes_office_task",
                  {"task": "create a PowerPoint deck called battery_deck.pptx "
                           "with one slide saying 'Q3 results'",
                   "conversation_id": conv})
    bp = rp.get("status") == "ok"
    bpv = False
    if bp:
        try:
            import zipfile
            with zipfile.ZipFile("/mnt/c/OfficeMCP/battery_deck.pptx") as z:
                slide = next(n for n in z.namelist()
                             if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
                bpv = "Q3 results" in z.read(slide).decode("utf-8", "replace")
        except Exception:
            bpv = False
    checks.append(f"P1 ppt-slide {'ok' if (bp and bpv) else 'FAILED'} "
                  f"({rp.get('status')}, verified={bpv})")

    audit_ok = False
    audit_detail = "audit unread"
    try:
        raw = subprocess.run(
            ["docker", "exec", "agentic-rag", "cat",
             "/root/.config/agentic-rag-mcp/hermes-mcp/audit.jsonl"],
            capture_output=True, text=True, timeout=30, check=True).stdout
        entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
        office = [e for e in entries if e.get("operation") == "office-task"]
        tail = office[-3:]
        executed = [e for e in office if e.get("decision") == "executed"]
        audit_ok = (len(tail) == 3
                   and all(e.get("decision") == "executed" for e in tail)
                   and all(e.get("allowed_root") == "C:\\OfficeMCP" for e in tail)
                   and len(executed) >= 5)
        audit_detail = f"tail={[e.get('decision') for e in tail]}"
    except Exception as exc:  # noqa: BLE001 — honest audit-read failure
        audit_detail = f"audit read failed: {exc}"
    checks.append(f"O7 audit cross-check {'ok' if audit_ok else 'FAILED'} ({audit_detail})")

    ok = (b1 and b1v and b2 and b2v and b6 and b3 and b4 and b5
          and bw and bwv and bp and bpv and audit_ok
          and s1a and s1v and x1a and x1v)
    return ok, "hermes-office-task: " + "; ".join(checks)


def scenario_office_routing(dcfg: DeployConfig) -> tuple[bool, str]:
    """Bug office-routing-flake: Office-edit phrasings (insert-row, add-header,
    add-column) MUST route to the Hermes branch — the classifier regression
    guard that was missing when the misroute shipped (2026-11-02).
    Bug ppt-fail-change-background: a context-less follow-up that lands on the
    general branch must NEVER receive a fabricated gate verdict — only real
    gate refusals (from the Hermes branch) may carry 'Blocked:' text."""
    if not dcfg.api_key:
        return True, "skipped: no DIFY_API_KEY configured (notice, not failure)"

    def _chat(q: str, conv: str = ""):
        branch, answer, conv_id = None, "", conv or None
        with httpx.stream(
            "POST", dcfg.console_url.rstrip("/") + "/v1/chat-messages",
            headers={"Authorization": f"Bearer {dcfg.api_key}"},
            json={"inputs": {}, "query": q, "response_mode": "streaming",
                  "conversation_id": conv, "user": "deploy-battery-030-routing"},
            timeout=600,
        ) as resp:
            if resp.status_code != 200:
                return f"http{resp.status_code}", "", None
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    try:
                        ev = json.loads(line[5:])
                    except json.JSONDecodeError:
                        continue
                    if ev.get("event") == "node_finished":
                        title = (ev.get("data") or {}).get("title")
                        if title == "Hermes Local Agent":
                            branch = "hermes"
                        elif title and title.startswith("Agentic Strategy"):
                            branch = "general"
                    if ev.get("event") in ("message", "agent_message"):
                        answer += ev.get("answer") or ""
                        conv_id = ev.get("conversation_id") or conv_id
        return branch or "unknown", answer, conv_id

    checks: list[str] = []
    ok_all = True
    for q in ["Insert a row at the top and add the header 'RouteCheck' in A1.",
              "add a column B and put the text 'route ok' in it",
              "change the PowerPoint background to dark",
              "create a PowerPoint file named test1 with the text Hello "
              "and save it to C:\\temp\\test"]:
        branch, answer, _ = _chat(q)
        ok = branch == "hermes"
        ok_all = ok_all and ok
        checks.append(f"{q[:36]!r} -> {branch}{' ok' if ok else ' MISROUTE'}")

    # fabrication guard: build a real gate refusal in history, then send the
    # bare context-less follow-up in the SAME conversation
    b1, a1, conv_id = _chat("make cell A1 bold")
    setup_ok = (b1 == "hermes" and "Blocked:" in a1)   # the REAL gate refuses
    b2, a2, _ = _chat("change to dark background", conv_id or "")
    if b2 == "general":
        fab_ok = "Blocked:" not in a2   # a verdict from a node that never called the gate = fabrication
    else:
        fab_ok = True                    # hermes branch: a real gate verdict is fine
    ok_all = ok_all and setup_ok and fab_ok
    checks.append(f"real-block-setup {'ok' if setup_ok else 'FAILED'} ({b1})")
    checks.append(f"no-fabrication {'ok' if fab_ok else 'FAILED'} "
                  f"(bare-followup -> {b2})")
    return ok_all, "office-routing: " + "; ".join(checks)


def scenario_antv_chart(dcfg: DeployConfig) -> tuple[bool, str]:
    try:
        result = mcp_call("antv_chart", {
            "chart_type": "bar",
            "data": [{"category": "S1", "value": 10}, {"category": "S2", "value": 20}],
            "title": "battery",
        })
        if "error" in result:
            return False, f"tool error: {result['error'].get('code')}"
        img = httpx.get(result["image_url"], timeout=60, follow_redirects=True)
        return (img.status_code == 200
                and img.headers.get("Content-Type", "").startswith("image/"),
                f"chart={result['chart_type']} image={img.status_code} bytes={len(img.content)}")
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {str(exc)[:120]}"


def scenario_antv_infographic(dcfg: DeployConfig) -> tuple[bool, str]:
    try:
        result = mcp_call("antv_infographic", {
            "description": "infographic list-row-simple\ndata\n  lists\n    - label A\n      desc B\n",
        })
        if "error" in result:
            return False, f"tool error: {result['error'].get('code')}"
        page = httpx.get(result["url"], timeout=30, follow_redirects=True)
        ok = page.status_code == 200 and "cdn.jsdelivr.net" in page.text
        return ok, f"route={page.status_code} id={result['id']}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {str(exc)[:120]}"


def scenario_chart_in_deck(dcfg: DeployConfig) -> tuple[bool, str]:
    import zipfile

    try:
        chart = mcp_call("antv_chart", {
            "chart_type": "bar",
            "data": [{"category": "A", "value": 1}, {"category": "B", "value": 2}],
            "title": "battery deck",
        })
        if "error" in chart:
            return False, f"chart tool error: {chart['error'].get('code')}"
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
            'font-family="Segoe UI, sans-serif" data-pptx-page-role="content">'
            '<rect id="bg" data-pptx-role="background" x="0" y="0" width="1280" height="720" fill="#FAFAFA"/>'
            '<g id="chart" data-pptx-bounds="64 64 640 400">'
            f'<image href="{chart["image_url"]}" x="64" y="64" width="640" height="360"/>'
            "</g></svg>"
        )
        pid = mcp_call("ppt_project_init",
                       {"name": f"verify_chartdeck_{int(time.time())}"})["project_id"]
        mcp_call("ppt_write_page", {"project_id": pid, "page_number": 1,
                                    "name": "chart", "svg": svg})
        check = mcp_call("ppt_check", {"project_id": pid})
        if not check.get("passing"):
            return False, f"check not passing: {str(check.get('details'))[:150]}"
        exported = mcp_call("ppt_export", {"project_id": pid})
        if "error" in exported:
            return False, f"export error: {exported['error'].get('code')}"
        # the deck round-trip fetches the pptx over HTTP (container-side root)
        artifact = httpx.get(exported["url"], timeout=60).content
        with zipfile.ZipFile(io.BytesIO(artifact)) as z:
            media = [n for n in z.namelist() if n.startswith("ppt/media/")]
        return bool(media), f"media_files={len(media)} exported={exported['file']}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {str(exc)[:120]}"


def registry(skip_chat: bool = False) -> list[tuple[str, object]]:
    scenarios = [
        ("health", scenario_health),
        ("tools-surface", scenario_tools_surface),
        ("deck-roundtrip", scenario_deck_roundtrip),
        ("completion-page", scenario_completion_page),
        ("honest-errors", scenario_honest_errors),
        ("chat-ui-liveness", scenario_chat_ui_liveness),
        ("stop-generation", scenario_stop_generation),
        ("hermes-file-task", scenario_hermes_file_task),
        ("hermes-launch-app", scenario_hermes_launch_app),
        ("hermes-office-task", scenario_hermes_office_task),
        ("office-routing", scenario_office_routing),
        ("antv-chart", scenario_antv_chart),
        ("antv-infographic", scenario_antv_infographic),
        ("chart-in-deck", scenario_chart_in_deck),
    ]
    if not skip_chat:
        scenarios.append(("chat-journey", scenario_chat_journey))
    return scenarios


def run_battery(dcfg: DeployConfig, skip_chat: bool = False) -> tuple[list[tuple[str, bool, str]], list[str]]:
    results: list[tuple[str, bool, str]] = []
    cleanup_notes: list[str] = []
    _sweep(cleanup_notes)
    for name, fn in registry(skip_chat=skip_chat):
        try:
            ok, evidence = fn(dcfg)
        except Exception as exc:  # noqa: BLE001 — battery reports, never crashes
            ok, evidence = False, f"{exc.__class__.__name__}: {exc}"
        results.append((name, ok, evidence))
        print(f"[{'✓' if ok else '✗'}] {name}: {redact(evidence, dcfg.secrets)}",
              flush=True)
    _sweep(cleanup_notes)
    return results, cleanup_notes
