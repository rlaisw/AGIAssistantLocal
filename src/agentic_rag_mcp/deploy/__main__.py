"""CLI: python -m agentic_rag_mcp.deploy {redeploy|chatflow|verify|all} [--dry-run] (spec 011)."""

from __future__ import annotations

import argparse
import sys

import yaml

from . import docker_ops, host_assets, tool_sync
from .battery import run_battery
from .config import ConfigError, DeployConfig, resolve
from .report import RunReport


def echo_config(dcfg: DeployConfig) -> None:
    safe = (f"console_url={dcfg.console_url} "
            f"console_email={dcfg.console_email or '<unset>'} "
            f"console_password={'***' if dcfg.console_password else '<unset>'} "
            f"api_key={'***' if dcfg.api_key else '<unset>'} "
            f"image={dcfg.sidecar_image} container={dcfg.container}")
    print(f"config: {safe}", flush=True)


def cmd_redeploy(dcfg: DeployConfig, dry: bool) -> int:
    report = RunReport()
    report.configure(dcfg)
    plan = ["stage health script", "build image", "recreate container", "wait health",
            "ensure MCP registration", "re-sync tool cache"]
    if dry:
        print("dry-run plan (redeploy):")
        for p in plan:
            print(f"  - {p}")
        return 0
    try:
        host_assets.stage_health_script(report)
        docker_ops.build_image(dcfg.sidecar_image, report)
        docker_ops.recreate_container(dcfg.container, dcfg.sidecar_image, report)
        if not docker_ops.wait_health():
            report.add("health-wait", "failed",
                       evidence="sidecar did not become healthy in 120s")
            print(report.summary(dcfg))
            return 1
        report.add("health-wait", evidence="ok")
        tool_sync.sync_provider(dcfg, report)
    except host_assets.HostAssetError:
        print(report.summary(dcfg))
        return 1
    except Exception as exc:  # noqa: BLE001 — honest failure boundary
        report.add("redeploy", "failed", evidence=str(exc))
        print(report.summary(dcfg))
        return 1
    print(report.summary(dcfg))
    return report.exit_code()


def cmd_chatflow(dcfg: DeployConfig, dry: bool) -> int:
    from .dify_console import ConsoleError, DifyConsole

    report = RunReport()
    report.configure(dcfg)
    if dry:
        print("dry-run plan (chatflow):")
        print(f"  - login to {dcfg.console_url}")
        print(f"  - find or import app '{dcfg.app_name}' from {dcfg.dsl_path}")
        print("  - update workflow draft (in place) when the app exists")
        print("  - publish")
        return 0
    try:
        dcfg.require_console()
        with open(dcfg.dsl_path, encoding="utf-8") as f:
            dsl = yaml.safe_load(f)
        console = DifyConsole(dcfg)
        console.login()
        report.add("console-login", evidence="ok")
        app = console.find_app(dcfg.app_name)
        if app:
            console.update_workflow_draft(app["id"], dsl.get("workflow", {}))
            report.add("chatflow-update", evidence=f"draft updated in place (app {app['id'][:8]})")
            app_id = app["id"]
        else:
            with open(dcfg.dsl_path, encoding="utf-8") as f:
                app_id = console.import_app(f.read())
            report.add("chatflow-import", evidence=f"imported as app {app_id[:8]}")
        console.publish(app_id)
        report.add("chatflow-publish", evidence="published")
    except (ConfigError, ConsoleError, FileNotFoundError, OSError) as exc:
        report.add("chatflow", "failed", evidence=str(exc))
        print(report.summary(dcfg))
        return 2 if isinstance(exc, ConfigError) else 1
    print(report.summary(dcfg))
    return report.exit_code()


def cmd_models(dcfg: DeployConfig, dry: bool) -> int:
    from . import model_setup

    report = RunReport()
    report.configure(dcfg)
    if dry:
        print("dry-run plan (models):")
        print("  - install marketplace Ollama plugin if absent")
        print(f"  - save provider credential (base_url={dcfg.ollama_base_url})")
        print(f"  - register model {dcfg.ollama_model} as a custom LLM")
        return 0
    try:
        dcfg.require_console()
        model_setup.setup_models(dcfg, report)
    except Exception as exc:  # noqa: BLE001 — honest failure boundary
        report.add("models", "failed", evidence=str(exc))
        print(report.summary(dcfg))
        return 1 if not isinstance(exc, ConfigError) else 2
    print(report.summary(dcfg))
    return report.exit_code()


