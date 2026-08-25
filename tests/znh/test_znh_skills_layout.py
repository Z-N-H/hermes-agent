"""Layout and integrity checks for znh-skills/ (Zack's bespoke, fork-only skills).

znh-skills/ is the git-tracked source of truth for skills that previously
lived untracked under ``$HERMES_HOME/skills/`` (and the opencode profile's
own ``skills/``). They are served to Hermes via ``skills.external_dirs``
(see znh-skills/README.md), so a malformed capture breaks skill discovery at
runtime with no other safety net -- these checks are the safety net.

Run:  uv run pytest tests/znh/test_znh_skills_layout.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ZNH_SKILLS = REPO_ROOT / "znh-skills"

# Each root is registered (or, for archive/, linked) independently.
ACTIVE_ROOTS = (ZNH_SKILLS / "skills", ZNH_SKILLS / "profiles" / "opencode")
ARCHIVE_ROOT = ZNH_SKILLS / "archive"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _skill_mds(root: Path) -> list[Path]:
    assert root.is_dir(), f"missing znh-skills root: {root}"
    return sorted(root.rglob("SKILL.md"))


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    assert match, f"{skill_md}: no leading YAML frontmatter block"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict), f"{skill_md}: frontmatter is not a mapping"
    return data


def test_active_roots_have_expected_skill_counts() -> None:
    """50+ skills live here; a bad recursive copy that silently drops whole
    categories must fail loudly."""
    assert len(_skill_mds(ACTIVE_ROOTS[0])) == 60
    assert len(_skill_mds(ACTIVE_ROOTS[1])) == 11
    assert len(_skill_mds(ARCHIVE_ROOT)) == 10


@pytest.mark.parametrize("root", ACTIVE_ROOTS, ids=["main", "profile-opencode"])
def test_every_skill_has_parseable_frontmatter(root: Path) -> None:
    for skill_md in _skill_mds(root):
        fm = _frontmatter(skill_md)
        assert fm.get("name"), f"{skill_md}: frontmatter has no name"
        assert fm.get("description"), f"{skill_md}: frontmatter has no description"


@pytest.mark.parametrize("root", ACTIVE_ROOTS, ids=["main", "profile-opencode"])
def test_skill_names_unique_within_root(root: Path) -> None:
    """_find_all_skills dedups by name first-wins and skill_view refuses
    ambiguous bare names, so a collision inside one registration root is a
    silent shadow or a runtime error."""
    names = [_frontmatter(p)["name"] for p in _skill_mds(root)]
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate skill names in {root}: {dupes}"


# Deployed pre-capture with a dir/frontmatter-name mismatch; kept as-is because
# that is how the live profile already resolves it. Do not extend this list —
# fix the skill instead.
_NAME_MISMATCH_EXEMPT = {
    ZNH_SKILLS
    / "profiles"
    / "opencode"
    / "mlops"
    / "models"
    / "audiocraft"
    / "SKILL.md",
    ZNH_SKILLS
    / "profiles"
    / "opencode"
    / "mlops"
    / "models"
    / "segment-anything"
    / "SKILL.md",
}


def test_skill_dir_matches_frontmatter_name() -> None:
    """The install and retirement flows address skills by directory name; keep
    dir name == frontmatter name in the ACTIVE roots so nothing can drift
    apart. (The archive is exempt: it is never name-scanned, and e.g.
    audiocraft-audio-generation/SKILL.md is named 'audiocraft' inside.)"""
    for root in ACTIVE_ROOTS:
        for skill_md in _skill_mds(root):
            if skill_md in _NAME_MISMATCH_EXEMPT:
                continue
            fm_name = _frontmatter(skill_md)["name"]
            assert skill_md.parent.name == fm_name, (
                f"{skill_md}: dir name '{skill_md.parent.name}' != frontmatter name '{fm_name}'"
            )


def test_no_python_cache_or_vcs_garbage_committed() -> None:
    for junk in ZNH_SKILLS.rglob("*"):
        assert junk.name not in {"__pycache__", ".git", ".DS_Store"}, junk
        assert junk.suffix not in {".pyc", ".pyo"}, junk


def test_archive_never_scanned_as_active() -> None:
    """iter_skill_index_files prunes EXCLUDED_SKILL_DIRS ('.archive',
    '.git', ...). The live archive is linked at $HERMES_HOME/skills/.archive;
    assert the pruned-names constant still covers whatever directory name the
    symlink carries, so an upstream rename can't silently re-activate the
    whole archive."""
    from agent.skill_utils import EXCLUDED_SKILL_DIRS

    assert ".archive" in EXCLUDED_SKILL_DIRS


def test_installer_is_valid_bash() -> None:
    install = ZNH_SKILLS / "install.sh"
    result = subprocess.run(
        ["bash", "-n", str(install)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
