"""
detect_games.py - GamingTweaksAppliedIV game detection

Detects installed GTA IV from two sources:
  1. Steam library (appid 12210) - primary path
  2. Own-game scan (user-provided game files) - fallback

Unlike NFSBlacklist (four non-Steam titles), GTA IV is on Steam, so the
primary detection path is Steam library scanning via appmanifest_12210.acf.

The game root where mods are installed is the GTAIV subfolder, not the
top-level "Grand Theft Auto IV" folder:
    steamapps/common/Grand Theft Auto IV/GTAIV/GTAIV.exe

Case sensitivity: Linux filesystems are case-sensitive, but game files
from Windows installs have unpredictable casing. All file lookups use
case-insensitive matching to handle whatever the user gives us.
"""

import os
import re
import glob

from log import get_logger

_log = get_logger(__name__)

# -- Game definitions ---------------------------------------------------------
# GTA IV: The Complete Edition is the only title GamingTweaksAppliedIV supports.

GAMES = {
    "gtaiv": {
        "name": "Grand Theft Auto IV: The Complete Edition",
        "order": 1,
        "exe": "GTAIV.exe",
        "year": 2008,
        "steam_appid": 12210,
        "steam_folder": "Grand Theft Auto IV",
    },
}

# Steam appid for GTA IV
GTAIV_APPID = 12210


# -- Case-insensitive file helpers --------------------------------------------
# Game files from Windows installs have unpredictable casing. These helpers
# find files regardless of how the user's copy is cased.

def _ipath(base, *parts):
    """
    Case-insensitive path join. Walks each path component and finds the
    actual entry on disk that matches case-insensitively.

    Returns the resolved path if every component is found, None otherwise.

    Example:
        _ipath("/home/deck/Games/GTAIV", "pc", "data")
        might return "/home/deck/Games/GTAIV/PC/Data" or whatever
        casing actually exists on disk.
    """
    current = base
    for part in parts:
        if not os.path.isdir(current):
            return None
        part_lower = part.lower()
        try:
            entries = os.listdir(current)
        except OSError:
            return None
        match = None
        for entry in entries:
            if entry.lower() == part_lower:
                match = entry
                break
        if match is None:
            return None
        current = os.path.join(current, match)
    return current


def _iexists(base, *parts):
    """Case-insensitive check for whether a path exists."""
    return _ipath(base, *parts) is not None


def _ifind_exe(game_root, exe_name):
    """
    Find the game exe in game_root with case-insensitive matching.
    Returns the full path to the exe, or a best-guess path if not found.
    """
    resolved = _ipath(game_root, exe_name)
    if resolved and os.path.isfile(resolved):
        return resolved
    # Fall back to the expected path even if it doesn't exist on disk
    return os.path.join(game_root, exe_name)


def get_exe_size(exe_path):
    if os.path.exists(exe_path):
        return os.path.getsize(exe_path)
    return None


# -- Steam library detection ---------------------------------------------------
# GTA IV is on Steam (appid 12210). This is the primary detection path.
# Scans all Steam library folders for the appmanifest, then resolves the
# actual game root (the GTAIV subfolder).

def _find_steam_libraries():
    """
    Find all Steam library folders from libraryfolders.vdf.
    Returns a list of paths to steamapps/ directories.
    """
    steam_root = os.path.expanduser("~/.local/share/Steam")
    vdf_path = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")

    if not os.path.exists(vdf_path):
        # Try the symlink path
        vdf_path = os.path.expanduser("~/.steam/root/steamapps/libraryfolders.vdf")
        if not os.path.exists(vdf_path):
            return [os.path.join(steam_root, "steamapps")]

    libraries = []
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # Extract "path" values from libraryfolders.vdf
        for match in re.finditer(r'"path"\s*"([^"]+)"', content):
            lib_path = os.path.join(match.group(1), "steamapps")
            if os.path.isdir(lib_path):
                libraries.append(lib_path)
    except OSError:
        _log.debug("libraryfolders.vdf read failed", exc_info=True)

    # Always include the default library
    default = os.path.join(steam_root, "steamapps")
    if default not in libraries and os.path.isdir(default):
        libraries.insert(0, default)

    return libraries


