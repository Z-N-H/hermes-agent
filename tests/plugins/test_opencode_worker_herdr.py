"""Tests for the Tier-2 nested-delegation pane lane in the opencode_worker plugin.

The plugin under test is the deployed site plugin at
``/mnt/z/pantheon/.hermes/plugins/opencode_worker/`` -- it lives outside this
repo, so the whole file skips when that path is absent (e.g. upstream CI).

The properties under test mirror the dispatcher lane's suite
(``vault/ZNH/scripts/tests/test_kanban_herdr_lane.py``):

* the herdr gate is a no-op outside a pane and `HERDR_DELEGATE_PANES=0` is a
  working kill switch;
* the delegation's verdict comes from the worker's real exit code, read back
  from a file the pane writes -- never from herdr's agent state;
* `pane run` printing no JSON on success is not a failure, and a JSON error
  body on rc=0 is;
* the temp spool is removed on every exit path, while the *pane* follows the
  retention rule: a run that actually ran is kept for review (success,
  non-zero exit, unreadable rc) and only a timeout or an infra failure closes
  it. Timeout closes because closing the pane is what stops the run.

Note the pane is created with `pane split` off the parent's pane -- so a
delegation appears as a child in the parent's tab -- not with
`workspace create`. `pane split` returns the new pane as `.result.pane`;
`workspace create` returned `.result.root_pane`. Stubs must use the former.

Run:  uv run pytest tests/plugins/test_opencode_worker_herdr.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import types
from pathlib import Path

import pytest

PLUGIN_INIT = Path("/mnt/z/pantheon/.hermes/plugins/opencode_worker/__init__.py")

pytestmark = pytest.mark.skipif(
    not PLUGIN_INIT.exists(),
    reason=f"opencode_worker plugin not deployed at {PLUGIN_INIT}",
)


@pytest.fixture
def plugin(monkeypatch):
    """Import the deployed plugin module fresh (it is a package __init__).

    Each test gets a clean copy so module-level env reads (HERDR_BIN) and
    monkeypatched helpers never leak between tests.
    """
    name = "_opencode_worker_under_test"
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
    monkeypatch.setattr(mod, "HERDR_POLL_SECONDS", 0.01, raising=False)
    # Tests never talk to a real herdr; make sure the env can't reach one.
    for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_SOCKET_PATH",
                "HERDR_DELEGATE_PANES"):
        monkeypatch.delenv(var, raising=False)
    return mod


# The pane line captures the worker's status into `_rc` before echoing it, so
# the trailing report-agent/report-metadata calls cannot overwrite `$?` and
# change the verdict. Anchored at the front only: everything after the rc
# write is best-effort reporting the tests do not model.
_PANE_RUN_RE = re.compile(
    r"^(?P<cmd>.*?) > (?P<out>\S+) 2> (?P<err>\S+); "
    r"_rc=\$\?; echo \$_rc > (?P<rc>\S+)(?:;|$)"
)


def _fake_herdr(calls: list, *, exit_code: str | None = "0",
                stdout_text: str = "", stderr_text: str = ""):
    """Stand in for `_herdr`, keeping its (ok, payload) contract.

    Log/exit paths come out of the pane-run command line, exactly as the real
    pane would find them. `pane run` answers (True, None): it really does
    print nothing on success, which is why success is judged by exit status
    rather than a parsable body. exit_code=None simulates a command that
    never finishes (nothing writes rc) -> timeout.
    """

    def _call(*args: str, timeout: int = 30):
        calls.append(args)
        if args[:2] == ("pane", "split"):
            return True, {"result": {"pane": {"pane_id": "w1:p2"}}}
        if args[:2] == ("pane", "run"):
            m = _PANE_RUN_RE.match(args[3])
            assert m, f"unparseable pane-run line: {args[3]!r}"
            Path(m["out"]).write_text(stdout_text, encoding="utf-8")
            Path(m["err"]).write_text(stderr_text, encoding="utf-8")
            if exit_code is not None:
                Path(m["rc"]).write_text(exit_code, encoding="utf-8")
            return True, None
        return True, {"result": {"type": "ok"}}

    return _call


def _spool_dirs() -> set[Path]:
    """Leftover delegation spools in TMPDIR."""
    return set(Path(tempfile.gettempdir()).glob("herdr-delegate-*"))


# --- the gate -------------------------------------------------------------


@pytest.mark.parametrize(
    "env,pane,sock,delegate_panes,expected",
    [
        ("1", "w1:p1", "/tmp/herdr.sock", None, True),
        ("1", "w1:p1", "/tmp/herdr.sock", "1", True),
        # kill switch
        ("1", "w1:p1", "/tmp/herdr.sock", "0", False),
        # plain `hermes chat` at a terminal: all unset
        (None, None, None, None, False),
        # partial environments must not half-enable it
        ("1", None, "/tmp/herdr.sock", None, False),
        ("1", "w1:p1", None, None, False),
        (None, "w1:p1", "/tmp/herdr.sock", None, False),
        ("0", "w1:p1", "/tmp/herdr.sock", None, False),
        # kill switch wins even over a complete environment
        (None, None, None, "0", False),
    ],
)
def test_gate_permutations(plugin, monkeypatch, env, pane, sock,
                           delegate_panes, expected):
    for var, val in (("HERDR_ENV", env), ("HERDR_PANE_ID", pane),
                     ("HERDR_SOCKET_PATH", sock),
                     ("HERDR_DELEGATE_PANES", delegate_panes)):
        if val is None:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, val)
    assert plugin._use_herdr_pane() is expected


def test_gate_off_keeps_the_subprocess_path(plugin, monkeypatch, tmp_path):
    """Outside a pane, `_run_in_pane` must never be reached."""
    monkeypatch.setattr(
        plugin, "_run_in_pane",
        lambda *a, **k: pytest.fail("pane lane used outside a herdr pane"),
    )

    class _Result:
        returncode = 0
        stdout = "from subprocess\n"
        stderr = "sub-err\n"

    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
    out = json.loads(plugin._handle_opencode_delegate(
        {"task": "x", "workdir": str(tmp_path)}))
    assert out["output"] == "from subprocess"
    assert out["stderr"] == "sub-err"


def test_kill_switch_keeps_the_subprocess_path_in_a_pane(
        plugin, monkeypatch, tmp_path):
    """HERDR_DELEGATE_PANES=0 inside a pane must delegate via subprocess."""
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    monkeypatch.setenv("HERDR_DELEGATE_PANES", "0")
    monkeypatch.setattr(
        plugin, "_run_in_pane",
        lambda *a, **k: pytest.fail("kill switch did not disable the pane lane"),
    )

    class _Result:
        returncode = 3
        stdout = ""
        stderr = "boom\n"

    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
    out = json.loads(plugin._handle_opencode_delegate(
        {"task": "x", "workdir": str(tmp_path)}))
    assert out["error"] == "OpenCode exited 3"


# --- exit-code fidelity ---------------------------------------------------


@pytest.mark.parametrize("code", [0, 1, 7, 127])
def test_returns_the_real_exit_code(plugin, monkeypatch, tmp_path, code):
    """The verdict is the delegated run's own exit status, read back from the pane."""
    calls: list = []
    monkeypatch.setattr(plugin, "_herdr", _fake_herdr(calls, exit_code=str(code)))

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")
    assert (rc, failure) == (code, None)


