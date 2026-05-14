"""
fusionfix.py - FusionFix installer for GetToAmericaIV

Downloads and installs GTAIV.EFLC.FusionFix from ThirteenAG's GitHub
releases. This is the foundation mod -- it provides the ASI loader
(dinput8.dll), the Fusion Overloader system (update/ folder), and
hundreds of bug fixes and graphics improvements.

FusionFix must be installed before any other mod. Console Visuals,
Various Fixes, and Higher Res Misc Pack all depend on the Fusion
Overloader that FusionFix creates.

The zip extracts flat into the game root (GTAIV/ subfolder):
    dinput8.dll                -> GTAIV/
    GTAIV.EFLC.FusionFix.asi  -> GTAIV/
    GTAIV.EFLC.FusionFix.ini  -> GTAIV/
    plugins/                   -> GTAIV/plugins/
    update/                    -> GTAIV/update/

Usage:
    from fusionfix import install, uninstall, is_installed, get_latest_version

    version, url = get_latest_version()
    success = install(game_root, on_progress=callback)
    installed = is_installed(game_root)
    success = uninstall(game_root)
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

_GITHUB_USER = "ThirteenAG"
_GITHUB_REPO = "GTAIV.EFLC.FusionFix"
_GITHUB_API  = f"https://api.github.com/repos/{_GITHUB_USER}/{_GITHUB_REPO}"

# The zip asset name is consistent across all releases
_ZIP_NAME = "GTAIV.EFLC.FusionFix.zip"

# Direct download URL for latest release (follows redirects)
_DIRECT_URL = (
    f"https://github.com/{_GITHUB_USER}/{_GITHUB_REPO}"
    f"/releases/latest/download/{_ZIP_NAME}"
)

# -- Key files for detection ---------------------------------------------------
# dinput8.dll is the ASI loader that FusionFix ships. If it exists in
# the game root, FusionFix is installed (or at least the loader is).
# The .asi file is the definitive FusionFix marker.

_ASI_NAME = "GTAIV.EFLC.FusionFix.asi"
_INI_NAME = "GTAIV.EFLC.FusionFix.ini"
_DLL_NAME = "dinput8.dll"

# Files and folders placed by FusionFix (for uninstall)
_FF_FILES = [_DLL_NAME, _ASI_NAME, _INI_NAME]
_FF_DIRS  = ["plugins", "update"]


# -- Public API ----------------------------------------------------------------

def get_latest_version():
    """
    Query the GitHub API for the latest FusionFix release.

    Returns (version_tag, download_url) on success, e.g. ("v5.0.1", "https://...").
    Returns (None, None) if the API call fails.
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

        # Find the zip asset in the release
        dl_url = None
        for asset in data.get("assets", []):
            if asset.get("name") == _ZIP_NAME:
                dl_url = asset.get("browser_download_url")
                break

        if not dl_url:
            # Fall back to the direct /latest/download/ URL
            dl_url = _DIRECT_URL

        _log.info("fusionfix: latest release is %s", tag)
        return tag, dl_url

    except Exception:
        _log.warning("fusionfix: failed to query GitHub API", exc_info=True)
        return None, None


