"""
radio_restoration.py - Radio Restoration installer for GamingTweaksAppliedIV

Downloads and extracts the Radio Restoration mod from Tomasak's
GTA-Downgraders GitHub releases. Restores licensed music tracks that
Rockstar removed due to expired licenses, and restores The Classics 104.1
and The Beat 102.7 radio stations.

How it works
------------
The release is a .rar containing:
    IVCERadioRestoration.exe    (NSIS GUI installer)
    Resources/
        External/7za.exe        (extraction tool used by the exe)
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

Install method:
    1. Extract the rar to get the exe and Resources/ folder
    2. Write the game's install path as a registry key into the Wine
       prefix's system.reg so the NSIS installer can find the game
    3. Run the exe silently through Proton (/S flag)
    4. Verify files landed (RADIO_RESTORATION.rpf, EFLC XMLs)

The NSIS exe handles hash verification, old-install cleanup, component
selection, and file extraction internally. Running it through Proton
is more reliable than reimplementing its logic in Python.

Usage
-----
    from radio_restoration import install, is_installed, get_latest_version

    version, url = get_latest_version()
    success = install(game_root, radio_option="opALL",
                      compatdata_path="...", steam_root="...",
                      on_progress=callback)
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request

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

# GTA IV Steam appid -- used for default compatdata path
_GTAIV_APPID = "12210"

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

# Files that must exist after a successful install
_VERIFY_FILES = [
    os.path.join("update", "pc", "audio", "sfx", "RADIO_RESTORATION.rpf"),
    os.path.join("update", "TLAD", "e1_radio.xml"),
    os.path.join("update", "TBoGT", "e2_radio.xml"),
]


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
            compatdata_path=None, on_progress=None,
            version_tag=None, download_url=None):
    """
    Download and install Radio Restoration to a GTA IV game root.

    Runs the NSIS installer silently through Proton after writing the
    game path into the Wine prefix registry.

    game_root        -- path to the GTAIV/ folder where GTAIV.exe lives
    radio_option     -- which variant to install (unused in silent mode,
                        the exe defaults to opALL when run with /S)
    steam_root       -- path to the Steam root directory
    compatdata_path  -- path to the game's compatdata prefix
    on_progress      -- optional callback(message: str)
    version_tag      -- optional version string to save in config
    download_url     -- optional direct download URL

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

    # Resolve compatdata path
    if not compatdata_path:
        compatdata_path = os.path.join(
            os.path.expanduser("~/.local/share/Steam"),
            "steamapps", "compatdata", _GTAIV_APPID,
        )
    _log.info("radio_restoration: compatdata = %s", compatdata_path)

    # Resolve steam_root
    if not steam_root:
        steam_root = os.path.expanduser("~/.local/share/Steam")

    # Find Proton (vanilla only -- NSIS exe fails under GE-Proton)
    proton_path = _find_vanilla_proton(steam_root)
    if not proton_path:
        _log.error("radio_restoration: no vanilla Proton found")
        return False
    _log.info("radio_restoration: proton = %s", proton_path)

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

        # -- Step 3: Find the NSIS exe -----------------------------------------
        exe_path = _find_exe(extract_dir)
        if not exe_path:
            _log.error("radio_restoration: IVCERadioRestoration.exe not "
                         "found in extracted content")
            return False
        _log.info("radio_restoration: exe = %s", exe_path)

        # -- Step 4: Write registry key ----------------------------------------
        prog("Writing install path to registry...")
        _write_install_path_registry(compatdata_path, game_root)

        # -- Step 5: Run the NSIS exe silently through Proton ------------------
        prog("Running Radio Restoration installer...")
        wine_game_root = _linux_to_wine_path(game_root)
        _log.info("radio_restoration: Wine path = %s", wine_game_root)

        env = os.environ.copy()
        env["STEAM_COMPAT_DATA_PATH"] = compatdata_path
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root

        try:
            result = subprocess.run(
                [proton_path, "run", exe_path, "/S",
                 f"/D={wine_game_root}"],
                env=env,
                capture_output=True,
                timeout=600,
                cwd=os.path.dirname(exe_path),
            )
            _log.info("radio_restoration: exe exit code = %d",
                       result.returncode)
            if result.returncode != 0:
                _log.warning("radio_restoration: non-zero exit code %d "
                              "(may still be OK)", result.returncode)
        except subprocess.TimeoutExpired:
            _log.error("radio_restoration: installer timed out after 10 min")
            return False
        except Exception as e:
            _log.error("radio_restoration: installer failed: %s", e)
            return False

        # -- Step 6: Verify files landed ---------------------------------------
        prog("Verifying installation...")
        missing = []
        for rel_path in _VERIFY_FILES:
            full = os.path.join(game_root, rel_path)
            if not os.path.exists(full):
                missing.append(rel_path)

        if missing:
            _log.error("radio_restoration: verification failed, "
                         "missing files: %s", missing)
            return False

        _log.info("radio_restoration: verification passed")

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