CLOUD_MODEL_IDS = (
    "deepseek/deepseek-v4.1-flash",
    "moonshotai/kimi-k3",
    "z-ai/glm-5.3-flash",
    "qwen/qwen3.8-flash",
)


def cmd_apply_model(dcfg: DeployConfig, model_id: str | None, dry: bool) -> int:
    from . import model_apply

    if not model_id:
        print("error: apply-model requires a cloud model id")
        print("valid:", ", ".join(CLOUD_MODEL_IDS))
        return 2
    if model_id not in CLOUD_MODEL_IDS:
        print(f"error: unknown cloud model id: {model_id}")
        print("valid:", ", ".join(CLOUD_MODEL_IDS))
        return 2
    report = RunReport()
    report.configure(dcfg)
    if dry:
        print(f"dry-run plan (apply-model {model_id}):")
        print("  - export the AGI Assistant app to dify/AGIAssistant/AGI_Assistant.yml")
        print(f"  - patch the three main LLM nodes to {model_id} (+ idempotent cleanup)")
        print("  - overwrite the app draft (published app untouched until publish)")
        print("  - publish")
        return 0
    try:
        dcfg.require_console()
        model_apply.apply_model(dcfg, report, model_id)
    except Exception as exc:  # noqa: BLE001 — honest failure boundary
        report.add("apply-model", "failed", evidence=str(exc))
        print(report.summary(dcfg))
        return 1 if not isinstance(exc, ConfigError) else 2
    print(report.summary(dcfg))
    return report.exit_code()


def cmd_verify(dcfg: DeployConfig, dry: bool, skip_chat: bool = False) -> int:
    if dry:
        print("dry-run plan (verify): run the battery scenarios headlessly,")
        print("  unique verify_<ts> projects, teardown sweep, exit = failure count")
        return 0
    results, cleanup = run_battery(dcfg, skip_chat=skip_chat)
    failed = [name for name, ok, _ in results if not ok]
    for note in cleanup:
        print(f"[i] {note}")
    print(f"summary: {len(results) - len(failed)}/{len(results)} passed"
          + (f", failed: {', '.join(failed)}" if failed else ""))
    return len(failed)


def cmd_cleanup(dcfg: DeployConfig, dry: bool, retention_days: int | None) -> int:
    from .battery import prune_old_projects

    days = retention_days if retention_days is not None else dcfg.retention_days
    if dry:
        would = prune_old_projects(days, dry=True)
        print(f"dry-run plan (cleanup, retention {days}d): "
              f"{len(would)} project(s) would be removed")
        for name in would:
            print(f"  - {name}")
        return 0
    removed = prune_old_projects(days)
    print(f"cleanup: removed {len(removed)} project(s) older than {days} day(s)"
          + (f": {', '.join(removed)}" if removed else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentic-rag-deploy")
    parser.add_argument("command",
                         choices=["redeploy", "chatflow", "models", "apply-model", "verify", "cleanup", "all"])
    parser.add_argument("model_id", nargs="?",
                         help="cloud model id for apply-model (e.g. moonshotai/kimi-k3)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-chat", action="store_true")
    parser.add_argument("--retention-days", type=int, default=None,
                        help="override [deploy] retention_days for 'cleanup'")
    args = parser.parse_args(argv)

    from ..config import load_config

    dcfg = resolve(load_config())
    echo_config(dcfg)

    if args.command == "redeploy":
        return cmd_redeploy(dcfg, args.dry_run)
    if args.command == "chatflow":
        return cmd_chatflow(dcfg, args.dry_run)
    if args.command == "models":
        return cmd_models(dcfg, args.dry_run)
    if args.command == "apply-model":
        return cmd_apply_model(dcfg, args.model_id, args.dry_run)
    if args.command == "verify":
        return cmd_verify(dcfg, args.dry_run, args.skip_chat)
    if args.command == "cleanup":
        return cmd_cleanup(dcfg, args.dry_run, args.retention_days)
    # all: redeploy → chatflow → verify
    if args.dry_run:
        print("dry-run plan (all): redeploy → chatflow → verify")
        return 0
    for step in (cmd_redeploy, cmd_chatflow):
        code = step(dcfg, False)
        if code != 0:
            print(f"aborting 'all' before verify (exit {code})")
            return code
    return cmd_verify(dcfg, False, args.skip_chat)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ConfigError as exc:
        print(f"configuration error: {exc}")
        sys.exit(2)