def install(game_root, on_progress=None, version_tag=None, download_url=None):
    """
    Download and install FusionFix to a GTA IV game root.

    game_root    -- path to the GTAIV/ subfolder where GTAIV.exe lives
    on_progress  -- optional callback(message: str) for status updates
    version_tag  -- optional version string to save (e.g. "v5.0.1").
                    If None, queries the API first.
    download_url -- optional direct download URL. If None, queries the
                    API or uses the /latest/download/ URL.

    Returns True on success, False on error.
    Raises DownloadError if the download fails (caller can show a
    manual download dialog).
    """
    _log.info("fusionfix: installing to %s", game_root)

    # Resolve version and URL if not provided
    if not download_url:
        if not version_tag:
            version_tag, download_url = get_latest_version()
        if not download_url:
            download_url = _DIRECT_URL

    tmp_dir = tempfile.mkdtemp(prefix="gettoamericaiv_ff_")
    try:
        # Step 1: Download the zip
        zip_path = os.path.join(tmp_dir, _ZIP_NAME)
        if on_progress:
            on_progress("Downloading FusionFix...")

        try:
            download(download_url, zip_path, label="FusionFix")
        except Exception as e:
            raise DownloadError(
                url=download_url,
                dest=zip_path,
                label="FusionFix",
                cause=e,
            )

        # Step 2: Extract the zip
        if on_progress:
            on_progress("Extracting FusionFix...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile:
            _log.error("fusionfix: corrupt zip: %s", zip_path)
            return False

        # Step 3: Copy files to game root
        # The zip extracts flat -- dinput8.dll, .asi, .ini at the root level,
        # plus plugins/ and update/ folders.
        if on_progress:
            on_progress("Installing FusionFix files...")

        extracted_root = tmp_dir

        # Check if the zip has a wrapping folder (some releases do)
        # by looking for dinput8.dll at the top level vs one level down
        if not os.path.exists(os.path.join(extracted_root, _DLL_NAME)):
            # Check for a single subfolder containing the files
            subdirs = [
                d for d in os.listdir(extracted_root)
                if os.path.isdir(os.path.join(extracted_root, d))
            ]
            for sd in subdirs:
                candidate = os.path.join(extracted_root, sd)
                if os.path.exists(os.path.join(candidate, _DLL_NAME)):
                    extracted_root = candidate
                    break

        # Verify dinput8.dll exists in extracted content
        dll_src = os.path.join(extracted_root, _DLL_NAME)
        if not os.path.exists(dll_src):
            _log.error("fusionfix: dinput8.dll not found in zip")
            return False

        # Copy individual files
        for fname in _FF_FILES:
            src = os.path.join(extracted_root, fname)
            dst = os.path.join(game_root, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                _log.debug("fusionfix: copied %s", fname)

        # Copy directories (plugins/, update/)
        for dname in _FF_DIRS:
            src_dir = os.path.join(extracted_root, dname)
            dst_dir = os.path.join(game_root, dname)
            if os.path.isdir(src_dir):
                # Merge into existing directory if it exists
                if os.path.exists(dst_dir):
                    _merge_dirs(src_dir, dst_dir)
                else:
                    shutil.copytree(src_dir, dst_dir)
                _log.debug("fusionfix: copied %s/", dname)

        # Step 4: Save version to config
        if version_tag:
            cfg.set_fusionfix_version(version_tag)

        if on_progress:
            on_progress("FusionFix installed")

        _log.info("fusionfix: installed successfully (version: %s)", version_tag)
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def uninstall(game_root):
    """
    Remove FusionFix files from a game directory.

    Removes the ASI loader, FusionFix ASI/INI, and the plugins/ folder.
    Does NOT remove the update/ folder since other mods (Console Visuals,
    Various Fixes, etc.) put their content there too. The update/ folder
    is only cleaned up when the user does a full reset.

    Returns True on success, False on error.
    """
    _log.info("fusionfix: uninstalling from %s", game_root)

    # Remove individual files
    for fname in _FF_FILES:
        fpath = os.path.join(game_root, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                _log.debug("fusionfix: removed %s", fname)
            except OSError:
                _log.warning("fusionfix: failed to remove %s", fpath)

    # Remove plugins/ directory (FusionFix-specific)
    plugins_dir = os.path.join(game_root, "plugins")
    if os.path.isdir(plugins_dir):
        try:
            shutil.rmtree(plugins_dir)
            _log.debug("fusionfix: removed plugins/")
        except OSError:
            _log.warning("fusionfix: failed to remove plugins/")

    # Clear version from config
    cfg.set_fusionfix_version(None)

    _log.info("fusionfix: uninstalled")
    return True


def is_installed(game_root):
    """
    Check if FusionFix is installed in a game directory.

    Looks for the .asi file -- that's the definitive marker.
    dinput8.dll alone isn't enough since other ASI mods could ship it.

    Returns True if installed, False otherwise.
    """
    asi_path = os.path.join(game_root, _ASI_NAME)
    return os.path.exists(asi_path)


def get_installed_version():
    """
    Return the installed FusionFix version from config, or None.
    """
    return cfg.get_fusionfix_version()


# -- Internal helpers ----------------------------------------------------------

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