def _linux_to_wine_path(linux_path):
    """
    Convert a Linux path to a Wine Z: drive path.

    Wine maps the entire Linux filesystem under Z:, so
    /home/deck/.local/share/Steam/steamapps/common/Grand Theft Auto IV/GTAIV
    becomes
    Z:\\home\\deck\\.local\\share\\Steam\\steamapps\\common\\Grand Theft Auto IV\\GTAIV
    """
    return "Z:" + linux_path.replace("/", "\\")


def _write_install_path_registry(compatdata_path, game_root):
    """
    Write the GTA IV install path into the Wine prefix's system.reg (HKLM)
    so the NSIS installer can auto-detect the game directory.

    The Radio Restoration NSIS installer reads:
        HKLM\\SOFTWARE\\Rockstar Games\\Grand Theft Auto IV\\InstallFolder

    Wine system.reg format:
      Keys are relative to HKEY_LOCAL_MACHINE (no HKLM prefix).
      Path separators in key names are double-backslash (\\\\).
      String values use Wine's escaped format with double backslashes.

    We write to both the native path and the Wow6432Node path because
    the NSIS exe is 32-bit — Wine may look under either location.
    """
    system_reg = os.path.join(compatdata_path, "pfx", "system.reg")

    if not os.path.exists(system_reg):
        _log.warning("radio_restoration: system.reg not found at %s",
                       system_reg)
        return False

    with open(system_reg, "r", errors="replace") as f:
        content = f.read()

    # Convert Linux path to Wine Z: path, then double backslashes for
    # the .reg file format (Wine system.reg stores \\ for each \)
    wine_path = _linux_to_wine_path(game_root)
    reg_value_path = wine_path.replace("\\", "\\\\")

    key_paths = [
        r"[Software\\Rockstar Games\\Grand Theft Auto IV]",
        r"[Software\\Wow6432Node\\Rockstar Games\\Grand Theft Auto IV]",
    ]

    for key_path in key_paths:
        value_line = f'"InstallFolder"="{reg_value_path}"'

        escaped_key = re.escape(key_path)
        pattern = re.compile(
            rf'({escaped_key}[^\n]*\n)((?:(?!\[)[^\n]*\n)*)',
            re.MULTILINE
        )
        match = pattern.search(content)

        if match:
            header = match.group(1)
            existing_body = match.group(2)

            # Parse existing values to preserve any we don't manage
            existing_values = {}
            for line in existing_body.strip().split("\n"):
                line = line.strip()
                if line and "=" in line:
                    k = line.split("=", 1)[0]
                    existing_values[k] = line

            # Set or overwrite InstallFolder
            existing_values['"InstallFolder"'] = value_line

            new_body = "\n".join(existing_values.values()) + "\n"
            content = (
                content[:match.start()] + header + new_body +
                content[match.end():]
            )
            _log.debug("radio_restoration: updated registry key %s",
                        key_path)
        else:
            # Key block doesn't exist — append it
            block = f"\n{key_path}\n{value_line}\n"
            content += block
            _log.debug("radio_restoration: added registry key %s", key_path)

    with open(system_reg, "w", errors="replace") as f:
        f.write(content)

    _log.info("radio_restoration: registry key written (%s)", wine_path)
    return True


def _find_vanilla_proton(steam_root):
    """
    Find the newest vanilla Proton in steamapps/common/.

    The NSIS Radio Restoration exe only works with vanilla Proton
    (tested: Proton 11.0 works, GE-Proton exits with code 5).
    This function specifically avoids GE-Proton.

    Returns the path to the proton binary, or None if not found.
    """
    def _version_key(name):
        parts = re.findall(r'\d+', name)
        return tuple(int(p) for p in parts)

    common = os.path.join(steam_root, "steamapps", "common")
    if not os.path.isdir(common):
        return None

    proton_dirs = [
        d for d in os.listdir(common)
        if d.startswith("Proton") and
        not d.startswith("Proton GE") and
        not d.startswith("Proton Hotfix") and
        os.path.exists(os.path.join(common, d, "proton"))
    ]
    if not proton_dirs:
        return None

    proton_dirs.sort(key=_version_key, reverse=True)
    chosen = os.path.join(common, proton_dirs[0], "proton")
    _log.debug("radio_restoration: vanilla proton = %s", chosen)
    return chosen


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
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            _log.debug("radio_restoration: rar extracted to %s", dest_dir)
            return True
        else:
            _log.error("radio_restoration: unrar failed: %s", result.stderr)
            return False
    except subprocess.TimeoutExpired:
        _log.error("radio_restoration: unrar timed out (rar is ~1 GB)")
        return False
    except Exception:
        _log.error("radio_restoration: unrar failed", exc_info=True)
        return False


def _find_exe(base_dir):
    """
    Find IVCERadioRestoration.exe in extracted content.
    The rar may or may not have a wrapping folder.
    Returns the full path, or None if not found.
    """
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower() == "ivceradiorestoration.exe":
                return os.path.join(root, f)
    return None
