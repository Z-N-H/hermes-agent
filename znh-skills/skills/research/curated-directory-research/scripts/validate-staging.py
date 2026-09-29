#!/usr/bin/env python3
"""
Validate a curated-directory staging JSON in ONE pass.

Usage:
    python3 validate-staging.py research/tools-staging.json

Reads a top-level {"tools": [...], "category_totals": {...}} staging file (the
shape produced by the curated-directory-research workflow). Reports every
field-bar violation across all entries at once, so you fix them in one batch
instead of iterating one-per-fix (the tagline word-count is the most common
miss and the reason this script exists).

Exit code: 0 = all entries pass; 1 = one or more failures.
No DB / network access — purely a local shape+presence check.
"""

import json
import os
import sys

# ---- Configurable per directory project --------------------------------
ALLOWED_CATEGORIES = None  # e.g. {"accessibility", "session-recording"}
ALLOWED_PRICING = {"free", "freemium", "paid", "free_trial"}
REQUIRED_FIELDS = [
    "name",
    "slug",
    "category",
    "pricing",
    "tagline",
    "description",
    "website",
    "logo",
    "best_for",
    "key_features",
    "tags",
    "status",
    "featured",
    "featured_order",
    "initial",
    "card_color",
]
LOGO_DIR = "logos"  # relative to the staging file's directory
# ------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    base = os.path.dirname(os.path.abspath(path)) or "."
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    tools = data.get("tools", [])
    errors = []

    for t in tools:
        slug = t.get("slug", "?")
        for f in REQUIRED_FIELDS:
            if f not in t:
                errors.append(f"{slug}: missing field '{f}'")
        if "pricing" in t and t["pricing"] not in ALLOWED_PRICING:
            errors.append(f"{slug}: pricing '{t['pricing']}' not in {ALLOWED_PRICING}")
        if (
            ALLOWED_CATEGORIES is not None
            and "category" in t
            and t["category"] not in ALLOWED_CATEGORIES
        ):
            errors.append(f"{slug}: category '{t['category']}' not allowed")
        if "website" in t and not t["website"].startswith("https://"):
            errors.append(f"{slug}: website must start https:// -> {t.get('website')}")
        kf = t.get("key_features", [])
        if not (3 <= len(kf) <= 6):
            errors.append(f"{slug}: key_features has {len(kf)} (want 3..6)")
        tags = t.get("tags", [])
        if not (2 <= len(tags) <= 6):
            errors.append(f"{slug}: tags has {len(tags)} (want 2..6)")
        tl = t.get("tagline", "")
        n = len(str(tl).split())
        if not (8 <= n <= 14):
            errors.append(f"{slug}: tagline {n} words (want 8..14) -> {tl!r}")
        # logo path must resolve to a real file
        logo = t.get("logo", "")
        if logo:
            expect = f"logos/{t.get('slug', '?')}.{logo.split('.')[-1]}"
            if logo != expect:
                errors.append(f"{slug}: logo '{logo}' != expected '{expect}'")
            else:
                full = os.path.join(base, logo.split("/", 1)[-1])
                if not (os.path.isfile(full) and os.path.getsize(full) > 0):
                    errors.append(f"{slug}: logo file missing/empty {full}")

    # slug uniqueness within this file
    slugs = [t.get("slug") for t in tools]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    for s in dupes:
        errors.append(f"duplicate slug in file: {s}")

    if errors:
        print(f"FAIL: {len(errors)} issue(s) across {len(tools)} tools:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: {len(tools)} tools all pass field-bar checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
