#!/usr/bin/env bash
# Register this directory's bespoke skills with Hermes via skills.external_dirs.
#
# Why external_dirs and not symlinks (the znh-plugins/ pattern): Hermes has a
# native config for extra skill roots (agent/skill_utils.py
# get_external_skills_dirs), and this home already uses it for
# .pantheon/agent_context/skills. External dirs are scanned with
# local-then-external name dedup (tools/skills_tool.py _find_all_skills),
# count as trusted so skill_view logs no "outside trusted skills directory"
# warning, and are explicitly out of the Curator's jurisdiction ("DO NOT touch
# bundled, hub-installed, or external-dir skills", agent/curator.py ~:434) --
# which is exactly what you want once git is the source of truth.
#
# The .archive/ of restorable-deactivated skills is not scanned at all
# (EXCLUDED_SKILL_DIRS), so it is linked back into $HERMES_HOME/skills/.archive
# as a plain symlink to keep Curator restore flows working in place.
#
# Restore after a fresh clone:
#     ./znh-skills/install.sh
#
# Idempotent. Already-correct config entries and symlinks are left alone; a
# real directory or file in the way is reported and skipped, not clobbered.
# The config patcher is line-based -- it adds exactly one list item (or one
# block, if skills.external_dirs is absent) and leaves the rest of the file,
# comments included, byte-identical.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/mnt/z/pantheon/.hermes}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

status=0

# --- external_dirs registration -------------------------------------------
register_external_dir() {
    local config="$1" dir="$2" label="$3"
    if [[ ! -f "$config" ]]; then
        echo "SKIP     $label -- $config does not exist"
        status=1
        return
    fi
    uv run python - "$config" "$dir" "$label" <<'PY'
import re
import shutil
import sys
from pathlib import Path

config = Path(sys.argv[1])
ext_dir, label = sys.argv[2], sys.argv[3]
lines = config.read_text().splitlines(keepends=True)

if any(ext_dir in ln for ln in lines):
    print(f"ok       {label} (already registered)")
    sys.exit(0)

def indent_of(ln):
    return len(ln) - len(ln.lstrip())

# Locate the top-level `skills:` block.
sk_i = next((i for i, ln in enumerate(lines)
             if re.match(r"^skills:\s*(#.*)?$", ln)), None)

new_item = f"  - {ext_dir}\n"
if sk_i is None:
    patch = lines + [f"skills:\n  external_dirs:\n    - {ext_dir}\n"]
else:
    block_end = next((i for i in range(sk_i + 1, len(lines))
                      if lines[i].strip() and indent_of(lines[i]) == 0),
                     len(lines))
    ed_i = next((i for i in range(sk_i + 1, block_end)
                 if re.match(r"^\s+external_dirs:\s*(#.*)?$", lines[i])), None)
    if ed_i is None:
        patch = (lines[:sk_i + 1]
                 + [f"  external_dirs:\n    - {ext_dir}\n"]
                 + lines[sk_i + 1:])
    else:
        item_indent = indent_of(lines[ed_i]) + 2
        last = ed_i
        for i in range(ed_i + 1, block_end):
            if re.match(rf"^\s{{{item_indent}}}- ", lines[i]):
                last = i
            elif lines[i].strip() and indent_of(lines[i]) <= indent_of(lines[ed_i]):
                break
        new_item = f"{' ' * item_indent}- {ext_dir}\n"
        patch = lines[:last + 1] + [new_item] + lines[last + 1:]

backup = config.with_name(config.name + ".bak-znh-skills")
if not backup.exists():
    shutil.copy2(config, backup)
config.write_text("".join(patch))
print(f"added    {label}")
PY
}

register_external_dir "$HERMES_HOME/config.yaml" "$SRC/skills" "external_dirs (main home)"

PROFILE_CONFIG="$HERMES_HOME/profiles/opencode/config.yaml"
if [[ -f "$PROFILE_CONFIG" ]]; then
    register_external_dir "$PROFILE_CONFIG" "$SRC/profiles/opencode" "external_dirs (opencode profile)"
fi

# --- .archive symlink ------------------------------------------------------
ARCHIVE_TARGET="$HERMES_HOME/skills/.archive"
if [[ -L "$ARCHIVE_TARGET" ]]; then
    current="$(readlink -f "$ARCHIVE_TARGET" || true)"
    if [[ "$current" == "$(readlink -f "$SRC/archive")" ]]; then
        echo "ok       .archive (already linked)"
    else
        echo "relink   .archive (pointed at $current)"
        rm "$ARCHIVE_TARGET"
        ln -s "$SRC/archive" "$ARCHIVE_TARGET"
    fi
elif [[ -d "$ARCHIVE_TARGET" ]]; then
    if diff -r --exclude=__pycache__ "$ARCHIVE_TARGET" "$SRC/archive" >/dev/null 2>&1; then
        mv "$ARCHIVE_TARGET" "${ARCHIVE_TARGET}.pre-znh-skills-bak"
        ln -s "$SRC/archive" "$ARCHIVE_TARGET"
        echo "linked   .archive (identical real dir moved to .pre-znh-skills-bak)"
    else
        echo "SKIP     .archive -- a real directory is already there and DIFFERS."
        echo "         Compare it against $SRC/archive and resolve by hand."
        status=1
    fi
elif [[ -e "$ARCHIVE_TARGET" ]]; then
    echo "SKIP     .archive -- unexpected non-directory at $ARCHIVE_TARGET"
    status=1
else
    mkdir -p "$HERMES_HOME/skills"
    ln -s "$SRC/archive" "$ARCHIVE_TARGET"
    echo "linked   .archive"
fi

echo
echo "Verify with:  hermes skills list"
echo "Every skill under znh-skills/skills should appear once with its usual"
echo "category; nothing under znh-skills/archive should appear at all."
exit "$status"
