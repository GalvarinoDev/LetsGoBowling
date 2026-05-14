"""
shortcut.py - GetToAmericaIV non-Steam shortcut creator

Creates non-Steam game shortcuts in Steam for GTA IV own-game installs.
GTA IV is on Steam (appid 12210), so Steam installs don't need shortcuts.
This module is only used when the user has the game files outside of Steam
(retail copy, other source) and wants to launch via a non-Steam shortcut
with Proton.

Shortcuts include:
  - Proper artwork (icon, grid, wide, hero, logo) from SteamGridDB
  - Correct compatdata prefix via STEAM_COMPAT_DATA_PATH
  - WINEDLLOVERRIDES="dinput8=n,b" for ASI loader (FusionFix needs this)
  - Proton compat tool assignment
  - Steam Input enabled (AllowDesktopConfig)
  - Controller template assignment (stubbed - Phase 5)

Called from ui_install.py in two phases:
  1. enrich_own_games()    -- early, before prefix creation
  2. write_own_shortcuts() -- after mod installs are complete

Must be called while Steam is closed.
"""

import binascii
import os
import re
import shutil
import struct
import threading
import time
import urllib.request

from identity import INSTALL_DIR, asset_url
from log import get_logger

_log = get_logger(__name__)


# -- Paths --------------------------------------------------------------------

STEAM_ROOT     = os.path.expanduser("~/.local/share/Steam")
USERDATA_DIR   = os.path.join(STEAM_ROOT, "userdata")
COMPAT_ROOT    = os.path.join(STEAM_ROOT, "steamapps", "compatdata")
STEAM_CONFIG   = os.path.join(STEAM_ROOT, "config", "config.vdf")

_HERE          = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(_HERE)

# Controller templates directory - not populated yet (Phase 5).
# When TPS/driving VDFs land they go here.
ASSETS_DIR     = os.path.join(PROJECT_ROOT, "assets", "controllers")

MIN_UID = 10000

_BROWSER_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
}


# -- GTA IV shortcut definitions ----------------------------------------------
# Used for own-game non-Steam shortcuts. Steam installs (appid 12210) get
# their artwork via STEAM_ARTWORK below, not from here.
#
# template_type is reserved for Phase 5 controller templates. GTA IV uses
# a combined TPS + driving layout (unlike DeckOps FPS or NFSBlacklist racing).
#
# Artwork credits: SteamGridDB community artists (see README.md)

GTAIV_SHORTCUTS = {
    "gtaiv": {
        "name":           "Grand Theft Auto IV: The Complete Edition",
        "template_type":  "tps",
        "icon_url":       "https://cdn2.steamgriddb.com/icon/8d8818c8e140c64c743113f563cf750f/32/256x256.png",
        "grid_url":       "https://cdn2.steamgriddb.com/grid/a32bc8141e168ff20fdfe3f0fbc72155.png",
        "wide_url":       "https://cdn2.steamgriddb.com/grid/aa5438a141ecad74c9b9b284971ab20c.png",
        "hero_url":       "https://cdn2.steamgriddb.com/hero/ed58966527f3896422f854dc5d703513.png",
        "logo_url":       "https://cdn2.steamgriddb.com/logo/e69aa3389bba902b227d5de50c815dd1.png",
        "icon_ext": "png", "grid_ext": "png", "wide_ext": "png",
        "hero_ext": "png", "logo_ext": "png",
    },
}


# -- Steam install artwork ----------------------------------------------------
# Custom artwork applied to the GTA IV Steam library entry (appid 12210).
# Files are written to userdata/<uid>/config/grid/ using the Steam appid as
# the filename prefix so Steam picks them up on next launch.
#
# Artwork credits: SteamGridDB community artists (see README.md)

