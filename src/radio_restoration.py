"""
radio_restoration.py - Radio Restoration installer for GamingTweaksAppliedIV

Downloads and runs the IVCERadioRestoration NSIS installer from
Tomasak's GTA-Downgraders GitHub releases. This mod restores licensed
music tracks that Rockstar removed due to expired licenses, and
restores The Classics and The Beat 102.7 radio stations.

The installer is an NSIS exe that patches the game's audio RPF archives
using binary diffs (the .dat files in Resources/Radio Restorer/). It
cannot be done by simply copying files -- the exe must be run.

On Linux/SteamOS, the installer runs through GE-Proton using the
game's existing Wine prefix (compatdata/12210/). NSIS supports silent
mode via /S flag, with /D= to set the install directory.

The release asset is a .rar archive, so we need unrar to extract it.
SteamOS has unrar available. If it's missing, we fall back to showing
a manual install prompt.

Structure inside the rar:
    Radio.Restoration.Mod/
        IVCERadioRestoration.exe
        Resources/
            Banners/          (installer UI images)
            External/
                7za.exe       (bundled 7-Zip for patching)
            Radio Restorer/
                data1.dat     (main radio data)
                hashes.ini    (hash verification)
                opALL.dat     (all restoration)
                opCLASSIC.dat (classic/pre-cut only)
                opSPLIT*.dat  (split radio variants)
                opVANILLA*.dat (vanilla variants)

Usage:
    from radio_restoration import install, is_installed, get_latest_version

    version, url = get_latest_version()
    success = install(game_root, steam_root, on_progress=callback)
"""

import json
import os
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

# GTA IV Steam appid (for finding the Proton prefix)
_GTAIV_APPID = 12210


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


