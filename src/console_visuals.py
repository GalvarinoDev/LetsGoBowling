"""
console_visuals.py - GamingTweaksAppliedIV visual mods installer

Downloads and installs modular visual packs via Fusion Overloader from:
  - Tomasak's Console Visuals (GitHub)
  - Ash_735's texture packs (Internet Archive)
  - Attramet's restoration mods (Internet Archive)

All packs install by merging an update/ folder into the game root.
FusionFix must be installed first (provides Fusion Overloader).

Note: Console HUD and TBoGT HUD Colors are mutually exclusive.
Console HUD has console sizing + TBoGT colors. TBoGT HUD Colors has
PC sizing with just the TBoGT color changes.

Usage:
    from console_visuals import (
        PACKS, install_pack, install_packs, uninstall_all,
        is_any_installed, get_latest_version,
        apply_props_compat_patches,
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

# -- Internet Archive base URLs ------------------------------------------------

_IA_ASH735 = "https://archive.org/download/optionalgtaivmods/"
_IA_ATTRAMET = "https://archive.org/download/various-gta-iv-attramets-workshop/"

# -- Pack definitions ----------------------------------------------------------
# key: internal name used in config and UI
# zip_name: asset filename on the GitHub release page or Internet Archive
# label: human-readable name shown in the UI
# description: short description for the selection screen
# source: "github" or "archive" (Internet Archive)
# exclusive_with: list of pack keys this is mutually exclusive with
# group: UI grouping identifier (used by ModSelectScreen)

PACKS = {
    # -- Console Visuals (Tomasak, GitHub) -------------------------------------
    "anims": {
        "zip_name": "Console.Anims.zip",
        "label": "Console Animations",
        "description": "Restored console weapon and movement animations.",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    "clothing": {
        "zip_name": "Console.Clothing.zip",
        "label": "Console Clothing",
        "description": "Console character models and suits with script edits.",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    "fences": {
        "zip_name": "Console.Fences.zip",
        "label": "Console Fences",
        "description": "Restored console fence models.",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    "hud": {
        "zip_name": "Console.HUD.zip",
        "label": "Console HUD",
        "description": "Console HUD sizing with TBoGT HUD colors.",
        "source": "github",
        "exclusive_with": ["tbogt_hud_colors"],
        "group": "hud_options",
    },
    "loading_screens": {
        "zip_name": "Console.Loading.Screens.zip",
        "label": "Console Loading Screens",
        "description": "Console-style loading screens for GTA IV and TBoGT.",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    "peds": {
        "zip_name": "Console.Peds.zip",
        "label": "Console Pedestrians",
        "description": "Restored console pedestrian models.",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    "tbogt_hud_colors": {
        "zip_name": "Console.TBoGT.Hud.Colors.zip",
        "label": "TBoGT HUD Colors",
        "description": "PC HUD sizing with TBoGT HUD color scheme.",
        "source": "github",
        "exclusive_with": ["hud"],
        "group": "hud_options",
    },
    "vegetation": {
        "zip_name": "Console.Vegetation.zip",
        "label": "Console Vegetation",
        "description": "Console trees and grass (fixes underground grass bug).",
        "source": "github",
        "exclusive_with": [],
        "group": "console_visuals",
    },
    # -- Texture Packs (Ash_735, Internet Archive) -----------------------------
    "hi_res_misc": {
        "zip_name": "Higher Resolution Miscellaneous Pack v2.0-357-2-0-1735494802.zip",
        "label": "Higher Resolution Misc Pack",
        "description": "Higher res textures for props, minigames, interiors.",
        "source": "archive",
        "url": (
            _IA_ASH735
            + "Higher%20Resolution%20Miscellaneous%20Pack%20v2.0-357-2-0-1735494802.zip"
        ),
        "exclusive_with": [],
        "group": "texture_packs",
    },
    "vehicle_pack": {
        "zip_name": "1776555876_IV_CE_Vehicle_Pack2.4.zip",
        "label": "Vehicle Pack 2.4",
        "description": "Higher res vehicle textures from MP3/GTA5 assets.",
        "source": "archive",
        "url": (
            _IA_ASH735
            + "1776555876_IV_CE_Vehicle_Pack2.4.zip"
        ),
        "exclusive_with": [],
        "group": "texture_packs",
    },
    # -- Attramet's Workshop (Internet Archive) --------------------------------
    "restored_pedestrians": {
        "zip_name": "Restored Pedestrians 2.0.zip",
        "label": "Restored Pedestrians",
        "description": (
            "Restores 18+ unused pedestrians with assets and fixes. "
            "Large download (~112 MB)."
        ),
        "source": "archive",
        "url": (
            _IA_ATTRAMET
            + "Restored%20Pedestrians%202.0.zip"
        ),
        "exclusive_with": [],
        "group": "attramet",
    },
    "various_ped_actions": {
        "zip_name": "Various Pedestrian Actions.zip",
        "label": "Various Pedestrian Actions",
        "description": (
            "Adds, corrects, and completes unfinished pedestrian "
            "actions (drinking, reading, ice cream, etc.)."
        ),
        "source": "archive",
        "url": (
            _IA_ATTRAMET
            + "Various%20Pedestrian%20Actions.zip"
        ),
        "exclusive_with": [],
        "group": "attramet",
    },
    "more_visible_interiors": {
        "zip_name": "More Visible Interiors.zip",
        "label": "More Visible Interiors",
        "description": (
            "Makes building interiors visible from the street. "
            "Minor pop-in possible."
        ),
        "source": "archive",
        "url": (
            _IA_ATTRAMET
            + "More%20Visible%20Interiors.zip"
        ),
        "exclusive_with": [],
        "group": "attramet",
    },
    "props_restoration": {
        "zip_name": "Props Restoration.zip",
        "label": "Props Restoration",
        "description": (
            "Restores beta, unused, and removed props to the map."
        ),
        "source": "archive",
        "url": (
            _IA_ATTRAMET
            + "Props%20Restoration.zip"
        ),
        "exclusive_with": [],
        "group": "attramet",
    },
    "restored_trees": {
        "zip_name": "Restored Trees Position.zip",
        "label": "Restored Trees Position",
        "description": (
            "Restores beta tree positions removed during development. "
            "May cause FPS drops in Steinway on Steam Deck."
        ),
        "source": "archive",
        "url": (
            _IA_ATTRAMET
            + "Restored%20Trees%20Position.zip"
        ),
        "exclusive_with": [],
        "group": "attramet",
    },
}

# Recommended default packs -- a sensible starting selection
DEFAULT_PACKS = [
    "anims", "clothing", "fences", "hud", "loading_screens",
    "peds", "vegetation",
]

# Attramet packs that default to on (restored_pedestrians off -- large download)
DEFAULT_ATTRAMET = [
    "various_ped_actions", "more_visible_interiors",
    "props_restoration", "restored_trees",
]

# All Attramet pack keys (for UI grouping)
ATTRAMET_PACKS = [
    "various_ped_actions", "more_visible_interiors",
    "props_restoration", "restored_trees", "restored_pedestrians",
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
    Download and install a single pack.

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

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_cv_")
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
        # others may have it nested one or two levels down.
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
    Download and install multiple packs.

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


def apply_props_compat_patches(game_root, installed_keys,
                               on_progress=None):
    """
    Apply Props Restoration compatibility patches.

    Props Restoration ships .ide files that resolve conflicts with
    Various Fixes and More Visible Interiors. These are extracted
    from the Props Restoration zip's Compatibility/ folder and
    placed into the game's update/ tree.

    Patches are applied for whichever of the following is installed:
      - Various Fixes: always (it's required by our setup)
      - More Visible Interiors: only if "more_visible_interiors" is
        in installed_keys

    The Props Restoration zip must already be downloaded and extracted
    in the temp dir. This function re-downloads the zip to apply the
    patches. Call after both Props Restoration and the target mods
    are installed.

    Returns True on success, False on error.
    """
    pack = PACKS.get("props_restoration")
    if not pack:
        return False

    dl_url = pack["url"]
    zip_name = pack["zip_name"]

    if on_progress:
        on_progress("Applying Props Restoration compatibility patches...")

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_prcompat_")
    try:
        zip_path = os.path.join(tmp_dir, zip_name)
        try:
            download(dl_url, zip_path, label="Props Restoration (compat)")
        except Exception:
            _log.warning("props_compat: failed to download for compat patches")
            return False

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile:
            _log.error("props_compat: corrupt zip")
            return False

        # Find the Compatibility/ folder
        compat_dir = _find_compat_dir(tmp_dir)
        if not compat_dir:
            _log.warning("props_compat: no Compatibility/ folder found")
            return False

        update_dst = os.path.join(game_root, "update")

        # Patch map: compat subfolder -> target path under update/
        # The compat folder uses dashed paths like
        # "pc-data-maps-interiors-generic" which map to
        # "update/pc/data/maps/interiors/generic"
        patches_applied = 0

        # Always apply Various Fixes compat (VF is always installed)
        vf_dir = os.path.join(compat_dir, "With Various Fixes")
        if os.path.isdir(vf_dir):
            patches_applied += _apply_compat_folder(vf_dir, update_dst)
            _log.info("props_compat: applied Various Fixes compat patch")

        # Apply MVI compat only if More Visible Interiors is installed
        if "more_visible_interiors" in installed_keys:
            mvi_dir = os.path.join(compat_dir, "With More Visible Interiors")
            if os.path.isdir(mvi_dir):
                patches_applied += _apply_compat_folder(mvi_dir, update_dst)
                _log.info("props_compat: applied MVI compat patch")

        if on_progress and patches_applied:
            on_progress(
                f"Applied {patches_applied} compatibility patch(es)")

        return patches_applied > 0

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
    Checks the base level first, then one level down, then two
    levels down (some Attramet zips nest it deeper).
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

    # Check two levels down (e.g. "Mod Name/Installation .../update/")
    for item in os.listdir(base_dir):
        sub = os.path.join(base_dir, item)
        if os.path.isdir(sub):
            for item2 in os.listdir(sub):
                sub2 = os.path.join(sub, item2)
                if os.path.isdir(sub2):
                    candidate = os.path.join(sub2, "update")
                    if os.path.isdir(candidate):
                        return candidate

    return None


def _find_compat_dir(base_dir):
    """
    Search for a 'Compatibility' directory in the extracted content.
    Checks one and two levels down.
    """
    for item in os.listdir(base_dir):
        sub = os.path.join(base_dir, item)
        if os.path.isdir(sub):
            candidate = os.path.join(sub, "Compatibility")
            if os.path.isdir(candidate):
                return candidate
            # Also check direct match
            if item == "Compatibility":
                return sub

    return None


def _apply_compat_folder(compat_subfolder, update_dst):
    """
    Apply compatibility .ide files from a Props Restoration compat
    subfolder (e.g. "With Various Fixes/").

    The compat folder contains subfolders with dashed path names like
    "pc-data-maps-interiors-generic" containing .ide files. The dashes
    map to directory separators under update/.

    Returns the number of files copied.
    """
    count = 0
    for dashed_dir in os.listdir(compat_subfolder):
        src_dir = os.path.join(compat_subfolder, dashed_dir)
        if not os.path.isdir(src_dir):
            continue

        # Convert dashed path to real path under update/
        # "pc-data-maps-interiors-generic" -> "pc/data/maps/interiors/generic"
        real_path = dashed_dir.replace("-", os.sep)
        dst_dir = os.path.join(update_dst, real_path)
        os.makedirs(dst_dir, exist_ok=True)

        for fname in os.listdir(src_dir):
            src_file = os.path.join(src_dir, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, os.path.join(dst_dir, fname))
                _log.debug("props_compat: copied %s -> %s", fname, dst_dir)
                count += 1

    return count


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
