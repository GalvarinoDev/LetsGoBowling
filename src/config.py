"""
config.py - GamingTweaksAppliedIV configuration manager

Handles reading and writing gamingtweaksappliediv.json which lives at the
install directory (path provided by identity.py).

The config file tracks:
    - Whether first-time setup has been completed
    - Which device the user has (oled, lcd, other, or steam_machine)
    - For 'other' and 'steam_machine' devices, which resolution profile to use
    - Which games have been set up and when
    - The Steam root path found during setup
    - GTA IV mod versions and install state
"""

import os
import json
import re
import shutil
import threading
from datetime import datetime

from identity import CONFIG_PATH, INSTALL_DIR

DEFAULTS = {
    "first_run_complete": False,
    "os_type": None,             # "steamos", "bazzite", "cachyos", or "other_linux"
    "deck_model": None,          # "oled", "lcd", "other", or "steam_machine"
    "other_device": None,         # resolution key for non-Deck devices and Steam Machine,
                                  # e.g. "1920x1200", "1920x1200_144hz", "1920x1080"
    "other_device_type": None,    # device type for controller profile selection:
                                  # "legion_go", "legion_go_2", "legion_go_s",
                                  # "2btn", "generic", "steam_machine"
    "gyro_mode":  None,          # "on" or "off"
    "play_mode":  None,          # "handheld" or "docked"
    "external_controller": None, # "playstation", "xbox", "steamcontroller", or "other"
                                 # only used when play_mode is "docked"
    "docked_resolution": None,   # "1280x720", "1280x800", "1920x1080", "1920x1200", or "own"
                                 # only used when play_mode is "docked"
    "ge_proton_version": None,   # e.g. "GE-Proton10-32"
    "steam_root": None,
    "player_name": None,         # in-game player name
    "music_enabled": True,       # background music on/off
    "music_volume":  0.4,        # 0.0 to 1.0
    "setup_games": {},           # key: game key, value: { "source": "steam"|"own",
                                 #   "setup_at": timestamp }

    # -- GTA IV mod state -----------------------------------------------------
    "fusionfix_version": None,          # e.g. "v5.0.1"
    "console_visuals_version": None,    # e.g. "v2.0.3c"
    "console_visuals_packs": [],        # list of installed pack names,
                                        # e.g. ["vegetation", "animations", "hud"]
    "various_fixes_version": None,      # e.g. "v2.2"
    "radio_restoration_installed": False,
    "radio_option": "opALL",            # which restoration variant was installed:
                                        # "opALL", "opCLASSIC", "opSPLITbase",
                                        # "opVANILLA", "opVANILLABETA",
                                        # "opSPLITBETA", "opSPLITVANILLA"
}


# -- In-memory cache ----------------------------------------------------------
# Avoids re-reading and re-parsing gamingtweaksappliediv.json on every getter call.
# The cache is invalidated on save() and on external file changes (mtime check).
# Thread-safe: all cache access is guarded by _lock.

_lock = threading.Lock()
_cache = None        # cached merged dict, or None if invalidated
_cache_mtime = 0.0   # mtime of CONFIG_PATH when _cache was populated


# -- Disk-backed temp directory -----------------------------------------------
# /tmp on SteamOS is tmpfs (RAM-backed, ~7 GB). Mod downloads like Various
# Fixes (1.6 GB) and Radio Restoration (1 GB) can exhaust it mid-pipeline.
# This gives installers a temp dir on the real filesystem instead.

_TMP_DIR = os.path.join(INSTALL_DIR, "tmp")
_tmp_cleaned = False  # only clean stale dirs once per session


def get_tmp_dir() -> str:
    """
    Return a disk-backed temp directory for mod installers.

    Lives at ~/GamingTweaksAppliedIV/tmp/ on the NVMe, not in /tmp tmpfs.
    On first call each session, removes any stale gamingtweaksappliediv_*
    subdirs left by crashed previous runs. Individual installers still
    clean up their own dirs in their finally blocks.
    """
    global _tmp_cleaned

    os.makedirs(_TMP_DIR, exist_ok=True)

    if not _tmp_cleaned:
        for entry in os.listdir(_TMP_DIR):
            if entry.startswith("gamingtweaksappliediv_"):
                stale = os.path.join(_TMP_DIR, entry)
                try:
                    shutil.rmtree(stale)
                except OSError:
                    pass
        _tmp_cleaned = True

    return _TMP_DIR


