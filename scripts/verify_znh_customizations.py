#!/usr/bin/env python3
"""Verify that znh/custom's customizations survived the last merge/pull.

A clean 3-way git merge can silently drop a customization with NO conflict
at all when upstream rewrites the surrounding code heavily enough — this
has already happened three times in this repo (TPS tracking, the
status-bar plugin hook, and the emoji-to-Nerd-Font icon system, all lost
in the 2026-07-30/31 upstream sync with zero conflict markers to flag it).

This script checks structural markers (not byte-identity, so it tolerates
legitimate upstream changes around them) for every known customization,
then runs the companion pytest files. Run it after every merge/pull into
znh/custom — it's also wired as .git/hooks/post-merge for that repo.

See: hermes_cli/skills/software-development/hermes-znh-custom-workflow/SKILL.md
     hermes_cli/skills/software-development/hermes-znh-custom-workflow/references/2026-07-31-main-merge-record.md
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class Check:
    def __init__(self, name: str, file: str, pattern: str, *, min_count: int = 1, flags: int = 0):
        self.name = name
        self.file = file
        self.pattern = pattern
        self.min_count = min_count
        self.flags = flags

    def run(self) -> tuple[bool, str]:
        path = REPO_ROOT / self.file
        if not path.is_file():
            return False, f"file missing: {self.file}"
        text = path.read_text(encoding="utf-8", errors="replace")
        count = len(re.findall(self.pattern, text, self.flags))
        if count < self.min_count:
            return False, f"{self.file}: expected >= {self.min_count} match(es) of {self.pattern!r}, found {count}"
        return True, f"{self.file}: {count} match(es) of {self.pattern!r}"


CHECKS: list[Check] = [
    # --- TPS tracking (run_agent.py / agent_init.py / chat_completion_helpers.py) ---
    Check("TPS: _record_tps_token defined", "run_agent.py", r"def _record_tps_token\("),
    Check("TPS: called from _fire_stream_delta/_fire_reasoning_delta", "run_agent.py",
          r"self\._record_tps_token\(", min_count=2),
    Check("TPS: state init in agent_init.py", "agent/agent_init.py", r"agent\._tps_token_count = 0"),
    Check("TPS: recorded on streamed content/tool-call args", "agent/chat_completion_helpers.py",
          r"agent\._record_tps_token\(", min_count=2),

    # --- status_bar_fragment plugin hook ---
    Check("status_bar_fragment hook invoked in cli.py", "cli.py",
          r'invoke_hook\(\s*\n?\s*"status_bar_fragment"'),
    Check("status_bar_fragment registered in VALID_HOOKS", "hermes_cli/plugins.py",
          r'"status_bar_fragment"'),

    # --- emoji -> Nerd Font icon system ---
    Check("hermes_icons.py module present", "hermes_icons.py", r"class NerdFontIcons"),
    Check("cli.py imports ICON_BOLT", "cli.py", r"from hermes_icons import ICON_BOLT"),
    Check("cli.py uses get_active_brand_icon (not hardcoded ⚕ everywhere)", "cli.py",
          r"get_active_brand_icon\(\)", min_count=10),
    Check("cli.py tuple-style prompt_toolkit patch", "cli.py",
          r"def _apply_prompt_toolkit_tuple_style_patch"),
    Check("agent/display.py imports hermes_icons", "agent/display.py",
          r"from hermes_icons import ICON_BOLT, ICON_GEAR, NerdFontIcons"),
    Check("agent/display.py get_tool_emoji defaults to ICON_BOLT", "agent/display.py",
          r"def get_tool_emoji\(tool_name: str, default: str = ICON_BOLT\)"),
    Check("agent/display.py get_cute_tool_message uses NerdFontIcons", "agent/display.py",
          r"NerdFontIcons\.get\(", min_count=20),
    Check("skin_engine.py defines get_active_brand_icon", "hermes_cli/skin_engine.py",
          r"def get_active_brand_icon\("),
    Check("skin_engine.py has status_bar_model skin color", "hermes_cli/skin_engine.py",
          r'"status_bar_model"', min_count=5),
    Check("tools/registry.py get_emoji defaults to ICON_BOLT", "tools/registry.py",
          r"def get_emoji\(self, name: str, default: str = ICON_BOLT\)"),
    Check("gateway/platforms/base.py tool-emoji default is ICON_GEAR", "gateway/platforms/base.py",
          r"get_tool_emoji\(event\.tool_name, default=ICON_GEAR\)"),
    Check("gateway/run.py tool-emoji default is ICON_GEAR", "gateway/run.py",
          r"get_tool_emoji\(tool_name, default=ICON_GEAR\)"),
    Check("hermes_cli/gateway.py uses get_active_brand_icon", "hermes_cli/gateway.py",
          r"get_active_brand_icon\(\)", min_count=2),
    Check("hermes_cli/main.py uses get_active_brand_icon", "hermes_cli/main.py",
          r"get_active_brand_icon\(\)", min_count=3),
    Check("hermes_cli/agent_import.py uses get_active_brand_icon", "hermes_cli/agent_import.py",
          r"get_active_brand_icon\(\)"),
    Check("hermes_cli/cli_billing_mixin.py uses get_active_brand_icon", "hermes_cli/cli_billing_mixin.py",
          r"get_active_brand_icon\(\)", min_count=3),

    # --- Other known custom commits (lighter existence checks) ---
    Check("Phoenix observability plugin present", "plugins/observability/phoenix/__init__.py",
          r"def register"),
    Check("ShellCheck security plugin present", "plugins/security/__init__.py",
          r"_get_shellcheck"),
    Check("Slack Block Kit rendering present", "plugins/platforms/slack/block_kit.py",
          r"def "),
]


def run_pytest() -> tuple[bool, str]:
    test_files = [
        "tests/test_hermes_icons.py",
        "tests/agent/test_display_emoji.py",
        "tests/tools/test_registry.py",
    ]
    existing = [f for f in test_files if (REPO_ROOT / f).is_file()]
    if not existing:
        return False, "no companion test files found"
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.is_file() else sys.executable
    result = subprocess.run(
        [python, "-m", "pytest", *existing, "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PATH": "/usr/bin:/bin"},
    )
    ok = result.returncode == 0
    tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-5:])
    return ok, tail


def main() -> int:
    import sys as _sys

    # --skip-tests: run only the structural checks, not the companion pytest
    # files. Needed in CI and any fresh clone: the icon tests import
    # data/nerdfonts/glyphnames.json, and `data/` is gitignored (upstream
    # .gitignore), so that file exists only on machines where it was fetched
    # by hand. The companion tests are run by the normal test suite anyway;
    # the structural checks are the part that catches dropped fork patches.
    skip_tests = "--skip-tests" in _sys.argv[1:]

    failures: list[str] = []
    print(f"Verifying znh/custom customizations in {REPO_ROOT} ...\n")

    for check in CHECKS:
        ok, detail = check.run()
        status = "OK  " if ok else "FAIL"
        print(f"[{status}] {check.name}")
        if not ok:
            print(f"       {detail}")
            failures.append(check.name)

    print()
    if skip_tests:
        print("Skipping companion tests (--skip-tests).")
    else:
        print("Running companion tests...")
        tests_ok, tail = run_pytest()
        print(f"[{'OK  ' if tests_ok else 'FAIL'}] companion pytest files")
        if not tests_ok:
            print(f"       {tail}")
            failures.append("companion pytest files")

    print()
    if failures:
        print(f"❌ {len(failures)} check(s) failed — a customization may have been silently")
        print("   dropped by the last merge/pull. See:")
        print("   hermes_cli/skills/software-development/hermes-znh-custom-workflow/SKILL.md")
        for name in failures:
            print(f"     - {name}")
        return 1

    suffix = "" if skip_tests else " + companion tests"
    print(f"\u2713 All {len(CHECKS)} customization checks{suffix} passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
