"""Unit: deploy model_apply patch function (spec 026, FR-001/FR-005)."""

from __future__ import annotations

import pytest
import yaml

from agentic_rag_mcp.deploy.model_apply import CLOUD_PROVIDER, PINNED_MODEL, patch_dsl

MINIMAL_DSL = """
app:
  name: AGI Assistant
kind: app
workflow:
  graph:
    nodes:
    - data:
        type: start
        title: User Input
        variables:
        - variable: ai_model
        - variable: cloud_model
      id: '1776072202913'
    - data:
        cases:
        - case_id: 'true'
          conditions: []
        - case_id: kimi
          conditions: []
        - case_id: glm
          conditions: []
        - case_id: qwen38
          conditions: []
        type: if-else
        title: AI LLM Router
      id: model_router
    - data:
        model:
          completion_params: {}
          mode: chat
          model: deepseek/deepseek-v4.1-flash
          model_type: llm
          name: deepseek/deepseek-v4.1-flash
          provider: langgenius/openrouter/openrouter
          type: model-selector
        type: question-classifier
        title: PPT or General?
      id: intent_router
    - data:
        agent_parameters:
          model:
            value:
              completion_params: {}
              mode: chat
              model: deepseek/deepseek-v4.1-flash
              model_type: llm
              name: deepseek/deepseek-v4.1-flash
              provider: langgenius/openrouter/openrouter
              type: model-selector
        type: agent
        title: Agentic Strategy
      id: agentic_strategy
    - data:
        agent_parameters:
          model:
            value:
              completion_params: {}
              mode: chat
              model: deepseek/deepseek-v4.1-flash
              model_type: llm
              name: deepseek/deepseek-v4.1-flash
              provider: langgenius/openrouter/openrouter
              type: model-selector
        type: agent
        title: PPT-Master
      id: ppt_master
    - data:
        agent_parameters:
          model:
            value:
              completion_params: {}
              mode: chat
              model: moonshotai/kimi-k3
              model_type: llm
              name: moonshotai/kimi-k3
              provider: langgenius/openrouter/openrouter
              type: model-selector
        type: agent
        title: Hermes File Agent
      id: hermes_agent
    - data:
        model:
          completion_params: {think: false}
          mode: chat
          model: qwen3-8b-nothink
          model_type: llm
          name: qwen3-8b-nothink
          provider: langgenius/ollama/ollama
          type: model-selector
        type: question-classifier
        title: PPT or General? (Local)
      id: intent_router_local
    - data:
        model:
          completion_params: {}
          mode: chat
          model: moonshotai/kimi-k3
          model_type: llm
          name: moonshotai/kimi-k3
          provider: langgenius/openrouter/openrouter
          type: model-selector
        type: question-classifier
        title: PPT or General? (kimi)
      id: intent_router_kimi
    - data:
        type: answer
        answer: '{{#agentic_strategy.text#}}{{#agentic_strategy_local.text#}}{{#agentic_strategy_kimi.text#}}{{#agentic_strategy_glm.text#}}'
      id: answer
    - data:
        type: answer
        answer: '{{#ppt_master.text#}}{{#ppt_master_kimi.text#}}{{#ppt_master_qwen38.text#}}'
      id: ppt_answer
    edges:
    - id: e1
      source: model_router
      sourceHandle: kimi
      target: intent_router_kimi
    - id: e2
      source: intent_router_kimi
      sourceHandle: source
      target: answer
    - id: e3
      source: intent_router
      sourceHandle: general
      target: agentic_strategy
"""

NEW_MODEL = "moonshotai/kimi-k3"


def test_pins_the_four_lane_nodes_regardless_of_selection():
    """not-saved-in-outlook-drafts-folder-and-not-send-email (2026-11-05):
    the lane nodes are pinned to kimi-k3 — the requested model (dropdown or
    CLI) must be ignored, or a blanket swap re-introduces the fabrication."""
    doc = yaml.safe_load(patch_dsl(MINIMAL_DSL, "deepseek/deepseek-v4.1-flash"))
    by_id = {n["id"]: n for n in doc["workflow"]["graph"]["nodes"]}
    for nid, get_block in (
        ("intent_router", lambda n: n["data"]["model"]),
        ("agentic_strategy", lambda n: n["data"]["agent_parameters"]["model"]["value"]),
        ("ppt_master", lambda n: n["data"]["agent_parameters"]["model"]["value"]),
        ("hermes_agent", lambda n: n["data"]["agent_parameters"]["model"]["value"]),
    ):
        block = get_block(by_id[nid])
        assert block["model"] == NEW_MODEL
        assert block["name"] == NEW_MODEL
        assert block["provider"] == CLOUD_PROVIDER
        assert block["mode"] == "chat"
        assert block["completion_params"] == {}
    local_block = by_id["intent_router_local"]["data"]["model"]
    assert local_block["model"] == "qwen3-8b-nothink"
    assert local_block["provider"] == "langgenius/ollama/ollama"
    assert local_block["completion_params"] == {"think": False}


