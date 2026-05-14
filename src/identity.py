"""
identity.py - GamingTweaksAppliedIV identity

Single source of truth for repo URLs, install paths, and branding strings.
Every module that needs these imports from here instead of hardcoding them.

Zero internal GamingTweaksAppliedIV imports so it can be loaded first without
circular-dependency risk (same pattern as log.py).
"""

import os

# -- Identity ------------------------------------------------------------------

GITHUB_USER = "GalvarinoDev"

GITHUB_REPO = "LetsGoBowling"

GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main"

GITHUB_API = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"

# Local install directory name - no path, just the folder name
INSTALL_DIR_NAME = "GamingTweaksAppliedIV"

# Full install path
INSTALL_DIR = os.path.expanduser(f"~/{INSTALL_DIR_NAME}")

# Config and log paths
CONFIG_PATH = os.path.join(INSTALL_DIR, "gamingtweaksappliediv.json")
LOG_DIR = os.path.join(INSTALL_DIR, "logs")
LEDGER_PATH = os.path.join(INSTALL_DIR, "vdf_ledger.json")

# XDG paths (save backups, shared DLLs)
_XDG_ID = "gamingtweaksappliediv"

# Desktop entry paths
DESKTOP_FILE = os.path.expanduser(
    f"~/.local/share/applications/{_XDG_ID}.desktop"
)
DESKTOP_SHORTCUT_NAME = f"{INSTALL_DIR_NAME}.desktop"

# Venv python path
VENV_PYTHON = os.path.join(INSTALL_DIR, ".venv", "bin", "python3")

# -- UI branding --------------------------------------------------------------

APP_TITLE = "GamingTweaksAppliedIV"

# Build badge - set to a string to show a badge in the UI, None to hide
BUILD_BADGE = None

BUILD_HASH_FALLBACK = "stable"

DESKTOP_ENTRY_NAME = APP_TITLE
DESKTOP_ENTRY_COMMENT = f"{APP_TITLE} - GTA IV on SteamOS"

# -- GitHub raw asset URLs ----------------------------------------------------


def asset_url(path: str) -> str:
    """Build a raw GitHub URL for a repo asset.

    Usage:
        from identity import asset_url
        url = asset_url("assets/images/icon.png")
    """
    return f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/refs/heads/main/{path}"


def api_url(endpoint: str) -> str:
    """Build a GitHub API URL.

    Usage:
        from identity import api_url
        url = api_url("commits/main")
    """
    return f"{GITHUB_API}/{endpoint}"
