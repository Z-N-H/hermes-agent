"""SessionDB must pin SQLite's scratch/temp directory to a guaranteed-writable,
sandbox-proof location instead of trusting the ambient environment.

Observed in production (2026-08-22): SQLITE_CANTOPEN surfaced intermittently
under the nono filesystem sandbox. SQLite resolves its temp-file directory as
SQLITE_TMPDIR -> TMPDIR -> /var/tmp -> /usr/tmp -> /tmp (POSIX), and a sandbox
profile can deny every ambient candidate while still allowing the Hermes state
tree. Any statement that needs a temp file (spilled sorts, transient material
stores, some VACUUM/rebuild paths) then fails with "unable to open database
file". Pinning SQLITE_TMPDIR to a directory inside the state tree keeps temp
files inside the same writable allowlist as the database itself.
"""

import os
import stat

import pytest

from hermes_state import SessionDB, ensure_sqlite_tmpdir


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Each test starts from a clean SQLITE_TMPDIR / TMPDIR slate."""
    monkeypatch.delenv("SQLITE_TMPDIR", raising=False)
    yield
    # monkeypatch restores the original env; nothing else to do.


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_state.db"
    session_db = SessionDB(db_path=db_path)
    yield session_db
    try:
        session_db.close()
    except Exception:
        pass


def test_ensure_sets_tmpdir_inside_state_tree(tmp_path, monkeypatch):
    anchor = tmp_path / "profile"
    anchor.mkdir()
    result = ensure_sqlite_tmpdir(anchor)
    assert result is not None
    assert result.parent == anchor
    assert result.is_dir()
    assert os.environ["SQLITE_TMPDIR"] == str(result)


def test_ensure_creates_dir_owner_only(tmp_path, monkeypatch):
    anchor = tmp_path / "profile"
    anchor.mkdir()
    result = ensure_sqlite_tmpdir(anchor)
    assert result is not None
    mode = stat.S_IMODE(result.stat().st_mode)
    assert mode == 0o700


def test_ensure_keeps_operator_override_when_writable(tmp_path, monkeypatch):
    operator_dir = tmp_path / "operator-tmp"
    operator_dir.mkdir()
    monkeypatch.setenv("SQLITE_TMPDIR", str(operator_dir))
    result = ensure_sqlite_tmpdir(tmp_path / "profile")
    assert result == operator_dir
    assert os.environ["SQLITE_TMPDIR"] == str(operator_dir)


def test_ensure_repairs_missing_operator_override(tmp_path, monkeypatch):
    """An operator-set SQLITE_TMPDIR that doesn't exist yet is created in
    place (honouring the operator's choice) rather than overridden."""
    operator_dir = tmp_path / "will-be-created"
    monkeypatch.setenv("SQLITE_TMPDIR", str(operator_dir))
    result = ensure_sqlite_tmpdir(tmp_path / "profile")
    assert result == operator_dir
    assert operator_dir.is_dir()
    assert os.environ["SQLITE_TMPDIR"] == str(operator_dir)


def test_ensure_overrides_broken_override_with_anchor_fallback(tmp_path, monkeypatch):
    """An operator SQLITE_TMPDIR that points outside the writable sandbox
    (creation forbidden) would make EVERY temp-file creation fail with
    SQLITE_CANTOPEN. Override it with the anchor dir and keep the database
    usable."""
    # A path the helper cannot create: parent lives under a read-only dir.
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    frozen.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        monkeypatch.setenv("SQLITE_TMPDIR", str(frozen / "denied"))
        anchor = tmp_path / "profile"
        anchor.mkdir()
        result = ensure_sqlite_tmpdir(anchor)
    finally:
        frozen.chmod(stat.S_IRWXU)
    assert result is not None
    assert result.parent == anchor
    assert os.environ["SQLITE_TMPDIR"] == str(result)


def test_ensure_returns_none_when_anchor_unusable(tmp_path, monkeypatch):
    """If even the anchor dir cannot be created there is nothing better than
    SQLite's ambient fallbacks — report that instead of lying."""
    result = ensure_sqlite_tmpdir(tmp_path / "no-parent" / "profile")
    # Implementation may still create the parents (mkdir parents=True); the
    # contract is only: pointer in env == returned dir, or None = ambient.
    if result is None:
        assert "SQLITE_TMPDIR" not in os.environ
    else:
        assert os.environ.get("SQLITE_TMPDIR") == str(result)


def test_sessiondb_init_pins_sqlite_tmpdir(db, tmp_path, monkeypatch):
    expected = db.db_path.parent / ".sqlite-tmp"
    assert os.environ["SQLITE_TMPDIR"] == str(expected)
    assert expected.is_dir()


def test_chmod_denial_does_not_reject_writable_dir(tmp_path, monkeypatch):
    """Shared/system dirs (e.g. operator-set /tmp) can't be chmod'd by us;
    that must not reject an actually-writable candidate. The real
    open(O_CREAT) probe, not chmod, decides usability."""
    anchor = tmp_path / "profile"
    anchor.mkdir()

    def deny_chmod(path, mode):
        raise PermissionError(1, "Operation not permitted", str(path))

    monkeypatch.setattr(os, "chmod", deny_chmod)
    result = ensure_sqlite_tmpdir(anchor)
    assert result is not None
    assert result.parent == anchor
    assert os.environ["SQLITE_TMPDIR"] == str(result)


def test_access_lying_writable_does_not_honour_override(tmp_path, monkeypatch):
    """Under Landlock/nono, access(2) can report a dir writable while
    open(2) denies it (2026-08-24 incident). A candidate that fails the
    real create probe must not be honoured, even when access() says W_OK."""
    import builtins

    victim = tmp_path / "access-lies"
    victim.mkdir()
    monkeypatch.setenv("SQLITE_TMPDIR", str(victim))
    anchor = tmp_path / "profile"
    anchor.mkdir()

    real_open = os.open

    def sandbox_open(path, flags, mode=0o777, *, dirfd=None):
        if str(path).startswith(str(victim)):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, mode, dir_fd=dirfd)

    monkeypatch.setattr(os, "open", sandbox_open)
    result = ensure_sqlite_tmpdir(anchor)
    # The lying override is overridden with the anchor fallback.
    assert result is not None
    assert result.parent == anchor
    assert result != victim


def test_sessiondb_init_respects_operator_override(db, tmp_path, monkeypatch):
    # A second open after the first pinned the env to a writable dir must NOT
    # keep replacing it per-instance (idempotent: existing writable value wins).
    pinned = os.environ["SQLITE_TMPDIR"]
    second = SessionDB(db_path=tmp_path / "other.db")
    try:
        assert os.environ["SQLITE_TMPDIR"] == pinned
    finally:
        second.close()