def test_stdout_and_stderr_come_back_separately(plugin, monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(
        plugin, "_herdr",
        _fake_herdr(calls, exit_code="0", stdout_text="OUT\n", stderr_text="ERR\n"))

    rc, out, err, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")
    assert (rc, failure) == (0, None)
    assert out == "OUT\n"
    assert err == "ERR\n"


def test_workdir_acquires_no_stray_files(plugin, monkeypatch, tmp_path):
    """Logs go to the temp spool, never into the caller-chosen workdir."""
    calls: list = []
    monkeypatch.setattr(
        plugin, "_herdr", _fake_herdr(calls, stdout_text="o", stderr_text="e"))

    # A dedicated subdir: the conftest plants its own fixture files in
    # tmp_path, so the workdir must be one the suite doesn't share.
    wd = tmp_path / "callers-workdir"
    wd.mkdir()

    plugin._run_in_pane(["opencode", "run", "x"], wd, timeout=5, label="t")
    assert list(wd.iterdir()) == []


def test_handler_resolves_opencode_to_an_absolute_path(
        plugin, monkeypatch, tmp_path):
    """Delegate panes get a server-side PATH that need not contain opencode
    (herdr server's panes resolve only ~/.opencode/bin and ~/.local/bin;
    opencode lives in ~/.bun/bin). The handler must hand the pane an absolute
    path resolved in Hermes' own environment."""
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    seen: dict = {}

    def _spy(cmd, wd, timeout, label):
        seen["cmd"] = cmd
        return 0, "ok", "", None

    monkeypatch.setattr(plugin, "_run_in_pane", _spy)
    monkeypatch.setattr(plugin.shutil, "which", lambda name: "/abs/stub/opencode")

    plugin._handle_opencode_delegate(
        {"task": "t", "workdir": str(tmp_path), "timeout": 5})
    assert seen["cmd"][0] == "/abs/stub/opencode"


def test_handler_keeps_bare_name_when_opencode_unresolvable(
        plugin, monkeypatch, tmp_path):
    """`which` failing must leave the bare name so the subprocess lane keeps
    its FileNotFoundError handling and the pane lane reports 127, either way
    surfacing 'opencode' as the missing thing."""
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    seen: dict = {}

    def _spy(cmd, wd, timeout, label):
        seen["cmd"] = cmd
        return 0, "ok", "", None

    monkeypatch.setattr(plugin, "_run_in_pane", _spy)
    monkeypatch.setattr(plugin.shutil, "which", lambda name: None)
    monkeypatch.delenv("OPENCODE_BIN", raising=False)
    # No ~/.bun/bin/opencode under a hermetic home either.
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")

    plugin._handle_opencode_delegate(
        {"task": "t", "workdir": str(tmp_path), "timeout": 5})
    assert seen["cmd"][0] == "opencode"


def test_handler_falls_back_to_opencode_bin_and_bun_location(
        plugin, monkeypatch, tmp_path):
    """Hermes in a pristine herdr pane lacks ~/.bun/bin on PATH; the env
    override (same one the vault dispatcher uses) must still resolve."""
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    monkeypatch.setattr(plugin.shutil, "which", lambda name: None)

    for expected in ("/custom/opencode", None):
        seen: dict = {}

        def _spy(cmd, wd, timeout, label):
            seen["cmd"] = cmd
            return 0, "ok", "", None

        monkeypatch.setattr(plugin, "_run_in_pane", _spy)
        if expected:
            monkeypatch.setenv("OPENCODE_BIN", expected)
        else:
            monkeypatch.delenv("OPENCODE_BIN", raising=False)
            bun = tmp_path / "home" / ".bun" / "bin"
            bun.mkdir(parents=True)
            (bun / "opencode").touch()
            monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
            expected = str(bun / "opencode")

        plugin._handle_opencode_delegate(
            {"task": "t", "workdir": str(tmp_path), "timeout": 5})
        assert seen["cmd"][0] == expected


def test_check_fn_uses_the_same_resolution_chain(plugin, monkeypatch, tmp_path):
    """The availability gate must not hide the tool where opencode is
    installed but off-PATH -- inside a pristine herdr pane shutil.which fails
    while ~/.bun/bin/opencode exists (the exact production situation)."""
    monkeypatch.setattr(plugin.shutil, "which", lambda name: None)
    monkeypatch.delenv("OPENCODE_BIN", raising=False)

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    assert plugin._check_opencode_available() is False

    bun = tmp_path / "home" / ".bun" / "bin"
    bun.mkdir(parents=True)
    (bun / "opencode").touch()
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert plugin._check_opencode_available() is True

    monkeypatch.setenv("OPENCODE_BIN", "/custom/opencode")
    assert plugin._check_opencode_available() is True


# --- the two herdr CLI gotchas (regressions already paid for once) ---------


def test_pane_run_succeeds_with_no_json_body(plugin, monkeypatch):
    """`herdr pane run` prints nothing on success -- that must not read as failure.

    Regression: judging it by a parsable JSON body made every real dispatch
    fail with "herdr pane run failed" while the pane had in fact started fine.
    """

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
    assert plugin._herdr("pane", "run", "w1:p1", "true") == (True, None)


def test_error_payload_on_exit_zero_is_not_success(plugin, monkeypatch):
    """herdr answers errors as JSON on stdout with rc=0; don't read that as ok."""

    class _Result:
        returncode = 0
        stdout = '{"id":"x","error":{"code":"server_not_running"}}'
        stderr = ""

    monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
    ok, payload = plugin._herdr("workspace", "list")
    assert ok is False
    assert payload and "error" in payload


# --- retention and spool teardown on every exit path -----------------------
#
# The spool is removed unconditionally (it is a temp dir the caller never
# asked for). The pane is not: a run that actually ran is retained at `done`
# so it can be reviewed, and only a timeout or an infra failure closes it.


def _closes(calls: list) -> list:
    return [c for c in calls if c[:2] == ("pane", "close")]


def test_pane_retained_and_spool_removed_on_success(
        plugin, monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(plugin, "_herdr", _fake_herdr(calls, exit_code="0"))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert (rc, failure) == (0, None)
    # Retention: a finished run stays visible for review.
    assert _closes(calls) == []
    assert _spool_dirs() == before


def test_pane_retained_and_spool_removed_on_nonzero_exit(
        plugin, monkeypatch, tmp_path):
    """A failed run is the *most* worth reviewing -- it must not vanish."""
    calls: list = []
    monkeypatch.setattr(plugin, "_herdr", _fake_herdr(calls, exit_code="127"))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert (rc, failure) == (127, None)
    assert _closes(calls) == []
    assert _spool_dirs() == before


def test_pane_closed_and_spool_removed_on_timeout(
        plugin, monkeypatch, tmp_path):
    """Timeout is the one ran-but-closed case: closing is what stops the run.

    Unlike the old whole-workspace close, this leaves the parent pane and the
    shared client workspace untouched.
    """
    calls: list = []
    # exit_code=None -> the pane never writes rc -> poll loop times out.
    monkeypatch.setattr(plugin, "_herdr", _fake_herdr(calls, exit_code=None))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=0.05, label="t")

    assert rc is None
    assert "timed out" in failure
    assert ("pane", "close", "w1:p2") in calls
    assert _spool_dirs() == before


def test_pane_retained_and_spool_removed_on_unreadable_exit_code(
        plugin, monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(plugin, "_herdr", _fake_herdr(calls, exit_code="garbage"))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert rc is None
    assert "unreadable exit code" in failure
    # The worker ran and wrote *something*; keep the pane so it can be read.
    assert _closes(calls) == []
    assert _spool_dirs() == before


def test_pane_closed_and_spool_removed_when_pane_run_fails(
        plugin, monkeypatch, tmp_path):
    """Infra failure: the worker never ran, so there is nothing to review."""
    def _call(*args, timeout=30):
        calls.append(args)
        if args[:2] == ("pane", "split"):
            return True, {"result": {"pane": {"pane_id": "w1:p2"}}}
        if args[:2] == ("pane", "run"):
            return False, None
        return True, {"result": {"type": "ok"}}

    calls: list = []
    monkeypatch.setattr(plugin, "_herdr", _call)
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert rc is None
    assert failure == "herdr pane run failed"
    assert ("pane", "close", "w1:p2") in calls
    assert _spool_dirs() == before


# --- spool leak on the early returns (the bug in scope item 2) -------------


def test_failed_pane_split_leaves_no_spool(plugin, monkeypatch, tmp_path):
    """herdr unreachable must not leak one mkdtemp dir per delegation."""
    monkeypatch.setattr(plugin, "_herdr", lambda *a, **k: (False, None))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert rc is None
    assert failure == "herdr pane split failed"
    assert _spool_dirs() == before


def test_bad_create_payload_leaves_no_spool(plugin, monkeypatch, tmp_path):
    """A payload missing the pane/workspace ids leaks the spool the same way."""
    monkeypatch.setattr(
        plugin, "_herdr", lambda *a, **k: (True, {"result": {"oops": True}}))
    before = _spool_dirs()

    rc, _, _, failure = plugin._run_in_pane(
        ["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    assert rc is None
    assert "unexpected payload" in failure
    assert _spool_dirs() == before


def test_create_failure_does_not_close_a_workspace(plugin, monkeypatch, tmp_path):
    """No workspace was created, so nothing must be closed."""
    calls: list = []

    def _failing(*args, timeout=30):
        calls.append(args)
        return False, None

    monkeypatch.setattr(plugin, "_herdr", _failing)

    plugin._run_in_pane(["opencode", "run", "x"], tmp_path, timeout=5, label="t")

    workspace_ids = {c[2] for c in calls if c[:2] == ("workspace", "close")}
    assert workspace_ids == set()


# --- handler-level shape ----------------------------------------------------


def test_handler_success_shape_through_the_pane(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    calls: list = []
    monkeypatch.setattr(
        plugin, "_herdr",
        _fake_herdr(calls, exit_code="0", stdout_text="OUT\n", stderr_text="ERR\n"))

    out = json.loads(plugin._handle_opencode_delegate(
        {"task": "do the thing", "workdir": str(tmp_path), "timeout": 5}))
    assert out["workdir"] == str(tmp_path)
    assert out["output"] == "OUT"
    assert out["stderr"] == "ERR"


def test_handler_nonzero_exit_is_a_tool_error(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    calls: list = []
    monkeypatch.setattr(
        plugin, "_herdr",
        _fake_herdr(calls, exit_code="7", stderr_text="failed hard\n"))

    out = json.loads(plugin._handle_opencode_delegate(
        {"task": "do the thing", "workdir": str(tmp_path), "timeout": 5}))
    assert out["error"] == "OpenCode exited 7"
    assert out["stderr"] == "failed hard"


def test_handler_pane_failure_is_a_tool_error_not_a_crash(
        plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_PANE_ID", "w9:p9")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/tmp/herdr.sock")
    monkeypatch.setattr(plugin, "_herdr", lambda *a, **k: (False, None))

    out = json.loads(plugin._handle_opencode_delegate(
        {"task": "do the thing", "workdir": str(tmp_path), "timeout": 5}))
    assert out["error"] == "herdr pane split failed"
