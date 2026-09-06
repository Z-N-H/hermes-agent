"""Required-MCP hard-fail guard for cron jobs.

Background
==========
``cron/scheduler.py:run_job()`` initializes MCP tools before every agent
turn, deliberately non-fatal on failure (#4219) — right for jobs that don't
need MCP. But for a job whose entire purpose depends on a specific MCP (e.g.
``granola-meeting-scanner`` needs ``granola_*`` tools), "non-fatal" meant the
scheduler launched the LLM turn anyway, the model discovered mid-run its
tools were missing, and the run burned API calls and could end reporting a
hollow "completed successfully".

The fix: jobs declaring ``required_mcp_tools`` / ``required_mcp_servers``
(set explicitly at creation, or inherited from attached skills' frontmatter)
are verified against ``discover_mcp_tools()`` output BEFORE ``AIAgent`` is
constructed. Any miss → the run fails closed, no inference call is made, and
the standard failure path marks the run errored + delivers the alert. Jobs
declaring nothing keep the legacy non-fatal behavior.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cron.scheduler import run_job


def _base_job(**overrides):
    job = {
        "id": "req-mcp-test",
        "name": "req mcp test",
        "prompt": "hello",
        "model": None,
        "provider": None,
        "provider_snapshot": None,
        "base_url": None,
    }
    job.update(overrides)
    return job


def _run(job, tmp_path, *, discovered_tools=(), discovery_exc=None, connected_servers=()):
    """Drive run_job with MCP discovery pinned. Returns
    (success, output, final_response, error, agent_constructed)."""
    fake_db = MagicMock()
    if discovery_exc is not None:
        discover_patch = patch(
            "tools.mcp_tool.discover_mcp_tools", side_effect=discovery_exc
        )
    else:
        discover_patch = patch(
            "tools.mcp_tool.discover_mcp_tools", return_value=list(discovered_tools)
        )
    with patch("cron.scheduler._hermes_home", tmp_path), \
         patch("cron.scheduler._get_hermes_home", return_value=tmp_path), \
         patch("cron.scheduler._resolve_origin", return_value=None), \
         patch("hermes_cli.env_loader.load_hermes_dotenv"), \
         patch("hermes_cli.env_loader.reset_secret_source_cache"), \
         patch("hermes_state.SessionDB", return_value=fake_db), \
         patch(
             "hermes_cli.runtime_provider.resolve_runtime_provider",
             return_value={
                 "api_key": "test-key",
                 "base_url": "https://example.invalid/v1",
                 "provider": "openrouter",
                 "api_mode": "chat_completions",
             },
         ), \
         discover_patch, \
         patch(
             "cron.scheduler._connected_mcp_server_names",
             return_value=set(connected_servers),
         ), \
         patch("run_agent.AIAgent") as mock_agent_cls:
        mock_agent = MagicMock()
        mock_agent.run_conversation.return_value = {"final_response": "ok"}
        mock_agent_cls.return_value = mock_agent
        success, output, final_response, error = run_job(job)
        agent_constructed = mock_agent_cls.called
    return success, output, final_response, error, agent_constructed


class TestRequiredMcpHardFail:
    def test_required_tool_glob_absent_fails_closed(self, tmp_path):
        """Required tool pattern with no match in discover output → the run
        must fail BEFORE the agent turn, with zero AIAgent construction."""
        job = _base_job(required_mcp_tools=["granola_*"])
        success, output, final_response, error, agent_constructed = _run(
            job,
            tmp_path,
            discovered_tools=["mcp__pantheon__search", "mcp__pantheon__execute"],
        )

        assert agent_constructed is False, "LLM turn must never start when required MCP tools are missing"
        assert success is False
        assert error is not None
        assert "required MCP tool(s) unavailable: granola_*" in error
        assert "no inference call was made" in error.lower()

    def test_required_tool_exact_absent_fails_closed(self, tmp_path):
        job = _base_job(required_mcp_tools=["granola_list_meetings"])
        success, _o, _r, error, agent_constructed = _run(job, tmp_path, discovered_tools=[])
        assert agent_constructed is False
        assert success is False
        assert "required MCP tool(s) unavailable: granola_list_meetings" in error

    def test_required_tool_present_runs_normally(self, tmp_path):
        """Satisfied requirement → the job proceeds to the agent turn."""
        job = _base_job(required_mcp_tools=["granola_*"])
        success, _o, final_response, error, agent_constructed = _run(
            job,
            tmp_path,
            discovered_tools=["granola_list_meetings", "granola_get_meetings"],
        )
        assert agent_constructed is True
        assert success is True
        assert error is None
        assert final_response == "ok"

    def test_required_server_absent_fails_closed(self, tmp_path):
        job = _base_job(required_mcp_servers=["granola"])
        success, _o, _r, error, agent_constructed = _run(
            job, tmp_path, connected_servers={"pantheon"}
        )
        assert agent_constructed is False
        assert success is False
        assert "required MCP server(s) unavailable: granola" in error

    def test_required_server_connected_runs_normally(self, tmp_path):
        job = _base_job(required_mcp_servers=["pantheon"])
        success, _o, _r, error, agent_constructed = _run(
            job, tmp_path, connected_servers={"pantheon"}
        )
        assert agent_constructed is True
        assert success is True
        assert error is None

    def test_mixed_requirement_reports_both(self, tmp_path):
        job = _base_job(
            required_mcp_tools=["granola_*"], required_mcp_servers=["granola"]
        )
        success, _o, _r, error, agent_constructed = _run(
            job, tmp_path, connected_servers={"pantheon"}
        )
        assert agent_constructed is False
        assert success is False
        assert "tool(s) unavailable: granola_*" in error
        assert "server(s) unavailable: granola" in error

    def test_no_requirement_unaffected_backcompat(self, tmp_path):
        """Jobs with no declared requirement keep today's non-fatal behavior:
        MCP discovery returning nothing must NOT block the run."""
        job = _base_job()  # neither field set, and keys absent entirely
        success, _o, final_response, error, agent_constructed = _run(
            job, tmp_path, discovered_tools=[]
        )
        assert agent_constructed is True
        assert success is True
        assert error is None
        assert final_response == "ok"

    def test_no_requirement_survives_discovery_exception(self, tmp_path):
        """#4219 regression: discovery raising is non-fatal for jobs that
        declare no requirement."""
        job = _base_job()
        success, _o, final_response, error, agent_constructed = _run(
            job, tmp_path, discovery_exc=RuntimeError("hub exploded")
        )
        assert agent_constructed is True
        assert success is True
        assert error is None

    def test_discovery_exception_with_requirement_fails_closed(self, tmp_path):
        """Discovery failing means the requirement cannot be verified → fail
        closed rather than gamble an inference turn on an unknown landscape."""
        job = _base_job(required_mcp_tools=["granola_*"])
        success, _o, _r, error, agent_constructed = _run(
            job, tmp_path, discovery_exc=RuntimeError("hub exploded")
        )
        assert agent_constructed is False
        assert success is False
        assert "could not be verified" in error
        assert "no inference call was made" in error.lower()


class _StorageIsolation:
    """Patch cron.jobs storage so create/update never touch the real store."""

    def __init__(self, monkeypatch, initial=None):
        import contextlib
        import cron.jobs as jobs

        self.jobs = jobs
        self.store = list(initial or [])

        @contextlib.contextmanager
        def _noop_lock():
            yield

        monkeypatch.setattr(jobs, "_jobs_lock", _noop_lock, raising=True)
        monkeypatch.setattr(jobs, "load_jobs", lambda: list(self.store), raising=True)

        def _save(new_jobs):
            self.store.clear()
            self.store.extend(new_jobs)

        monkeypatch.setattr(jobs, "save_jobs", _save, raising=True)


class TestCreateJobRequiredMcp:
    def test_explicit_fields_stored(self, monkeypatch):
        _StorageIsolation(monkeypatch)
        import cron.jobs as jobs

        job = jobs.create_job(
            prompt="do a thing",
            schedule="every 1 hour",
            required_mcp_tools=["granola_*"],
            required_mcp_servers=["pantheon"],
        )
        assert job["required_mcp_tools"] == ["granola_*"]
        assert job["required_mcp_servers"] == ["pantheon"]

    def test_no_requirement_keys_absent(self, monkeypatch):
        """Back-compat: jobs without declarations stay byte-identical (keys absent)."""
        _StorageIsolation(monkeypatch)
        import cron.jobs as jobs

        job = jobs.create_job(prompt="do a thing", schedule="every 1 hour")
        assert "required_mcp_tools" not in job
        assert "required_mcp_servers" not in job

    def test_inherited_from_skill_frontmatter(self, monkeypatch):
        _StorageIsolation(monkeypatch)
        import cron.jobs as jobs

        skill_md = (
            "---\n"
            "name: granola-meeting-filing\n"
            "description: test\n"
            "required_mcp_tools: [granola_*]\n"
            "required_mcp_servers: [pantheon]\n"
            "---\n\n"
            "# Body\n"
        )
        import json as _json

        with patch(
            "tools.skills_tool.skill_view",
            return_value=_json.dumps({"success": True, "content": skill_md}),
        ):
            job = jobs.create_job(
                prompt="run the skill",
                schedule="every 1 hour",
                skills=["granola-meeting-filing"],
            )
        assert job["required_mcp_tools"] == ["granola_*"]
        assert job["required_mcp_servers"] == ["pantheon"]

    def test_explicit_overrides_skill_frontmatter(self, monkeypatch):
        _StorageIsolation(monkeypatch)
        import cron.jobs as jobs

        skill_md = (
            "---\nname: s\nrequired_mcp_tools: [other_*]\n---\n\n# Body\n"
        )
        import json as _json

        with patch(
            "tools.skills_tool.skill_view",
            return_value=_json.dumps({"success": True, "content": skill_md}),
        ):
            job = jobs.create_job(
                prompt="run the skill",
                schedule="every 1 hour",
                skills=["s"],
                required_mcp_tools=["granola_*"],
                required_mcp_servers=["granola"],
            )
        assert job["required_mcp_tools"] == ["granola_*"]
        assert job["required_mcp_servers"] == ["granola"]

    def test_skill_load_failure_non_fatal(self, monkeypatch):
        """A skill mid-edit must never break job creation."""
        _StorageIsolation(monkeypatch)
        import cron.jobs as jobs

        with patch("tools.skills_tool.skill_view", side_effect=RuntimeError("boom")):
            job = jobs.create_job(
                prompt="run it", schedule="every 1 hour", skills=["s"]
            )
        assert "required_mcp_tools" not in job


class TestUpdateJobRequiredMcp:
    def test_update_sets_and_clears(self, monkeypatch):
        import cron.jobs as jobs

        iso = _StorageIsolation(monkeypatch)
        existing = {
            "id": "upd-test",
            "name": "upd test",
            "prompt": "hi",
            "schedule": {"kind": "interval", "minutes": 60},
            "schedule_display": "every 1 hour",
        }
        iso.store.append(existing)

        updated = jobs.update_job(
            "upd-test", {"required_mcp_tools": ["granola_*", " ntfy_*", "granola_*"]}
        )
        assert updated["required_mcp_tools"] == ["granola_*", "ntfy_*"]

        cleared = jobs.update_job("upd-test", {"required_mcp_tools": None})
        assert not cleared.get("required_mcp_tools")


class TestCheckRequiredMcpUnit:
    """Direct unit tests of the matcher semantics."""

    def test_glob_and_exact_matching(self):
        from cron.scheduler import _check_required_mcp

        job = {"required_mcp_tools": ["granola_*", "exact_tool"]}
        assert _check_required_mcp(job, ["granola_x", "exact_tool"]) is None
        assert _check_required_mcp(job, ["granola_x"]) is not None
        # Glob does not match a mere substring/embedding.
        assert _check_required_mcp(job, ["mygranola_x"]) is not None

    def test_no_declaration_returns_none(self):
        from cron.scheduler import _check_required_mcp

        assert _check_required_mcp({}, []) is None
        assert _check_required_mcp({"required_mcp_tools": []}, []) is None