def test_cleanup_removes_routing_era_branches_cases_and_input():
    doc = yaml.safe_load(patch_dsl(MINIMAL_DSL, NEW_MODEL))
    graph = doc["workflow"]["graph"]
    ids = {n["id"] for n in graph["nodes"]}
    assert "intent_router_kimi" not in ids
    edge_ids = {e["id"] for e in graph["edges"]}
    assert "e1" not in edge_ids and "e2" not in edge_ids
    router = next(n for n in graph["nodes"] if n["id"] == "model_router")
    assert [c["case_id"] for c in router["data"]["cases"]] == ["true"]
    start = next(n for n in graph["nodes"] if n["id"] == "1776072202913")
    assert [v["variable"] for v in start["data"]["variables"]] == ["ai_model"]


def test_cleanup_strips_removed_node_refs_from_answer_templates():
    doc = yaml.safe_load(patch_dsl(MINIMAL_DSL, NEW_MODEL))
    by_id = {n["id"]: n for n in doc["workflow"]["graph"]["nodes"]}
    assert (
        by_id["answer"]["data"]["answer"]
        == "{{#agentic_strategy.text#}}{{#agentic_strategy_local.text#}}"
    )
    assert by_id["ppt_answer"]["data"]["answer"] == "{{#ppt_master.text#}}"


def test_idempotent_second_run_is_noop():
    once = patch_dsl(MINIMAL_DSL, NEW_MODEL)
    assert patch_dsl(once, NEW_MODEL) == once


def test_missing_main_node_raises_honestly():
    broken = MINIMAL_DSL.replace("    id: intent_router\n", "    id: renamed_router\n")
    with pytest.raises(ValueError, match="intent_router"):
        patch_dsl(broken, NEW_MODEL)


def test_strips_null_variable_selectors_from_agent_params():
    """ppt-no-response (2026-10-29): {"type": "variable", "value": None} params
    crash Dify 1.18's variable_pool.get(None) with len(None) before any
    LLM/tool call; bare nulls fail AgentNodeData validation. patch_dsl must
    leave the keys absent (the shape that ran before spec 026), while real
    variable selectors pass through untouched."""
    doc = yaml.safe_load(MINIMAL_DSL)
    ppt = next(n for n in doc["workflow"]["graph"]["nodes"] if n["id"] == "ppt_master")
    ap = ppt["data"]["agent_parameters"]
    for k in ("allowed_tools", "context", "files"):
        ap[k] = {"type": "variable", "value": None}
    ap["files_keep"] = {"type": "variable", "value": ["sys", "files"]}

    patched = yaml.safe_load(patch_dsl(yaml.dump(doc), NEW_MODEL))
    out = next(
        n for n in patched["workflow"]["graph"]["nodes"] if n["id"] == "ppt_master"
    )["data"]["agent_parameters"]

    for k in ("allowed_tools", "context", "files"):
        assert k not in out, f"{k} must be absent, not a null variable selector"
    assert out["files_keep"] == {"type": "variable", "value": ["sys", "files"]}
    assert out["model"]["value"]["model"] == NEW_MODEL


def test_strips_bare_null_agent_params_to_absent():
    """Bare nulls are equally invalid at AgentNodeData validation — the
    runnable shape is the key absent entirely."""
    doc = yaml.safe_load(MINIMAL_DSL)
    ppt = next(n for n in doc["workflow"]["graph"]["nodes"] if n["id"] == "ppt_master")
    for k in ("allowed_tools", "context", "files"):
        ppt["data"]["agent_parameters"][k] = None

    patched = yaml.safe_load(patch_dsl(yaml.dump(doc), NEW_MODEL))
    out = next(
        n for n in patched["workflow"]["graph"]["nodes"] if n["id"] == "ppt_master"
    )["data"]["agent_parameters"]
    for k in ("allowed_tools", "context", "files"):
        assert k not in out
