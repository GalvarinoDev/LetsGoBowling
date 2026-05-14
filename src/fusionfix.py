"""
fusionfix.py - FusionFix installer for GamingTweaksAppliedIV

Downloads and installs GTAIV.EFLC.FusionFix from ThirteenAG's GitHub
releases. This is the foundation mod -- it provides the ASI loader
(dinput8.dll), the Fusion Overloader system (update/ folder), and
hundreds of bug fixes and graphics improvements.

FusionFix must be installed before any other mod. Console Visuals,
Various Fixes, and Higher Res Misc Pack all depend on the Fusion
Overloader that FusionFix creates.

The zip extracts into the game root (GTAIV/ subfolder) as follows:
    d3d9.dll                              -> GTAIV/
    dinput8.dll                           -> GTAIV/
    vulkan.dll                            -> GTAIV/
    plugins/GTAIV.EFLC.FusionFix.asi     -> GTAIV/plugins/
    plugins/GTAIV.EFLC.FusionFix.ini     -> GTAIV/plugins/

Also handles XboxRainDroplets (by the same author), which installs:
    plugins/GTAIV.XboxRainDroplets.asi    -> GTAIV/plugins/
    plugins/GTAIV.XboxRainDroplets.ini    -> GTAIV/plugins/

Usage:
    from fusionfix import install, uninstall, is_installed, get_latest_version
    from fusionfix import install_rain_droplets, is_rain_droplets_installed

    version, url = get_latest_version()
    success = install(game_root, on_progress=callback)
    installed = is_installed(game_root)
    success = uninstall(game_root)

    success = install_rain_droplets(game_root, on_progress=callback)
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

# -- XboxRainDroplets ----------------------------------------------------------

_XRD_GITHUB_USER = "ThirteenAG"
_XRD_GITHUB_REPO = "XboxRainDroplets"
_XRD_TAG = "gtaiv"
_XRD_ZIP_NAME = "GTAIV.XboxRainDroplets.zip"
_XRD_DIRECT_URL = (
    f"https://github.com/{_XRD_GITHUB_USER}/{_XRD_GITHUB_REPO}"
    f"/releases/download/{_XRD_TAG}/{_XRD_ZIP_NAME}"
)
_XRD_ASI_NAME = "GTAIV.XboxRainDroplets.asi"
_XRD_INI_NAME = "GTAIV.XboxRainDroplets.ini"

# -- Key files for detection and install ---------------------------------------
# Root-level DLLs that FusionFix places in the game root:
#   dinput8.dll  -- ASI loader (tells Proton/Wine to load ASI plugins)
#   d3d9.dll     -- Direct3D 9 wrapper for FusionFix rendering hooks
#   vulkan.dll   -- Vulkan rendering backend
#
# The .asi plugin and .ini config live inside plugins/:
#   plugins/GTAIV.EFLC.FusionFix.asi
#   plugins/GTAIV.EFLC.FusionFix.ini

_DLL_NAME = "dinput8.dll"
_D3D9_NAME = "d3d9.dll"
_VULKAN_NAME = "vulkan.dll"
_ASI_NAME = "GTAIV.EFLC.FusionFix.asi"
_INI_NAME = "GTAIV.EFLC.FusionFix.ini"

# Root-level files placed by FusionFix (for copy and uninstall)
_FF_ROOT_FILES = [_DLL_NAME, _D3D9_NAME, _VULKAN_NAME]

# Directories placed by FusionFix (for copy and uninstall)
_FF_DIRS = ["plugins", "update"]


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

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_ff_")
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
        # The zip extracts flat -- d3d9.dll, dinput8.dll, vulkan.dll at the
        # root level, plus plugins/ and update/ folders.
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

        # Copy root-level DLLs (dinput8.dll, d3d9.dll, vulkan.dll)
        for fname in _FF_ROOT_FILES:
            src = os.path.join(extracted_root, fname)
            dst = os.path.join(game_root, fname)
            if os.path.exists(src):
                shutil.copy2(src, dst)
                _log.debug("fusionfix: copied %s", fname)
            else:
                _log.warning("fusionfix: expected root file not found: %s",
                             fname)

        # Copy directories (plugins/, update/)
        # plugins/ contains the .asi and .ini files
        # update/ contains the Fusion Overloader content
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

    Removes the root-level DLLs (dinput8.dll, d3d9.dll, vulkan.dll)
    and the plugins/ folder (which contains the .asi and .ini).

    Does NOT remove the update/ folder since other mods (Console Visuals,
    Various Fixes, etc.) put their content there too. The update/ folder
    is only cleaned up when the user does a full reset.

    Returns True on success, False on error.
    """
    _log.info("fusionfix: uninstalling from %s", game_root)

    # Remove root-level DLLs
    for fname in _FF_ROOT_FILES:
        fpath = os.path.join(game_root, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                _log.debug("fusionfix: removed %s", fname)
            except OSError:
                _log.warning("fusionfix: failed to remove %s", fpath)

    # Remove plugins/ directory (contains .asi and .ini)
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

    Looks for the .asi file inside plugins/ -- that's the definitive
    marker. dinput8.dll alone isn't enough since other ASI mods could
    ship it.

    Returns True if installed, False otherwise.
    """
    asi_path = os.path.join(game_root, "plugins", _ASI_NAME)
    return os.path.exists(asi_path)


def get_installed_version():
    """
    Return the installed FusionFix version from config, or None.
    """
    return cfg.get_fusionfix_version()


# -- Xbox Rain Droplets --------------------------------------------------------

def install_rain_droplets(game_root, on_progress=None):
    """
    Download and install Xbox Rain Droplets to a GTA IV game root.

    Extracts GTAIV.XboxRainDroplets.asi and .ini into plugins/.
    FusionFix must be installed first (provides the ASI loader).

    game_root   -- path to the GTAIV/ subfolder where GTAIV.exe lives
    on_progress -- optional callback(message: str) for status updates

    Returns True on success, False on error.
    Raises DownloadError if the download fails.
    """
    _log.info("rain_droplets: installing to %s", game_root)

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_xrd_")
    try:
        # Download
        zip_path = os.path.join(tmp_dir, _XRD_ZIP_NAME)
        if on_progress:
            on_progress("Downloading Xbox Rain Droplets...")

        try:
            download(_XRD_DIRECT_URL, zip_path, label="Xbox Rain Droplets")
        except Exception as e:
            raise DownloadError(
                url=_XRD_DIRECT_URL,
                dest=zip_path,
                label="Xbox Rain Droplets",
                cause=e,
            )

        # Extract
        if on_progress:
            on_progress("Extracting Xbox Rain Droplets...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile:
            _log.error("rain_droplets: corrupt zip: %s", zip_path)
            return False

        # Find the .asi and .ini files in the extracted content
        if on_progress:
            on_progress("Installing Xbox Rain Droplets...")

        plugins_dir = os.path.join(game_root, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        installed_count = 0
        for root, _dirs, files in os.walk(tmp_dir):
            for fname in files:
                if fname in (_XRD_ASI_NAME, _XRD_INI_NAME):
                    src = os.path.join(root, fname)
                    dst = os.path.join(plugins_dir, fname)
                    shutil.copy2(src, dst)
                    _log.debug("rain_droplets: copied %s -> plugins/",
                               fname)
                    installed_count += 1

        if installed_count < 2:
            _log.warning("rain_droplets: expected 2 files, found %d",
                          installed_count)

        if on_progress:
            on_progress("Xbox Rain Droplets installed")

        _log.info("rain_droplets: installed successfully")
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def is_rain_droplets_installed(game_root):
    """
    Check if Xbox Rain Droplets is installed.

    Looks for the .asi file inside plugins/.
    """
    asi_path = os.path.join(game_root, "plugins", _XRD_ASI_NAME)
    return os.path.exists(asi_path)


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