def _find_game_root_from_manifest(steamapps_dir, install_dir_name):
    """
    Given a steamapps directory and the installdir name from the manifest,
    resolve the actual game root where mods are installed.

    For GTA IV, the mod target is the GTAIV subfolder inside the install dir:
        steamapps/common/Grand Theft Auto IV/GTAIV/

    Returns the game root path or None if not found.
    """
    common_dir = os.path.join(steamapps_dir, "common", install_dir_name)
    if not os.path.isdir(common_dir):
        return None

    # The GTAIV subfolder is the actual game root where mods go
    gtaiv_sub = _ipath(common_dir, "GTAIV")
    if gtaiv_sub and os.path.isdir(gtaiv_sub):
        return gtaiv_sub

    # Fallback: check if GTAIV.exe is in the top-level dir (unusual layout)
    if _iexists(common_dir, "GTAIV.exe"):
        return common_dir

    return None


def find_steam_installed(on_progress=None):
    """
    Detect GTA IV installed via Steam.

    Scans all Steam library folders for appmanifest_12210.acf, then
    resolves the game root (the GTAIV subfolder where mods go).

    Returns a dict of game keys -> game info dicts with "source": "steam",
    or empty dict if not found.

    on_progress -- optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    libraries = _find_steam_libraries()
    if not libraries:
        prog("No Steam libraries found.")
        return {}

    found = {}

    for steamapps_dir in libraries:
        manifest = os.path.join(steamapps_dir, f"appmanifest_{GTAIV_APPID}.acf")
        if not os.path.exists(manifest):
            continue

        prog(f"Found GTA IV manifest in {steamapps_dir}")

        # Parse installdir from the manifest
        install_dir_name = None
        try:
            with open(manifest, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            match = re.search(r'"installdir"\s*"([^"]+)"', content, re.IGNORECASE)
            if match:
                install_dir_name = match.group(1)
        except OSError:
            _log.debug("appmanifest read failed", exc_info=True)
            continue

        if not install_dir_name:
            install_dir_name = "Grand Theft Auto IV"

        game_root = _find_game_root_from_manifest(steamapps_dir, install_dir_name)
        if not game_root:
            prog(f"  !!  Game files not found at expected location")
            continue

        meta = GAMES["gtaiv"]
        exe_path = _ifind_exe(game_root, meta["exe"])

        # Compatdata path for the Steam install
        compatdata_path = os.path.join(steamapps_dir, "compatdata", str(GTAIV_APPID))

        found["gtaiv"] = {
            **meta,
            "install_dir":     game_root,
            "exe_path":        exe_path,
            "exe_size":        get_exe_size(exe_path),
            "source":          "steam",
            "steam_appid":     GTAIV_APPID,
            "compatdata_path": compatdata_path if os.path.isdir(compatdata_path) else None,
            "steamapps_dir":   steamapps_dir,
        }
        prog(f"  found gtaiv: {meta['name']} at {game_root}")
        break  # Only one GTA IV install possible

    return found


# -- Own-game detection --------------------------------------------------------
# Fallback for users who have GTA IV game files outside of Steam.
# Scans common locations for known folder names and verifies with sentinel files.

# Sentinel file for GTA IV: GTAIV.exe in the game root confirms this is
# actually GTA IV and not some other Rockstar game.
GAME_SENTINELS = {
    "gtaiv": ("GTAIV.exe",),
}

KEY_TO_SENTINEL = {
    "gtaiv": "gtaiv",
}

# Exact folder name -> list of game keys (case-insensitive).
FOLDER_TO_KEYS = {
    "grand theft auto iv":                    ["gtaiv"],
    "grand theft auto iv the complete edition": ["gtaiv"],
    "gta iv":                                 ["gtaiv"],
    "gta4":                                   ["gtaiv"],
    "gtaiv":                                  ["gtaiv"],
}

# Keyword rules checked when exact match fails.
_SEP = r'(?:^|(?<=[\s_\-])|\b)'
_END = r'(?:$|(?=[\s_\-])|\b)'

_KEYWORD_RULES = [
    (re.compile(_SEP + r'(gta[\s_\-]*iv|gta[\s_\-]*4|gtaiv)' + _END, re.IGNORECASE), ["gtaiv"]),
]

# Default scan locations
OWN_SCAN_PATHS = [
    os.path.expanduser("~/Games"),
    os.path.expanduser("~/games"),
    os.path.expanduser("~/GTA"),
    "/run/media/deck/*/Games",
    "/run/media/deck/*/games",
    "/run/media/deck/*/GTA",
    "/run/media/deck/*",
    "/run/media/mmcblk0p1",
]

_MAX_SCAN_DEPTH = 5
_SENTINEL_SCAN_DEPTH = 3


def _check_sentinel(candidate_dir, sentinel_group):
    """
    Check if a sentinel file exists relative to candidate_dir.
    Uses case-insensitive path matching since game files from
    Windows installs have unpredictable casing.

    Returns True if the sentinel is found, False otherwise.
    """
    sentinel_parts = GAME_SENTINELS.get(sentinel_group)
    if not sentinel_parts:
        return False

    return _iexists(candidate_dir, *sentinel_parts)


def _find_game_root(candidate_dir, sentinel_group):
    """
    Starting from candidate_dir (a folder that matched by name), search
    for the sentinel file to confirm the game identity and locate the
    actual game root directory.

    For GTA IV, the game root may be a GTAIV subfolder inside the matched
    directory (matching the Steam layout).

    1. Check candidate_dir itself
    2. Walk up to _SENTINEL_SCAN_DEPTH levels deep looking for the sentinel

    Returns the confirmed game root path, or None if the sentinel was not
    found (indicating an incomplete, wrong, or empty install).
    """
    # Check the candidate dir directly first - most common case
    if _check_sentinel(candidate_dir, sentinel_group):
        return candidate_dir

    # Search subdirectories up to _SENTINEL_SCAN_DEPTH levels deep
    skip = {"__pycache__", ".git", ".svn"}
    for dirpath, dirnames, _filenames in os.walk(candidate_dir):
        rel = os.path.relpath(dirpath, candidate_dir)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= _SENTINEL_SCAN_DEPTH:
            dirnames.clear()
            continue
        # Skip hidden dirs and known junk
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip]

        # Don't re-check candidate_dir (already checked above)
        if dirpath == candidate_dir:
            continue

        if _check_sentinel(dirpath, sentinel_group):
            return dirpath

    return None


def _walk_limited(root, max_depth):
    """Walk a directory tree up to max_depth levels deep."""
    skip = {".steam", ".local", ".cache", ".config", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= max_depth:
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in skip]
        yield dirpath, dirnames, filenames


def _match_folder(name):
    """
    Try to match a folder name to a set of game keys.
    Returns a list of keys or an empty list if no match.

    Pass 1 - exact match (case-insensitive).
    Pass 2 - keyword regex rules in priority order.
    """
    name_lower = name.lower()

    # Pass 1 - exact
    if name_lower in FOLDER_TO_KEYS:
        return FOLDER_TO_KEYS[name_lower]

    # Pass 2 - keyword
    for pattern, keys in _KEYWORD_RULES:
        if pattern.search(name):
            return keys

    return []


def find_own_installed(extra_paths=None, on_progress=None):
    """
    Scan the filesystem for GTA IV game folders outside of Steam.

    Searches ~/Games, ~/games, ~/GTA, SD card game folders, plus any
    user-provided extra paths (e.g. from a folder picker in the UI).

    Detection is two-phase:
      1. Folder name matching (exact then keyword) finds candidate directories
      2. Sentinel file check confirms the game and locates the actual game root
         (which may be the matched folder or a subfolder up to 3 levels deep)

    Returns a dict of game keys -> game info dicts with "source": "own".

    extra_paths -- optional list of additional directories to scan
    on_progress -- optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    # Build scan list: defaults + globs + extras
    scan_dirs = []
    seen = set()
    for pattern in OWN_SCAN_PATHS:
        for path in glob.glob(pattern):
            path = os.path.normpath(path)
            if path not in seen and os.path.isdir(path):
                seen.add(path)
                scan_dirs.append(path)
    if extra_paths:
        for path in extra_paths:
            path = os.path.normpath(path)
            if path not in seen and os.path.isdir(path):
                seen.add(path)
                scan_dirs.append(path)

    if not scan_dirs:
        prog("No game folders found to scan.")
        return {}

    found = {}

    for scan_dir in scan_dirs:
        prog(f"Scanning {scan_dir}...")
        for dirpath, dirnames, _filenames in _walk_limited(scan_dir, _MAX_SCAN_DEPTH):
            folder_name = os.path.basename(dirpath)
            matched_keys = _match_folder(folder_name)

            if not matched_keys:
                continue

            # Determine the sentinel group from the first matched key
            sentinel_group = KEY_TO_SENTINEL.get(matched_keys[0])
            if not sentinel_group:
                dirnames.clear()
                for key in matched_keys:
                    if key in found:
                        continue
                    meta = GAMES.get(key)
                    if not meta:
                        continue
                    exe_path = _ifind_exe(dirpath, meta["exe"])
                    found[key] = {
                        **meta,
                        "install_dir": dirpath,
                        "exe_path":    exe_path,
                        "exe_size":    get_exe_size(exe_path),
                        "source":      "own",
                    }
                    prog(f"  found {key}: {meta['name']} at {dirpath}")
                continue

            # Run sentinel check to confirm and locate actual game root
            game_root = _find_game_root(dirpath, sentinel_group)

            if game_root is None:
                prog(f"  {folder_name}: folder matched but game files not found, skipping")
                continue

            # Sentinel confirmed - stop descending into this branch
            dirnames.clear()

            if game_root != dirpath:
                prog(f"  {folder_name}: game root found in subfolder {os.path.relpath(game_root, dirpath)}")

            for key in matched_keys:
                if key in found:
                    continue
                meta = GAMES.get(key)
                if not meta:
                    continue

                exe_path = _ifind_exe(game_root, meta["exe"])
                found[key] = {
                    **meta,
                    "install_dir": game_root,
                    "exe_path":    exe_path,
                    "exe_size":    get_exe_size(exe_path),
                    "source":      "own",
                }
                prog(f"  found {key}: {meta['name']} at {game_root}")

    if not found:
        prog("No GTA IV install found outside Steam.")
    else:
        prog(f"Found {len(found)} game(s).")

    return found