def load() -> dict:
    """
    Load config from disk with in-memory caching.

    Returns a fresh copy of the cached config if the file hasn't changed
    since the last read (mtime check). Re-reads from disk if the file
    was modified externally or if save() invalidated the cache.

    Returns defaults if the file doesn't exist or is corrupt.
    """
    global _cache, _cache_mtime

    with _lock:
        # Check if file exists
        try:
            current_mtime = os.path.getmtime(CONFIG_PATH)
        except OSError:
            # File doesn't exist or can't be stat'd - return defaults
            return dict(DEFAULTS)

        # Return cached copy if file hasn't changed
        if _cache is not None and current_mtime == _cache_mtime:
            return dict(_cache)

        # Cache miss or stale - re-read from disk
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            merged = dict(DEFAULTS)
            merged.update(data)
            _cache = merged
            _cache_mtime = current_mtime
            return dict(_cache)
        except (json.JSONDecodeError, IOError):
            return dict(DEFAULTS)


def save(config: dict):
    """
    Write config to disk and invalidate the cache.
    Creates the directory if needed.
    """
    global _cache, _cache_mtime

    with _lock:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        # Invalidate cache so the next load() picks up the fresh write
        _cache = None
        _cache_mtime = 0.0


def is_first_run() -> bool:
    """Returns True if setup has never been completed."""
    return not load().get("first_run_complete", False)


def get_os_type() -> str | None:
    """Returns 'steamos', 'bazzite', 'cachyos', 'other_linux', or None."""
    return load().get("os_type")


def set_os_type(os_type: str):
    """Save the user's operating system type.

    os_type -- 'steamos', 'bazzite', 'cachyos', or 'other_linux'
    """
    config = load()
    config["os_type"] = os_type
    save(config)


def is_bazzite() -> bool:
    """Returns True if the user selected Bazzite as their OS."""
    return load().get("os_type") == "bazzite"


def get_deck_model() -> str | None:
    """Returns 'oled', 'lcd', 'other', 'steam_machine', or None if not yet set."""
    return load().get("deck_model")


def set_deck_model(model: str):
    """Save the user's device model.

    model -- 'oled', 'lcd', 'other', or 'steam_machine'
    """
    config = load()
    config["deck_model"] = model
    save(config)


def is_oled() -> bool:
    """True only for actual Steam Deck OLED hardware."""
    return load().get("deck_model") == "oled"


def is_lcd() -> bool:
    """True only for Steam Deck LCD hardware."""
    return load().get("deck_model") == "lcd"


def is_other() -> bool:
    """True for non-Deck SteamOS devices (Legion Go, ROG Ally, etc.)."""
    return load().get("deck_model") == "other"


def is_steam_machine() -> bool:
    """True for Valve Steam Machine hardware."""
    return load().get("deck_model") == "steam_machine"


def get_other_device() -> str | None:
    """Returns the resolution key for Other/Steam Machine devices.

    e.g. '1920x1200', '1920x1080', or None.
    Steam Machine also stores its user-picked resolution here.
    """
    return load().get("other_device")


def set_other_device(device: str):
    """Save the resolution key, e.g. '1920x1200_144hz'.

    Used by both Other devices (preset per device) and Steam Machine
    (user-picked from the resolution screen).
    """
    config = load()
    config["other_device"] = device
    save(config)


def get_other_device_type() -> str | None:
    """Returns the device type for controller profile selection.

    Values: 'legion_go', 'legion_go_2', 'legion_go_s', '2btn', 'generic',
            'steam_machine', or None.
    Used by controller_profiles.py to pick the correct profile variant.
    """
    return load().get("other_device_type")


def set_other_device_type(device_type: str):
    """Save the device type for controller profile selection.

    device_type -- 'legion_go' (Go 1), 'legion_go_2' (Go 2),
                   'legion_go_s', '2btn' (ROG Ally,
                   MSI Claw), 'generic', or 'steam_machine'
    """
    config = load()
    config["other_device_type"] = device_type
    save(config)


