"""
console_visuals.py - Console Visuals installer for GetToAmericaIV

Downloads and installs modular Console Visuals packs from Tomasak's
GitHub releases, plus two supplementary mods from Internet Archive:
    - Higher Resolution Miscellaneous Pack (by Ash_735)
    - Vehicle Pack 2.0 - 15th Anniversary Edition (by Ash_735)

Console Visuals restores Xbox 360/PS3 assets to the PC version. It's
modular -- the user picks which packs to install. Each pack is a
separate zip containing an update/ folder that merges into the game
root via Fusion Overloader (requires FusionFix).

Note: Console HUD and TBoGT HUD Colors are mutually exclusive.
Console HUD has console sizing + TBoGT colors. TBoGT HUD Colors has
PC sizing with just the TBoGT color changes.

Usage:
    from console_visuals import (
        PACKS, install_pack, install_packs, uninstall_all,
        is_any_installed, get_latest_version,
    )

    version, assets = get_latest_version()
    success = install_packs(["anims", "vegetation", "hud"], game_root)
"""

import json
import os
import shutil
import tempfile
import urllib.request
import zipfile

import config as cfg
from log import get_logger
from net import download, DownloadError, BROWSER_UA

_log = get_logger(__name__)

# -- GitHub API ----------------------------------------------------------------

_GITHUB_USER = "Tomasak"
_GITHUB_REPO = "Console-Visuals"
_GITHUB_API  = f"https://api.github.com/repos/{_GITHUB_USER}/{_GITHUB_REPO}"

# We target the "latest" tag (stable release, currently 2.0.3c).
# The release page also has pre-releases (2.1) but we skip those.
_RELEASE_TAG = "latest"

# -- Pack definitions ----------------------------------------------------------
# key: internal name used in config and UI
# zip_name: asset filename on the GitHub release page
# label: human-readable name shown in the UI
# description: short description for the selection screen
# source: "github" or "archive" (Internet Archive)
# exclusive_with: list of pack keys this is mutually exclusive with

PACKS = {
    "anims": {
        "zip_name": "Console.Anims.zip",
        "label": "Console Animations",
        "description": "Restored console weapon and movement animations.",
        "source": "github",
        "exclusive_with": [],
    },
    "clothing": {
        "zip_name": "Console.Clothing.zip",
        "label": "Console Clothing",
        "description": "Console character models and suits with script edits.",
        "source": "github",
        "exclusive_with": [],
    },
    "fences": {
        "zip_name": "Console.Fences.zip",
        "label": "Console Fences",
        "description": "Restored console fence models.",
        "source": "github",
        "exclusive_with": [],
    },
    "hud": {
        "zip_name": "Console.HUD.zip",
        "label": "Console HUD",
        "description": "Console HUD sizing with TBoGT HUD colors.",
        "source": "github",
        "exclusive_with": ["tbogt_hud_colors"],
    },
    "loading_screens": {
        "zip_name": "Console.Loading.Screens.zip",
        "label": "Console Loading Screens",
        "description": "Console-style loading screens for GTA IV and TBoGT.",
        "source": "github",
        "exclusive_with": [],
    },
    "peds": {
        "zip_name": "Console.Peds.zip",
        "label": "Console Pedestrians",
        "description": "Restored console pedestrian models.",
        "source": "github",
        "exclusive_with": [],
    },
    "tbogt_hud_colors": {
        "zip_name": "Console.TBoGT.Hud.Colors.zip",
        "label": "TBoGT HUD Colors",
        "description": "PC HUD sizing with TBoGT HUD color scheme.",
        "source": "github",
        "exclusive_with": ["hud"],
    },
    "vegetation": {
        "zip_name": "Console.Vegetation.zip",
        "label": "Console Vegetation",
        "description": "Console trees and grass (fixes underground grass bug).",
        "source": "github",
        "exclusive_with": [],
    },
    "hi_res_misc": {
        "zip_name": "Higher Resolution Miscellaneous Pack v2.0-357-2-0-1735494802.zip",
        "label": "Higher Resolution Misc Pack",
        "description": "Higher res textures for props, minigames, interiors.",
        "source": "archive",
        "url": (
            "https://archive.org/download/optionalgtaivmods/"
            "Higher%20Resolution%20Miscellaneous%20Pack%20v2.0-357-2-0-1735494802.zip"
        ),
        "exclusive_with": [],
    },
    "vehicle_pack": {
        "zip_name": "1776555876_IV_CE_Vehicle_Pack2.4.zip",
        "label": "Vehicle Pack 2.4",
        "description": "Higher res vehicle textures from MP3/GTA5 assets.",
        "source": "archive",
        "url": (
            "https://archive.org/download/optionalgtaivmods/"
            "1776555876_IV_CE_Vehicle_Pack2.4.zip"
        ),
        "exclusive_with": [],
    },
}

