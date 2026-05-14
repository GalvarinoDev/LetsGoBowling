"""
radio_restoration.py - Radio Restoration installer for GamingTweaksAppliedIV

Downloads and extracts the Radio Restoration mod from Tomasak's
GTA-Downgraders GitHub releases. Restores licensed music tracks that
Rockstar removed due to expired licenses, and restores The Classics 104.1
and The Beat 102.7 radio stations.

How it works
------------
The release is a .rar containing:
    IVCERadioRestoration.exe    (NSIS GUI installer -- NOT used)
    Resources/
        Radio Restorer/
            data1.dat           (zip: ~970 MB of audio files + config)
            hashes.ini          (CRC-32 checksums for integrity check)
            opALL.dat           (zip: GAME.DAT16 for all-restoration)
            opCLASSIC.dat       (zip: GAME.DAT16 for pre-cut only)
            opSPLITbase.dat     (zip: GAME.DAT16 for split radio)
            opVANILLA.dat       (zip: GAME.DAT16 for vanilla)
            opVANILLABETA.dat   (zip: GAME.DAT16 for vanilla beta)
            opSPLITBETA.dat     (zip: GAME.DAT16 for split beta)
            opSPLITVANILLA.dat  (zip: GAME.DAT16 for split vanilla)

The install is purely a zip extraction -- no Wine or Proton needed:
    1. Extract data1.dat into game_root  (drops RADIO_RESTORATION.rpf,
       config DATs, TLAD/TBoGT RPFs, XML files into update/)
    2. Extract op{option}.dat into game_root  (drops the correct GAME.DAT16
       for the chosen radio restoration variant)

The NSIS exe exists only to provide a GUI for picking the option and the
game folder. We replicate that entirely in Python.

Usage
-----
    from radio_restoration import install, is_installed, get_latest_version

    version, url = get_latest_version()
    success = install(game_root, radio_option="opALL", on_progress=callback)
"""

import binascii
import configparser
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

import config as cfg
from log import get_logger
from net import download, DownloadError, BROWSER_UA

_log = get_logger(__name__)

# -- GitHub API ----------------------------------------------------------------

_GITHUB_USER = "Tomasak"
_GITHUB_REPO = "GTA-Downgraders"
_GITHUB_API  = f"https://api.github.com/repos/{_GITHUB_USER}/{_GITHUB_REPO}"
_RELEASE_TAG = "iv-latest"

# Asset matching: the rar filename contains "Radio" and ends with .rar
_ASSET_KW = "Radio"

# Valid radio option keys (without .dat extension)
RADIO_OPTIONS = {
    "opALL":         "All restored tracks (recommended)",
    "opCLASSIC":     "Pre-cut only",
    "opSPLITbase":   "Split radio",
    "opVANILLA":     "Vanilla",
    "opVANILLABETA": "Vanilla Beta",
    "opSPLITBETA":   "Split Beta",
    "opSPLITVANILLA":"Split Vanilla",
}


# -- Public API ----------------------------------------------------------------

