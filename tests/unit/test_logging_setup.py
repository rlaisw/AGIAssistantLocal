"""Logging setup (spec 008; matrix U1–U7, research.md D1–D8):
level resolution + invalid fallback, rotation bounds, redaction, unwritable-path
fallback, console mirror, disabled-level laziness, framework propagation."""

import logging

import agentic_rag_mcp.logging_setup as ls
from agentic_rag_mcp.config import Config


def _cfg(tmp_path, **kw):
    kw.setdefault("log_level", "INFO")
    kw.setdefault("log_file", tmp_path / "logs" / "server.log")
    kw.setdefault("rotation_size_mb", 10.0)
    kw.setdefault("rotation_count", 5)
    return Config(state_db=tmp_path / "s.sqlite3", vector_dir=tmp_path / "v",
                  decider_enabled=False, **kw)


def _configure(tmp_path, **kw):
    cfg = _cfg(tmp_path, **kw)
    setup = ls.configure_logging(cfg)
    return setup, cfg.log_file


def _file_text(path):
    return path.read_text(errors="replace") if path.exists() else ""


def _emit(msg, *args):
    logging.getLogger("agentic_rag_mcp.test").info(msg, *args)


def test_level_resolution_and_default(tmp_path):
    setup, _ = _configure(tmp_path, log_level="debug")  # case-insensitive
    assert setup.level_name == "DEBUG"
    assert logging.getLogger("agentic_rag_mcp.test").isEnabledFor(logging.DEBUG)
    setup2, _ = _configure(tmp_path)  # default INFO
    assert setup2.level_name == "INFO"
    assert not logging.getLogger("agentic_rag_mcp.test").isEnabledFor(logging.DEBUG)


def test_invalid_level_falls_back_with_warn(tmp_path):
    """U1/FR-003: INF0 → INFO + a WARNING record naming the bad value, in the file."""
    setup, path = _configure(tmp_path, log_level="INF0")
    assert setup.level_name == "INFO" and setup.level == logging.INFO
    text = _file_text(path)
    assert "WARNING" in text and "INF0" in text and "INFO" in text


def test_rotation_bounds_disk(tmp_path):
    """U2/FR-006: past the threshold, generations rotate; total usage is capped."""
    size_mb, count = 0.001, 2  # 1048 bytes per generation, 2 backups
    _, path = _configure(tmp_path, log_level="INFO", rotation_size_mb=size_mb,
                         rotation_count=count)
    for i in range(60):
        _emit("rotation probe line %03d — padded content to fill the log file quickly", i)
    for h in logging.getLogger().handlers:  # flush before measuring
        h.flush()
    gen = list(path.parent.glob("server.log*"))
    assert len(gen) >= 2, "rollover must have produced a .1 generation"
    total = sum(p.stat().st_size for p in gen)
    assert total <= int(size_mb * 1024 * 1024) * (count + 1) + 1024  # bounded


def test_redaction_filter_all_levels(tmp_path):
    """U3/FR-005: credentials never appear at any level; placeholders do."""
    setup, path = _configure(tmp_path, log_level="DEBUG")
    logging.getLogger("agentic_rag_mcp.test").debug(
        "download %s", "https://api.onedrive.com/v1.0/shares/u!x/content?tempauth=1")
    _emit("auth Bearer eyJhbGciOiJIUzI1NiJ9.secret-token-value")
    _emit("config client_secret=\"supersecret-value-123\"")
    _emit('config api_key = "k-12345"')
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    assert "[REDACTED:token]" in text and "eyJhbGciOiJIUzI1NiJ9" not in text
    assert "[REDACTED:secret]" in text and "supersecret" not in text
    assert "[REDACTED:download-url]" in text and "tempauth=1" not in text
    assert "k-12345" not in text


def test_unwritable_path_console_only(tmp_path, capsys):
    """U4/FR-008: unwritable destination never blocks — console fallback + honest record."""
    blocker = tmp_path / "nope"
    blocker.write_text("i am a file, not a directory")
    setup, path = _configure(tmp_path, log_file=blocker / "logs" / "server.log")
    assert setup.writable is False and setup.fallback_reason
    _emit("after fallback the server still works")
    captured = capsys.readouterr()
    assert "log file not writable" in captured.err
    assert "after fallback" in captured.err  # console mirror still records
    assert not path.exists()


def test_console_mirror_parity(tmp_path, capsys):
    """U5/FR-007: the same record lands on stderr and in the file."""
    _, path = _configure(tmp_path)
    _emit("mirror probe %s", "A1")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "mirror probe A1" in _file_text(path)
    assert "mirror probe A1" in capsys.readouterr().err


def test_disabled_level_lazy(tmp_path):
    """U6/FR-009: at INFO, DEBUG records are skipped without formatting work."""
    _configure(tmp_path, log_level="INFO")
    assert logging.getLogger("agentic_rag_mcp.test").isEnabledFor(logging.DEBUG) is False


def test_reconfigure_resets_handlers(tmp_path):
    """build_server runs per test — configuration must not accumulate handlers."""
    _configure(tmp_path)
    n_after_first = len(logging.getLogger().handlers)
    _configure(tmp_path)
    assert len(logging.getLogger().handlers) == n_after_first


