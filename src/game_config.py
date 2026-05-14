"""
game_config.py - GamingTweaksAppliedIV display config writer

Writes display resolution and launch parameters for GTA IV on Linux
handhelds. Two responsibilities:

  1. commandline.txt in the GTAIV game root -- parsed by the engine on
     startup for resolution, memory flags, and restriction overrides.

  2. Steam launch options in localconfig.vdf -- WINEDLLOVERRIDES for
     the ASI loader (dinput8.dll) plus %command%. Only written for
     Steam installs. Own-game installs get their launch options baked
     into the non-Steam shortcut by shortcut.py.

GTA IV stores display settings in a profile inside the Wine prefix, but
commandline.txt overrides those and is simpler to manage. The engine
reads it on every launch, no prefix patching needed.

FusionFix INI patching is NOT done here. FusionFix v5.0+ has an in-game
menu that handles Vulkan, FPS cap, AA, etc. Programmatic INI patching
may be added later for first-launch Steam Deck defaults.

Prefix preheating is intentionally skipped. For Steam installs, Steam
manages the prefix lifecycle -- touching it risks wiping Rockstar
Launcher credentials. GE-Proton initialises the prefix correctly on
first game launch. Own-game prefixes are likewise left to be created
on first launch.

Called from ui_install.py during the install pipeline.
"""

import os

from log import get_logger

_log = get_logger(__name__)


# -- Constants ----------------------------------------------------------------

# GTA IV Steam appid
_GTAIV_APPID = "12210"

# -- Device resolution presets ------------------------------------------------
# Keyed by the model_config_dir string returned by config.get_model_config_dir().
# Steam Deck LCD and OLED both run at 1280x800.
# Other devices use their native panel resolution.
# Docked mode is handled separately via config.get_docked_resolution().

_DEVICE_RESOLUTIONS = {
    "LCD":              (1280, 800),
    "OLED":             (1280, 800),
    "Other/1920x1200":          (1920, 1200),   # Legion Go, Go S, MSI Claw 8
    "Other/1920x1200_144hz":    (1920, 1200),   # Legion Go 2
    "Other/1920x1080":          (1920, 1080),   # ROG Ally, Ally X
    "Other/1280x800":           (1280, 800),    # Generic fallback
    "Other/1280x720":           (1280, 720),    # 720p devices
}

# -- Steam launch option string -----------------------------------------------
# WINEDLLOVERRIDES tells Proton to load FusionFix's dinput8.dll (the ASI
# loader) instead of Wine's built-in version. Without this, no ASI mods
# load and FusionFix does nothing.
#
# Memory and resolution flags go in commandline.txt, NOT here. The GTA IV
# engine reads commandline.txt on startup. Putting them in Steam launch
# options passes them to Proton's command line which is the wrong place.

_DLL_OVERRIDE = 'WINEDLLOVERRIDES="dinput8=n,b"'

# -- Memory flags for commandline.txt -----------------------------------------
# These tell the engine to stop being conservative with VRAM and system
# RAM allocation. GTA IV's original port was notoriously bad at memory
# management -- these flags are the standard community fix.

_MEMORY_FLAGS = [
    "-availablevidmem 4096",
    "-nomemrestrict",
    "-norestrictions",
]


# -- Resolution helpers -------------------------------------------------------

def get_resolution():
    """
    Determine the target resolution from the user's device config.

    Checks docked mode first (user may have picked a TV resolution),
    then falls back to the handheld panel resolution based on device
    model. Returns (width, height) tuple.

    Returns (1280, 800) as the safe fallback if nothing is configured.
    Returns None if docked mode is set to "own" (user sets in-game).
    """
    import config as cfg

    # Docked mode -- user picked a specific TV/monitor resolution
    if cfg.is_docked():
        docked = cfg.get_docked_resolution()
        if docked and docked != "own":
            parts = docked.split("x")
            if len(parts) == 2:
                try:
                    return (int(parts[0]), int(parts[1]))
                except ValueError:
                    pass
        if docked == "own":
            return None

    # Handheld mode -- use device panel resolution
    model_dir = cfg.get_model_config_dir()
    resolution = _DEVICE_RESOLUTIONS.get(model_dir)
    if resolution:
        return resolution

    # Unknown device -- safe default
    _log.warning("Unknown model_config_dir '%s', defaulting to 1280x800",
                 model_dir)
    return (1280, 800)


# -- commandline.txt ----------------------------------------------------------

def _build_commandline(width=None, height=None):
    """
    Build the contents of commandline.txt.

    If width/height are provided, resolution flags are included.
    Memory flags are always included.

    Returns a string with one flag per line (the format GTA IV expects).
    """
    lines = []

    if width and height:
        lines.append(f"-width {width}")
        lines.append(f"-height {height}")
        lines.append("-fullscreen")

    lines.extend(_MEMORY_FLAGS)

    return "\n".join(lines) + "\n"