# Recommended default packs -- a sensible starting selection
DEFAULT_PACKS = [
    "anims", "clothing", "fences", "hud", "loading_screens",
    "peds", "vegetation",
]


# -- Public API ----------------------------------------------------------------

def get_latest_version():
    """
    Query the GitHub API for the latest Console Visuals release.

    Returns (version_tag, asset_urls) where asset_urls is a dict mapping
    zip_name -> download_url for each asset found in the release.
    Returns (None, {}) if the API call fails.
    """
    try:
        url = f"{_GITHUB_API}/releases/tags/{_RELEASE_TAG}"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            **BROWSER_UA,
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))

        tag = data.get("tag_name")
        asset_urls = {}
        for asset in data.get("assets", []):
            name = asset.get("name")
            dl = asset.get("browser_download_url")
            if name and dl:
                asset_urls[name] = dl

        _log.info("console_visuals: latest release is %s (%d assets)",
                   tag, len(asset_urls))
        return tag, asset_urls

    except Exception:
        _log.warning("console_visuals: failed to query GitHub API",
                      exc_info=True)
        return None, {}


def install_pack(pack_key, game_root, asset_urls=None, on_progress=None):
    """
    Download and install a single Console Visuals pack.

    pack_key    -- key from PACKS dict (e.g. "anims", "vegetation")
    game_root   -- path to the GTAIV/ subfolder where GTAIV.exe lives
    asset_urls  -- optional dict of zip_name -> download_url from
                   get_latest_version(). Required for GitHub packs.
    on_progress -- optional callback(message: str)

    Returns True on success, False on error.
    Raises DownloadError if the download fails.
    """
    if pack_key not in PACKS:
        _log.error("console_visuals: unknown pack key: %s", pack_key)
        return False

    pack = PACKS[pack_key]
    label = pack["label"]
    zip_name = pack["zip_name"]

    # Resolve download URL
    if pack["source"] == "archive":
        dl_url = pack["url"]
    elif asset_urls and zip_name in asset_urls:
        dl_url = asset_urls[zip_name]
    else:
        # Build a direct URL from the release tag
        dl_url = (
            f"https://github.com/{_GITHUB_USER}/{_GITHUB_REPO}"
            f"/releases/download/{_RELEASE_TAG}/{zip_name}"
        )

    _log.info("console_visuals: installing %s from %s", label, dl_url)

    tmp_dir = tempfile.mkdtemp(prefix="gettoamericaiv_cv_")
    try:
        # Download
        zip_path = os.path.join(tmp_dir, zip_name)
        if on_progress:
            on_progress(f"Downloading {label}...")

        try:
            download(dl_url, zip_path, label=label)
        except Exception as e:
            raise DownloadError(
                url=dl_url,
                dest=zip_path,
                label=label,
                cause=e,
            )

        # Extract
        if on_progress:
            on_progress(f"Extracting {label}...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile:
            _log.error("console_visuals: corrupt zip: %s", zip_path)
            return False

        # Find the update/ folder in extracted content and merge it
        # into the game root. Some zips have update/ at top level,
        # others may have it nested one level down.
        if on_progress:
            on_progress(f"Installing {label}...")

        update_src = _find_update_dir(tmp_dir)
        if update_src:
            update_dst = os.path.join(game_root, "update")
            os.makedirs(update_dst, exist_ok=True)
            _merge_dirs(update_src, update_dst)
            _log.info("console_visuals: %s installed (merged update/)", label)
        else:
            # No update/ folder -- try copying everything except the zip
            # itself into the game root (some packs extract flat)
            _log.warning("console_visuals: no update/ folder found in %s, "
                          "copying all extracted content", label)
            for item in os.listdir(tmp_dir):
                if item == zip_name:
                    continue
                src = os.path.join(tmp_dir, item)
                dst = os.path.join(game_root, item)
                if os.path.isdir(src):
                    if os.path.isdir(dst):
                        _merge_dirs(src, dst)
                    else:
                        shutil.copytree(src, dst)
                elif os.path.isfile(src):
                    shutil.copy2(src, dst)

        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def install_packs(pack_keys, game_root, on_progress=None):
    """
    Download and install multiple Console Visuals packs.

    Queries the GitHub API once, then installs each pack in sequence.
    Saves the installed pack list and version to config on success.

    Returns a list of pack keys that were installed successfully.
    """
    # Check for mutual exclusions
    selected = set(pack_keys)
    for key in pack_keys:
        pack = PACKS.get(key)
        if not pack:
            continue
        for exc in pack.get("exclusive_with", []):
            if exc in selected:
                _log.warning(
                    "console_visuals: %s and %s are mutually exclusive, "
                    "skipping %s", key, exc, exc)
                selected.discard(exc)

    # Get GitHub asset URLs (one API call for all GitHub packs)
    version_tag, asset_urls = get_latest_version()

    installed = []
    for key in selected:
        try:
            ok = install_pack(key, game_root, asset_urls=asset_urls,
                              on_progress=on_progress)
            if ok:
                installed.append(key)
        except DownloadError:
            _log.error("console_visuals: download failed for %s", key)
            # Continue with remaining packs -- don't abort everything

    # Save state to config
    if installed:
        cfg.set_console_visuals_packs(installed)
        if version_tag:
            cfg.set_console_visuals_version(version_tag)

    _log.info("console_visuals: installed %d/%d packs", len(installed),
               len(selected))
    return installed


def uninstall_all(game_root):
    """
    Remove all Console Visuals content from the game.

    This is a best-effort operation. Console Visuals merges content
    into the shared update/ folder, so we can't selectively remove
    individual files without tracking every file from each pack.
    The safest approach is to remove the entire update/ folder and
    reinstall FusionFix (which recreates it with its own content).

    Returns True. Caller should reinstall FusionFix after this.
    """
    update_dir = os.path.join(game_root, "update")
    if os.path.isdir(update_dir):
        try:
            shutil.rmtree(update_dir)
            _log.info("console_visuals: removed update/ folder")
        except OSError:
            _log.warning("console_visuals: failed to remove update/")

    cfg.set_console_visuals_packs([])
    cfg.set_console_visuals_version(None)

    _log.info("console_visuals: uninstalled (update/ removed)")
    return True


def is_any_installed():
    """Check if any Console Visuals packs are recorded as installed."""
    return len(cfg.get_console_visuals_packs()) > 0


def get_installed_packs():
    """Return the list of installed pack keys from config."""
    return cfg.get_console_visuals_packs()


def get_installed_version():
    """Return the installed Console Visuals version from config, or None."""
    return cfg.get_console_visuals_version()


# -- Internal helpers ----------------------------------------------------------

def _find_update_dir(base_dir):
    """
    Search for an 'update' directory in the extracted content.
    Checks the base level first, then one level down.
    Returns the path if found, None otherwise.
    """
    # Check top level
    candidate = os.path.join(base_dir, "update")
    if os.path.isdir(candidate):
        return candidate

    # Check one level down (wrapping folder)
    for item in os.listdir(base_dir):
        sub = os.path.join(base_dir, item)
        if os.path.isdir(sub):
            candidate = os.path.join(sub, "update")
            if os.path.isdir(candidate):
                return candidate

    return None


def _merge_dirs(src, dst):
    """
    Recursively merge src directory into dst. Files in src overwrite
    files in dst with the same name. Subdirectories are merged
    recursively.
    """
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            if os.path.isdir(d):
                _merge_dirs(s, d)
            else:
                shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
