"""
various_fixes.py - Various Fixes installer for GamingTweaksAppliedIV

Downloads and installs GTAIV.EFLC.Various.Fixes from valentyn-l's
GitHub releases using the Fusion Overloader method.

Two assets are downloaded:
    1. Installation.through.Fusion.Overloader.zip (~1.5 GB) - main fixes
    2. Optional.Content.zip (~74 MB) - three optional extras

The optional content (all via Fusion Overloader) includes:
    - Functional Pedestrian Traffic Lights (by brokensymmetry)
    - Fixed Misspelled Russian Text
    - Billboards from Chinatown Wars (by Ash_735)

Requires FusionFix (provides the Fusion Overloader system).

Usage:
    from various_fixes import install, OPTIONAL_CONTENT

    success = install(
        game_root,
        optional=["traffic_lights", "ctw_billboards"],
        on_progress=callback,
    )
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

_GITHUB_USER = "valentyn-l"
_GITHUB_REPO = "GTAIV.EFLC.Various.Fixes"
_GITHUB_API  = f"https://api.github.com/repos/{_GITHUB_USER}/{_GITHUB_REPO}"

# Asset matching keywords
_MAIN_KW = ("Fusion", "Overloader")     # main Fusion Overloader zip
_OPT_KW  = ("Optional", "Content")      # optional content zip

# -- Optional content definitions ----------------------------------------------
# key: internal name used in config and UI
# folder: path inside the zip under "Optional Content/Installation through
#         Fusion Overloader/" -- each contains an update/ folder to merge.

OPTIONAL_CONTENT = {
    "traffic_lights": {
        "label": "Functional Pedestrian Traffic Lights",
        "description": "Working pedestrian traffic lights (by brokensymmetry).",
        "folder": "Pedestrian traffic lights/Functional",
    },
    "russian_text": {
        "label": "Fixed Misspelled Russian Text",
        "description": "Corrects Russian typos on signs around Liberty City.",
        "folder": "Fixed misspelled russian text",
    },
    "ctw_billboards": {
        "label": "Chinatown Wars Billboards",
        "description": "Adds billboard variety from GTA: Chinatown Wars (by Ash_735).",
        "folder": "Billboards from Chinatown Wars",
    },
}


# -- Public API ----------------------------------------------------------------

def get_latest_version():
    """
    Query the GitHub API for the latest Various Fixes release.

    Returns (version_tag, main_url, optional_url) on success.
    Returns (None, None, None) if the API call fails.
    """
    try:
        url = f"{_GITHUB_API}/releases/latest"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            **BROWSER_UA,
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))

        tag = data.get("tag_name")
        main_url = None
        opt_url = None

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            dl = asset.get("browser_download_url")
            if not dl:
                continue
            # Match main Fusion Overloader zip (but not Optional Content)
            if (_MAIN_KW[0] in name and _MAIN_KW[1] in name
                    and _OPT_KW[0] not in name):
                main_url = dl
            # Match Optional Content zip
            elif _OPT_KW[0] in name and _OPT_KW[1] in name:
                opt_url = dl

        _log.info("various_fixes: latest release is %s (main: %s, opt: %s)",
                   tag, bool(main_url), bool(opt_url))
        return tag, main_url, opt_url

    except Exception:
        _log.warning("various_fixes: failed to query GitHub API",
                      exc_info=True)
        return None, None, None


def install(game_root, optional=None, on_progress=None,
            version_tag=None, main_url=None, opt_url=None):
    """
    Download and install Various Fixes to a GTA IV game root.

    game_root    -- path to the GTAIV/ subfolder where GTAIV.exe lives
    optional     -- list of optional content keys to install, e.g.
                    ["traffic_lights", "ctw_billboards"]. None or []
                    skips optional content entirely.
    on_progress  -- optional callback(message: str)
    version_tag  -- optional version string to save. If None, queries API.
    main_url     -- optional direct download URL for main zip.
    opt_url      -- optional direct download URL for optional content zip.

    Returns True on success, False on error.
    Raises DownloadError if a download fails.
    """
    _log.info("various_fixes: installing to %s", game_root)

    # Resolve version and URLs if not provided
    if not main_url:
        if not version_tag:
            version_tag, main_url, opt_url = get_latest_version()
        if not main_url:
            _log.error("various_fixes: no download URL available")
            return False

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_vf_",
                               dir=cfg.get_tmp_dir())
    try:
        # -- Step 1: Download and install the main zip -------------------------
        main_zip = os.path.join(tmp_dir, "VF_FusionOverloader.zip")
        if on_progress:
            on_progress("Downloading Various Fixes (this may take a while)...")

        try:
            download(main_url, main_zip, label="Various Fixes")
        except Exception as e:
            raise DownloadError(
                url=main_url, dest=main_zip,
                label="Various Fixes", cause=e,
            )

        if on_progress:
            on_progress("Extracting Various Fixes...")

        if not _extract_and_merge_update(main_zip, tmp_dir, game_root,
                                          "main"):
            return False

        # -- Step 2: Download and install optional content (if any) ------------
        if optional and opt_url:
            opt_zip = os.path.join(tmp_dir, "VF_OptionalContent.zip")
            if on_progress:
                on_progress("Downloading Various Fixes optional content...")

            try:
                download(opt_url, opt_zip, label="Various Fixes Optional")
            except Exception as e:
                _log.warning("various_fixes: optional content download "
                              "failed: %s", e)
                # Don't fail the whole install over optional content
                optional = []

            if optional:
                if on_progress:
                    on_progress("Extracting optional content...")

                _install_optional(opt_zip, tmp_dir, game_root, optional,
                                   on_progress)

        # -- Step 3: Save state to config --------------------------------------
        if version_tag:
            cfg.set_various_fixes_version(version_tag)

        if on_progress:
            on_progress("Various Fixes installed")

        _log.info("various_fixes: installed successfully (version: %s)",
                   version_tag)
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def uninstall(game_root):
    """
    Remove Various Fixes from the game.

    Since all content merges into the shared update/ folder, we can't
    selectively remove files. Removes the entire update/ folder.
    Caller should reinstall FusionFix and other mods after.
    """
    update_dir = os.path.join(game_root, "update")
    if os.path.isdir(update_dir):
        try:
            shutil.rmtree(update_dir)
            _log.info("various_fixes: removed update/ folder")
        except OSError:
            _log.warning("various_fixes: failed to remove update/")

    cfg.set_various_fixes_version(None)
    _log.info("various_fixes: uninstalled (update/ removed)")
    return True


def is_installed():
    """Check if Various Fixes is recorded as installed in config."""
    return cfg.get_various_fixes_version() is not None


def get_installed_version():
    """Return the installed Various Fixes version from config, or None."""
    return cfg.get_various_fixes_version()


# -- Internal helpers ----------------------------------------------------------

def _extract_and_merge_update(zip_path, tmp_dir, game_root, label):
    """
    Extract a zip and merge its update/ folder into the game root.
    Returns True on success, False on error.
    """
    extract_dir = os.path.join(tmp_dir, f"extract_{label}")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        _log.error("various_fixes: corrupt zip: %s", zip_path)
        return False

    update_src = _find_update_dir(extract_dir)
    if not update_src:
        _log.error("various_fixes: no update/ folder found in %s zip", label)
        return False

    update_dst = os.path.join(game_root, "update")
    os.makedirs(update_dst, exist_ok=True)
    _merge_dirs(update_src, update_dst)
    _log.info("various_fixes: merged %s update/ folder", label)
    return True


def _install_optional(opt_zip, tmp_dir, game_root, keys, on_progress):
    """
    Extract the Optional Content zip and install selected items.
    Each item has an update/ folder under its subfolder inside
    "Optional Content/Installation through Fusion Overloader/".
    """
    extract_dir = os.path.join(tmp_dir, "extract_optional")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(opt_zip, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        _log.error("various_fixes: corrupt optional content zip")
        return

    base = os.path.join(
        extract_dir,
        "Optional Content",
        "Installation through Fusion Overloader",
    )

    if not os.path.isdir(base):
        _log.error("various_fixes: Fusion Overloader folder not found "
                     "in optional content zip")
        return

    update_dst = os.path.join(game_root, "update")
    os.makedirs(update_dst, exist_ok=True)

    for key in keys:
        opt = OPTIONAL_CONTENT.get(key)
        if not opt:
            _log.warning("various_fixes: unknown optional key: %s", key)
            continue

        item_dir = os.path.join(base, opt["folder"])
        if not os.path.isdir(item_dir):
            _log.warning("various_fixes: optional folder not found: %s",
                          opt["folder"])
            continue

        # Find update/ inside this item's folder
        update_src = _find_update_dir(item_dir)
        if update_src:
            _merge_dirs(update_src, update_dst)
            _log.info("various_fixes: installed optional: %s", opt["label"])
            if on_progress:
                on_progress(f"Installed {opt['label']}")
        else:
            _log.warning("various_fixes: no update/ folder in optional "
                          "item: %s", opt["label"])


def _find_update_dir(base_dir):
    """
    Search for an 'update' directory in the extracted content.
    Checks the base level first, then one level down.
    """
    candidate = os.path.join(base_dir, "update")
    if os.path.isdir(candidate):
        return candidate

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
    files in dst with the same name.
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