def write_commandline_txt(game_root, on_progress=None):
    """
    Write commandline.txt to the GTA IV game root.

    game_root   -- path to the GTAIV subfolder (where GTAIV.exe lives)
    on_progress -- optional callback(str) for status messages

    Returns True on success, False on failure.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    resolution = get_resolution()

    if resolution is None:
        content = _build_commandline()
        prog("  commandline.txt: memory flags only (user sets resolution in-game)")
    else:
        width, height = resolution
        content = _build_commandline(width, height)
        prog(f"  commandline.txt: {width}x{height} + memory flags")

    dest = os.path.join(game_root, "commandline.txt")
    try:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        _log.info("Wrote commandline.txt to %s", dest)
        return True
    except OSError:
        _log.error("Failed to write commandline.txt", exc_info=True)
        prog("  !!  Failed to write commandline.txt")
        return False


def remove_commandline_txt(game_root):
    """
    Remove commandline.txt from the game root. Used during uninstall.

    Silently no-ops if the file doesn't exist.
    """
    dest = os.path.join(game_root, "commandline.txt")
    if os.path.exists(dest):
        try:
            os.remove(dest)
            _log.info("Removed commandline.txt from %s", game_root)
        except OSError:
            _log.debug("Failed to remove commandline.txt", exc_info=True)


# -- Steam launch options -----------------------------------------------------

def get_launch_options():
    """
    Build the full Steam launch option string for GTA IV.

    Format:
        WINEDLLOVERRIDES="dinput8=n,b" %command%

    The DLL override must come before %command%. It tells Proton to load
    FusionFix's dinput8.dll (the ASI loader) instead of Wine's built-in
    version. Without this, no ASI mods load and FusionFix does nothing.

    Memory and resolution flags go in commandline.txt, not here.
    """
    return f'{_DLL_OVERRIDE} %command%'


def apply_launch_options(steam_root, on_progress=None):
    """
    Write GTA IV launch options into Steam's localconfig.vdf.

    Uses wrapper.set_launch_options() which handles all Steam user
    accounts, flat-block targeting, and VDF validation.

    Only called for Steam installs. Own-game installs get their launch
    options baked into the non-Steam shortcut by shortcut.py.

    steam_root  -- path to the Steam root directory
    on_progress -- optional callback(str) for status messages

    Must be called while Steam is closed.
    """
    import wrapper

    def prog(msg):
        if on_progress:
            on_progress(msg)

    options = get_launch_options()
    prog(f"  Setting launch options for appid {_GTAIV_APPID}")
    _log.info("Setting launch options: %s", options)

    try:
        wrapper.set_launch_options(steam_root, _GTAIV_APPID, options)
        prog("  ok  Launch options set")
        return True
    except Exception:
        _log.error("Failed to set launch options", exc_info=True)
        prog("  !!  Failed to set launch options")
        return False


def clear_launch_options(steam_root, on_progress=None):
    """
    Remove GTA IV launch options from Steam's localconfig.vdf.

    Used during uninstall. Wrapper handles the VDF editing.
    """
    import wrapper

    def prog(msg):
        if on_progress:
            on_progress(msg)

    try:
        wrapper.clear_launch_options(steam_root, _GTAIV_APPID)
        prog("  ok  Launch options cleared")
    except Exception:
        _log.error("Failed to clear launch options", exc_info=True)
        prog("  !!  Failed to clear launch options")


# -- Full config apply (called from ui_install.py) ----------------------------

def apply_game_config(game_root, steam_root, source="steam",
                      compatdata_path=None, on_progress=None):
    """
    Apply all game configuration in one call:
      1. Write commandline.txt to the game root
      2. Set Steam launch options (Steam installs only)

    Prefix preheating is intentionally skipped for both Steam and
    own-game installs. Steam manages the prefix lifecycle for Steam
    installs and GE-Proton will initialise it correctly on first launch.

    game_root       -- path to the GTAIV subfolder (where GTAIV.exe lives)
    steam_root      -- path to the Steam root directory
    source          -- "steam" or "own"
    compatdata_path -- unused, kept for call-site compatibility
    on_progress     -- optional callback(str) for status messages

    Returns True if all steps succeed, False if any fail.
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    prog("Writing game configuration...")

    # Step 1: commandline.txt (both Steam and own-game)
    ok_cmd = write_commandline_txt(game_root, on_progress=prog)

    # Step 2: Steam launch options (Steam installs only)
    # Own-game installs get launch options from shortcut.py
    ok_launch = True
    if source == "steam":
        ok_launch = apply_launch_options(steam_root, on_progress=prog)
    else:
        prog("  --  Skipping Steam launch options (own-game shortcut "
             "handles this)")

    all_ok = ok_cmd and ok_launch
    if all_ok:
        prog("Game configuration complete.")
    else:
        prog("  !!  Game configuration had errors (see above)")

    return all_ok


def remove_game_config(game_root, steam_root, source="steam",
                       on_progress=None):
    """
    Remove game configuration. Used during uninstall.
      1. Delete commandline.txt
      2. Clear Steam launch options (Steam installs only)

    game_root   -- path to the GTAIV subfolder
    steam_root  -- path to the Steam root directory
    source      -- "steam" or "own"
    on_progress -- optional callback(str) for status messages
    """
    def prog(msg):
        if on_progress:
            on_progress(msg)

    prog("Removing game configuration...")
    remove_commandline_txt(game_root)

    if source == "steam":
        clear_launch_options(steam_root, on_progress=prog)
    else:
        prog("  --  Skipping Steam launch option cleanup (own-game)")

    prog("Game configuration removed.")


# -- CLI for testing ----------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print("game_config.py -- GTA IV display config writer")
    print("Run through ui_install.py for real usage.")
    print()
    print("Launch options (Steam):")
    print(f"  {get_launch_options()}")
    print()
    print("Resolution presets:")
    for model, (w, h) in _DEVICE_RESOLUTIONS.items():
        print(f"  {model}: {w}x{h}")
    print()
    print("Sample commandline.txt (1280x800):")
    print(_build_commandline(1280, 800))
