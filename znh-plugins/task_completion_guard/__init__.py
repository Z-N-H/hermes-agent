"""Task Completion Guard — blocks hallucinated Kanban 'ready-for-review'/'done' writes.

The sanctioned way to change an Obsidian Kanban card's status is
``vault_board.py`` (see the ``task-dispatch`` skill), which enforces a
cross-session completion-evidence gate and keeps the board in sync. Agent
completion only ever reaches ``ready-for-review`` through that path — ``done`` is a
manual promotion Zack makes by hand in Obsidian. This plugin is the
defence-in-depth layer for attempts that bypass ``vault_board.py``: it
vetoes any write_file/patch call that would hand-set a vault card's
``status`` to ``ready-for-review`` or ``done`` unless this session's own tool-call
history (in ``~/.hermes/state.db``) shows a successful, *confirmed-complete*
OpenCode delegation earlier in the same session, with evidence its workdir actually
changed.

Two things make this harder than "check exit_code == 0":

1. Per the mandatory CRITICAL_BOUNDARY_GUIDANCE dispatch pattern, `opencode
   run` is launched via `terminal(background=true, ..., notify_on_complete=
   true)`. The dispatching tool call's OWN result row is just a "Background
   process started" acknowledgment with a hardcoded `exit_code: 0` -- that is
   NOT OpenCode's real exit code, just proof the shell accepted the command.
   The real outcome only shows up later, as a `role='user'` synthetic
   message injected by process_registry.py's notification queue:
   "[IMPORTANT: Background process {proc_id} completed (exit code N)...]".
   Checking the dispatch call's own result (as an earlier version of this
   guard did) would treat every dispatch as "successful" the instant it
   *started*, regardless of whether OpenCode ever actually finished or what
   it did -- confirmed to be exactly how a real false-completion incident
   slipped through (OpenCode ran, produced an unrelated `ls -la` dump, exited
   0, and the then-current completion path took that as proof of work done).
2. Even a genuinely-exit-0 OpenCode run can be a no-op (reads files, reports
   "I'll make the changes", writes nothing). So a confirmed-complete,
   exit-0 delegation is necessary but not sufficient -- we also check that
   its workdir shows real change (git log/status), when the workdir is a
   git repo.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

CARD_PATH_RE = re.compile(r"TaskNotes/Tasks/[^/]+\.md$")
STATUS_GATED_RE = re.compile(r"status:\s*[\"']?(ready-for-review|done)[\"']?", re.IGNORECASE)
OPENCODE_RUN_RE = re.compile(r"\bopencode\s+run\b")
COMPLETION_NOTICE_RE = re.compile(
    r"Background process (\S+) completed \(exit code (-?\d+)\)"
)
TITLE_RE = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.MULTILINE)
CD_PREFIX_RE = re.compile(r"^\s*cd\s+(\S+)\s*&&")
_KEYWORD_STOPWORDS = {
    "this", "that", "with", "from", "into", "wire", "fix", "the", "and",
    "for", "add", "update", "remove", "build", "implement", "create",
    "using", "make", "task", "work", "card",
    # Domain words that appear in nearly every dispatch in this environment
    # (everything here touches the vault/pantheon/hermes/opencode stack) --
    # near-zero discriminative signal for telling one card's work apart from
    # another's, confirmed empirically: "obsidian" alone falsely correlated
    # two unrelated dispatches to an unrelated card in the same session.
    "obsidian", "vault", "pantheon", "hermes", "opencode", "agent",
}

_POINTER = (
    " Do not retry this file edit — the sanctioned path is "
    "`python3 /mnt/z/pantheon/vault/ZNH/scripts/vault_board.py` (complete/update), "
    "which enforces the evidence gate across sessions and only ever reaches "
    "`ready-for-review` (never `done` — Zack promotes that by hand). If you can't point "
    "at completed work, leave the card `in-progress` with a `blocker_reason` "
    "instead."
)

BLOCK_MESSAGES = {
    "not_invoked": (
        "TASK COMPLETION GUARD: This write would mark a Kanban card ready-for-review/done, "
        "but no OpenCode delegation (a `terminal` call running `opencode run ...`, "
        "or an `opencode_delegate` call) was found earlier in this session. "
        "Delegate the actual coding work to OpenCode first, then let "
        "vault_board.py mark it `ready-for-review`." + _POINTER
    ),
    "not_confirmed": (
        "TASK COMPLETION GUARD: An OpenCode delegation was dispatched in this "
        "session, but there is no confirmed-complete result for it yet (no "
        "'Background process ... completed' notification, and no successful "
        "opencode_delegate result). If it's still running, wait for it to finish "
        "before marking the card ready-for-review/done." + _POINTER
    ),
    "no_changes": (
        "TASK COMPLETION GUARD: OpenCode was dispatched and completed (exit code 0) "
        "in this session, but its workdir shows no git evidence of real changes "
        "(no new commit, no uncommitted changes). This matches a known failure "
        "mode where OpenCode runs but does nothing. Re-delegate with a tighter, "
        "more prescriptive brief rather than marking this card done." + _POINTER
    ),
}


def _targets_gated_card(tool_name: str, args: dict) -> bool:
    if tool_name not in ("write_file", "patch"):
        return False
    path = str(args.get("path") or "")
    if not CARD_PATH_RE.search(path):
        return False
    body = str(args.get("content") or args.get("new_string") or args.get("patch") or "")
    return bool(STATUS_GATED_RE.search(body))


_NOISE_FILENAMES = {"pantheonstatus.json"}


# Bounds how far past a dispatch's own timestamp a commit can land and still
# count as evidence for it -- without this, an unbounded `--since` window
# picks up completely unrelated changes made hours or days later (confirmed:
# the card's own filename, still git-tracked, reappears in every subsequent
# commit that merely rebuilds the board index, long after the incident).
_CHANGE_WINDOW_SECONDS = 3600


def _changed_paths_in_workdir(workdir: str, since_ts: float) -> "list[str] | None":
    """List file paths changed in `workdir`'s own subtree in the window after `since_ts`.

    Scoped via a `-- .` pathspec so a shared monorepo/vault repo doesn't let
    a sibling dispatch's changes count for this one. Returns None when
    `workdir` isn't inside a git repo, or git can't be run at all -- callers
    should trust the exit code alone in that case (most delegation workdirs
    in practice are git repos, so this covers the common case).
    """
    if not workdir:
        return None
    path = Path(workdir).expanduser()
    if not path.is_dir():
        return None
    try:
        toplevel = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if toplevel.returncode != 0:
            return None
        paths: list[str] = []
        status = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(path),
             "status", "--porcelain", "--", "."],
            capture_output=True, text=True, timeout=10,
        )
        if status.returncode == 0:
            for line in status.stdout.splitlines():
                if len(line) > 3:
                    paths.append(line[3:].strip())
        since_iso = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(since_ts))
        until_iso = time.strftime(
            "%Y-%m-%dT%H:%M:%S+0000", time.gmtime(since_ts + _CHANGE_WINDOW_SECONDS)
        )
        log = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(path), "log",
             f"--since={since_iso}", f"--until={until_iso}", "--name-only",
             "--format=", "--", "."],
            capture_output=True, text=True, timeout=10,
        )
        if log.returncode == 0:
            paths.extend(p for p in log.stdout.splitlines() if p.strip())
        return paths
    except (subprocess.SubprocessError, OSError):
        return None


def _workdir_has_relevant_changes(
    workdir: str, since_ts: float, card_words: set[str], card_path: str = ""
) -> bool:
    """Did real, task-relevant changes land in `workdir` shortly after `since_ts`?

    A repo-wide "did a commit happen" check is not enough here: this vault
    repo auto-commits on a 15-minute timer regardless of content (confirmed
    live -- every checkpoint commit in the incident's dispatch-to-completion
    window touched only `PantheonStatus.json`, a heartbeat file, yet a bare
    commit-existence check would have treated that as proof of real work).
    So beyond "workdir isn't a git repo" (trust the exit code, return True),
    changed paths must also (a) not be a known noise file, (b) not be the
    card file itself -- its own filename often shares words with its title,
    which would make the very "mark it done" write being gated trivially
    "prove" itself once committed -- and (c) overlap the card's title
    keywords, when we have any (same soft-correlation idea as
    `_text_matches_card`, applied to file paths instead of task text).
    """
    paths = _changed_paths_in_workdir(workdir, since_ts)
    if paths is None:
        return True
    card_name = Path(card_path).name.lower() if card_path else ""
    candidates = [
        p for p in paths
        if Path(p.strip('"')).name.lower() not in _NOISE_FILENAMES
        and Path(p.strip('"')).name.lower() != card_name
    ]
    if not candidates:
        return False
    if not card_words:
        return True
    path_words = set(re.findall(r"[a-zA-Z]{4,}", " ".join(candidates).lower()))
    return bool(card_words & path_words)


def _card_keywords(card_path: str) -> set[str]:
    """Significant words from the card's title, read fresh from disk.

    Best-effort correlation signal, not a hard boundary: a session that
    dispatches multiple unrelated tasks in parallel (confirmed to happen in
    practice -- 5 parallel `opencode run` dispatches for 5 different cards in
    one turn) must not let one unrelated success vouch for every card touched
    in that session. Empty on any read failure -- callers treat that as "no
    filtering available" and fall back to session-level trust rather than
    blocking everything.
    """
    try:
        text = Path(card_path).read_text(encoding="utf-8")
    except OSError:
        return set()
    m = TITLE_RE.search(text)
    if not m:
        return set()
    words = re.findall(r"[a-zA-Z]{4,}", m.group(1).lower())
    return {w for w in words if w not in _KEYWORD_STOPWORDS}


def _text_matches_card(task_text: str, card_words: set[str]) -> bool:
    if not card_words:
        return True  # couldn't extract a title -- don't filter, fall back to session-level trust
    text_words = set(re.findall(r"[a-zA-Z]{4,}", task_text.lower()))
    return bool(card_words & text_words)


def _verify_opencode_delegation(session_id: str, card_path: str = "") -> str:
    """Return "verified", or a key into BLOCK_MESSAGES describing why not."""
    if not session_id:
        return "not_invoked"
    db_path = get_hermes_home() / "state.db"
    if not db_path.exists():
        return "not_invoked"

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return "not_invoked"

    try:
        cur = con.cursor()
        cur.execute(
            "SELECT tool_calls FROM messages "
            "WHERE session_id = ? AND role = 'assistant' AND tool_calls IS NOT NULL",
            (session_id,),
        )
        card_words = _card_keywords(card_path) if card_path else set()
        dispatches: list[tuple[str, str, str, str]] = []  # (call_id, kind, workdir, task_text)
        for (tool_calls_json,) in cur.fetchall():
            try:
                calls = json.loads(tool_calls_json)
            except (TypeError, ValueError):
                continue
            for call in calls or []:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                arguments_raw = fn.get("arguments") or ""
                call_id = call.get("call_id") or call.get("id")
                if not call_id:
                    continue
                if name == "opencode_delegate":
                    try:
                        call_args = json.loads(arguments_raw)
                    except (TypeError, ValueError):
                        call_args = {}
                    workdir = str(call_args.get("workdir") or "")
                    task_text = str(call_args.get("task") or "")
                    dispatches.append((call_id, "opencode_delegate", workdir, task_text))
                elif name == "terminal" and OPENCODE_RUN_RE.search(arguments_raw):
                    try:
                        call_args = json.loads(arguments_raw)
                    except (TypeError, ValueError):
                        call_args = {}
                    task_text = str(call_args.get("command") or arguments_raw)
                    workdir = str(call_args.get("workdir") or "")
                    if not workdir:
                        cd_match = CD_PREFIX_RE.match(task_text)
                        if cd_match:
                            workdir = cd_match.group(1)
                    dispatches.append((call_id, "terminal", workdir, task_text))

        if not dispatches:
            return "not_invoked"

        call_ids = [d[0] for d in dispatches]
        placeholders = ",".join("?" for _ in call_ids)
        cur.execute(
            "SELECT tool_call_id, content, timestamp FROM messages "
            f"WHERE session_id = ? AND role = 'tool' AND tool_call_id IN ({placeholders})",
            (session_id, *call_ids),
        )
        dispatch_results: dict[str, tuple[dict, float]] = {}
        for tool_call_id, content, ts in cur.fetchall():
            if not content:
                continue
            try:
                parsed = json.loads(content)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                dispatch_results[tool_call_id] = (parsed, ts)

        # Every "[IMPORTANT: Background process ... completed (exit code N)...]"
        # notification landed in this session as a role='user' message --
        # mandatory since notify_on_complete=true is required for every dispatch.
        cur.execute(
            "SELECT content FROM messages "
            "WHERE session_id = ? AND role = 'user' AND content LIKE '%completed (exit code%'",
            (session_id,),
        )
        completions: dict[str, int] = {}
        for (content,) in cur.fetchall():
            if not content:
                continue
            for proc_id, exit_code in COMPLETION_NOTICE_RE.findall(content):
                try:
                    completions[proc_id] = int(exit_code)
                except ValueError:
                    continue

        saw_dispatch_without_confirmed_completion = False
        any_matched_card = False

        for call_id, kind, workdir, task_text in dispatches:
            if not _text_matches_card(task_text, card_words):
                continue
            any_matched_card = True
            result, result_ts = dispatch_results.get(call_id, (None, 0.0))
            if result is None:
                continue

            if kind == "opencode_delegate":
                if result.get("error"):
                    continue
                exit_ok = True  # synchronous call -- its own result is the real outcome
                since_ts = result_ts
                wd = str(result.get("workdir") or workdir)
            else:
                proc_id = result.get("session_id")
                if not proc_id or proc_id not in completions:
                    saw_dispatch_without_confirmed_completion = True
                    continue
                exit_ok = completions[proc_id] == 0
                since_ts = result_ts
                wd = workdir

            if not exit_ok:
                continue
            if _workdir_has_relevant_changes(wd, since_ts, card_words, card_path=card_path):
                return "verified"
            saw_dispatch_without_confirmed_completion = False  # confirmed-but-empty, more specific

        if not any_matched_card:
            return "not_invoked"
        if saw_dispatch_without_confirmed_completion:
            return "not_confirmed"
        return "no_changes"
    finally:
        con.close()


def on_pre_tool_call(
    tool_name: str,
    args: dict[str, Any],
    tool_call_id: str,
    task_id: str = "",
    session_id: str = "",
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Block a Kanban 'ready-for-review'/'done' write with no confirmed, evidenced OpenCode delegation."""
    if not _targets_gated_card(tool_name, args):
        return None
    verdict = _verify_opencode_delegation(session_id, card_path=str(args.get("path") or ""))
    if verdict == "verified":
        return None
    return {"action": "block", "message": BLOCK_MESSAGES[verdict]}


def register(ctx) -> None:
    """Register the pre_tool_call guard. Called once by the plugin loader."""
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
