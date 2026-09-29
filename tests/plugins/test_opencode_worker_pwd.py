"""Regression test for the opencode_delegate PWD staleness bug (task 013).

Loads THIS REPO's own znh-plugins/opencode_worker/__init__.py -- not the
deployed site plugin at /mnt/z/pantheon/.hermes/plugins/opencode_worker/
that test_opencode_worker_herdr.py exercises. That module lives outside
this repo and is unaffected by anything here until a deploy/sync step
copies this file over it.

Bug (found live, reproduced 3x against the real installed OpenCode 1.18.25):
`_handle_opencode_delegate`'s direct-subprocess lane passed `cwd=wd` to
subprocess.run but built `env` via a verbatim `os.environ.copy()`, leaving
`env["PWD"]` stale at whatever the *calling* hermes process's PWD was.
OpenCode was observed trusting PWD over the actual working directory for
at least part of its own project-root resolution, so a delegated task
could silently operate in the wrong directory with no error.

Run:  uv run pytest tests/plugins/test_opencode_worker_pwd.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_INIT = REPO_ROOT / "znh-plugins" / "opencode_worker" / "__init__.py"

pytestmark = pytest.mark.skipif(
    not PLUGIN_INIT.exists(),
    reason=f"opencode_worker plugin not found at {PLUGIN_INIT}",
)


@pytest.fixture
def plugin(monkeypatch):
    """Import this repo's own opencode_worker/__init__.py fresh."""
    name = "_opencode_worker_pwd_under_test"
    for key in (name, f"{name}.__init__"):
        monkeypatch.delitem(sys.modules, key, raising=False)
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(PLUGIN_INIT.parent)]
    monkeypatch.setitem(sys.modules, name, pkg)
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_INIT, submodule_search_locations=[str(PLUGIN_INIT.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_SOCKET_PATH", "HERDR_DELEGATE_PANES"):
        monkeypatch.delenv(var, raising=False)
    return mod


class TestSubprocessLaneSetsPwd:
    def test_env_pwd_matches_the_requested_workdir(self, plugin, monkeypatch, tmp_path):
        """The bug: env["PWD"] used to be a verbatim copy of the CALLING
        process's PWD, disagreeing with cwd=wd. Must now match wd exactly."""
        # Make the calling process's own PWD provably different from wd,
        # so a test that passed by accident (both happening to match) is
        # ruled out.
        monkeypatch.setenv("PWD", "/somewhere/else/entirely")

        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, *, cwd=None, env=None, **kwargs):
            captured["cwd"] = cwd
            captured["env_pwd"] = (env or {}).get("PWD")
            return _Result()

        monkeypatch.setattr(plugin.subprocess, "run", _fake_run)
        monkeypatch.setattr(plugin, "_resolve_opencode_bin", lambda: None)

        plugin._handle_opencode_delegate({"task": "x", "workdir": str(tmp_path)})

        assert captured["cwd"] == tmp_path.resolve()
        assert captured["env_pwd"] == str(tmp_path.resolve()), (
            "env['PWD'] must match the resolved workdir, not the calling "
            "process's own (stale) PWD"
        )

    def test_pwd_matches_cwd_for_relative_workdir_too(self, plugin, monkeypatch, tmp_path):
        """workdir may be given relative to the project root (see
        _resolve_workdir) -- PWD must match whatever wd actually resolves
        to, not the raw (possibly relative) input string."""
        monkeypatch.setenv("PWD", "/somewhere/else/entirely")
        monkeypatch.setattr(plugin, "find_project_root", lambda start: tmp_path)

        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, *, cwd=None, env=None, **kwargs):
            captured["cwd"] = cwd
            captured["env_pwd"] = (env or {}).get("PWD")
            return _Result()

        monkeypatch.setattr(plugin.subprocess, "run", _fake_run)
        monkeypatch.setattr(plugin, "_resolve_opencode_bin", lambda: None)

        subdir = tmp_path / "sub"
        subdir.mkdir()
        plugin._handle_opencode_delegate({"task": "x", "workdir": "sub"})

        assert captured["cwd"] == subdir.resolve()
        assert captured["env_pwd"] == str(subdir.resolve())