def install(game_root, steam_root=None, on_progress=None,
            version_tag=None, download_url=None):
    """
    Download and install Radio Restoration to a GTA IV game root.

    The installer is run through GE-Proton in silent mode. If silent
    mode fails, falls back to launching with GUI visible.

    game_root    -- path to the GTAIV/ subfolder where GTAIV.exe lives
    steam_root   -- path to Steam root (for finding compatdata prefix).
                    If None, uses cfg.get_steam_root() or default path.
    on_progress  -- optional callback(message: str)
    version_tag  -- optional version string to save.
    download_url -- optional direct download URL.

    Returns True on success, False on error.
    Raises DownloadError if the download fails.
    """
    _log.info("radio_restoration: installing to %s", game_root)

    # Resolve version and URL if not provided
    if not download_url:
        if not version_tag:
            version_tag, download_url = get_latest_version()
        if not download_url:
            _log.error("radio_restoration: no download URL available")
            return False

    # Check for unrar
    if not _has_unrar():
        _log.error("radio_restoration: unrar not found -- cannot extract "
                     "the .rar archive. Install unrar and try again.")
        return False

    # Resolve steam root for the Proton prefix
    if not steam_root:
        steam_root = cfg.load().get("steam_root")
    if not steam_root:
        steam_root = os.path.expanduser("~/.local/share/Steam")

    tmp_dir = tempfile.mkdtemp(prefix="gamingtweaksappliediv_rr_")
    try:
        # Step 1: Download the rar
        rar_name = "RadioRestoration.rar"
        rar_path = os.path.join(tmp_dir, rar_name)
        if on_progress:
            on_progress("Downloading Radio Restoration...")

        try:
            download(download_url, rar_path, label="Radio Restoration")
        except Exception as e:
            raise DownloadError(
                url=download_url, dest=rar_path,
                label="Radio Restoration", cause=e,
            )

        # Step 2: Extract the rar
        if on_progress:
            on_progress("Extracting Radio Restoration...")

        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        if not _extract_rar(rar_path, extract_dir):
            _log.error("radio_restoration: failed to extract rar")
            return False

        # Step 3: Find the exe inside extracted content
        exe_path = _find_exe(extract_dir)
        if not exe_path:
            _log.error("radio_restoration: IVCERadioRestoration.exe "
                         "not found in extracted content")
            return False

        # Step 4: Run the installer through Proton
        if on_progress:
            on_progress("Running Radio Restoration installer...")

        # Convert game_root to a Wine Z: drive path
        wine_game_root = "Z:" + game_root.replace("/", "\\")

        success = _run_installer(
            exe_path, wine_game_root, steam_root, on_progress
        )

        if success:
            cfg.set_radio_restoration_installed(True)
            if on_progress:
                on_progress("Radio Restoration installed")
            _log.info("radio_restoration: installed successfully")
        else:
            _log.error("radio_restoration: installer failed")

        return success

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def uninstall(game_root):
    """
    Mark Radio Restoration as uninstalled.

    Radio Restoration patches the game's audio RPF archives in place.
    To actually undo the changes, the user would need to verify game
    files through Steam (Properties -> Installed Files -> Verify).
    We just clear the config flag.

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


def _find_exe(base_dir):
    """
    Recursively search for IVCERadioRestoration.exe in extracted content.
    The rar may have a wrapping folder (Radio.Restoration.Mod/).
    """
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower() == "ivceradiorestoration.exe":
                return os.path.join(root, f)
    return None


def _find_proton(steam_root):
    """
    Find GE-Proton or Proton Experimental in the Steam compatibilitytools.d
    directory. Returns the path to the proton script, or None.
    """
    compat_dir = os.path.join(steam_root, "compatibilitytools.d")
    if not os.path.isdir(compat_dir):
        # Try the home directory fallback
        compat_dir = os.path.expanduser(
            "~/.steam/root/compatibilitytools.d"
        )

    if not os.path.isdir(compat_dir):
        return None

    # Prefer GE-Proton, fall back to any Proton
    candidates = []
    for d in sorted(os.listdir(compat_dir), reverse=True):
        proton_script = os.path.join(compat_dir, d, "proton")
        if os.path.isfile(proton_script):
            if "GE-Proton" in d:
                return proton_script
            candidates.append(proton_script)

    return candidates[0] if candidates else None


def _get_prefix_path(steam_root):
    """Get the Wine prefix path for GTA IV (appid 12210)."""
    # Check common locations
    for base in [
        os.path.join(steam_root, "steamapps", "compatdata"),
        os.path.expanduser(
            "~/.local/share/Steam/steamapps/compatdata"
        ),
    ]:
        prefix = os.path.join(base, str(_GTAIV_APPID), "pfx")
        if os.path.isdir(prefix):
            return prefix

    return None


def _run_installer(exe_path, wine_game_root, steam_root, on_progress):
    """
    Run the NSIS installer through Proton.

    Tries silent mode first (/S /D=path). If that fails or times out,
    logs a warning. The installer needs to run in the directory where
    the exe and Resources/ folder are located.

    Returns True if the installer exits successfully, False otherwise.
    """
    proton = _find_proton(steam_root)
    if not proton:
        _log.error("radio_restoration: no Proton found in %s", steam_root)
        return False

    prefix = _get_prefix_path(steam_root)
    if not prefix:
        _log.error("radio_restoration: GTA IV Wine prefix not found")
        return False

    # The installer must run from its own directory (where Resources/ is)
    exe_dir = os.path.dirname(exe_path)

    env = os.environ.copy()
    env["STEAM_COMPAT_DATA_PATH"] = os.path.dirname(prefix)
    env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = steam_root
    env["WINEPREFIX"] = prefix

    # Log environment for diagnostics
    _log.info("radio_restoration: proton = %s", proton)
    _log.info("radio_restoration: STEAM_COMPAT_DATA_PATH = %s",
              env["STEAM_COMPAT_DATA_PATH"])
    _log.info("radio_restoration: STEAM_COMPAT_CLIENT_INSTALL_PATH = %s",
              env["STEAM_COMPAT_CLIENT_INSTALL_PATH"])
    _log.info("radio_restoration: WINEPREFIX = %s", env["WINEPREFIX"])
    _log.info("radio_restoration: wine_game_root = %s", wine_game_root)
    _log.info("radio_restoration: exe_path = %s", exe_path)
    _log.info("radio_restoration: cwd (exe_dir) = %s", exe_dir)

    # Log contents of exe_dir so we can verify Resources/ is present
    try:
        dir_contents = os.listdir(exe_dir)
        _log.info("radio_restoration: exe_dir contents: %s", dir_contents)
        # Check for Resources subdirectory
        resources_dir = os.path.join(exe_dir, "Resources")
        if os.path.isdir(resources_dir):
            res_contents = os.listdir(resources_dir)
            _log.info("radio_restoration: Resources/ contents: %s",
                       res_contents)
        else:
            _log.warning("radio_restoration: Resources/ not found in "
                          "exe_dir -- installer may fail")
    except OSError:
        _log.warning("radio_restoration: could not list exe_dir",
                      exc_info=True)

    # Try silent mode
    cmd = [
        proton, "run", exe_path,
        "/S",
        f"/D={wine_game_root}",
    ]

    _log.info("radio_restoration: running installer (silent mode): %s", cmd)

    try:
        result = subprocess.run(
            cmd, cwd=exe_dir, env=env,
            capture_output=True, text=True,
            timeout=300,  # 5 minute timeout for patching
        )

        _log.info("radio_restoration: installer exit code: %d",
                   result.returncode)
        if result.stdout:
            _log.info("radio_restoration: installer stdout:\n%s",
                       result.stdout.strip())
        if result.stderr:
            _log.info("radio_restoration: installer stderr:\n%s",
                       result.stderr.strip())

        if result.returncode == 0:
            _log.info("radio_restoration: silent install succeeded")
            return True
        else:
            _log.error("radio_restoration: silent install failed with "
                        "exit code %d", result.returncode)
            return False

    except subprocess.TimeoutExpired:
        _log.warning("radio_restoration: installer timed out after 5 min")
        return False
    except Exception:
        _log.error("radio_restoration: failed to run installer",
                     exc_info=True)
        return False
