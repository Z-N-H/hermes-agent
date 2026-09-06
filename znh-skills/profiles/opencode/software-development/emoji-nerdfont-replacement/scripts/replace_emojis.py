#!/usr/bin/env python3
"""Bulk-replace emojis in Hermes Agent source files with Nerd Font PUA codepoints.

Usage:
    # 1. Fetch the authoritative codepoint list (v3.4.0 as of this writing)
    curl -sL https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/glyphnames.json \
         -o /tmp/nf.json

    # 2. Run the replacement
    python3 replace_emojis.py /tmp/nf.json /path/to/hermes-agent

What it does:
    - Loads `glyphnames.json` (the canonical Nerd Fonts codepoint list).
    - For each `(emoji, set, icon_name)` in ICON_MAP below, looks up the
      codepoint in the JSON and substitutes it into every matching file.
    - Walks the target tree, modifying `.py`, `.sh`, `.yaml`, `.yml` files
      in place.
    - Skips vendored deps, tests, messaging-platform adapters, and kaomoji
      data (see SKIP_PATH_PARTS).
    - Reports a per-file replacement count.

What it does NOT do:
    - Does not run tests. After this script, you must run pytest and
      update broken assertions (see SKILL.md pitfall 4).
    - Does not update documentation files (*.md, *.rst).
    - Does not touch personality text in `cli.py` containing kaomoji.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Mapping: (emoji, nf_set, icon_name)
# All icon names verified against Nerd Fonts v3.4.0 glyphnames.json.
# To add a new emoji: append to this list AND verify the icon name exists
# in the JSON. See references/nerdfont-codepoints.md for the full table.
# ---------------------------------------------------------------------------
ICON_MAP: list[tuple[str, str, str]] = [
    # Branding
    ("⚕", "fa", "stethoscope"),
    # Prompt / arrows
    ("❯", "fa", "chevron_right"),
    ("➜", "fa", "chevron_right"),
    ("➡", "fa", "arrow_right"),
    ("➕", "fa", "plus"),
    ("➖", "fa", "minus"),
    ("⏵", "fa", "play"),
    ("⏸", "fa", "pause"),
    ("⏹", "fa", "stop"),
    # Status
    ("✓", "fa", "check"),
    ("✅", "fa", "circle_check"),
    ("✗", "fa", "xmark"),
    ("❌", "fa", "circle_xmark"),
    ("⚠", "fa", "triangle_exclamation"),
    ("🚫", "fa", "ban"),
    ("🟡", "fa", "circle"),
    # Activity
    ("⚡", "fa", "bolt"),
    ("⚙", "fa", "gear"),
    ("🗜", "fa", "compress"),
    ("🔄", "fa", "arrows_rotate"),
    ("🔁", "fa", "arrows_rotate"),
    ("👁", "fa", "eye"),
    ("🔍", "fa", "magnifying_glass"),
    ("🔎", "fa", "magnifying_glass"),
    ("💾", "fa", "floppy_disk"),
    ("📞", "fa", "phone"),
    ("💬", "fa", "comment"),
    ("💭", "fa", "comment_dots"),
    ("💡", "fa", "lightbulb"),
    ("♻", "fa", "recycle"),
    ("✦", "fa", "star"),
    # Domain
    ("🤖", "md", "robot"),
    ("🔧", "fa", "screwdriver_wrench"),
    ("🛠", "fa", "screwdriver_wrench"),
    ("🌐", "fa", "globe"),
    ("🚀", "fa", "rocket"),
    ("🔒", "fa", "lock"),
    ("🔐", "fa", "lock"),
    ("💳", "fa", "credit_card"),
    ("💀", "fa", "skull"),
    ("💻", "fa", "laptop"),
    ("✍", "fa", "pen"),
    ("📸", "fa", "camera"),
    ("👆", "fa", "hand_pointer"),
    ("🖼", "fa", "image"),
    ("🎨", "fa", "palette"),
    ("📨", "fa", "envelope"),
    ("🐍", "fa", "python"),
    ("🔀", "fa", "shuffle"),
    # Documents
    ("📊", "fa", "chart_bar"),
    ("📈", "md", "trending_up"),
    ("📉", "md", "trending_down"),
    ("📋", "fa", "clipboard_list"),
    ("📝", "fa", "note_sticky"),
    ("📦", "fa", "box"),
    ("📁", "fa", "folder"),
    ("📂", "fa", "folder_open"),
    ("📚", "fa", "book"),
    ("📖", "fa", "book_open"),
    ("📄", "fa", "file_lines"),
    ("📎", "fa", "paperclip"),
    ("🧾", "fa", "receipt"),
    # Spinner / display elements
    ("🧠", "md", "brain"),
    ("💫", "fa", "star"),
    ("🏢", "fa", "building"),
    ("📐", "fa", "ruler_combined"),
    ("🔕", "fa", "bell_slash"),
    ("🔌", "fa", "plug"),
    ("🔗", "fa", "link"),
    ("🔑", "fa", "key"),
    ("🛡", "fa", "shield"),
    ("📱", "fa", "mobile_screen"),
    ("📅", "fa", "calendar"),
    ("🏆", "fa", "trophy"),
    # Misc
    ("🎲", "fa", "dice"),
    ("🎉", "md", "party_popper"),
    ("🎊", "md", "party_popper"),
    ("🎯", "fa", "bullseye"),
    ("✂", "fa", "scissors"),
    ("🔥", "fa", "fire"),
    ("💪", "fa", "dumbbell"),
    ("🤙", "fa", "hand_peace"),
    ("😤", "fa", "face_angry"),
    ("🤝", "fa", "handshake"),
    ("👋", "fa", "hand"),
    ("✨", "fa", "wand_sparkles"),
    ("⭐", "fa", "star"),
]

# Paths to skip (substring match against absolute path).
SKIP_PATH_PARTS: tuple[str, ...] = (
    "/venv/",
    "/.venv/",
    "/tests/",  # emoji in tests are test fixtures; fix them separately
    "/optional-skills/",
    "/node_modules/",
    "/.git/",
    "/site-packages/",
)


def load_lookups(glyph_json_path: Path) -> dict[tuple[str, str], str]:
    """Build (set, name) -> codepoint-hex lookup from the official JSON."""
    with open(glyph_json_path, encoding="utf-8") as f:
        raw = json.load(f)

    lookups: dict[tuple[str, str], str] = {}
    for k, v in raw.items():
        if k == "METADATA" or "-" not in k:
            continue
        set_, name = k.split("-", 1)
        lookups[(set_, name)] = v["code"]
    return lookups


def build_replacements(
    icon_map: list[tuple[str, str, str]],
    lookups: dict[tuple[str, str], str],
) -> list[tuple[str, str]]:
    """Resolve each (emoji, set, name) to (emoji, actual_character)."""
    out: list[tuple[str, str]] = []
    missing: list[str] = []
    for emoji, set_, name in icon_map:
        code = lookups.get((set_, name))
        if not code:
            missing.append(f"{set_}-{name}")
            continue
        ch = chr(int(code, 16))
        out.append((emoji, ch))

    if missing:
        print(
            f"WARNING: {len(missing)} icon names not in glyphnames.json "
            f"(likely renamed or never existed):",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
    return out


def build_pattern(replacements: list[tuple[str, str]]) -> re.Pattern:
    """Build a single regex matching any mapped emoji, with optional VS16."""
    # Order by length desc so multi-char emoji match first
    emoji_sorted = sorted(
        (e for e, _ in replacements),
        key=lambda s: (-len(s), s),
    )
    pattern_str = "|".join(re.escape(e) + "\ufe0f?" for e in emoji_sorted)
    return re.compile("(" + pattern_str + ")")


def replace_in_text(
    text: str,
    mapping: dict[str, str],
    pattern: re.Pattern,
) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        s = m.group(1)
        # Strip optional VS16 for lookup
        key = s.replace("\ufe0f", "")
        if key in mapping:
            count += 1
            return mapping[key]
        return s

    return pattern.sub(sub, text), count


def should_skip(path: Path, root: Path) -> bool:
    """Return True if this path should be left alone."""
    abs_str = str(path.resolve())
    if any(part in abs_str for part in SKIP_PATH_PARTS):
        return True
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True  # outside root
    parts = rel.parts
    # Skip outbound messaging adapters — they send emoji to other platforms.
    if "gateway" in parts and "platforms" in parts:
        return True
    if "plugins" in parts and "platforms" in parts:
        return True
    return False


def process_file(
    path: Path,
    root: Path,
    mapping: dict[str, str],
    pattern: re.Pattern,
) -> int:
    """Replace emojis in one file. Returns count."""
    if should_skip(path, root):
        return 0
    if path.suffix not in (".py", ".sh", ".yaml", ".yml", ".ts", ".tsx"):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0

    new_text, count = replace_in_text(text, mapping, pattern)
    if count > 0:
        path.write_text(new_text, encoding="utf-8")
        print(f"  [{count:4d}] {path.relative_to(root.parent)}")
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "glyph_json",
        type=Path,
        help="Path to nerd-fonts glyphnames.json (download from upstream)",
    )
    ap.add_argument(
        "root",
        type=Path,
        help="Path to hermes-agent (or another source tree) to modify",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Count matches without writing any files",
    )
    args = ap.parse_args()

    if not args.glyph_json.exists():
        print(f"ERROR: {args.glyph_json} not found", file=sys.stderr)
        print(
            "Download it with:\n"
            "  curl -sL https://raw.githubusercontent.com/ryanoasis/"
            "nerd-fonts/master/glyphnames.json -o /tmp/nf.json",
            file=sys.stderr,
        )
        return 1

    if not args.root.exists():
        print(f"ERROR: {args.root} not found", file=sys.stderr)
        return 1

    lookups = load_lookups(args.glyph_json)
    replacements = build_replacements(ICON_MAP, lookups)
    if not replacements:
        print("ERROR: no replacements resolved (icon names broken?)", file=sys.stderr)
        return 1

    mapping = dict(replacements)
    pattern = build_pattern(replacements)

    total_files = 0
    total_replacements = 0
    print(f"Processing {args.root} (dry_run={args.dry_run})...")

    for path in sorted(args.root.rglob("*")):
        if not path.is_file():
            continue
        if args.dry_run:
            if should_skip(path, args.root):
                continue
            if path.suffix not in (".py", ".sh", ".yaml", ".yml", ".ts", ".tsx"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            _, count = replace_in_text(text, mapping, pattern)
            if count > 0:
                print(f"  [{count:4d}] {path.relative_to(args.root.parent)}")
                total_files += 1
                total_replacements += count
        else:
            n = process_file(path, args.root, mapping, pattern)
            if n > 0:
                total_files += 1
                total_replacements += n

    print(f"\nFiles matched: {total_files}")
    print(f"Total replacements: {total_replacements}")

    if not args.dry_run:
        print(
            "\nNext steps:\n"
            "  1. python3 -m py_compile $(git diff --name-only | grep '\\.py$')\n"
            "  2. pytest tests/agent/test_display_emoji.py tests/cli/test_cli_status_bar.py\n"
            "  3. Restart `hermes` and visually verify the status bar.\n"
            "  4. If you see tofu boxes, install a Nerd Font in your terminal.\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
