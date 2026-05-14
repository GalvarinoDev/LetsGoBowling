"""
bootstrap.py - GetToAmericaIV pre-launch asset checker

Verifies that bundled assets (font, grid images) are present before the
PyQt5 UI initialises. Called from BootstrapScreen on a background thread
so the UI can show progress.

GTA IV is on Steam (appid 12210) so we don't need non-Steam shortcut
grid art in the same way DeckOps or NFSBlacklist does. Grid art is only
needed if we create non-Steam shortcuts for own-game installs.

Orbitron variable font is bundled at assets/fonts/Orbitron-VariableFont_wght.ttf.

Music is NOT downloaded here. If assets/music/background.mp3 is present
it will be played automatically.
"""

import os

# -- Paths ---------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
MUSIC_DIR    = os.path.join(PROJECT_ROOT, "assets", "music")

os.makedirs(FONTS_DIR,   exist_ok=True)
os.makedirs(HEADERS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR,   exist_ok=True)

# -- Font ----------------------------------------------------------------------
# Orbitron is shipped with the repo in assets/fonts/ - no download needed.

FONT_FILE = "Orbitron-VariableFont_wght.ttf"

# -- Grid images ---------------------------------------------------------------
# Grid art for non-Steam shortcuts. One image per game key.
# Only needed for own-game installs that get added as non-Steam shortcuts.

HEADER_KEYS = ["gtaiv"]


# -- Public API ----------------------------------------------------------------

def run(on_progress=None, on_complete=None):
    """Check that all required assets are present.

    Since all assets are bundled (no downloads), this is just a verification
    pass. It reports what's present and what's missing.
    """
    if on_progress is None:
        on_progress = lambda pct, msg: print(f"[{pct:3d}%] {msg}")
    if on_complete is None:
        on_complete = lambda ok: None

    failed = 0

    # Font check
    font_path = os.path.join(FONTS_DIR, FONT_FILE)
    if os.path.exists(font_path):
        on_progress(10, f"Font: {FONT_FILE} (ok)")
    else:
        on_progress(10, f"Font: {FONT_FILE} (missing)")
        failed += 1

    # Grid image checks
    total_images = len(HEADER_KEYS)
    for i, key in enumerate(HEADER_KEYS):
        img_path = os.path.join(HEADERS_DIR, f"{key}_grid.jpg")
        pct = 10 + int((i + 1) / total_images * 80)
        if os.path.exists(img_path):
            on_progress(pct, f"Grid: {key}_grid.jpg (ok)")
        else:
            on_progress(pct, f"Grid: {key}_grid.jpg (missing)")
            # Not a hard failure - grid images are nice to have but
            # the app works without them. Don't increment failed.

    on_progress(100, "Assets ready.")
    on_complete(failed == 0)


def fonts_ready() -> bool:
    """Returns True if the bundled Orbitron font file is present on disk."""
    return os.path.exists(os.path.join(FONTS_DIR, FONT_FILE))


def headers_ready() -> bool:
    """Returns True if all grid images are present."""
    return all(
        os.path.exists(os.path.join(HEADERS_DIR, f"{key}_grid.jpg"))
        for key in HEADER_KEYS
    )


def all_ready() -> bool:
    return fonts_ready() and headers_ready()