STEAM_ARTWORK = {
    "12210": {
        "icon_url":  "https://cdn2.steamgriddb.com/icon/8d8818c8e140c64c743113f563cf750f/32/256x256.png",
        "grid_url":  "https://cdn2.steamgriddb.com/grid/a32bc8141e168ff20fdfe3f0fbc72155.png",
        "wide_url":  "https://cdn2.steamgriddb.com/grid/aa5438a141ecad74c9b9b284971ab20c.png",
        "hero_url":  "https://cdn2.steamgriddb.com/hero/ed58966527f3896422f854dc5d703513.png",
        "logo_url":  "https://cdn2.steamgriddb.com/logo/e69aa3389bba902b227d5de50c815dd1.png",
        "icon_ext": "png", "grid_ext": "png", "wide_ext": "png",
        "hero_ext": "png", "logo_ext": "png",
    },
}


# -- Helpers ------------------------------------------------------------------

def _find_all_steam_uids():
    """Return all valid Steam user ID folders from userdata/."""
    if not os.path.isdir(USERDATA_DIR):
        return []
    seen, uids = set(), []
    for entry in os.listdir(USERDATA_DIR):
        if not entry.isdigit() or int(entry) < MIN_UID:
            continue
        real = os.path.realpath(os.path.join(USERDATA_DIR, entry))
        if real in seen:
            continue
        seen.add(real)
        uids.append(entry)
    return uids


