"""Spec 036 — skill trust + search envelope suite (tasks T010/T012):
the FR-002 matrix through the API surface, decay-by-feedback, outage vs miss."""

from __future__ import annotations

from agentic_rag_mcp.skill_manager.api import SkillManager

DESC = "Restarts the print spooler. Use for printing issues, stuck queue."


def _manager(tmp_path, embed=None):
    from agentic_rag_mcp.hermes_audit import HermesAudit
    mgr = SkillManager(tmp_path / "skills.db", tmp_path / "vdb",
                       HermesAudit(tmp_path / "audit.jsonl"))
    if embed is not None:
        mgr.intent = embed
    return mgr


def _skill(name, s, f):
    return {
        "name": name,
        "description": f"{name} description with trigger keywords",
        "tier": 1,
        "workflow": [{"step": 1, "tool": "hermes_run_command", "service": "os-control",
                      "params_template": {"task": "restart {{service_name}}"},
                      "expect": "service restarted"}],
    }, s, f


class _FakeIntent:
    """Search double: underscore/space-insensitive token matching."""

    def __init__(self, names):
        self.names = list(names)

    def _norm(self, s):
        return set("".join(c if c.isalnum() else " " for c in s.lower()).split())

    def search(self, intent, limit=5):
        itoks = self._norm(intent)
        hits = [n for n in self.names if self._norm(n) & itoks]
        return (hits or list(self.names))[:limit]


class TestSearchTrust:
    def test_reusable_flag_matrix(self, tmp_path):
        mgr = _manager(tmp_path)
        # all names share "print" tokens so one intent surfaces all four
        for name, s, f in [("fix_print_spooler", 4, 0), ("lucky_print_once", 2, 0),
                           ("demoted_print_old", 8, 3), ("fresh_print_v1", 0, 0)]:
            skill = _skill(name, s, f)[0]
            mgr.store.save(skill)
            for _ in range(s):
                mgr.store.record_feedback(name, "success")
            for _ in range(f):
                mgr.store.record_feedback(name, "failure")
        mgr.intent = _FakeIntent(["fix_print_spooler", "lucky_print_once",
                                   "demoted_print_old", "fresh_print_v1"])
        out = mgr.search("fix print spooler printing", cid="c1")
        assert out["found"] is True
        flags = {r["name"]: r["reusable"] for r in out["skills"]}
        assert flags["fix_print_spooler"] is True
        assert flags["lucky_print_once"] is False       # sample floor
        assert flags["demoted_print_old"] is False       # decayed below 80%
        assert flags["fresh_print_v1"] is False          # n=0

    def test_miss_is_found_false_not_error(self, tmp_path):
        mgr = _manager(tmp_path, embed=_FakeIntent([]))
        out = mgr.search("nothing matches this", cid="c1")
        assert out == {"found": False, "skills": []}


class TestOutageEnvelope:
    def test_store_down_is_error_not_miss(self, tmp_path):
        mgr = _manager(tmp_path)
        mgr.intent = _FakeIntent(["fix_print_spooler"])

        class _DeadStore:
            def get(self, *a, **k):
                raise OSError("disk I/O error")

            def counts(self, name):
                raise OSError("disk I/O error")

        mgr.store = _DeadStore()
        out = mgr.search("fix print spooler", cid="c1")
        assert out["status"] == "error"
        assert "skill-store-unavailable" in out["reason"]

    def test_degradation_notice(self, tmp_path):
        mgr = _manager(tmp_path)
        mgr.intent = _FakeIntent([])
        mgr.store = type("Dead", (), {
            "get": staticmethod(lambda *a: (_ for _ in ()).throw(OSError("down"))),
        })()
        out = mgr.get("any", cid="c1")
        assert out["status"] == "error"
        assert "skill-store-unavailable" in out["reason"]


class TestDecay:
    def test_feedback_drives_demotion(self, tmp_path):
        mgr = _manager(tmp_path)
        mgr.store.save(_skill("fix_print_spooler", 0, 0)[0])
        for _ in range(5):
            mgr.store.record_feedback("fix_print_spooler", "success")
        mgr.intent = _FakeIntent(["fix_print_spooler"])
        assert mgr.search("print", cid="c1")["skills"][0]["reusable"] is True
        # 4 failures on 5 successes -> 55% -> demoted, no time involved
        for _ in range(4):
            mgr.store.record_feedback("fix_print_spooler", "failure")
        assert mgr.search("print", cid="c1")["skills"][0]["reusable"] is False