# -- Combined detection --------------------------------------------------------

def detect_all(extra_paths=None, on_progress=None):
    """
    Detect GTA IV from all sources. Steam library is checked first,
    then own-game scan as a fallback.

    Returns a dict of game keys -> game info dicts. Steam installs
    take priority over own-game installs if both are found.

    extra_paths -- optional list of additional directories for own-game scan
    on_progress -- optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    found = {}

    # Steam first (primary path)
    prog("Checking Steam library...")
    steam = find_steam_installed(on_progress=on_progress)
    found.update(steam)

    # Own-game fallback (only if Steam didn't find it)
    if "gtaiv" not in found:
        prog("GTA IV not found in Steam library. Scanning for own-game installs...")
        own = find_own_installed(extra_paths=extra_paths, on_progress=on_progress)
        found.update(own)

    if found:
        source = found["gtaiv"]["source"]
        prog(f"GTA IV detected ({source} install).")
    else:
        prog("GTA IV not found.")

    return found


# -- CLI test harness ----------------------------------------------------------

if __name__ == "__main__":
    print("GTA IV detection:")
    print()
    print("--- Steam library ---")
    steam = find_steam_installed(on_progress=print)
    for key, game in steam.items():
        print(f"  [{key}] {game['name']}")
        print(f"        {game['install_dir']}")
        print(f"        source: {game['source']}")

    print()
    print("--- Own-game scan ---")
    own = find_own_installed(on_progress=print)
    for key, game in own.items():
        print(f"  [{key}] {game['name']}")
        print(f"        {game['install_dir']}")

    print()
    print("--- Combined ---")
    all_found = detect_all(on_progress=print)
    for key, game in all_found.items():
        print(f"  [{key}] {game['name']} ({game['source']})")
        print(f"        {game['install_dir']}")