def _get_deck_serial() -> str | None:
    """Read the Steam Deck serial number from Steam's config.vdf."""
    if not os.path.exists(STEAM_CONFIG):
        return None
    try:
        with open(STEAM_CONFIG, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        match = re.search(r'"SteamDeckRegisteredSerialNumber"\s+"([^"]+)"', content)
        if match:
            return match.group(1)
    except Exception:
        _log.debug("serial number read failed", exc_info=True)
    return None


def _calc_shortcut_appid(exe_path: str, name: str) -> int:
    """
    Calculate the Steam shortcut appid from exe path and name.
    This must match Steam's internal algorithm exactly. If the CRC or
    bitmask changes, shortcuts will not resolve and artwork/controller
    configs will point to the wrong appid. Do not modify.
    """
    key = (exe_path + name).encode("utf-8")
    crc = binascii.crc32(key) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


def _to_signed32(n):
    """Convert unsigned int32 appid to signed int32 for vdf binary format."""
    return n if n <= 2147483647 else n - 2**32


def _download(url: str, dest: str) -> bool:
    """Download a file from URL to dest path. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        req = urllib.request.Request(url, headers=_BROWSER_UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(dest, "wb") as f:
                f.write(r.read())
        return True
    except Exception:
        _log.debug("artwork download failed", exc_info=True)
        return False


# -- Binary VDF helpers -------------------------------------------------------

def _vdf_string(key: str, val: str) -> bytes:
    """Encode a string field for binary VDF."""
    return b'\x01' + key.encode('utf-8') + b'\x00' + val.encode('utf-8') + b'\x00'


def _vdf_int32(key: str, val: int) -> bytes:
    """Encode an int32 field for binary VDF."""
    return b'\x02' + key.encode('utf-8') + b'\x00' + struct.pack('<i', val)


def _make_shortcut_entry(idx: int, fields: dict) -> bytes:
    """Build a single shortcut entry in binary VDF format."""
    data = b'\x00' + str(idx).encode('utf-8') + b'\x00'

    for key, value in fields.items():
        if key == "tags":
            # Tags is a sub-dict
            data += b'\x00' + b'tags' + b'\x00'
            for tk, tv in value.items():
                data += _vdf_string(tk, tv)
            data += b'\x08'
        elif isinstance(value, str):
            data += _vdf_string(key, value)
        elif isinstance(value, int):
            data += _vdf_int32(key, value)

    data += b'\x08'
    return data


def _read_existing_shortcuts(path: str) -> list:
    """Return list of existing shortcut names from shortcuts.vdf."""
    if not os.path.exists(path):
        return []

    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        _log.debug("shortcuts.vdf read failed", exc_info=True)
        return []

    # Extract AppName values
    existing = []
    for match in re.finditer(b'\x01[Aa]pp[Nn]ame\x00([^\x00]+)\x00', data):
        existing.append(match.group(1).decode('utf-8', errors='replace'))

    return existing


def _read_shortcuts_raw(path: str) -> bytes:
    """Read the raw shortcuts.vdf content, stripping header/footer."""
    if not os.path.exists(path):
        return b''

    try:
        with open(path, 'rb') as f:
            data = f.read()
    except Exception:
        _log.debug("shortcuts.vdf read failed", exc_info=True)
        return b''

    # Strip header (b'\x00shortcuts\x00') and footer (b'\x08\x08')
    header = b'\x00shortcuts\x00'
    if data.startswith(header):
        data = data[len(header):]
    if data.endswith(b'\x08\x08'):
        data = data[:-2]
    elif data.endswith(b'\x08'):
        data = data[:-1]

    return data


def _get_next_index(raw_data: bytes) -> int:
    """
    Find the next available shortcut index from raw shortcut entry data.

    Shortcut entries start with the byte sequence: 0x00 <index_str> 0x00
    immediately followed by 0x02 (the appid int field marker). This two-byte
    lookahead distinguishes real entry headers from the many other 0x00...0x00
    numeric sequences present in binary VDF data.
    """
    if not raw_data:
        return 0

    indices = []
    i = 0
    while i < len(raw_data) - 2:
        if raw_data[i] == 0x00:
            end = raw_data.find(b'\x00', i + 1)
            if end != -1 and end > i + 1:
                if end + 1 < len(raw_data) and raw_data[end + 1] == 0x02:
                    try:
                        idx_str = raw_data[i + 1:end].decode('utf-8')
                        if idx_str.isdigit():
                            indices.append(int(idx_str))
                    except (UnicodeDecodeError, ValueError):
                        _log.debug("shortcut index parse failed", exc_info=True)
                i = end + 1
            else:
                i += 1
        else:
            i += 1

    return max(indices, default=-1) + 1


def _backup_file(path: str):
    """Write a .bak copy before modifying a Steam config file."""
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            _log.debug("shortcuts.vdf backup failed", exc_info=True)


def _write_shortcuts_vdf(path: str, existing_raw: bytes, new_entries: list):
    """Write shortcuts.vdf with existing entries preserved and new ones appended."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _backup_file(path)

    data = b'\x00shortcuts\x00'

    if existing_raw:
        data += existing_raw

    for entry_bytes in new_entries:
        data += entry_bytes

    data += b'\x08\x08'

    with open(path, 'wb') as f:
        f.write(data)


# -- Artwork download ---------------------------------------------------------

def _download_artwork(grid_dir: str, appid: int, shortcut_def: dict, prog,
                      force: bool = False, clean_stale: bool = False):
    """Download all artwork for a shortcut to the grid directory (concurrent).

    force       - if True, re-download even if the file already exists on disk.
    clean_stale - if True, delete all existing {appid}* files in grid_dir
                  before downloading. Handles extension changes between
                  versions that would otherwise leave orphans.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    appid_str = str(appid)
    os.makedirs(grid_dir, exist_ok=True)

    if clean_stale:
        try:
            import glob as _glob
            for f in _glob.glob(os.path.join(grid_dir, f"{appid_str}*")):
                try:
                    os.remove(f)
                except OSError:
                    _log.debug("file removal failed", exc_info=True)
        except Exception:
            _log.debug("stale artwork cleanup failed", exc_info=True)

    artwork_map = [
        ("icon_url",  f"{appid_str}_icon.{shortcut_def['icon_ext']}",  "icon"),
        ("grid_url",  f"{appid_str}p.{shortcut_def['grid_ext']}",      "grid"),
        ("wide_url",  f"{appid_str}.{shortcut_def['wide_ext']}",       "wide"),
        ("hero_url",  f"{appid_str}_hero.{shortcut_def['hero_ext']}",  "hero"),
        ("logo_url",  f"{appid_str}_logo.{shortcut_def['logo_ext']}",  "logo"),
    ]

    # Collect items that actually need downloading
    to_download = []
    for url_key, filename, label in artwork_map:
        url = shortcut_def.get(url_key)
        if not url:
            continue
        dest = os.path.join(grid_dir, filename)
        if not force and os.path.exists(dest):
            prog(f"    ok  {label} (cached)")
            continue
        to_download.append((url, dest, label))

    if not to_download:
        return

    # Download up to 5 images concurrently
    results_lock = threading.Lock()

    def _dl(url, dest, label):
        ok = _download(url, dest)
        with results_lock:
            if ok:
                prog(f"    ok  {label}")
            else:
                prog(f"    !!  {label} failed")

    with ThreadPoolExecutor(max_workers=min(5, len(to_download))) as ex:
        futs = [ex.submit(_dl, url, dest, label) for url, dest, label in to_download]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                _log.debug("artwork download task failed", exc_info=True)


# -- Controller template assignment (Phase 5 stub) ---------------------------
# When TPS/driving controller VDFs are ready, this function will copy the
# template to the per-appid config directory and patch configset VDFs, same
# as DeckOps. For now it's a no-op so the rest of the shortcut pipeline can
# be tested.

def _assign_controller_config(uid: str, appid: int, shortcut_def: dict,
                               gyro_mode: str, prog):
    """
    Assign controller template for a non-Steam shortcut.

    Phase 5 stub - logs a skip message. When TPS/driving VDFs land in
    assets/controllers/, this will copy the template and patch:
      - configset_controller_neptune.vdf
      - configset_{serial}.vdf (for Game Mode on Deck)

    The function signature matches the DeckOps pattern so Phase 5
    just fills in the body.
    """
    prog(f"    --  Controller config skipped (Phase 5)")


# -- Entry-stripping helper (rewrite-on-collision support) -------------------
# When a shortcut with a matching AppName already exists, we strip the stale
# entry from the raw VDF body and re-index the remaining entries so the new
# write can append a fresh entry with correct Exe / LaunchOptions / StartDir.

def _strip_entries_by_name(raw_body: bytes, names_to_strip: set) -> tuple:
    """
    Remove entries from raw_body whose AppName matches any name in
    names_to_strip. raw_body is the shortcut body with header/footer
    already stripped (as returned by _read_shortcuts_raw).

    Returns (new_body, stripped_names) where stripped_names is a set of
    names that were actually found and removed. Re-indexes remaining
    entries to contiguous numeric indices starting at 0.

    If no matching entries are found, returns (raw_body, set()) unchanged.
    """
    if not raw_body or not names_to_strip:
        return raw_body, set()

    # Find entry boundaries
    entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', raw_body)]
    if not entry_starts:
        return raw_body, set()

    entries = []
    for i, start in enumerate(entry_starts):
        end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(raw_body)
        entries.append(raw_body[start:end])

    kept = []
    stripped = set()
    for entry in entries:
        matched_name = None
        for name in names_to_strip:
            name_bytes = name.encode("utf-8")
            if (b'\x01AppName\x00' + name_bytes + b'\x00' in entry or
                b'\x01appname\x00' + name_bytes + b'\x00' in entry):
                matched_name = name
                break
        if matched_name is not None:
            stripped.add(matched_name)
            continue
        kept.append(entry)

    if not stripped:
        return raw_body, set()

    # Re-index remaining entries so Steam sees contiguous indices starting at 0
    reindexed = []
    for new_idx, entry in enumerate(kept):
        entry = re.sub(
            rb'^\x00\d+\x00',
            f'\x00{new_idx}\x00'.encode(),
            entry,
        )
        reindexed.append(entry)

    return b''.join(reindexed), stripped


# -- Public API ---------------------------------------------------------------

def enrich_own_games(own_games: dict, selected_keys: list,
                     on_progress=None):
    """
    Compute shortcut appids, compatdata paths, and launch options for
    own games - WITHOUT writing any VDF entries, artwork, or configs.

    Must run early in the install flow so prefix creation can use the
    computed compatdata_path. The actual shortcut writing is deferred to
    write_own_shortcuts(), which should run AFTER all mod installs so
    every target exe exists on disk.

    GTA IV own-game installs use the same launch pattern as NFSBlacklist:
      - Direct exe launch via GE-Proton
      - STEAM_COMPAT_DATA_PATH for the prefix
      - WINEDLLOVERRIDES="dinput8=n,b" for the ASI loader (FusionFix)

    own_games     - dict {key: game_dict} from detect_games
    selected_keys - list of game keys the user selected
    on_progress   - optional callback(msg: str)

    Returns own_games dict enriched with:
      shortcut_appid, compatdata_path, source, current_name,
      _own_actual_exe, _own_launch_options
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    for key in selected_keys:
        if key not in GTAIV_SHORTCUTS:
            continue
        if key not in own_games:
            continue
        game = own_games[key]
        install_dir = game.get("install_dir")
        if not install_dir:
            continue

        shortcut_def = GTAIV_SHORTCUTS[key]
        name         = shortcut_def["name"]
        exe_path     = game["exe_path"]

        # Calculate appid from quoted exe + canonical name.
        # Must use quoted exe path - this is how Steam calculates the CRC.
        quoted_exe     = f'"{exe_path}"'
        shortcut_appid = _calc_shortcut_appid(quoted_exe, name)

        # Own games always get their own CRC-based prefix
        compatdata_path = os.path.join(COMPAT_ROOT, str(shortcut_appid))

        # Enrich the game dict
        game["shortcut_appid"]  = shortcut_appid
        game["compatdata_path"] = compatdata_path
        game["source"]          = "own"
        game["current_name"]    = name

        # GTA IV uses the same launch pattern as NFS: direct exe via GE-Proton
        # with WINEDLLOVERRIDES for the ASI loader (dinput8.dll from FusionFix)
        game["_own_actual_exe"]     = exe_path
        game["_own_launch_options"] = (
            f'STEAM_COMPAT_DATA_PATH="{compatdata_path}" '
            f'WINEDLLOVERRIDES="dinput8=n,b" %command%'
        )

        prog(f"  -> {name}  appid: {shortcut_appid}")

    return own_games


def write_own_shortcuts(own_games: dict, selected_keys: list,
                        gyro_mode: str, on_progress=None):
    """
    Write non-Steam shortcut VDF entries, download artwork, assign
    controller configs, and set Proton compat tool for own games.

    Must run AFTER all mod installs so every target exe exists on disk.
    Reads enrichment data (shortcut_appid, _own_actual_exe,
    _own_launch_options) previously set by enrich_own_games().

    own_games     - dict {key: game_dict} enriched by enrich_own_games()
    selected_keys - list of game keys the user selected
    gyro_mode     - "on" or "off"
    on_progress   - optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    to_create = {}
    for key in selected_keys:
        if key not in GTAIV_SHORTCUTS:
            continue
        if key not in own_games:
            continue
        game = own_games[key]
        if not game.get("install_dir"):
            continue
        if game.get("_own_actual_exe") is None:
            continue
        to_create[key] = (GTAIV_SHORTCUTS[key], game)

    if not to_create:
        prog("No non-Steam game shortcuts to write.")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("!!  No Steam user accounts found - own shortcuts skipped.")
        return

    for uid in uids:
        prog(f"Writing shortcuts for user {uid}...")

        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        existing_raw = _read_shortcuts_raw(shortcuts_path)

        # Strip any existing entries whose AppName matches a shortcut we're
        # about to write so reinstalls replace stale entries cleanly.
        names_to_write = {d["name"] for d, _ in to_create.values()}
        existing_raw, stripped = _strip_entries_by_name(
            existing_raw, names_to_write
        )
        if stripped:
            prog(f"  Replacing {len(stripped)} stale shortcut(s)...")

        existing_names = [
            n for n in _read_existing_shortcuts(shortcuts_path)
            if n not in stripped
        ]

        next_idx = _get_next_index(existing_raw)

        new_entries = []

        for key, (shortcut_def, game) in to_create.items():
            name           = shortcut_def["name"]
            install_dir    = game["install_dir"]
            actual_exe     = game["_own_actual_exe"]
            launch_options = game["_own_launch_options"]
            shortcut_appid = game["shortcut_appid"]

            icon_path = os.path.join(
                grid_dir, f"{shortcut_appid}_icon.{shortcut_def['icon_ext']}"
            )

            if not os.path.exists(actual_exe):
                prog(f"  -> {name}")
                prog(f"    !!  {os.path.basename(actual_exe)} not found - shortcut will be created anyway")
            else:
                prog(f"  -> {name}")
            prog(f"    appid: {shortcut_appid}")

            if name in existing_names:
                prog(f"    !!  Unexpected name collision after strip")

            entry = {
                "appid":               _to_signed32(shortcut_appid),
                "AppName":             name,
                "Exe":                 f'"{actual_exe}"',
                "StartDir":            f'"{install_dir}"',
                "icon":                icon_path,
                "ShortcutPath":        "",
                "LaunchOptions":       launch_options,
                "IsHidden":            0,
                "AllowDesktopConfig":  1,
                "AllowOverlay":        1,
                "OpenVR":              0,
                "Devkit":              0,
                "DevkitGameID":        "",
                "DevkitOverrideAppID": 0,
                "LastPlayTime":        0,
                "FlatpakAppID":        "",
                "tags":                {"0": "GetToAmericaIV"},
            }

            entry_bytes = _make_shortcut_entry(next_idx, entry)
            new_entries.append(entry_bytes)
            next_idx += 1
            prog(f"    ok  Shortcut created")

            # Download artwork
            _download_artwork(grid_dir, shortcut_appid, shortcut_def, prog,
                              force=True, clean_stale=True)

            # Controller config (Phase 5 stub)
            _assign_controller_config(uid, shortcut_appid, shortcut_def, gyro_mode, prog)

            # Set Proton compat tool
            try:
                import config as _cfg
                from wrapper import set_compat_tool
                ge_version = _cfg.get_ge_proton_version()
                if ge_version:
                    set_compat_tool([str(shortcut_appid)], ge_version)
                    prog(f"    ok  Proton compat tool: {ge_version}")
                else:
                    prog(f"    !!  Proton version unknown - compat tool not set")
            except Exception as ex:
                prog(f"    !!  Could not set Proton compat tool: {ex}")

        if new_entries:
            try:
                _write_shortcuts_vdf(shortcuts_path, existing_raw, new_entries)
                prog(f"  ok  shortcuts.vdf saved")
            except Exception as e:
                prog(f"  !!  Failed to write shortcuts.vdf: {e}")
        else:
            prog(f"  ok  No new shortcuts needed")

    prog("ok  Own game shortcuts written.")


def apply_steam_artwork(on_progress=None):
    """
    Download and apply custom artwork for the GTA IV Steam library entry
    (appid 12210).

    Files are written to userdata/<uid>/config/grid/ using the Steam appid
    as the filename prefix. Steam picks them up on next launch without any
    shortcuts.vdf changes -- the library entry already exists for owned games.

    Called from ui_install.py for Steam installs after mod installation is
    complete. Safe to call on reinstall; force=True re-downloads every time
    so artwork stays current if URLs are updated.

    on_progress -- optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    art_def = STEAM_ARTWORK.get("12210")
    if not art_def:
        prog("  !!  No Steam artwork defined for appid 12210")
        return

    uids = _find_all_steam_uids()
    if not uids:
        prog("  !!  No Steam user accounts found -- artwork skipped")
        return

    for uid in uids:
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")
        os.makedirs(grid_dir, exist_ok=True)
        prog(f"  Downloading artwork for uid {uid}...")
        _download_artwork(grid_dir, 12210, art_def, prog,
                          force=True, clean_stale=True)

    prog("ok  Steam artwork applied.")


def remove_shortcut(name: str, exe_path: str, artwork_def: dict = None,
                    on_progress=None):
    """
    Remove a non-Steam shortcut by name from shortcuts.vdf for all UIDs.
    Also removes associated artwork from the grid directory.

    name        - AppName to match in shortcuts.vdf
    exe_path    - quoted exe path used for appid CRC (needed for artwork
                   file cleanup - artwork filenames are keyed on appid)
    artwork_def - dict with *_ext keys for artwork file removal;
                   if None, artwork files are left in place
    on_progress - optional callback(msg: str)
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    shortcut_appid = _calc_shortcut_appid(exe_path, name)

    uids = _find_all_steam_uids()
    if not uids:
        return

    for uid in uids:
        shortcuts_path = os.path.join(USERDATA_DIR, uid, "config", "shortcuts.vdf")
        grid_dir = os.path.join(USERDATA_DIR, uid, "config", "grid")

        if not os.path.exists(shortcuts_path):
            continue

        try:
            with open(shortcuts_path, "rb") as f:
                data = f.read()
        except OSError:
            _log.debug("shortcuts.vdf read failed", exc_info=True)
            continue

        header = b'\x00shortcuts\x00'
        footer = b'\x08\x08'

        body = data
        if body.startswith(header):
            body = body[len(header):]
        if body.endswith(footer):
            body = body[:-2]
        elif body.endswith(b'\x08'):
            body = body[:-1]

        entry_starts = [m.start() for m in re.finditer(rb'\x00\d+\x00', body)]
        if not entry_starts:
            continue

        entries = []
        for i, start in enumerate(entry_starts):
            end = entry_starts[i + 1] if i + 1 < len(entry_starts) else len(body)
            entries.append(body[start:end])

        title_bytes = name.encode("utf-8")
        filtered = [
            e for e in entries
            if b'\x01AppName\x00' + title_bytes + b'\x00' not in e
            and b'\x01appname\x00' + title_bytes + b'\x00' not in e
        ]

        if len(filtered) < len(entries):
            reindexed = []
            for new_idx, entry in enumerate(filtered):
                entry = re.sub(
                    rb'^\x00\d+\x00',
                    f'\x00{new_idx}\x00'.encode(),
                    entry,
                )
                reindexed.append(entry)
            new_data = header + b''.join(reindexed) + footer
            try:
                _backup_file(shortcuts_path)
                with open(shortcuts_path, "wb") as f:
                    f.write(new_data)
                prog(f"  Removed shortcut '{name}' for uid {uid}")
            except OSError as ex:
                prog(f"  Could not write shortcuts.vdf: {ex}")

        # Remove artwork
        if artwork_def:
            artwork_suffixes = [
                f"_icon.{artwork_def.get('icon_ext', 'png')}",
                f"p.{artwork_def.get('grid_ext', 'png')}",
                f".{artwork_def.get('wide_ext', 'png')}",
                f"_hero.{artwork_def.get('hero_ext', 'png')}",
                f"_logo.{artwork_def.get('logo_ext', 'png')}",
            ]
            for suffix in artwork_suffixes:
                art_path = os.path.join(grid_dir, f"{shortcut_appid}{suffix}")
                if os.path.exists(art_path):
                    try:
                        os.remove(art_path)
                    except OSError:
                        _log.debug("file removal failed", exc_info=True)


# -- CLI for testing ----------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from detect_games import find_own_installed

    print("Finding installed GTA IV...")
    found = find_own_installed(on_progress=print)

    if not found:
        print("No games found.")
        sys.exit(1)

    print(f"\nFound {len(found)} game(s)")
    for key, game in found.items():
        print(f"  {key}: {game['name']} at {game['install_dir']}")

    print("\nEnriching game data...")
    enriched = enrich_own_games(found, list(found.keys()), on_progress=print)

    print("\nEnriched data:")
    for key, game in enriched.items():
        print(f"  {key}:")
        print(f"    appid:          {game.get('shortcut_appid')}")
        print(f"    compatdata:     {game.get('compatdata_path')}")
        print(f"    exe:            {game.get('_own_actual_exe')}")
        print(f"    launch_options: {game.get('_own_launch_options')}")

    print("\nCreating shortcuts (test mode)...")
    write_own_shortcuts(
        enriched,
        list(enriched.keys()),
        gyro_mode="off",
        on_progress=print,
    )