def test_framework_logger_reaches_file(tmp_path):
    """U7/FR-011: framework loggers (uvicorn-style) propagate to the root handlers."""
    _, path = _configure(tmp_path)
    logging.getLogger("uvicorn.access").info("POST /mcp 200 OK")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "POST /mcp 200 OK" in _file_text(path)


def test_record_format_components(tmp_path):
    """FR-001: each record carries timestamp, level, component, message."""
    _, path = _configure(tmp_path)
    _emit("format probe")
    for h in logging.getLogger().handlers:
        h.flush()
    line = _file_text(path).strip().splitlines()[-1]
    assert " INFO " in line and "agentic_rag_mcp.test" in line and "format probe" in line


def test_current_setup_fallback_shape():
    """status safety: an unconfigured process still yields an honest shape."""
    setup = ls.current_setup()
    assert set(setup.status_dict()) == {"level", "log_file", "writable"}


def test_warn_alias_accepts_short_form(tmp_path):
    """Terminology: WARN is the documented shorthand for the canonical WARNING."""
    setup, _ = _configure(tmp_path, log_level="WARN")
    assert setup.level_name == "WARNING"


def test_health_transitions_logged(tmp_path):
    """US1/AC4 (convergence T017): degrade → WARN, recover → INFO — logged at the
    StateStore choke point so every call site (probe, tools, auth, migration) records."""
    from agentic_rag_mcp.store.state import StateStore

    setup, path = _configure(tmp_path)
    store = StateStore(tmp_path / "t.sqlite3")
    sid = store.add_source("onedrive", {"client_id": "x"})
    store.set_health(sid, "degraded", "needs sign-in")
    store.set_health(sid, "healthy", None)
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    degrade_line = [ln for ln in text.splitlines() if "degraded" in ln and sid in ln]
    recover_line = [ln for ln in text.splitlines() if "healthy" in ln and sid in ln
                    and " WARNING " not in ln]
    assert degrade_line and " WARNING " in degrade_line[0] and "needs sign-in" in degrade_line[0]
    assert recover_line and " INFO " in recover_line[0]


def test_mcp_action_screenshot_capability_redaction(tmp_path):
    """T018: access/application logs keep the route, never its 43-char capability."""
    _, path = _configure(tmp_path)
    token = "A" * 43
    route = f"/mcp-action/screenshots/{token}"
    url = f"https://sidecar.test{route}"
    _emit("GET %s HTTP/1.1", route)
    _emit("audit screenshot image_url=%s", url)
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    marker = "/mcp-action/screenshots/[REDACTED:screenshot-token]"
    assert text.count(marker) == 2
    assert token not in text
    assert route not in text and url not in text


def test_mcp_action_redaction_keeps_other_paths_and_existing_rules(tmp_path):
    """T018: only exact capabilities are masked; existing credential rules remain."""
    _, path = _configure(tmp_path)
    paths = [
        "/mcp-action/screenshots/" + "A" * 42,
        "/mcp-action/screenshots/" + "A" * 44,
        "/mcp-action/screenshots/not-a-capability",
        "/mcp",
    ]
    for value in paths:
        _emit("GET %s HTTP/1.1", value)
    bearer = "eyJhbGciOiJIUzI1NiJ9.secret-token-value"
    _emit('Authorization: Bearer %s client_secret="secret-value-123" api_key = "k-12345"',
          bearer)
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    for value in paths:
        assert f"GET {value} HTTP/1.1" in text
    assert "Authorization: Bearer [REDACTED:token]" in text and bearer not in text
    assert text.count("[REDACTED:secret]") == 2
    assert "secret-value-123" not in text and "k-12345" not in text


def test_mcp_action_report_capability_redaction(tmp_path):
    """T014: the report route keeps its prefix, never its 43-char capability."""
    _, path = _configure(tmp_path)
    token = "A" * 43
    route = f"/mcp-action/reports/{token}"
    url = f"https://sidecar.test{route}"
    _emit("GET %s HTTP/1.1", route)
    _emit("audit report report_url=%s", url)
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    marker = "/mcp-action/reports/[REDACTED:report-token]"
    assert text.count(marker) == 2
    assert token not in text
    assert route not in text and url not in text


def test_mcp_action_report_redaction_keeps_other_paths_and_existing_rules(tmp_path):
    """T014: only exact report capabilities are masked; other redactions remain."""
    _, path = _configure(tmp_path)
    paths = [
        "/mcp-action/reports/" + "A" * 42,
        "/mcp-action/reports/" + "A" * 44,
        "/mcp-action/reports/not-a-capability",
        "/mcp-action/other/" + "A" * 43,
    ]
    for value in paths:
        _emit("GET %s HTTP/1.1", value)
    screenshot = "/mcp-action/screenshots/" + "B" * 43
    _emit("GET %s HTTP/1.1", screenshot)
    bearer = "eyJhbGciOiJIUzI1NiJ9.secret-token-value"
    _emit('Authorization: Bearer %s client_secret="secret-value-123"', bearer)
    for h in logging.getLogger().handlers:
        h.flush()
    text = _file_text(path)
    for value in paths:
        assert f"GET {value} HTTP/1.1" in text
    assert text.count("/mcp-action/screenshots/[REDACTED:screenshot-token]") == 1
    assert "Authorization: Bearer [REDACTED:token]" in text and bearer not in text
    assert "[REDACTED:secret]" in text and "secret-value-123" not in text
