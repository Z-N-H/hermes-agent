"""Nerd Font icon library — single source of truth for Hermes UI glyphs.

Looks up Nerd Font Private Use Area codepoints by human-readable name, backed
by the upstream ``glyphnames.json`` (v3.4.0, 10,765 entries) committed at
``data/nerdfonts/glyphnames.json``. New code should reference icons by name
via ``NerdFontIcons.get("fa-check")`` instead of hardcoding raw ``\\uXXXX``
PUA escapes.

Back-compat module-level constants (``ICON_OK``, ``ICON_WARN``, ...) are kept
so existing ``from hermes_icons import ICON_OK`` imports keep working; they
are defined as aliases over ``NerdFontIcons.get()`` and produce byte-identical
values to the previous hardcoded codepoints.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class NerdFontIcons:
    """Single source of truth for Nerd Font icon lookups.

    The upstream ``glyphnames.json`` is parsed lazily on first access and
    cached for the life of the process. Each entry maps a full key
    (e.g. ``"fa-check"``, ``"md-robot"``) to the rendered Unicode character.
    """

    _json_path = Path(__file__).with_name("data") / "nerdfonts" / "glyphnames.json"
    _cache: dict[str, str] | None = None        # full-key -> character
    _by_emoji: dict[str, str] | None = None     # emoji -> full-key (for migration)
    _lock = threading.Lock()

    # Curated emoji -> Nerd Font key mapping used to build ``_by_emoji``.
    # This is intentionally hand-curated: there is no reliable way to derive
    # emoji-to-icon associations from glyphnames.json alone.
    _EMOJI_TO_KEY: dict[str, str] = {
        "\u2714": "fa-check",                   # ✔
        "\u2705": "fa-circle_check",            # ✅
        "\u274c": "fa-xmark",                   # ❌
        "\u26a0\ufe0f": "fa-triangle_exclamation",  # ⚠️
        "\u26a0": "fa-triangle_exclamation",    # ⚠ (no variation selector)
        "\U0001f6ab": "fa-ban",                 # 🚫
        "\u26a1": "fa-bolt",                    # ⚡
        "\u2699\ufe0f": "fa-gear",              # ⚙️
        "\u2699": "fa-gear",                    # ⚙
        "\U0001f4a0": "fa-compress",            # 💠
        "\U0001f504": "fa-arrows_rotate",       # 🔄
        "\U0001f441\ufe0f": "fa-eye",           # 👁️
        "\U0001f441": "fa-eye",                 # 👁
        "\U0001f50d": "fa-magnifying_glass",    # 🔍
        "\U0001f50e": "fa-magnifying_glass",    # 🔎
        "\U0001f4be": "fa-floppy_disk",         # 💾
        "\U0001f4de": "fa-phone",               # 📞
        "\U0001f4ac": "fa-comment",             # 💬
        "\U0001f916": "md-robot",               # 🤖
        "\U0001f527": "fa-screwdriver_wrench",  # 🔧
        "\U0001f310": "fa-globe",               # 🌐
        "\U0001f680": "fa-rocket",              # 🚀
        "\U0001f4ca": "fa-chart_bar",           # 📊
        "\U0001f4cb": "fa-clipboard_list",      # 📋
        "\U0001f4dd": "fa-note_sticky",         # 📝
        "\U0001f4e6": "fa-box",                 # 📦
        "\U0001f4c1": "fa-folder",              # 📁
        "\U0001f3b2": "fa-dice",                # 🎲
        "\U0001f3e0": "fa-house",                # 🏠
        "\U0001f3ac": "fa-film",                 # 🎬
        "\U0001f3a8": "fa-palette",              # 🎨
        "\U0001f493": "fa-heart",                # 💓
        "\U0001f4bb": "fa-laptop",               # 💻
        "\U0001f4c4": "fa-file",                  # 📄
        "\U0001f4d6": "fa-book_open",            # 📖
        "\U0001f4da": "fa-book",                 # 📚
        "\U0001f4dc": "fa-scroll",               # 📜
        "\U0001f4e8": "fa-envelope",            # 📨
        "\U0001f4f8": "fa-camera",               # 📸
        "\U0001f500": "fa-shuffle",              # 🔀
        "\U0001f50a": "fa-volume_high",          # 🔊
        "\U0001f517": "fa-link",                 # 🔗
        "\U0001f5a5\ufe0f": "fa-desktop",       # 🖥️
        "\U0001f5bc\ufe0f": "fa-image",          # 🖼️
        "\U0001f9ea": "fa-flask",               # 🧪
        "\U0001f9e0": "md-brain",                # 🧠
        "\U0001f40d": "fa-python",              # 🐍
        "\U0001f426": "fa-twitter",              # 🐦
        "\U0001f465": "fa-users",               # 👥
        "\u25c0\ufe0f": "fa-arrow_left",         # ◀️
        "\u25b6": "fa-play",                     # ▶
        "\u2328\ufe0f": "fa-keyboard",           # ⌨️
        "\u23f8\ufe0f": "fa-pause",              # ⏸
        "\u23f0": "fa-clock",                    # ⏰
        "\u270d\ufe0f": "fa-pen",                # ✍️
        "\u2709\ufe0f": "fa-envelope",          # ✉️
        "\u2795": "fa-plus",                    # ➕
        "\u2753": "fa-question",                # ❓
        "\u2191": "fa-arrow_up",                 # ↑
        "\u2193": "fa-arrow_down",               # ↓
        "\u2192": "fa-arrow_right",              # →
        "\u2190": "fa-arrow_left",               # ←
    }

    @classmethod
    def _load(cls) -> None:
        """Parse the JSON once and build the lookup tables (thread-safe)."""
        with cls._lock:
            if cls._cache is not None:
                return
            data = json.loads(cls._json_path.read_text(encoding="utf-8"))
            cache: dict[str, str] = {}
            for key, entry in data.items():
                if key == "METADATA":
                    continue
                if isinstance(entry, dict) and "char" in entry:
                    cache[key] = entry["char"]
            cls._cache = cache
            cls._by_emoji = dict(cls._EMOJI_TO_KEY)

    @classmethod
    def _reset(cls) -> None:
        """Clear the cached lookup tables (used by tests)."""
        with cls._lock:
            cls._cache = None
            cls._by_emoji = None

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """Lookup by full key, e.g. ``get('fa-check')`` -> ``''``."""
        if cls._cache is None:
            cls._load()
        assert cls._cache is not None
        return cls._cache.get(key, default)

    @classmethod
    def get_by_emoji(cls, emoji: str, default: str = "") -> str:
        """Reverse lookup: find the Nerd Font replacement for an emoji character."""
        if cls._by_emoji is None:
            cls._load()
        assert cls._by_emoji is not None
        key = cls._by_emoji.get(emoji)
        if key is None:
            return default
        return cls.get(key, default)

    @classmethod
    def find(cls, query: str) -> list[str]:
        """Fuzzy search by partial key name (case-insensitive substring match)."""
        if cls._cache is None:
            cls._load()
        assert cls._cache is not None
        q = query.lower()
        return [k for k in cls._cache if q in k.lower()]

    @classmethod
    def keys(cls) -> list[str]:
        """All available full keys (excludes the upstream METADATA block)."""
        if cls._cache is None:
            cls._load()
        assert cls._cache is not None
        return list(cls._cache)


# ---------------------------------------------------------------------------
# Back-compat aliases — byte-identical to the previous hardcoded codepoints.
# Existing ``from hermes_icons import ICON_OK`` imports keep working; future
# code should prefer ``NerdFontIcons.get("<key>")``.
# ---------------------------------------------------------------------------

# --- Branding ---
# Hermes brand icon — winged feather for the messenger.
ICON_BRAND = NerdFontIcons.get("fa-feather")             # nf-fa-feather

# --- Prompt / navigation ---
ICON_PROMPT = NerdFontIcons.get("fa-chevron_right")       # nf-fa-chevron_right
ICON_CHEVRON_RIGHT = NerdFontIcons.get("fa-chevron_right")

# --- Status / state ---
ICON_OK = NerdFontIcons.get("fa-check")                   # nf-fa-check
ICON_OK_CIRCLE = NerdFontIcons.get("fa-circle_check")     # nf-fa-circle_check
ICON_FAIL = NerdFontIcons.get("fa-xmark")                 # nf-fa-xmark
ICON_FAIL_CIRCLE = NerdFontIcons.get("fa-circle_xmark")   # nf-fa-circle_xmark
ICON_WARN = NerdFontIcons.get("fa-triangle_exclamation")  # nf-fa-triangle_exclamation
ICON_BAN = NerdFontIcons.get("fa-ban")                    # nf-fa-ban

# --- Activity / progress ---
ICON_BOLT = NerdFontIcons.get("fa-bolt")                  # nf-fa-bolt — TPS counter
ICON_GEAR = NerdFontIcons.get("fa-gear")                  # nf-fa-gear — background processes
ICON_COMPRESS = NerdFontIcons.get("fa-compress")          # nf-fa-compress — compressions
ICON_ROTATE = NerdFontIcons.get("fa-arrows_rotate")       # nf-fa-arrows_rotate
ICON_EYE = NerdFontIcons.get("fa-eye")                    # nf-fa-eye — vision/analyzing
ICON_MAGNIFY = NerdFontIcons.get("fa-magnifying_glass")   # nf-fa-magnifying_glass
ICON_FLOPPY = NerdFontIcons.get("fa-floppy_disk")         # nf-fa-floppy_disk
ICON_PHONE = NerdFontIcons.get("fa-phone")                # nf-fa-phone
ICON_COMMENT = NerdFontIcons.get("fa-comment")            # nf-fa-comment

# --- Domain icons ---
ICON_ROBOT = NerdFontIcons.get("md-robot")                # nf-md-robot
ICON_WRENCH = NerdFontIcons.get("fa-screwdriver_wrench")  # nf-fa-screwdriver_wrench
ICON_GLOBE = NerdFontIcons.get("fa-globe")                # nf-fa-globe
ICON_ROCKET = NerdFontIcons.get("fa-rocket")              # nf-fa-rocket

# --- Documents / collections ---
ICON_CHART = NerdFontIcons.get("fa-chart_bar")            # nf-fa-chart_bar
ICON_LIST = NerdFontIcons.get("fa-clipboard_list")        # nf-fa-clipboard_list
ICON_NOTE = NerdFontIcons.get("fa-note_sticky")           # nf-fa-note_sticky
ICON_BOX = NerdFontIcons.get("fa-box")                    # nf-fa-box
ICON_FOLDER = NerdFontIcons.get("fa-folder")              # nf-fa-folder

# --- Other ---
ICON_DICE = NerdFontIcons.get("fa-dice")                  # nf-fa-dice

ICON_HOUSE = NerdFontIcons.get("fa-house")
ICON_FILM = NerdFontIcons.get("fa-film")
ICON_PALETTE = NerdFontIcons.get("fa-palette")
ICON_HEART = NerdFontIcons.get("fa-heart")
ICON_LAPTOP = NerdFontIcons.get("fa-laptop")
ICON_FILE = NerdFontIcons.get("fa-file")
ICON_BOOK_OPEN = NerdFontIcons.get("fa-book_open")
ICON_BOOK = NerdFontIcons.get("fa-book")
ICON_SCROLL = NerdFontIcons.get("fa-scroll")
ICON_ENVELOPE = NerdFontIcons.get("fa-envelope")
ICON_CAMERA = NerdFontIcons.get("fa-camera")
ICON_SHUFFLE = NerdFontIcons.get("fa-shuffle")
ICON_VOLUME = NerdFontIcons.get("fa-volume_high")
ICON_LINK = NerdFontIcons.get("fa-link")
ICON_DESKTOP = NerdFontIcons.get("fa-desktop")
ICON_IMAGE = NerdFontIcons.get("fa-image")
ICON_FLASK = NerdFontIcons.get("fa-flask")
ICON_BRAIN = NerdFontIcons.get("md-brain")
ICON_PYTHON = NerdFontIcons.get("fa-python")
ICON_USERS = NerdFontIcons.get("fa-users")
ICON_PLAY = NerdFontIcons.get("fa-play")
ICON_CLOCK = NerdFontIcons.get("fa-clock")
ICON_ARROW_UP = NerdFontIcons.get("fa-arrow_up")
ICON_ARROW_DOWN = NerdFontIcons.get("fa-arrow_down")
ICON_ARROW_LEFT = NerdFontIcons.get("fa-arrow_left")
ICON_ARROW_RIGHT = NerdFontIcons.get("fa-arrow_right")


# Lookup table so we can also do reverse lookups in tests / tooling.
ICON_NAMES: dict[str, str] = {
    "brand": ICON_BRAND,
    "prompt": ICON_PROMPT,
    "ok": ICON_OK,
    "ok_circle": ICON_OK_CIRCLE,
    "fail": ICON_FAIL,
    "fail_circle": ICON_FAIL_CIRCLE,
    "warn": ICON_WARN,
    "ban": ICON_BAN,
    "bolt": ICON_BOLT,
    "gear": ICON_GEAR,
    "compress": ICON_COMPRESS,
    "rotate": ICON_ROTATE,
    "eye": ICON_EYE,
    "magnify": ICON_MAGNIFY,
    "floppy": ICON_FLOPPY,
    "phone": ICON_PHONE,
    "comment": ICON_COMMENT,
    "robot": ICON_ROBOT,
    "wrench": ICON_WRENCH,
    "globe": ICON_GLOBE,
    "rocket": ICON_ROCKET,
    "chart": ICON_CHART,
    "list": ICON_LIST,
    "note": ICON_NOTE,
    "box": ICON_BOX,
    "folder": ICON_FOLDER,
    "dice": ICON_DICE,
    "house": ICON_HOUSE,
    "film": ICON_FILM,
    "palette": ICON_PALETTE,
    "heart": ICON_HEART,
    "laptop": ICON_LAPTOP,
    "file": ICON_FILE,
    "book_open": ICON_BOOK_OPEN,
    "book": ICON_BOOK,
    "scroll": ICON_SCROLL,
    "envelope": ICON_ENVELOPE,
    "camera": ICON_CAMERA,
    "shuffle": ICON_SHUFFLE,
    "volume": ICON_VOLUME,
    "link": ICON_LINK,
    "desktop": ICON_DESKTOP,
    "image": ICON_IMAGE,
    "flask": ICON_FLASK,
    "brain": ICON_BRAIN,
    "python": ICON_PYTHON,
    "users": ICON_USERS,
    "play": ICON_PLAY,
    "clock": ICON_CLOCK,
    "arrow_up": ICON_ARROW_UP,
    "arrow_down": ICON_ARROW_DOWN,
    "arrow_left": ICON_ARROW_LEFT,
    "arrow_right": ICON_ARROW_RIGHT,
}
