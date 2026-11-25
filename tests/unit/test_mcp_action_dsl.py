"""Red-first static Dify DSL contracts for spec 047 T006 and T038.

These tests inspect only the checked-in chatflow artifact.  They deliberately
address nodes and edges by ID so unrelated tool/prompt changes do not affect
the MCP-Action contract.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

DSL_PATH = (
    Path(__file__).resolve().parents[2]
    / "dify"
    / "AGIAssistant"
    / "AGI_Assistant.yml"
)
MCP_ACTION_AGENTS = (
    "agentic_strategy",
    "hermes_agent",
)
MCP_ACTION_EXCLUDED_AGENTS = (
    "agentic_strategy_local",
    "ppt_master",
    "ppt_master_local",
)
OFFER = "Do you want me to do it automatically for you?"
SYS_BINDINGS = {
    "conversation_id": ["sys", "conversation_id"],
    "dialogue_count": ["sys", "dialogue_count"],
    "query": ["sys", "query"],
}


@pytest.fixture(scope="module")
def graph() -> dict:
    dsl = yaml.safe_load(DSL_PATH.read_text(encoding="utf-8"))
    return dsl["workflow"]["graph"]


def _nodes(graph: dict) -> dict[str, dict]:
    return {node["id"]: node for node in graph["nodes"]}


def _tools(node: dict) -> list[dict]:
    parameters = node["data"]["agent_parameters"]
    return (parameters.get("tools") or {}).get("value") or []


def _mcp_action_tool(node: dict) -> dict:
    matches = [tool for tool in _tools(node) if tool.get("tool_name") == "mcp_action"]
    assert len(matches) == 1, (
        f"{node['id']} must have exactly one mcp_action registration; "
        f"found {len(matches)}"
    )
    return matches[0]


def _prompt(node: dict) -> str:
    return node["data"]["agent_parameters"]["instruction"]["value"]


def _honesty_code(nodes: dict[str, dict]) -> str:
    return nodes["honesty_check"]["data"]["code"]


def _main_argument_names(code: str) -> set[str]:
    signature = re.search(r"function\s+main\s*\(\s*\{([^}]*)\}", code, re.DOTALL)
    assert signature, "honesty_check must keep Dify's destructured main({...}) signature"
    return {name.strip() for name in signature.group(1).split(",") if name.strip()}


def _leak_regexes(code: str) -> list[str]:
    """Return regex literals assigned to variables whose names mention leaks."""
    assignments = re.finditer(
        r"\b(?:var|let|const)\s+\w*leak\w*\s*=\s*"
        r"(/((?:\\.|[^/\n])*)/[a-z]*)",
        code,
        re.IGNORECASE,
    )
    return [match.group(2) for match in assignments]


def _execution_result(status: str = "ok") -> dict:
    return {
        "status": status,
        "changed": True,
        "before": {"default_printer": "Printer A"},
        "after": {"default_printer": "Printer B"},
        "verification": "verified",
        "display": {"status": "displayed"},
        "screenshot": {
            "status": "captured",
            "image_url": f"http://sidecar:8080/mcp-action/screenshots/{'A' * 43}",
        },
    }


def _run_honesty(
    code: str,
    answer: str,
    output: dict | None,
    *,
    lane: str = "general",
    tool_name: str = "mcp_action",
    phase: str = "confirm",
) -> str:
    items = []
    if output is not None:
        wrapped = "tool response: " + json.dumps(output) + "."
        items = [{
            "data": {
                "output": {
                    "tool_responses": [{
                        "tool_call_name": tool_name,
                        "tool_call_input": {"phase": phase},
                        "tool_response": wrapped,
                    }]
                }
            }
        }]
    inputs = {"answer": "", "items": [], "general_answer": "", "general_items": []}
    if lane == "general":
        inputs["general_answer"] = answer
        inputs["general_items"] = items
    else:
        inputs["answer"] = answer
        inputs["items"] = items
    runner = (
        "const fs=require('fs');"
        "const p=JSON.parse(fs.readFileSync(0,'utf8'));"
        "eval(p.code);process.stdout.write(JSON.stringify(main(p.inputs)));"
    )
    run = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"code": code, "inputs": inputs}),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)["result"]


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_mcp_action_is_registered_and_enabled(graph: dict, node_id: str):
    tool = _mcp_action_tool(_nodes(graph)[node_id])
    assert tool.get("enabled") is True


def test_mcp_action_is_not_registered_on_ppt_or_other_agents(graph: dict):
    registered = {
        node_id
        for node_id, node in _nodes(graph).items()
        if node.get("data", {}).get("type") == "agent"
        and any(tool.get("tool_name") == "mcp_action" for tool in _tools(node))
    }
    assert registered == set(MCP_ACTION_AGENTS), (
        "owner-approved scope is General cloud + Hermes only; "
        "agentic_strategy_local and both PPT agents must remain unregistered"
    )


@pytest.mark.parametrize("node_id", MCP_ACTION_EXCLUDED_AGENTS)
def test_mcp_action_surface_is_absent_from_unapproved_agents(graph: dict, node_id: str):
    node = _nodes(graph)[node_id]
    serialized_node = yaml.safe_dump(node).lower()
    assert "mcp_action" not in serialized_node
    assert "mcp-action" not in serialized_node
    assert "word_printer_duplex" not in serialized_node
    assert not any(tool.get("tool_name") == "mcp_action" for tool in _tools(node))
    prompt = _prompt(node)
    assert "mcp_action" not in prompt
    assert "mcp-action" not in prompt.lower()
    assert not prompt.startswith("MCP-ACTION OVERRIDE:")
    if node_id == "agentic_strategy_local":
        assert prompt.startswith("You are a test assistant")
        assert "ANSWER FORMAT — IMAGES" in prompt
        # spec 050 replaced the soft default wording with the binding policy
        assert "MUST be illustrated with the source images" in prompt
        assert "antv_infographic" in prompt


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_mcp_action_binds_raw_dify_system_arguments(graph: dict, node_id: str):
    tool = _mcp_action_tool(_nodes(graph)[node_id])
    parameters = tool.get("parameters") or {}
    for argument, expected_selector in SYS_BINDINGS.items():
        binding = parameters.get(argument)
        assert isinstance(binding, dict), f"{node_id} mcp_action.{argument} is not bound"
        assert binding.get("auto") == 0, (
            f"{node_id} mcp_action.{argument} must set auto: 0 or Dify leaves the "
            "variable binding unapplied and the model supplies a literal placeholder"
        )
        value_binding = binding.get("value")
        assert isinstance(value_binding, dict) and value_binding.get("type") == "variable", (
            f"{node_id} mcp_action.{argument}.value must be a Dify variable binding; "
            "template constants are JSON-serialized before tools parsing and break "
            "when raw query contains quotes or newlines"
        )
        assert value_binding.get("value") == expected_selector, (
            f"{node_id} mcp_action.{argument} must bind exactly "
            f"{expected_selector!r}, not a paraphrase or transformed value"
        )
    serialized = yaml.safe_dump(tool)
    assert "{{#sys.query#}}" not in serialized
    assert "{{#sys.conversation_id#}}" not in serialized
    assert "{{#sys.dialogue_count#}}" not in serialized


def test_no_generic_yes_no_prerouter_was_added(graph: dict):
    nodes = _nodes(graph)
    edges = graph["edges"]

    # A generic confirmation router would have to replace one of these direct
    # predecessors or add a yes/no class to an existing intent classifier.
    expected_agent_predecessors = {
        "agentic_strategy": {"intent_router", "attach_router_cloud"},
        "agentic_strategy_local": {"intent_router_local", "attach_router_local"},
        "hermes_agent": {"intent_router"},
    }
    for agent_id, expected in expected_agent_predecessors.items():
        actual = {edge["source"] for edge in edges if edge["target"] == agent_id}
        assert actual == expected, f"unexpected pre-router upstream of {agent_id}: {actual}"

    expected_classes = {
        "intent_router": {"ppt_request", "hermes_file", "general"},
        "intent_router_local": {"ppt_request", "general"},
    }
    for router_id, expected in expected_classes.items():
        classes = nodes[router_id]["data"]["classes"]
        assert {item["id"] for item in classes} == expected

    start_id = next(
        node_id for node_id, node in nodes.items()
        if node.get("data", {}).get("type") == "start"
    )
    assert {edge["target"] for edge in edges if edge["source"] == start_id} == {
        "model_router"
    }
    assert {edge["target"] for edge in edges if edge["source"] == "model_router"} == {
        "attach_router_cloud",
        "attach_router_local",
    }


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_shared_mcp_action_prompt_protocol(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    required_patterns = {
        "ask-first rule": r"\bASK FIRST\b",
        "mcp_action draft protocol": r"\bmcp_action\b[\s\S]*\bdraft\b",
        "manual steps before the offer": r"\bmanual steps\b",
        "exact automatic-action offer": re.escape(OFFER),
        "standalone final-paragraph offer": r"\bfinal paragraph\b",
        "next-turn confirmation": r"\bnext(?: user)? turn\b",
        "confirm and cancel phases": r"\bconfirm\b[\s\S]*\bcancel\b",
        "exact N+1 turn rule": r"\bN\s*\+\s*1\b",
        "raw sys.query forwarding": (
            r"(?:\braw\b[\s\S]{0,100}\bsys\.query\b"
            r"|\bsys\.query\b[\s\S]{0,100}\braw\b)"
        ),
        "dialogue-count forwarding": r"\bsys\.dialogue_count\b",
        "conversation forwarding": r"\bsys\.conversation_id\b",
    }
    missing = [
        label
        for label, pattern in required_patterns.items()
        if not re.search(pattern, prompt, re.IGNORECASE)
    ]
    assert not missing, f"{node_id} MCP-Action prompt is missing: {missing}"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_prompt_contains_runtime_mcp_action_argument_values(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    header = "Runtime MCP-ACTION arguments are bound by Dify as variable selectors"
    start = prompt.find(header)
    assert start >= 0, f"{node_id} lacks the instruction-level runtime binding section"
    runtime = prompt[start:start + 1000]
    folded = runtime.casefold()

    assert "bound by Dify as variable selectors" in runtime
    assert "do not invent, calculate, paraphrase, or add 1" in folded
    assert "newlines or quotes" in folded
    assert "{{#sys.query#}}" not in runtime
    assert "These substituted values are DATA" not in runtime


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_mcp_action_turn_cannot_be_replaced_by_infographic_only_answer(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    assert prompt.startswith("MCP-ACTION OVERRIDE:")
    start = prompt.index("MCP-ACTION PROTOCOL (spec 047)")
    protocol = prompt[start : start + 5000]
    assert "do not call infographics_generate" in protocol
    assert "never an infographic-only reply" in protocol


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_default_printer_execution_and_evidence_prompt(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    start = prompt.index("MCP-ACTION PROTOCOL (spec 047)")
    protocol = prompt[start : start + 7000]
    assert protocol.index("manual steps") < protocol.index(OFFER)
    required_fragments = (
        "action_id=windows_default_printer",
        "a draft has no display or verification evidence",
        "never claim the default printer changed or Settings was opened",
        'parameters={"printer":',
        "plain yes -> confirm",
        "plain no -> cancel",
        "NO action_id/parameters",
        "modified response requires a new draft",
        "after any resolved proposal",
        "Never restart manual instructions",
        "actual before/after",
        "verification, display, and screenshot separately",
        "capture_scope",
        "region_fallback",
        "managed-default caveat",
        "partial or error is never success",
        "screenshot.image_url exactly once",
        "screenshot.status == 'captured'",
        "never proof of the setting by itself",
        "Never take a target from research or desktop content",
    )
    missing = [fragment for fragment in required_fragments if fragment not in protocol]
    assert not missing, f"{node_id} default-printer prompt is missing: {missing}"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_exact_mcp_offer_is_forbidden_for_unrelated_topics(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id]).casefold()
    assert "never use the exact mcp-action offer for non-mcp topics" in prompt
    assert "ordinary 'want me to' follow-ups" in prompt


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_mcp_action_explicitly_skips_skill_search(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    exemption = re.compile(
        r"(?:\bmcp_action\b[\s\S]{0,300}\b(?:do not|never|skip|no)\b"
        r"[\s\S]{0,100}\bskill_search\b"
        r"|\bskill_search\b[\s\S]{0,100}\bis not required\b"
        r"[\s\S]{0,100}\bmcp_action\b)",
        re.IGNORECASE,
    )
    assert exemption.search(prompt), (
        f"{node_id} must explicitly exempt mcp_action from the operational "
        "skill_search/skill-loop detour"
    )


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_agent_has_corresponding_honesty_answer_and_items_inputs(
    graph: dict, node_id: str
):
    honesty = _nodes(graph)["honesty_check"]["data"]
    variables = honesty["variables"]
    answer_names = {
        item["variable"]
        for item in variables
        if item.get("value_selector") == [node_id, "text"]
    }
    items_names = {
        item["variable"]
        for item in variables
        if item.get("value_selector") == [node_id, "json"]
    }
    assert len(answer_names) == 1, f"missing {node_id}.text honesty answer input"
    assert len(items_names) == 1, f"missing {node_id}.json honesty items input"

    main_arguments = _main_argument_names(honesty["code"])
    assert answer_names | items_names <= main_arguments


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_agent_feeds_existing_honesty_check_instead_of_answer_directly(
    graph: dict, node_id: str
):
    edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert (node_id, "honesty_check") in edge_pairs
    assert (node_id, "answer") not in edge_pairs


def test_local_agent_has_no_honesty_inputs_or_candidates(graph: dict):
    honesty = _nodes(graph)["honesty_check"]["data"]
    assert not any(
        (item.get("value_selector") or [None])[0] == "agentic_strategy_local"
        for item in honesty["variables"]
    )
    main_arguments = _main_argument_names(honesty["code"])
    assert "local_answer" not in main_arguments
    assert "local_items" not in main_arguments
    assert "local_answer" not in honesty["code"]
    assert "local_items" not in honesty["code"]


def test_local_agent_answer_bypasses_shared_honesty(graph: dict):
    nodes = _nodes(graph)
    edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("agentic_strategy_local", "answer") in edge_pairs
    assert ("agentic_strategy_local", "honesty_check") not in edge_pairs
    assert "{{#agentic_strategy_local.text#}}" in nodes["answer"]["data"]["answer"]


def test_honesty_check_is_the_general_answer_source(graph: dict):
    nodes = _nodes(graph)
    edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert ("honesty_check", "answer") in edge_pairs

    answer_template = nodes["answer"]["data"]["answer"]
    assert "{{#honesty_check.result#}}" in answer_template
    for agent_id in MCP_ACTION_AGENTS:
        assert f"{{{{#{agent_id}.text#}}}}" not in answer_template, (
            f"{agent_id}.text bypasses honesty_check in the Answer template"
        )


def test_honesty_guard_binds_exact_offer_to_real_pending_mcp_action(graph: dict):
    code = _honesty_code(_nodes(graph))
    assert OFFER in code, "honesty_check must recognize the exact MCP-Action offer"
    assert "mcp_action" in code, (
        "research or arbitrary tool calls must not count as MCP-Action evidence"
    )
    assert "pending-confirmation" in code, (
        "the exact offer requires a real mcp_action pending-confirmation result"
    )
    assert re.search(
        r"\bmcp_action\b[\s\S]{0,1600}\bpending-confirmation\b"
        r"|\bpending-confirmation\b[\s\S]{0,1600}\bmcp_action\b",
        code,
    ), "pending status and the mcp_action tool identity must form one evidence check"


def test_honesty_guard_handles_observed_dify_tool_call_shapes(graph: dict):
    code = _honesty_code(_nodes(graph))
    assert "Array.isArray(o.tool_responses)" in code, (
        "honesty_check must traverse item.data.output.tool_responses[]"
    )
    for field in ("tool_call_name", "tool_call_input", "tool_response"):
        assert f"call.{field}" in code, (
            f"observed CALL/tool_responses field is not inspected: {field}"
        )


def test_honesty_guard_unwraps_bounded_tool_response_json(graph: dict):
    code = _honesty_code(_nodes(graph))
    assert "var MAX_TOOL_OUTPUT_CHARS = 250000;" in code
    assert "text.length > MAX_TOOL_OUTPUT_CHARS" in code
    assert "text.indexOf('{')" in code
    assert "text.lastIndexOf('}')" in code
    assert "text.slice(first, last + 1)" in code, (
        "wrapped 'tool response: {…}.' output must be unwrapped before JSON.parse"
    )


def test_honesty_guard_tracks_execution_display_and_screenshot_evidence(graph: dict):
    code = _honesty_code(_nodes(graph))
    required_fragments = (
        "var mcpActionExecution = false;",
        "var mcpActionDisplay = false;",
        "var mcpActionScreenshot = false;",
        "parsed.verification === 'verified'",
        "parsed.status === 'ok'",
        "parsed.status === 'partial'",
        "parsed.display.status === 'displayed'",
        "parsed.screenshot.status === 'captured'",
        "executionClaims",
        "displayClaims",
        "screenshotClaims",
        "/mcp-action/screenshots/",
    )
    for fragment in required_fragments:
        assert fragment in code, f"missing MCP-Action evidence handling: {fragment}"


def test_offline_honesty_allows_real_ok_and_partial_results(graph: dict):
    code = _honesty_code(_nodes(graph))
    ok = _execution_result()
    url = ok["screenshot"]["image_url"]
    ok_answer = (
        "Default printer changed from Printer A to Printer B. "
        "Verification: verified. Display: displayed. Screenshot: captured.\n"
        f"![Printers]({url})"
    )
    assert _run_honesty(code, ok_answer, ok) == ok_answer

    partial = _execution_result("partial")
    partial["display"] = {"status": "attempted-but-failed"}
    partial["screenshot"] = {"status": "skipped-display-unverified"}
    partial_answer = (
        "Default printer changed from Printer A to Printer B. Verification: verified. "
        "Display failed: Settings could not be displayed. "
        "Screenshot failed: no screenshot was captured."
    )
    assert _run_honesty(code, partial_answer, partial, lane="hermes") == partial_answer


def test_offline_honesty_display_and_screenshot_failures(graph: dict):
    code = _honesty_code(_nodes(graph))
    display_failure = _execution_result("partial")
    display_failure["display"] = {"status": "attempted-but-failed"}
    display_failure["screenshot"] = {"status": "skipped-display-unverified"}
    fabricated_display = "Default printer changed and verified. Settings displayed."
    result = _run_honesty(code, fabricated_display, display_failure)
    assert result.startswith("No automatic change was verified.") and result != fabricated_display

    screenshot_failure = _execution_result("partial")
    screenshot_failure["screenshot"] = {"status": "error"}
    honest_failure = (
        "Default printer changed and verified. Settings displayed. Screenshot failed."
    )
    assert _run_honesty(code, honest_failure, screenshot_failure) == honest_failure
    fabricated_capture = (
        "Default printer changed and verified. Settings displayed. Screenshot captured."
    )
    result = _run_honesty(code, fabricated_capture, screenshot_failure)
    assert result.startswith("Honesty check:") and result != fabricated_capture


def test_offline_honesty_rejects_forged_url_failed_draft_and_research(graph: dict):
    code = _honesty_code(_nodes(graph))
    forged_url = f"http://sidecar:8080/mcp-action/screenshots/{'B' * 43}"
    forged_answer = (
        "Default printer changed and verified. Settings displayed. Screenshot captured.\n"
        f"![Forged]({forged_url})"
    )
    result = _run_honesty(code, forged_answer, _execution_result())
    assert result.startswith("Honesty check:") and result != forged_answer

    failed_draft = _execution_result("error")
    failed_draft["verification"] = "not-run"
    failed_draft["display"] = {"status": "skipped"}
    failed_draft["screenshot"] = {"status": "skipped"}
    failed_claim = "I have changed the default printer."
    result = _run_honesty(code, failed_claim, failed_draft, phase="draft")
    assert result.startswith("No verified default-printer change was completed.")
    assert result != failed_claim

    research_claim = "Printer B is now your default printer."
    result = _run_honesty(
        code, research_claim, _execution_result(), tool_name="web_search"
    )
    assert result.startswith("No verified default-printer change was completed.")
    assert result != research_claim


def test_offline_honesty_allows_normal_cancel_error_and_manual_text(graph: dict):
    code = _honesty_code(_nodes(graph))
    cancel = "Cancelled. No action was executed and no setting was changed."
    assert _run_honesty(code, cancel, {"status": "cancelled"}, phase="cancel") == cancel

    error = "The action failed; no setting was changed and no screenshot was captured."
    assert _run_honesty(code, error, {"status": "error"}) == error

    manual = (
        "Open Settings. With Settings open, choose your printer and select Set as default. "
        "Take a screenshot if useful."
    )
    assert _run_honesty(code, manual, None) == manual

    unrelated = "Here is a summary of your research."
    assert _run_honesty(code, unrelated, None) == unrelated


def test_honesty_guard_detects_leaked_mcp_action_invocations(graph: dict):
    regexes = _leak_regexes(_honesty_code(_nodes(graph)))
    assert any(
        "mcp_action" in expression
        and all(tag in expression for tag in ("invoke", "function_call", "tool_call"))
        for expression in regexes
    ), "leaked <invoke>/<function_call>/<tool_call> mcp_action text must be detected"


def test_offline_honesty_ignores_hidden_think_claims_but_blocks_visible_claims(graph: dict):
    code = _honesty_code(_nodes(graph))
    hidden = (
        "<think>Settings was displayed and a screenshot was captured. "
        "Do you want me to do it automatically for you?</think>"
        "The proposal is not executed yet; no settings were changed."
    )
    assert not _run_honesty(code, hidden, None).startswith("Honesty check:")

    visible = "<think>Only reasoning.</think>Settings was displayed."
    visible_result = _run_honesty(code, visible, None)
    assert visible_result.startswith("No automatic change was verified.")
    assert "Honesty check:" not in visible_result

    execution_result = _run_honesty(code, "The default printer was set.", None)
    assert execution_result.startswith("No verified default-printer change was completed.")
    assert "Honesty check:" not in execution_result

    conditional = (
        "After you click the link, Settings is open. These are manual steps. "
        "After you click Set, the default printer was set. "
        "The duplex setting you apply here lives on the printer queue. "
        "Default printer settings can be reviewed manually. "
        "Print Preview is opened after you confirm. "
        "No document was created, saved, closed, or printed. Nothing was saved. "
        "No printer setting was changed; nothing was opened or verified. "
        "Print Preview was opened after you confirm. "
        "Settings was opened after you confirm. No Print Preview was opened."
    )
    assert not _run_honesty(code, conditional, None).startswith("Honesty check:")
    assert "display claims were blocked" not in _run_honesty(code, "I opened Settings.", None)
    assert "display claims were blocked" in _run_honesty(code, "I opened Print Preview.", None)


def test_offline_pending_manual_steps_are_not_treated_as_executed_actions(graph: dict):
    code = _honesty_code(_nodes(graph))
    pending = {"status": "pending-confirmation", "offer": OFFER}
    answer = (
        "Manual steps: open Settings, choose the duplex setting, and File > Print. "
        "Print Preview is open after you select it. "
        "Default printer settings and the printer queue can be reviewed manually. "
        + OFFER
    )
    assert _run_honesty(code, answer, pending, phase="draft") == answer

    premature = "I opened Settings before confirmation. " + OFFER
    assert _run_honesty(code, premature, pending, phase="draft").startswith("Honesty check:")


def test_existing_hermes_honesty_patterns_are_preserved(graph: dict):
    code = _honesty_code(_nodes(graph))
    leak_regexes = _leak_regexes(code)
    assert any(
        "hermes_" in expression
        and all(tag in expression for tag in ("invoke", "function_call", "tool_call"))
        for expression in leak_regexes
    )

    existing_claim_patterns = (
        r"local agent (completed|did|was)",
        r"the agent (sent|pressed|opened|typed|launched|focused|confirmed|handled)",
        r"the tool (returned|responded)",
        r"LAUNCH: ?(SUCCESS|FAILED)",
        r"hermes_(launch_app|office_task|file_task|cancel_turn|run_command|run_powershell)",
    )
    for pattern in existing_claim_patterns:
        assert pattern in code, f"existing Hermes honesty pattern was lost: {pattern}"


def _word_execution_result(
    status: str = "ok", orientation: str = "long-edge"
) -> dict:
    mode = {
        "long-edge": "TwoSidedLongEdge",
        "short-edge": "TwoSidedShortEdge",
    }[orientation]
    result = _execution_result(status)
    result["action_id"] = "word_printer_duplex"
    result["orientation"] = orientation
    result["requested_duplex"] = mode
    result["before"] = {"printer": "Printer B", "duplex": "OneSided"}
    result["after"] = {"printer": "Printer B", "duplex": mode}
    result["display"] = {
        "status": "displayed",
        "application": "Word",
        "print_preview": True,
        "foreground": True,
    }
    return result


WORD_EXECUTION_CLAIMS = (
    "Duplex was changed to long-edge.",
    "The printer configuration was updated to short-edge duplex.",
    "I set Word's duplex mode on the printer.",
    "The requested orientation is now active.",
    "The duplex read-back matched TwoSidedLongEdge.",
)
WORD_DISPLAY_CLAIMS = (
    "Word Print Preview is open.",
    "Print Preview was displayed.",
    "Word is showing the print screen.",
    "I opened Word's Print Preview.",
)
WORD_DOCUMENT_ACTION_CLAIMS = (
    "I changed the Word document content.",
    "The Word document was saved.",
    "I closed the Word document.",
    "The Word document was printed.",
)


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_has_manual_steps_before_exact_offer(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])
    start = prompt.index("MCP-ACTION PROTOCOL (spec 047)")
    protocol = prompt[start : start + 7000]
    word_manual = re.search(
        r"(?:\bWord(?: duplex)?\b[\s\S]{0,200}\bmanual steps\b"
        r"|\bmanual steps\b[\s\S]{0,200}\bWord(?: duplex)?\b)",
        protocol,
        re.IGNORECASE,
    )
    assert word_manual, f"{node_id} lacks Word-specific manual steps"
    window = protocol[word_manual.start() : word_manual.end() + 400]
    assert re.search(
        r"\bmanual steps\b[\s\S]{0,250}\boffer\b", window, re.IGNORECASE
    ), f"{node_id} must place Word manual steps before the automatic-action offer"
    assert OFFER in protocol


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_has_required_parameters_and_both_orientations(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])
    match = re.search(r"action_id=word_printer_duplex[\s\S]{0,1200}", prompt)
    assert match, f"{node_id} lacks the reviewed Word duplex action"
    schema = match.group(0)
    assert re.search(r'parameters=\{\s*"printer"\s*:', schema), (
        f"{node_id} Word duplex draft must require the exact printer parameter"
    )
    assert re.search(r'"orientation"\s*:', schema), (
        f"{node_id} Word duplex draft must require orientation beside printer"
    )
    assert "long-edge" in schema and "short-edge" in schema, (
        f"{node_id} must expose only the two reviewed duplex orientations"
    )


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_discloses_scope_blank_document_and_ask_first(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])
    start = prompt.index("MCP-ACTION PROTOCOL (spec 047)")
    protocol = prompt[start : start + 7000]
    required_patterns = {
        "printer-wide scope": r"\bprinter-wide\b",
        "effects beyond the current document": (
            r"\b(?:outside|beyond)\b[\s\S]{0,100}\b(?:current\s+)?Word document\b"
        ),
        "blank unsaved document used only for Print Preview": (
            r"\bblank(?:\s+unsaved)?\s+document\b[\s\S]{0,180}\bPrint Preview\b"
        ),
        "blank document creation only after confirmation": (
            r"\bblank(?:\s+unsaved)?\s+document\b[\s\S]{0,180}"
            r"\bonly after confirmation\b"
        ),
    }
    missing = [
        label
        for label, pattern in required_patterns.items()
        if not re.search(pattern, protocol, re.IGNORECASE)
    ]
    for parameter in ("printer", "orientation"):
        ask_first = (
            rf"(?:\b{parameter}\b[\s\S]{{0,160}}\b(?:missing|ambiguous)\b"
            rf"|\b(?:missing|ambiguous)\b[\s\S]{{0,160}}\b{parameter}\b)"
        )
        if not re.search(ask_first, protocol, re.IGNORECASE):
            missing.append(f"ask-first for missing/ambiguous {parameter}")
    assert not missing, f"{node_id} Word duplex prompt is missing: {missing}"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_result_format_uses_actual_fields_and_forbids_document_prose(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    assert "DUPLEX RESULT FORMAT" in prompt
    assert "do not discuss saving, closing, or printing" in prompt.casefold()
    assert "before/after.duplex" in prompt
    assert "verification, display, and screenshot separately" in prompt


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_mcp_action_scope_does_not_suppress_existing_hermes_office_routing(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    assert "does not change existing Hermes Office routing" in prompt
    assert "hermes_office_task still handles supported Office work and returns its own gate refusals" in prompt


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_confirmation_priority_prevents_redraft_on_plain_yes(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    assert "CONFIRMATION PRIORITY" in prompt
    assert 'yes, help to do it' in prompt
    assert "never draft again" in prompt
    assert "phase confirm" in prompt


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_confirms_only_stored_printer_and_orientation(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])
    start = prompt.find("action_id=word_printer_duplex")
    assert start >= 0, f"{node_id} lacks the Word duplex protocol"
    word_protocol = prompt[start : start + 4000]
    assert re.search(
        r"\bstored proposal(?:'s)?\b[\s\S]{0,250}\b(?:exact|confirmed)\b"
        r"[\s\S]{0,100}\bprinter\b[\s\S]{0,100}\borientation\b",
        word_protocol,
        re.IGNORECASE,
    ), f"{node_id} must bind confirmation to the stored printer and orientation"
    assert re.search(
        r"\bconfirm(?:ation)?\b[\s\S]{0,500}"
        r"(?:\bNO action_id/parameters\b|\bno action_id(?: or|/)? parameters\b"
        r"|\bwithout (?:action_id|parameters)\b)",
        word_protocol,
        re.IGNORECASE,
    ), f"{node_id} confirm must not accept replacement action parameters"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_forbids_document_actions_and_unsupported_offers(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])
    start = prompt.index("MCP-ACTION PROTOCOL (spec 047)")
    protocol = prompt[start : start + 7000]
    assert "word_printer_duplex" in protocol
    for claim_stem in ("content", "save", "close", "print"):
        assert re.search(
            rf"\b(?:never|do not|must not)\b[\s\S]{{0,100}}\bclaim(?:s|ed)?\b"
            rf"[\s\S]{{0,300}}\b{claim_stem}",
            protocol,
            re.IGNORECASE,
        ), f"{node_id} must forbid unsupported Word {claim_stem} claims"

    unsupported_office = re.search(
        r"(?:\bunsupported\b[\s\S]{0,250}\b(?:Office|Excel|PowerPoint|Outlook)\b"
        r"|\b(?:Office|Excel|PowerPoint|Outlook)\b[\s\S]{0,250}\bunsupported\b)"
        r"[\s\S]{0,250}\bmanual(?: steps)? only\b",
        protocol,
        re.IGNORECASE,
    )
    assert unsupported_office, (
        f"{node_id} must keep every unreviewed Office procedure manual-only"
    )
    unsupported_window = protocol[
        unsupported_office.start() : unsupported_office.start() + 700
    ]
    assert re.search(
        r"\bno\b[\s\S]{0,100}\bmcp_action\b", unsupported_window, re.IGNORECASE
    ), f"{node_id} unsupported Office procedures must not call mcp_action"
    assert re.search(
        r"\bno\b[\s\S]{0,100}\boffer\b", unsupported_window, re.IGNORECASE
    ), f"{node_id} unsupported Office procedures must not present the exact offer"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_word_duplex_prompt_skips_skill_search(graph: dict, node_id: str):
    prompt = _prompt(_nodes(graph)[node_id])
    assert "word_printer_duplex" in prompt
    assert re.search(
        r"\bmcp_action\b[\s\S]{0,100}\bdo not call skill_search\b",
        prompt,
        re.IGNORECASE,
    ), f"{node_id} Word duplex must not detour through the skill loop"


@pytest.mark.parametrize("lane", ("general", "hermes"))
@pytest.mark.parametrize("orientation", ("long-edge", "short-edge"))
def test_offline_honesty_allows_real_verified_word_result(
    graph: dict, lane: str, orientation: str
):
    code = _honesty_code(_nodes(graph))
    result = _word_execution_result(orientation=orientation)
    answer = (
        f"Duplex changed from OneSided to {result['requested_duplex']} on Printer B "
        f"for {orientation}. Verification: verified. Word Print Preview is open. "
        "Screenshot: captured.\n"
        f"![Word Print Preview]({result['screenshot']['image_url']})"
    )
    assert _run_honesty(code, answer, result, lane=lane) == answer


@pytest.mark.parametrize("answer", WORD_EXECUTION_CLAIMS + WORD_DISPLAY_CLAIMS)
def test_offline_honesty_rejects_word_claims_with_default_printer_evidence(
    graph: dict, answer: str
):
    result = _run_honesty(
        _honesty_code(_nodes(graph)), answer, _execution_result()
    )
    assert result.startswith("Honesty check:") and result != answer


@pytest.mark.parametrize("answer", WORD_DOCUMENT_ACTION_CLAIMS)
def test_offline_honesty_blocks_word_document_action_claims_without_evidence(
    graph: dict, answer: str
):
    result = _run_honesty(
        _honesty_code(_nodes(graph)), answer, _word_execution_result()
    )
    assert result.startswith("Honesty check:") and result != answer


@pytest.mark.parametrize("answer", WORD_DOCUMENT_ACTION_CLAIMS)
def test_offline_honesty_blocks_word_document_action_claims_without_any_tool(
    graph: dict, answer: str
):
    result = _run_honesty(_honesty_code(_nodes(graph)), answer, None)
    assert result.startswith("Honesty check:") and result != answer


def test_offline_honesty_preserves_evidenced_hermes_office_document_result(graph: dict):
    answer = "The Word document was saved."
    result = _run_honesty(
        _honesty_code(_nodes(graph)),
        answer,
        {"status": "ok", "changed": True},
        lane="hermes",
        tool_name="hermes_office_task",
    )
    assert result == answer


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-action-id",
        "wrong-action-id",
        "missing-requested-orientation",
        "orientation-mismatch",
        "requested-duplex-mismatch",
        "after-mismatch",
        "missing-before-duplex",
        "changed-flag-mismatch",
    ),
)
def test_offline_honesty_rejects_inconsistent_word_evidence(
    graph: dict, mutation: str
):
    result = _word_execution_result()
    if mutation == "missing-action-id":
        result.pop("action_id")
    elif mutation == "wrong-action-id":
        result["action_id"] = "windows_default_printer"
    elif mutation == "missing-requested-orientation":
        result.pop("orientation")
        result.pop("requested_duplex")
    elif mutation == "orientation-mismatch":
        result["orientation"] = "short-edge"
    elif mutation == "requested-duplex-mismatch":
        result["requested_duplex"] = "TwoSidedShortEdge"
    elif mutation == "after-mismatch":
        result["after"]["duplex"] = "TwoSidedShortEdge"
    elif mutation == "missing-before-duplex":
        result["before"] = {"printer": "Printer B"}
    elif mutation == "changed-flag-mismatch":
        result["changed"] = False

    answer = "Duplex was changed to long-edge."
    guarded = _run_honesty(_honesty_code(_nodes(graph)), answer, result)
    assert guarded.startswith("Honesty check:") and guarded != answer


def test_offline_honesty_rejects_word_result_for_default_printer_claim(graph: dict):
    answer = "I have changed the default printer to Printer B."
    result = _run_honesty(
        _honesty_code(_nodes(graph)), answer, _word_execution_result()
    )
    assert result.startswith("No verified default-printer change was completed.")
    assert result != answer


def test_offline_honesty_rejects_unverified_word_duplex(graph: dict):
    result = _word_execution_result("error")
    result["verification"] = "mismatch"
    result["display"] = {"status": "skipped"}
    result["screenshot"] = {"status": "skipped-display-unverified"}
    answer = "Duplex was changed to long-edge."
    guarded = _run_honesty(_honesty_code(_nodes(graph)), answer, result)
    assert guarded.startswith("Honesty check:") and guarded != answer


def test_offline_honesty_rejects_unverified_word_print_preview(graph: dict):
    result = _word_execution_result()
    result["display"] = {"status": "attempted-but-failed"}
    result["screenshot"] = {"status": "skipped-display-unverified"}
    answer = "Word Print Preview is open."
    guarded = _run_honesty(_honesty_code(_nodes(graph)), answer, result)
    assert guarded.startswith("Honesty check:") and guarded != answer


@pytest.mark.parametrize(
    "answer",
    (
        (
            "To show Print Preview manually, choose File > Print in Word. "
            "Do not save, close, or print the document."
        ),
        (
            "After you choose File > Print, Print Preview is open. "
            "These are manual steps."
        ),
        (
            "<think>Duplex was changed, Word Print Preview was displayed, and I saved "
            "the document.</think>The proposal is not executed yet; no setting was changed."
        ),
    ),
)
def test_offline_honesty_word_patterns_preserve_manual_conditional_and_hidden_text(
    graph: dict, answer: str
):
    assert _run_honesty(_honesty_code(_nodes(graph)), answer, None) == answer


HEALTH_URL = "http://sidecar:8080/mcp-action/reports/" + "H" * 43
HEALTH_FORGED_URL = "http://sidecar:8080/mcp-action/reports/" + "X" * 43
HEALTH_SHOT_URL = "http://sidecar:8080/mcp-action/screenshots/" + "I" * 43
HEALTH_COUNTS = {"pass": 8, "warn": 3, "fail": 1, "info": 2, "skip": 2}


def _health_execution_result(
    *,
    health_status: str = "warn",
    score: int = 72,
    report_status: str = "published",
    display_status: str = "displayed",
    screenshot_status: str = "captured",
    report_html: str = "",
) -> dict:
    report = {
        "status": report_status,
        "expires_in_s": 900,
        "host_path": r"C:\Users\Test\AppData\Local\Temp\selfcheck.html",
        "host_path_status": "written",
    }
    if report_status == "published":
        report["report_url"] = HEALTH_URL
    if report_html:
        report["html"] = report_html
    result = {
        "status": "ok",
        "action_id": "system_health_check",
        "changed": False,
        "verification": "reported",
        "health": {
            "status": health_status,
            "score": score,
            "counts": dict(HEALTH_COUNTS),
            "confidence": "reduced",
        },
        "report": report,
        "display": {"status": display_status},
        "screenshot": {"status": screenshot_status},
        "helpdesk": "Disk and Reliability need review; HelpDesk can help with repairs.",
    }
    if screenshot_status == "captured":
        result["screenshot"]["image_url"] = HEALTH_SHOT_URL
    return result


def test_health_check_protocol_is_present_only_in_approved_lanes(graph: dict):
    nodes = _nodes(graph)
    for node_id in MCP_ACTION_AGENTS:
        prompt = _prompt(nodes[node_id])
        assert "system_health_check" in prompt, (
            f"{node_id} must expose the reviewed system health check"
        )
        assert re.search(r"\bReliability Monitor\b", prompt, re.IGNORECASE)
        assert re.search(r"\bread[- ]only\b", prompt, re.IGNORECASE)

    for node_id in MCP_ACTION_EXCLUDED_AGENTS:
        serialized = yaml.safe_dump(nodes[node_id]).lower()
        assert "system_health_check" not in serialized
        assert "mcp-action/reports" not in serialized
        assert "reliability monitor" not in serialized


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_health_check_prompt_limits_eligibility_and_asks_first(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])

    assert re.search(
        r"\b(?:freez(?:e|es|ing)?|hang(?:s|ing)?|crash(?:es|ing)?|"
        r"bsod|blue screen|unstable|instability)\b",
        prompt,
        re.IGNORECASE,
    ), "health help must be scoped to Windows instability symptoms"
    assert re.search(
        r"\b(?:explicit|direct)(?:ly)?\b[\s\S]{0,120}\b(?:system )?health check\b"
        r"|\brun a system health check\b",
        prompt,
        re.IGNORECASE,
    ), "explicit health-check requests must be eligible"
    assert re.search(
        r"\b(?:one|two|1|2)\b[\s\S]{0,100}\b(?:targeted )?questions?\b",
        prompt,
        re.IGNORECASE,
    ), "missing symptom context must trigger targeted questions"
    assert re.search(
        r"\b(?:end|stop)\b[\s\S]{0,80}\b(?:that |the )?(?:turn|reply)\b"
        r"[\s\S]{0,140}\b(?:no|without|not)\b[\s\S]{0,60}"
        r"\b(?:run|draft|execute|check)\b",
        prompt,
        re.IGNORECASE,
    ), "an ask-back turn must not run or draft the health check"
    assert re.search(
        r"\b(?:out[- ]of[- ]scope|outside|not eligible|ineligible)\b"
        r"[\s\S]{0,220}\b(?:no|never|do not)\b[\s\S]{0,80}\boffer\b",
        prompt,
        re.IGNORECASE,
    ), "out-of-scope requests must not receive the health offer"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_health_check_prompt_uses_no_parameters_and_the_exact_offer(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])

    assert "action_id=system_health_check" in prompt
    assert re.search(r"parameters\s*=\s*\{\s*\}", prompt), (
        f"{node_id} health draft must use an empty parameter object"
    )
    assert re.search(
        r"\b(?:no|never|must not|do not)\b[\s\S]{0,120}"
        r"\b(?:parameters|printer|orientation|logging|event window)\b",
        prompt,
        re.IGNORECASE,
    ), "health must not accept or ask for diagnostic parameters"
    assert OFFER in prompt
    assert re.search(
        re.escape(OFFER) + r"[\s\S]{0,80}\b(?:final paragraph|standalone)\b"
        r"|\b(?:final paragraph|standalone)\b[\s\S]{0,120}" + re.escape(OFFER),
        prompt,
        re.IGNORECASE,
    ), "the offer must remain the standalone final paragraph"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_health_check_prompt_overrides_automatic_helpdesk_routing(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])

    assert re.search(
        r"\bhealth(?:[- ]check)?\b[\s\S]{0,600}"
        r"\b(?:override|overrides|do not|never|does not apply)\b"
        r"[\s\S]{0,300}\btask_helpdesk_tier[12]\b",
        prompt,
        re.IGNORECASE,
    ), "a health turn must override the ordinary automatic HelpDesk routing"
    assert re.search(
        r"\bHelpDesk\b[\s\S]{0,150}"
        r"\b(?:guidance[- ]only|only guidance|can help with repairs)\b",
        prompt,
        re.IGNORECASE,
    ), "repairs must remain HelpDesk guidance only"
    assert re.search(
        r"\b(?:never|do not|no)\b[\s\S]{0,150}"
        r"\b(?:automatic )?(?:ticket|repair request|task_helpdesk)\b",
        prompt,
        re.IGNORECASE,
    ), "health must never create a ticket, repair, or HelpDesk task"
    assert re.search(
        r"\b(?:later|subsequent|explicit repair request|separate repair)\b"
        r"[\s\S]{0,300}\brepair\b[\s\S]{0,300}"
        r"\b(?:normal|ordinary|existing)\b",
        prompt,
        re.IGNORECASE,
    ), "a later explicit repair request must still use normal HelpDesk routing"


@pytest.mark.parametrize("node_id", MCP_ACTION_AGENTS)
def test_health_check_prompt_requires_real_report_link_evidence(
    graph: dict, node_id: str
):
    prompt = _prompt(_nodes(graph)[node_id])

    assert "/mcp-action/reports/" in prompt
    assert re.search(r"\b43\b", prompt), "the report token grammar must be documented"
    assert re.search(
        r"report\.status[\s\S]{0,100}\bpublished\b", prompt, re.IGNORECASE
    ), "the report link requires a published report result"
    assert re.search(
        r"\bappend\b[\s\S]{0,150}\b(?:once|link|report)\b",
        prompt,
        re.IGNORECASE,
    ), "a published report link omitted from the answer must be appended once"
    assert re.search(
        r"\b(?:full|complete)\b[\s\S]{0,100}\bhtml report\b", prompt, re.IGNORECASE
    ), "the full HTML report must be returned, not summarized away"
    assert re.search(r"report\.host_path", prompt), "the saved report path must be the visible reference"
    assert re.search(
        r"do not include any /mcp-action/reports/ URL", prompt, re.IGNORECASE
    ), "the temporary URL must not be presented when the host file is written"
    assert re.search(
        r"\b(?:never|do not)\b[\s\S]{0,150}"
        r"\b(?:fabricate|forge|invent|make up)\b[\s\S]{0,120}"
        r"\b(?:report|score|display|count)\b",
        prompt,
        re.IGNORECASE,
    ), "health report, score, and display claims must be evidence-bound"


def test_health_honesty_guard_tracks_real_health_evidence(graph: dict):
    code = _honesty_code(_nodes(graph))

    assert "system_health_check" in code
    assert "/mcp-action/reports/" in code
    assert re.search(
        r"\breport\.status\s*===?\s*['\"]published['\"]", code
    ), "a report URL must require report.status == published"
    assert re.search(r"\bhealth\.status\b", code)
    assert re.search(r"\b(?:score|counts)\b", code)
    assert re.search(
        r"\bdisplay\.status\s*===?\s*['\"]displayed['\"]", code
    ), "Reliability Monitor claims require real display evidence"
    assert re.search(
        r"\bscreenshot\.status\s*===?\s*['\"]captured['\"]", code
    ), "screenshot claims require real capture evidence"


def test_offline_honesty_inserts_health_wait_notice_before_offer(graph: dict):
    code = _honesty_code(_nodes(graph))
    notice = (
        "Please wait about 2-5 minutes and do not use the keyboard or mouse "
        "during System-Self-Check is running\nuntil the report is finished"
    )
    result = {
        "status": "pending-confirmation",
        "action_id": "system_health_check",
        "offer": "Do you want me to do it automatically for you?",
        "notice": notice,
    }
    answer = (
        "Manual diagnostic steps.\n\n"
        "Do you want me to do it automatically for you?"
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.count(notice) == 1
    assert guarded.index(notice) < guarded.index(
        "Do you want me to do it automatically for you?"
    )
    assert guarded.rstrip().endswith(
        "Do you want me to do it automatically for you?"
    )


def test_offline_honesty_appends_a_missing_report_file_path(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result()
    answer = (
        "Overall: WARN (score 72). Disk and Reliability need attention; "
        "HelpDesk can help with repairs. Reliability Monitor is open. "
        "Screenshot: captured.\n"
        f"![Reliability Monitor]({HEALTH_SHOT_URL})"
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert guarded.count(r"C:\Users\Test\AppData\Local\Temp\selfcheck.html") == 1
    assert HEALTH_URL not in guarded


def test_offline_honesty_accepts_warn_overall_with_count_labels(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result()
    answer = (
        "Overall health: WARN. Score: 72. Pass: 8, Warn: 3, Fail: 1, "
        "Info: 2, Skip: 2. Disk and Reliability need review; HelpDesk can "
        "help with repairs. Reliability Monitor is open. Screenshot: captured."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert guarded.count(r"C:\Users\Test\AppData\Local\Temp\selfcheck.html") == 1
    assert HEALTH_URL not in guarded


def test_offline_honesty_accepts_fail_overall_with_count_labels(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result(health_status="fail", score=55)
    answer = (
        "Overall health: FAIL. Score: 55. Pass: 5, Warn: 2, Fail: 2, "
        "Info: 1, Skip: 1. Disk needs attention; HelpDesk can help with repairs."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert guarded.count(r"C:\Users\Test\AppData\Local\Temp\selfcheck.html") == 1
    assert HEALTH_URL not in guarded


def test_offline_honesty_blocks_a_false_pass_claim_with_count_labels(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result()
    answer = (
        "Overall health: PASS. Score: 72. Pass: 8, Warn: 3, Fail: 1. "
        "HelpDesk can help with repairs."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded != answer
    assert "did not match" in guarded
    assert HEALTH_URL not in guarded


def test_offline_honesty_appends_the_full_html_report_verbatim(graph: dict):
    code = _honesty_code(_nodes(graph))
    report_html = (
        "<!DOCTYPE html><html><head><title>Desktop Self-Check</title></head>"
        "<body><h1>Overall: WARN - score 70/100</h1><table><tr><td>C:</td>"
        "<td>206.7 GB free</td></tr></table></body></html>"
    )
    result = _health_execution_result(report_html=report_html)
    answer = (
        "Overall health: WARN. Score: 72. Pass: 8, Warn: 3, Fail: 1. "
        "HelpDesk can help with repairs."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert guarded.count(report_html) == 1
    assert r"C:\Users\Test\AppData\Local\Temp\selfcheck.html" in guarded
    assert HEALTH_URL not in guarded
    assert guarded.rstrip().endswith(
        "System-Self-Check finished — the complete report is above."
    )


def test_offline_honesty_allows_negated_repair_statement_with_full_report(graph: dict):
    code = _honesty_code(_nodes(graph))
    report_html = "<!DOCTYPE html><html><body><h1>Desktop Self-Check</h1></body></html>"
    result = _health_execution_result(report_html=report_html)
    answer = (
        "Overall health: WARN. Score: 72. HelpDesk can help with repairs. "
        "No repair was performed."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert report_html in guarded
    assert r"C:\Users\Test\AppData\Local\Temp\selfcheck.html" in guarded


def test_offline_honesty_does_not_guess_an_ambiguous_overall_status(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result()
    answer = (
        "Overall: 8 pass, 3 warn, 1 fail. Score: 72. "
        "HelpDesk can help with repairs."
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded.startswith(answer)
    assert guarded.count(r"C:\Users\Test\AppData\Local\Temp\selfcheck.html") == 1
    assert HEALTH_URL not in guarded


def test_offline_honesty_blocks_a_forged_health_report_url(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result()
    answer = (
        "Overall: WARN (score 72).\n"
        f"[Open the system health report]({HEALTH_FORGED_URL})"
    )

    guarded = _run_honesty(code, answer, result)

    assert guarded != answer
    assert HEALTH_FORGED_URL not in guarded
    assert HEALTH_URL not in guarded
    assert r"C:\Users\Test\AppData\Local\Temp\selfcheck.html" in guarded


def test_offline_honesty_blocks_a_report_url_when_publication_failed(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result(report_status="failed")
    answer = f"[Open the system health report]({HEALTH_URL})"

    guarded = _run_honesty(code, answer, result)

    assert guarded != answer
    assert HEALTH_URL not in guarded
    assert r"C:\Users\Test\AppData\Local\Temp\selfcheck.html" in guarded


def test_offline_honesty_blocks_fabricated_health_score_and_display(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result(
        display_status="unverified", screenshot_status="skipped-display-unverified"
    )
    answer = "Overall health: PASS, score 100. Reliability Monitor is open."

    guarded = _run_honesty(code, answer, result)

    assert guarded != answer
    assert "score 100" not in guarded.casefold()
    assert "reliability monitor is open" not in guarded.casefold()


def test_offline_honesty_blocks_health_repair_and_helpdesk_ticket_claims(graph: dict):
    code = _honesty_code(_nodes(graph))
    result = _health_execution_result(health_status="fail", score=55)
    answer = "I created a HelpDesk ticket and repaired the disk."

    guarded = _run_honesty(code, answer, result)

    assert guarded != answer
    assert "created a helpdesk ticket" not in guarded.casefold()
    assert "repaired the disk" not in guarded.casefold()
