"""Spec 026: apply a cloud LLM to the chatflow — export → patch → overwrite → publish.

Owner decision 2026-11-13 ("lift the pins"): the UI-selected cloud model applies
to ALL four LLM nodes (intent_router, agentic_strategy, ppt_master,
hermes_agent) — no model pins anywhere. The 2026-11-05 fabrication incident
(office lane narrating a plan and fabricating "email sent" with no tool call
on a blanket deepseek swap) is now defended STRUCTURALLY — honesty_check,
dispatch-leak detector, REPLACED: attestation, read-back verify — so the gates,
not the model, are the defense. Each apply is validated by the live battery on
the chosen model. The cycle still reconfigures the published app itself
(contracts §4): published untouched until the publish step; any failure leaves
the previous configuration serving (FR-004).
"""

from __future__ import annotations

import os
import re

import yaml

from .config import REPO_ROOT
from .dify_console import DifyConsole

CLOUD_PROVIDER = "langgenius/openrouter/openrouter"
# Owner decision 2026-11-13 ("lift the pins"): the UI selection applies
# to ALL nodes — no model pins anywhere. The 2026-11-05 fabrication
# incident is now guarded structurally (honesty_check, dispatch-leak
# detector, REPLACED: attestation, read-back verify) — the gates, not
# the model, are the defense; each apply is verified by a live
# battery on the chosen model.
DEFAULT_CHAT_MODEL = "deepseek/deepseek-v4.1-flash"
ALL_NODE_IDS = ("intent_router", "agentic_strategy", "ppt_master", "hermes_agent")
# kept for backward-compatible imports/tests
PINNED_MODEL = DEFAULT_CHAT_MODEL
ROUTER_MODEL = DEFAULT_CHAT_MODEL
CHAT_NODE_IDS = ALL_NODE_IDS
DESKTOP_NODE_IDS = ("ppt_master", "hermes_agent")
MAIN_NODE_IDS = ALL_NODE_IDS
START_NODE_ID = "1776072202913"
REMOVE_NODE_SUFFIXES = ("_kimi", "_glm", "_qwen38")
REMOVE_CASE_IDS = {"kimi", "glm", "qwen38"}
REMOVE_REF_RE = re.compile(
    r"\{\{#[^}]*?(?:_kimi|_glm|_qwen38)\.text#\}\}"
)
ARTIFACT = os.path.join(REPO_ROOT, "dify", "AGIAssistant", "AGI_Assistant.yml")


def _model_block(model_id: str) -> dict:
    return {
        "completion_params": {},
        "mode": "chat",
        "model": model_id,
        "model_type": "llm",
        "name": model_id,
        "provider": CLOUD_PROVIDER,
        "type": "model-selector",
    }


def strip_null_variable_params(doc: dict) -> None:
    """Bug fix ppt-no-response (2026-10-29): agent params exported as
    {"type": "variable", "value": None} carry a null variable selector —
    Dify 1.18's variable_pool.get(None) raises len(None) and kills the node
    before any LLM/tool call (PPT-Master failed in 59 ms). Bare nulls are
    equally invalid (AgentNodeData validation). The runnable shape — proven
    by the pre-026 export — is the key ABSENT entirely. Real selectors
    (non-empty lists) pass through untouched.
    """
    for n in doc["workflow"]["graph"]["nodes"]:
        params = (n.get("data") or {}).get("agent_parameters")
        if not isinstance(params, dict):
            continue
        for key in [k for k, v in params.items()
                    if isinstance(v, dict) and v.get("type") == "variable"
                    and not v.get("value")]:
            del params[key]
        for key in ("allowed_tools", "context", "files"):
            if key in params and params[key] is None:
                del params[key]


def patch_dsl(yaml_text: str, model_id: str) -> str:
    """Assign node models + idempotent FR-005 cleanup.

    CHAT nodes (intent_router, agentic_strategy) take `model_id`
    (default DEFAULT_CHAT_MODEL); DESKTOP nodes (ppt_master, hermes_agent)
    stay pinned to PINNED_MODEL (2026-11-05 incident). Owner decision
    2026-11-12: "Chat answers + UI chip only".
    """
    doc = yaml.safe_load(yaml_text)
    graph = doc["workflow"]["graph"]
    nodes, edges = graph["nodes"], graph["edges"]
    by_id = {n["id"]: n for n in nodes}

    chat_model = model_id or DEFAULT_CHAT_MODEL
    per_node = {nid: chat_model for nid in ALL_NODE_IDS}
    for nid, chosen in per_node.items():
        if nid not in by_id:
            raise ValueError(f"main node missing from DSL: {nid}")
        n = by_id[nid]
        block = _model_block(chosen)
        if n["data"]["type"] == "question-classifier":
            n["data"]["model"] = block
        else:
            n["data"]["agent_parameters"]["model"]["value"] = block

    # FR-005: remove routing-era branches, their edges, router cases, and the
    # cloud_model start variable (no-op when already clean).
    remove_ids = {
        n["id"] for n in nodes
        if any(n["id"].endswith(suffix) for suffix in REMOVE_NODE_SUFFIXES)
    }
    if remove_ids:
        graph["nodes"] = [n for n in nodes if n["id"] not in remove_ids]
        edges[:] = [
            e for e in edges
            if e["source"] not in remove_ids and e["target"] not in remove_ids
        ]
    router = by_id.get("model_router")
    if router and "cases" in router["data"]:
        router["data"]["cases"] = [
            c for c in router["data"]["cases"]
            if c["case_id"] not in REMOVE_CASE_IDS
        ]
    start = by_id.get(START_NODE_ID)
    if start and "variables" in start["data"]:
        start["data"]["variables"] = [
            v for v in start["data"]["variables"] if v["variable"] != "cloud_model"
        ]

    # FR-005 (convergence T019): strip the removed nodes' template references
    # from the shared answer nodes — dangling refs must not survive cleanup.
    for nid in ("answer", "ppt_answer"):
        n = by_id.get(nid)
        if n and isinstance(n["data"].get("answer"), str):
            n["data"]["answer"] = REMOVE_REF_RE.sub("", n["data"]["answer"])

    # ppt-no-response: exports can materialize null variable selectors
    # ({"type": "variable", "value": None}) on agent nodes — normalize so
    # every apply cycle leaves the DSL in the runnable shape.
    strip_null_variable_params(doc)

    return yaml.dump(doc, sort_keys=False, allow_unicode=True, width=1000)


def apply_model(dcfg, report, model_id: str) -> None:
    console = DifyConsole(dcfg)
    console.login()
    report.add("console-login", evidence="ok")

    app = console.find_app(dcfg.app_name)
    yaml_text = console.export_app(app["id"])
    report.add("export", evidence=f"{len(yaml_text)} bytes")

    patched = patch_dsl(yaml_text, model_id)
    with open(ARTIFACT, "w", encoding="utf-8") as f:
        f.write(patched)
    report.add(
        "patch",
        evidence=(
            f"all nodes {', '.join(ALL_NODE_IDS)} = "
            f"{model_id or DEFAULT_CHAT_MODEL} (pins lifted, owner "
            f"2026-11-13) → {os.path.relpath(ARTIFACT, REPO_ROOT)}"
        ),
    )

    console.update_workflow_draft(app["id"], yaml.safe_load(patched)["workflow"])
    report.add("overwrite", evidence="draft replaced (published app untouched)")

    console.publish(app["id"])
    report.add("publish",
               evidence=(f"all nodes={model_id or DEFAULT_CHAT_MODEL} "
                         f"(no pins)"))