def get_model_config_dir() -> str:
    """Return the asset subdirectory for the current device's configs.

    OLED          -> 'OLED'
    LCD           -> 'LCD'
    Other         -> 'Other/<resolution>'  (e.g. 'Other/1920x1200')
    Steam Machine -> 'Other/<resolution>'  (user-picked, same assets as Other)

    Falls back to 'OLED' if deck_model is unset.
    """
    model = load().get("deck_model") or "oled"
    if model in ("other", "steam_machine"):
        device = load().get("other_device") or "1920x1200"
        return f"Other/{device}"
    return "OLED" if model == "oled" else "LCD"


def get_gyro_mode() -> str | None:
    """Returns 'on', 'off', or None if not yet set."""
    return load().get("gyro_mode")


def set_gyro_mode(mode: str):
    """Save the user's gyro preference. mode should be 'on' or 'off'."""
    config = load()
    config["gyro_mode"] = mode
    save(config)


def get_play_mode() -> str | None:
    """Returns 'handheld', 'docked', or None if not yet set."""
    return load().get("play_mode")


def set_play_mode(mode: str):
    """Save the user's play mode. mode should be 'handheld' or 'docked'."""
    config = load()
    config["play_mode"] = mode
    save(config)


def is_docked() -> bool:
    return load().get("play_mode") == "docked"


def get_external_controller() -> str | None:
    """Returns 'playstation', 'xbox', 'other', or None if not yet set."""
    return load().get("external_controller")


def set_external_controller(controller_type: str):
    """Save the user's external controller type.

    controller_type -- 'playstation', 'xbox', 'steamcontroller', or 'other'
    """
    config = load()
    config["external_controller"] = controller_type
    save(config)


def get_docked_resolution() -> str | None:
    """Returns '1280x720', '1280x800', '1920x1080', '1920x1200', 'own', or None."""
    return load().get("docked_resolution")


def set_docked_resolution(resolution: str):
    """Save the user's docked display resolution.

    'own' means user sets it in-game.
    """
    config = load()
    config["docked_resolution"] = resolution
    save(config)


def get_music_enabled() -> bool:
    """Returns True if background music is enabled."""
    return load().get("music_enabled", True)


def set_music_enabled(enabled: bool):
    """Save background music on/off preference."""
    config = load()
    config["music_enabled"] = enabled
    save(config)


def get_music_volume() -> float:
    """Returns music volume as a float between 0.0 and 1.0."""
    return load().get("music_volume", 0.4)


def set_music_volume(volume: float):
    """Save music volume. Clamped to 0.0 - 1.0."""
    config = load()
    config["music_volume"] = max(0.0, min(1.0, volume))
    save(config)


def get_ge_proton_version() -> str | None:
    """Returns the installed GE-Proton version string, e.g. 'GE-Proton10-32', or None."""
    return load().get("ge_proton_version")


def set_ge_proton_version(version: str):
    """Save the installed GE-Proton version after CompatToolMapping is applied."""
    config = load()
    config["ge_proton_version"] = version
    save(config)


def get_player_name() -> str | None:
    """Returns the player's chosen in-game name, or None if not yet set."""
    return load().get("player_name")


def set_player_name(name: str):
    """Save the player's chosen in-game name."""
    config = load()
    config["player_name"] = name.strip() if name else None
    save(config)


def get_steam_display_name(steam_root: str | None = None) -> str | None:
    """
    Read the active Steam user's display name from loginusers.vdf.

    Looks for the account with MostRecent=1 and returns its PersonaName.
    Falls back to the first account if MostRecent is not set.
    Returns None if the file can't be read or parsed.

    steam_root -- path to Steam root. Defaults to ~/.local/share/Steam
    """
    if not steam_root:
        steam_root = os.path.expanduser("~/.local/share/Steam")
    vdf_path = os.path.join(steam_root, "config", "loginusers.vdf")
    if not os.path.exists(vdf_path):
        return None
    try:
        with open(vdf_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError):
        return None

    # Parse all accounts: find PersonaName and MostRecent per block
    # VDF is simple enough here to use regex instead of a full parser
    first_name = None
    most_recent_name = None
    # Split into per-account blocks by finding Steam ID headers
    blocks = re.split(r'"\d{17}"\s*\{', content)
    for block in blocks[1:]:  # skip the "users" { header
        persona = re.search(r'"PersonaName"\s+"([^"]*)"', block)
        recent = re.search(r'"MostRecent"\s+"1"', block)
        if persona:
            name = persona.group(1)
            if first_name is None:
                first_name = name
            if recent:
                most_recent_name = name

    return most_recent_name or first_name


