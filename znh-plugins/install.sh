#!/usr/bin/env bash
# Link this directory's plugins into HERMES_HOME so Hermes can discover them.
#
# Why this exists: Hermes scans three roots for plugins (hermes_cli/plugins.py
# ~:1367-1395) -- the repo's own `plugins/` (source "bundled"),
# `$HERMES_HOME/plugins` (source "user"), and optionally a project dir. These
# plugins are Zack's, not upstream's, so they live here rather than in the
# repo's `plugins/`: that keeps upstream merges clean and keeps them correctly
# classified as `user` rather than masquerading as bundled.
#
# The scanner has no is_symlink() guard (unlike the platform loader at
# gateway/platforms/base.py:1271), so symlinking into HERMES_HOME is safe and
# leaves runtime behaviour byte-identical.
#
# Restore after a fresh clone:
#     ./znh-plugins/install.sh
#
# Idempotent. Existing correct symlinks are left alone; a real directory in the
# way is reported and skipped rather than clobbered -- if it has diverged, you
# want to look at it, not lose it.

set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/mnt/z/pantheon/.hermes}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HERMES_HOME/plugins"

mkdir -p "$DEST"

status=0
for path in "$SRC"/*/; do
    name="$(basename "$path")"
    target="$DEST/$name"

    if [[ -L "$target" ]]; then
        current="$(readlink -f "$target" || true)"
        if [[ "$current" == "$(readlink -f "$path")" ]]; then
            echo "ok       $name (already linked)"
            continue
        fi
        echo "relink   $name (pointed at $current)"
        rm "$target"
    elif [[ -e "$target" ]]; then
        echo "SKIP     $name -- a real directory is already there."
        echo "         Compare it against $path and remove it by hand if it is stale."
        status=1
        continue
    fi

    ln -s "$path" "$target"
    echo "linked   $name"
done

echo
echo "Verify with:  hermes plugins list"
echo "Each of these should read 'enabled' with source 'user'; anything listed"
echo "in config.yaml plugins.enabled that does not appear here is not loading."
exit "$status"