def get_latest_version():
    """
    Query the GitHub API for the latest Radio Restoration release.

    Returns (version_tag, download_url) on success.
    Returns (None, None) if the API call fails or no .rar asset found.
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
        dl_url = None

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if _ASSET_KW in name and name.endswith(".rar"):
                dl_url = asset.get("browser_download_url")
                break

        if dl_url:
            _log.info("radio_restoration: latest release is %s", tag)
        else:
            _log.warning("radio_restoration: .rar asset not found in "
                          "release %s", tag)

        return tag, dl_url

    except Exception:
        _log.warning("radio_restoration: failed to query GitHub API",
                      exc_info=True)
        return None, None


def install(game_root, radio_option="opALL", steam_root=None,
            on_progress=None, version_tag=None, download_url=None):
    """
    Download and install Radio Restoration to a GTA IV game root.

    Extracts data1.dat and the chosen op*.dat directly into game_root
    using Python's zipfile module. No Wine or Proton required.

    game_root     -- path to the GTAIV/ folder where GTAIV.exe lives
    radio_option  -- which variant to install. One of the keys in
                     RADIO_OPTIONS: 'opALL', 'opCLASSIC', 'opSPLITbase',
                     'opVANILLA', 'opVANILLABETA', 'opSPLITBETA',
                     'opSPLITVANILLA'. Defaults to 'opALL'.
    steam_root    -- unused, kept for API compatibility
    on_progress   -- optional callback(message: str)
    version_tag   -- optional version string to save in config
    download_url  -- optional direct download URL

    Returns True on success, False on error.
    Raises DownloadError if the download fails.
    """
    _log.info("radio_restoration: installing to %s (option=%s)",
              game_root, radio_option)

    if radio_option not in RADIO_OPTIONS:
        _log.error("radio_restoration: unknown radio_option %r", radio_option)
        radio_option = "opALL"

    def prog(msg):
        _log.info("radio_restoration: %s", msg)
        if on_progress:
            on_progress(msg)

    # Resolve version and URL if not provided
    if not download_url:
        if not version_tag:
            version_tag, download_url = get_latest_version()
        if not download_url:
            _log.error("radio_restoration: no download URL available")
            return False

    # Check for unrar (still needed to extract the .rar release)
    if not _has_unrar():
        _log.error("radio_restoration: unrar not found -- cannot extract "
                     "the .rar archive. Install unrar and try again.")
        return False

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_rr_")
    try:
        # -- Step 1: Download the rar ------------------------------------------
        rar_path = os.path.join(tmp_dir, "RadioRestoration.rar")
        prog("Downloading Radio Restoration...")
        try:
            download(download_url, rar_path, label="Radio Restoration")
        except Exception as e:
            raise DownloadError(
                url=download_url, dest=rar_path,
                label="Radio Restoration", cause=e,
            )

        # -- Step 2: Extract the rar -------------------------------------------
        prog("Extracting archive...")
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        if not _extract_rar(rar_path, extract_dir):
            _log.error("radio_restoration: failed to extract rar")
            return False

        # -- Step 3: Find Resources/Radio Restorer/ ----------------------------
        restorer_dir = _find_restorer_dir(extract_dir)
        if not restorer_dir:
            _log.error("radio_restoration: could not find 'Radio Restorer' "
                         "directory in extracted content")
            return False

        _log.info("radio_restoration: restorer_dir = %s", restorer_dir)

        data1_path  = os.path.join(restorer_dir, "data1.dat")
        option_path = os.path.join(restorer_dir, f"{radio_option}.dat")
        hashes_path = os.path.join(restorer_dir, "hashes.ini")

        if not os.path.isfile(data1_path):
            _log.error("radio_restoration: data1.dat not found in %s",
                         restorer_dir)
            return False

        if not os.path.isfile(option_path):
            _log.error("radio_restoration: %s.dat not found in %s",
                         radio_option, restorer_dir)
            return False

        # -- Step 4: CRC-32 integrity check ------------------------------------
        if os.path.isfile(hashes_path):
            prog("Verifying integrity...")
            if not _verify_crc(hashes_path, data1_path, "data1.dat"):
                _log.error("radio_restoration: data1.dat CRC mismatch -- "
                             "download may be corrupt")
                return False
            if not _verify_crc(hashes_path, option_path,
                                f"{radio_option}.dat"):
                _log.error("radio_restoration: %s.dat CRC mismatch",
                             radio_option)
                return False
            _log.info("radio_restoration: CRC checks passed")
        else:
            _log.warning("radio_restoration: hashes.ini not found, "
                          "skipping integrity check")

        # -- Step 5: Extract data1.dat into game_root --------------------------
        prog("Extracting audio files (this may take a moment)...")
        _log.info("radio_restoration: extracting data1.dat -> %s", game_root)
        try:
            with zipfile.ZipFile(data1_path, "r") as zf:
                zf.extractall(game_root)
        except Exception as e:
            _log.error("radio_restoration: failed to extract data1.dat: %s",
                         e)
            return False

        # -- Step 6: Extract op*.dat into game_root ----------------------------
        prog(f"Applying {RADIO_OPTIONS.get(radio_option, radio_option)}...")
        _log.info("radio_restoration: extracting %s.dat -> %s",
                   radio_option, game_root)
        try:
            with zipfile.ZipFile(option_path, "r") as zf:
                zf.extractall(game_root)
        except Exception as e:
            _log.error("radio_restoration: failed to extract %s.dat: %s",
                         radio_option, e)
            return False

        # -- Step 7: Save state ------------------------------------------------
        cfg.set_radio_restoration_installed(True)
        cfg.set_radio_option(radio_option)
        if version_tag:
            _log.info("radio_restoration: version %s", version_tag)

        prog("Radio Restoration installed")
        _log.info("radio_restoration: installed successfully (option=%s)",
                   radio_option)
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def uninstall(game_root):
    """
    Mark Radio Restoration as uninstalled.

    Radio Restoration extracts files into the game's update/ folder.
    To fully undo the changes, the user should verify game files through
    Steam (Properties -> Installed Files -> Verify integrity).
    We clear the config flag here; the uninstaller shell script handles
    generic update/ folder removal.

    Returns True.
    """
    cfg.set_radio_restoration_installed(False)
    _log.info("radio_restoration: marked as uninstalled. User should "
               "verify game files through Steam to restore original audio.")
    return True


def is_installed():
    """Check if Radio Restoration is recorded as installed in config."""
    return cfg.is_radio_restoration_installed()


# -- Internal helpers ----------------------------------------------------------

def _has_unrar():
    """Check if unrar is available on the system."""
    try:
        subprocess.run(["unrar"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _extract_rar(rar_path, dest_dir):
    """Extract a .rar archive using unrar. Returns True on success."""
    try:
        result = subprocess.run(
            ["unrar", "x", "-o+", rar_path, dest_dir + "/"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            _log.debug("radio_restoration: rar extracted to %s", dest_dir)
            return True
        else:
            _log.error("radio_restoration: unrar failed: %s", result.stderr)
            return False
    except Exception:
        _log.error("radio_restoration: unrar failed", exc_info=True)
        return False


def _find_restorer_dir(base_dir):
    """
    Recursively search for the 'Radio Restorer' directory in extracted
    content. The rar may have a wrapping folder (Radio.Restoration.Mod/).
    Returns the full path to the directory, or None if not found.
    """
    for root, dirs, files in os.walk(base_dir):
        if "Radio Restorer" in dirs:
            return os.path.join(root, "Radio Restorer")
    return None


def _verify_crc(hashes_path, file_path, filename):
    """
    Verify a file's CRC-32 against hashes.ini.

    hashes_path -- path to hashes.ini
    file_path   -- path to the file to check
    filename    -- key name in hashes.ini (e.g. 'data1.dat')

    Returns True if the CRC matches or the key is not in hashes.ini.
    Returns False if there is a mismatch.
    """
    try:
        parser = configparser.ConfigParser()
        parser.read(hashes_path)

        # hashes.ini has a [Archives] section
        if not parser.has_option("Archives", filename):
            _log.debug("radio_restoration: no hash entry for %s, skipping",
                        filename)
            return True

        expected = parser.get("Archives", filename).strip().upper()

        # Compute CRC-32 of the file
        crc = 0
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                crc = binascii.crc32(chunk, crc)

        # CRC-32 result is unsigned 32-bit
        actual = format(crc & 0xFFFFFFFF, "08X")

        if actual == expected:
            _log.debug("radio_restoration: CRC OK for %s (%s)", filename,
                        actual)
            return True
        else:
            _log.error("radio_restoration: CRC mismatch for %s: "
                         "expected %s, got %s", filename, expected, actual)
            return False

    except Exception:
        _log.warning("radio_restoration: CRC check failed for %s",
                      filename, exc_info=True)
        return True  # Don't block install on unexpected CRC errors