# -- GTA IV mod state ---------------------------------------------------------


def get_fusionfix_version() -> str | None:
    """Returns the installed FusionFix version string, e.g. 'v5.0.1', or None."""
    return load().get("fusionfix_version")


def set_fusionfix_version(version: str):
    """Save the installed FusionFix version."""
    config = load()
    config["fusionfix_version"] = version
    save(config)


def get_console_visuals_version() -> str | None:
    """Returns the installed Console Visuals version string, or None."""
    return load().get("console_visuals_version")


def set_console_visuals_version(version: str):
    """Save the installed Console Visuals version."""
    config = load()
    config["console_visuals_version"] = version
    save(config)


def get_console_visuals_packs() -> list:
    """Returns the list of installed Console Visuals pack names.

    e.g. ["vegetation", "animations", "hud"]
    """
    return load().get("console_visuals_packs", [])


def set_console_visuals_packs(packs: list):
    """Save the list of installed Console Visuals pack names."""
    config = load()
    config["console_visuals_packs"] = packs
    save(config)


def get_various_fixes_version() -> str | None:
    """Returns the installed Various Fixes version string, or None."""
    return load().get("various_fixes_version")


def set_various_fixes_version(version: str):
    """Save the installed Various Fixes version."""
    config = load()
    config["various_fixes_version"] = version
    save(config)


def is_radio_restoration_installed() -> bool:
    """Returns True if Radio Restoration has been installed."""
    return load().get("radio_restoration_installed", False)


def set_radio_restoration_installed(installed: bool):
    """Save Radio Restoration install state."""
    config = load()
    config["radio_restoration_installed"] = installed
    save(config)


def get_radio_option() -> str:
    """Returns the radio restoration variant that was installed.

    One of: 'opALL', 'opCLASSIC', 'opSPLITbase', 'opVANILLA',
            'opVANILLABETA', 'opSPLITBETA', 'opSPLITVANILLA'.
    Defaults to 'opALL'.
    """
    return load().get("radio_option", "opALL")


def set_radio_option(option: str):
    """Save the radio restoration variant chosen by the user.

    option -- one of the op*.dat keys without the .dat extension,
              e.g. 'opALL', 'opCLASSIC', 'opSPLITbase'
    """
    config = load()
    config["radio_option"] = option
    save(config)


# -- Game setup tracking ------------------------------------------------------


def mark_game_setup(game_key: str, source: str = "steam"):
    """
    Record that a game has been set up successfully.

    game_key -- e.g. 'gtaiv', 'eflc'
    source   -- 'steam' or 'own' (which install path was used)
    """
    config = load()
    entry = {
        "source": source,
        "setup_at": datetime.now().isoformat(),
    }
    config["setup_games"][game_key] = entry
    save(config)


def is_game_setup(game_key: str) -> bool:
    """Returns True if this game key has been set up (any source)."""
    return game_key in load().get("setup_games", {})


def unmark_game_setup(game_keys):
    """
    Remove one or more game keys from setup_games so they appear as
    'not set up' in ManagementScreen. Accepts a single string or a list.
    Used when the user wants to do a clean reinstall of a game.
    """
    if isinstance(game_keys, str):
        game_keys = [game_keys]
    config = load()
    changed = False
    for key in game_keys:
        if key in config.get("setup_games", {}):
            del config["setup_games"][key]
            changed = True
    if changed:
        save(config)


def get_setup_games() -> dict:
    """Returns the full setup_games dict."""
    return load().get("setup_games", {})


def complete_first_run(steam_root: str):
    """
    Call this at the end of the setup wizard to mark first run as done.
    """
    config = load()
    config["first_run_complete"] = True
    config["steam_root"] = steam_root
    save(config)


def reset():
    """
    Wipe the config and start fresh. Useful for testing or reinstalling.
    """
    global _cache, _cache_mtime

    with _lock:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
        _cache = None
        _cache_mtime = 0.0
