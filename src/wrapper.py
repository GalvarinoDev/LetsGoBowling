"""
wrapper.py - GamingTweaksAppliedIV VDF / Proton / Wine prefix manager

Core Steam plumbing module. Handles:
  - VDF parsing with quote-aware brace parser
  - VDF edit ledger for clean uninstall reversal
  - Proton path finder (GE-Proton preferred, vanilla fallback)
  - CompatToolMapping in config.vdf
  - Launch option writing in localconfig.vdf
  - Steam Input enablement
  - Default launch option for multi-mode games (Deck configurator)
  - Steam process management (graceful shutdown)

All VDF writes are backed up before editing and validated after writing.
If brace balance fails, the backup is restored automatically.

Must be called while Steam is closed. Steam overwrites config files on
shutdown, so any edits made while Steam is running will be lost.
"""

import os
import json
import re
import stat
import shutil
import subprocess

from identity import LEDGER_PATH
from log import get_logger

_log = get_logger(__name__)

# -- VDF edit ledger -----------------------------------------------------------
# Records every VDF edit GamingTweaksAppliedIV makes so the uninstaller can reverse
# them precisely instead of regex-sweeping entire files.


def _read_ledger() -> dict:
    """Read the VDF edit ledger, returning empty dict if missing/corrupt."""
    if not os.path.exists(LEDGER_PATH):
        return {}
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        _log.debug("VDF ledger read failed, starting fresh", exc_info=True)
        return {}


def _write_ledger(data: dict):
    """Write the VDF edit ledger. Failures are logged but non-fatal."""
    try:
        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        _log.debug("VDF ledger write failed", exc_info=True)


def _record_localconfig(uid: str, appid: str, key: str, value: str):
    """Record a localconfig.vdf edit in the ledger."""
    ledger = _read_ledger()
    lc = ledger.setdefault("localconfig", {})
    uid_block = lc.setdefault(uid, {})
    app_block = uid_block.setdefault(appid, {})
    app_block[key] = value
    _write_ledger(ledger)


def _record_config_vdf(appid: str, key: str, value: str):
    """Record a config.vdf edit in the ledger."""
    ledger = _read_ledger()
    cv = ledger.setdefault("config_vdf", {})
    section = cv.setdefault(key, {})
    section[appid] = value
    _write_ledger(ledger)


def _remove_config_vdf(appid: str, key: str):
    """Remove a config.vdf entry from the ledger (for clear operations)."""
    ledger = _read_ledger()
    cv = ledger.get("config_vdf", {})
    section = cv.get(key, {})
    section.pop(appid, None)
    if not section:
        cv.pop(key, None)
    _write_ledger(ledger)


def _record_configset(configset_filename: str, key: str, template_name: str):
    """Record a configset VDF edit in the ledger."""
    ledger = _read_ledger()
    cs = ledger.setdefault("configsets", {})
    file_block = cs.setdefault(configset_filename, {})
    file_block[key] = template_name
    _write_ledger(ledger)



def _backup_file(path: str):
    """Write a .bak copy before modifying a Steam config file."""
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except OSError:
            _log.debug("VDF backup failed for config file", exc_info=True)


def _find_block_end(text, start):
    """
    Brace-depth parser that skips braces inside quoted strings.

    WARNING: Must skip braces inside quoted strings - VDF values like
    bash substitutions contain { and } characters that must NOT be
    counted as block delimiters. Failure to do this will corrupt
    localconfig.vdf.
    """
    depth = 0
    i = start
    in_quote = False
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i - 1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _validate_vdf(path: str) -> bool:
    """
    Read a VDF file back after writing and verify brace balance.

    Walks the entire file using the same quote-aware brace parser that
    _find_block_end uses. A valid VDF file has every { matched by a }.
    Returns True if balanced, False if corrupt.

    On failure, automatically restores from .bak if available and logs
    the error. This catches corruption before Steam ever sees the file.
    """
    try:
        with open(path, "r", errors="replace") as f:
            data = f.read()
    except OSError:
        _log.error("VDF validation: cannot read %s", path)
        return False

    depth = 0
    in_quote = False
    for i, c in enumerate(data):
        if c == '"' and (i == 0 or data[i - 1] != '\\'):
            in_quote = not in_quote
        elif not in_quote:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0:
                    break

    if depth != 0:
        _log.error(
            "VDF validation FAILED for %s (brace depth %d) - restoring backup",
            path, depth,
        )
        bak = path + ".bak"
        if os.path.exists(bak):
            try:
                shutil.copy2(bak, path)
                _log.info("VDF restored from %s", bak)
            except OSError:
                _log.error("VDF restore failed for %s", path, exc_info=True)
        return False

    return True


def _write_and_validate_vdf(path: str, data: str, encoding: str = "utf-8",
                            errors: str | None = None) -> bool:
    """
    Write VDF data to path, then validate brace balance.

    Backs up before writing. If validation fails, the backup is
    automatically restored. Returns True if the write is clean.

    encoding / errors - passed to open(). Use errors="replace" for
    localconfig.vdf which can contain non-UTF-8 bytes.
    """
    _backup_file(path)
    open_kwargs = {"encoding": encoding}
    if errors:
        open_kwargs["errors"] = errors
    with open(path, "w", **open_kwargs) as f:
        f.write(data)
    if not _validate_vdf(path):
        _log.error("VDF corruption detected in %s after write", path)
        return False
    return True


def get_proton_path(steam_root):
    """
    Find the best available Proton binary for running Windows executables.

    Preference order:
      1. GE-Proton in ~/.local/share/Steam/compatibilitytools.d/
      2. GE-Proton in steam_root/compatibilitytools.d/
      3. Newest vanilla Proton in steam_root/steamapps/common/

    Uses numeric version sorting so GE-Proton9-28 > GE-Proton9-5,
    and Proton 10 > Proton 9.
    """
    def _version_key(name):
        parts = re.findall(r'\d+', name)
        return tuple(int(p) for p in parts)

    # Check GE-Proton in both possible locations
    ge_search_dirs = [
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
        os.path.join(steam_root, "compatibilitytools.d"),
    ]
    for ge_dir in ge_search_dirs:
        if not os.path.isdir(ge_dir):
            continue
        ge_dirs = [
            d for d in os.listdir(ge_dir)
            if d.startswith("GE-Proton") and
            os.path.exists(os.path.join(ge_dir, d, "proton"))
        ]
        if ge_dirs:
            ge_dirs.sort(key=_version_key, reverse=True)
            return os.path.join(ge_dir, ge_dirs[0], "proton")

    # Fall back to vanilla Proton
    common = os.path.join(steam_root, "steamapps", "common")
    if not os.path.exists(common):
        return None

    proton_dirs = [
        d for d in os.listdir(common)
        if d.startswith("Proton") and
        os.path.exists(os.path.join(common, d, "proton"))
    ]
    if not proton_dirs:
        return None

    proton_dirs.sort(key=_version_key, reverse=True)
    return os.path.join(common, proton_dirs[0], "proton")


def find_compatdata(steam_root, appid):
    """
    Find the Wine prefix folder for a given appid.

    For GTA IV (Steam appid 12210), the prefix is created by Steam in the
    standard compatdata location. For own-game non-Steam shortcuts, the
    prefix lives at the CRC-based appid location.

    Returns the path or None if not found.
    """
    candidate = os.path.join(
        steam_root, "steamapps", "compatdata", str(appid)
    )
    if os.path.isdir(candidate):
        return candidate

    # Also check the expanded home path (steam_root might be a symlink)
    fallback = os.path.join(
        os.path.expanduser("~/.local/share/Steam"),
        "steamapps", "compatdata", str(appid),
    )
    if os.path.isdir(fallback):
        return fallback

    return None


def set_launch_options(steam_root, appid, options):
    """
    Set or append launch options for a Steam game in localconfig.vdf.

    Finds all Steam user accounts under steam_root/userdata and updates
    the LaunchOptions entry for the given appid in each one. Always writes
    to the flat app block, not inside any cloud sub-block. Steam's UI reads
    LaunchOptions from the flat block; writing to the cloud sub-block causes
    the option to be invisible in Steam properties even if correctly written.

    steam_root  - path to the Steam root directory
    appid       - int or str Steam appid (or non-Steam shortcut appid)
    options     - launch option string to set
    """
    appid = str(appid)
    # Escape double quotes so the value is valid inside a VDF quoted string
    vdf_options = options.replace('"', '\\"')
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(
            userdata, uid, "config", "localconfig.vdf"
        )
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        # Find the appid block using regex, then brace-depth parse to get its
        # true boundaries.
        #
        # WARNING: Must skip braces inside quoted strings - VDF values can
        # contain { and } characters that must NOT be counted as block
        # delimiters. Failure to do this will corrupt localconfig.vdf.
        key_pattern = re.compile(
            r'"' + re.escape(appid) + r'"\s*\{',
            re.IGNORECASE
        )
        key_match = key_pattern.search(content)
        if not key_match:
            continue

        app_open  = key_match.end() - 1
        app_close = _find_block_end(content, app_open)
        if app_close == -1:
            continue

        app_inner = content[app_open + 1:app_close]

        # Always write LaunchOptions directly in the flat app block.
        # Steam reads LaunchOptions from here, not the cloud sub-block.
        launch_pattern = re.compile(
            r'("LaunchOptions"\s*")((?:[^"\\]|\\.)*?)(")',
            re.IGNORECASE
        )

        # Only match LaunchOptions in the flat block, not inside sub-blocks.
        # Find the first sub-block start so we only search before it.
        subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
        flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

        launch_match = launch_pattern.search(flat_section)

        if launch_match:
            existing = launch_match.group(2)
            if vdf_options in existing:
                continue
            new_options = (existing.strip() + " " + vdf_options).strip()
            # Replace only within flat_section, then reassemble app_inner so we
            # never accidentally hit a LaunchOptions key inside a cloud sub-block.
            new_flat = launch_pattern.sub(
                lambda m: m.group(1) + new_options + m.group(3),
                flat_section,
                count=1
            )
            if subblock_match:
                new_app_inner = new_flat + app_inner[subblock_match.start():]
            else:
                new_app_inner = new_flat
        else:
            # Insert before the first sub-block, or at end if no sub-blocks.
            # Derive indent from existing flat keys so the entry aligns correctly
            # regardless of how deeply nested this appid block is in the file.
            indent_match = re.search(r'\n(\t+)"', flat_section)
            if indent_match:
                indent = indent_match.group(1)
            else:
                # Fall back: count tabs on the opening key line itself
                key_line = key_match.group(0)
                leading  = re.match(r'(\t*)', key_line)
                indent   = (leading.group(1) if leading else '\t\t\t\t\t') + '\t'
            insert_pos = subblock_match.start() if subblock_match else len(app_inner)
            insert_str = f'{indent}"LaunchOptions"\t\t"{vdf_options}"\n'
            new_app_inner = app_inner[:insert_pos] + insert_str + app_inner[insert_pos:]

        new_content = (
            content[:app_open + 1] +
            new_app_inner +
            content[app_close:]
        )

        _write_and_validate_vdf(vdf_path, new_content, errors="replace")
        _record_localconfig(uid, appid, "LaunchOptions", vdf_options)


def clear_launch_options(steam_root, appid):
    """
    Remove any LaunchOptions for a game in localconfig.vdf.

    Cleans up stale launch options. Must be called while Steam is closed.
    """
    appid = str(appid)
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        key_pattern = re.compile(
            r'"' + re.escape(appid) + r'"\s*\{',
            re.IGNORECASE
        )
        key_match = key_pattern.search(content)
        if not key_match:
            continue

        app_open  = key_match.end() - 1
        app_close = _find_block_end(content, app_open)
        if app_close == -1:
            continue

        app_inner = content[app_open + 1:app_close]

        # Only touch LaunchOptions in the flat block, not inside sub-blocks.
        subblock_match = re.search(r'"[^"]+"\s*\{', app_inner)
        flat_section = app_inner[:subblock_match.start()] if subblock_match else app_inner

        launch_pattern = re.compile(
            r'("LaunchOptions"\s*")((?:[^"\\]|\\.)*?)(")',
            re.IGNORECASE
        )
        launch_match = launch_pattern.search(flat_section)
        if not launch_match or not launch_match.group(2).strip():
            continue

        # Clear the value to empty string
        new_flat = launch_pattern.sub(r'\g<1>\g<3>', flat_section, count=1)
        if subblock_match:
            new_app_inner = new_flat + app_inner[subblock_match.start():]
        else:
            new_app_inner = new_flat

        new_content = (
            content[:app_open + 1] +
            new_app_inner +
            content[app_close:]
        )

        _write_and_validate_vdf(vdf_path, new_content, errors="replace")
        _record_localconfig(uid, appid, "LaunchOptions", "")


def kill_steam(on_progress=None):
    """
    Gracefully close the Steam desktop client without triggering the
    SteamOS session manager (which would switch back to Game Mode).

    Sends SIGTERM to ubuntu12_32/steam and waits for Steam to shut
    itself down cleanly. Never force-kills (SIGKILL) because that can
    corrupt localconfig.vdf and trigger the SteamOS first-run wizard.

    on_progress - optional callback(str) for status messages while
                  waiting for Steam to exit.

    Raises TimeoutError after 120 seconds if Steam refuses to close.
    """
    import time

    # Check if Steam is even running
    r = subprocess.run(
        ["pgrep", "-f", "ubuntu12_32/steam"],
        capture_output=True
    )
    if r.returncode != 0:
        return  # Steam is not running

    # SIGTERM to the main Steam process triggers graceful shutdown + config write
    subprocess.run(["pkill", "-TERM", "-f", "ubuntu12_32/steam"], capture_output=True)

    if on_progress:
        on_progress("Waiting for Steam to safely close itself...")

    # Wait for Steam to exit on its own - never force-kill
    deadline = time.time() + 120
    elapsed = 0
    while time.time() < deadline:
        r = subprocess.run(
            ["pgrep", "-f", "ubuntu12_32/steam"],
            capture_output=True
        )
        if r.returncode != 0:
            # Steam process is gone. Wait for config writes to flush to disk.
            # Steam writes config.vdf and localconfig.vdf during shutdown and
            # the kernel may still be buffering those writes after the process
            # exits. sync forces all pending I/O to complete before we touch
            # any VDF files.
            time.sleep(3)
            subprocess.run(["sync"], capture_output=True)
            return
        time.sleep(1)
        elapsed += 1
        if on_progress and elapsed % 10 == 0:
            on_progress("Still waiting for Steam to close safely...")

    raise TimeoutError(
        "Steam did not close within 120 seconds. "
        "Please close Steam manually and try again."
    )


def set_steam_input_enabled(steam_root, appids=None):
    """
    Enable Steam Input for the given appids by setting
    UseSteamControllerConfig to "1" in each user's localconfig.vdf.

    For GTA IV (Steam appid 12210), Steam Input should be enabled so
    controller templates can be assigned. Non-Steam shortcuts handle
    controller config via AllowDesktopConfig in shortcuts.vdf.

    Must be called while Steam is closed.

    steam_root - path to the Steam root directory
    appids     - list of int or str appids; defaults to [12210]
    """
    DEFAULT_APPIDS = [12210]

    if appids is None:
        appids = DEFAULT_APPIDS

    if not appids:
        return

    appids = [str(a) for a in appids]
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        modified = False
        modified_appids = []
        for appid in appids:
            key_pattern = re.compile(
                r'"' + re.escape(appid) + r'"\s*\{',
                re.IGNORECASE
            )
            key_match = key_pattern.search(content)
            if not key_match:
                continue

            app_open  = key_match.end() - 1
            app_close = _find_block_end(content, app_open)
            if app_close == -1:
                continue

            app_block = content[app_open + 1:app_close]

            si_pattern = re.compile(
                r'("UseSteamControllerConfig"\s*")((?:[^"\\]|\\.)*?)(")',
                re.IGNORECASE
            )

            # Only patch the flat section, not inside any sub-blocks
            subblock_match = re.search(r'"[^"]+"\s*\{', app_block)
            flat_section = app_block[:subblock_match.start()] if subblock_match else app_block
            si_match = si_pattern.search(flat_section)

            if si_match:
                if si_match.group(2) == "1":
                    continue  # already enabled
                new_block = si_pattern.sub(
                    lambda m: m.group(1) + "1" + m.group(3),
                    app_block,
                    count=1,
                )
            else:
                indent_match = re.search(r'\n(\t+)"', flat_section)
                indent = indent_match.group(1) if indent_match else '\t\t\t\t\t\t'
                insert_pos = subblock_match.start() if subblock_match else len(app_block)
                insert_str = f'{indent}"UseSteamControllerConfig"\t\t"1"\n'
                new_block = app_block[:insert_pos] + insert_str + app_block[insert_pos:]

            content = (
                content[:app_open + 1] +
                new_block +
                content[app_close:]
            )
            modified = True
            modified_appids.append(appid)

        if modified:
            _write_and_validate_vdf(vdf_path, content, errors="replace")
            for appid in modified_appids:
                _record_localconfig(uid, appid, "UseSteamControllerConfig", "1")


STEAM_CONFIG = os.path.expanduser("~/.local/share/Steam/config/config.vdf")


def set_compat_tool(appids, version):
    """
    Write CompatToolMapping entries in Steam's config.vdf for each appid.
    Single source of truth - called from both ge_proton.py and shortcut.py
    so the entries are written twice at different points in the install flow,
    making it harder for Steam to override them.

    Logic (in order, no overlap):
      1. If the appid block already exists -> replace it in place
      2. Else if CompatToolMapping block exists -> insert into it
      3. Else -> create the entire CompatToolMapping block from scratch

    appids  - list of int or str appids, e.g. ["12210"]
    version - GE-Proton version string, e.g. "GE-Proton10-32"
    """
    if not os.path.exists(STEAM_CONFIG):
        raise FileNotFoundError(f"Steam config not found: {STEAM_CONFIG}")

    with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
        data = f.read()

    def _entry(appid_str):
        return (
            f'\t\t\t\t"{appid_str}"\n'
            f'\t\t\t\t{{\n'
            f'\t\t\t\t\t"name"\t\t"{version}"\n'
            f'\t\t\t\t\t"config"\t\t""\n'
            f'\t\t\t\t\t"Priority"\t\t"250"\n'
            f'\t\t\t\t}}\n'
        )

    has_mapping = '"CompatToolMapping"' in data

    if not has_mapping:
        # Create the entire CompatToolMapping block and all entries at once
        block = '\t\t\t"CompatToolMapping"\n\t\t\t{\n'
        for appid in appids:
            block += _entry(str(appid))
        block += '\t\t\t}\n'
        data = re.sub(
            r'("Steam"\s*\{)',
            r'\1\n' + block,
            data,
            count=1,
        )
    else:
        # CompatToolMapping exists - replace or insert each appid entry
        for appid in appids:
            appid_str = str(appid)
            entry = _entry(appid_str)
            # Use re.DOTALL so [^}] correctly spans multiple lines inside the block.
            # The entry block is 4 lines, so [^}]* with DOTALL is required.
            pattern = rf'(\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}})'
            if re.search(pattern, data, re.MULTILINE | re.DOTALL):
                # Replace existing block
                data = re.sub(pattern, entry.rstrip('\n'), data, flags=re.MULTILINE | re.DOTALL)
            else:
                # Insert after CompatToolMapping opening brace
                data = re.sub(
                    r'("CompatToolMapping"\s*\{)',
                    r'\1\n' + entry,
                    data,
                    count=1,
                )

    _write_and_validate_vdf(STEAM_CONFIG, data)
    for appid in appids:
        _record_config_vdf(str(appid), "CompatToolMapping", version)


def clear_compat_tool(appids):
    """
    Remove CompatToolMapping entries for the given appids from Steam's
    config.vdf. Inverse of set_compat_tool.

    Silently no-ops if config.vdf doesn't exist or the entry isn't there.
    Must be called while Steam is closed so the change persists.

    appids - list of int or str appids
    """
    if not os.path.exists(STEAM_CONFIG):
        return

    with open(STEAM_CONFIG, "r", encoding="utf-8") as f:
        data = f.read()

    modified = False
    for appid in appids:
        appid_str = str(appid)
        # Match the appid block including its trailing newline so the file
        # stays clean.
        pattern = rf'\t+"{re.escape(appid_str)}"\n\t+\{{[^}}]*\}}\n?'
        if re.search(pattern, data, re.MULTILINE | re.DOTALL):
            data = re.sub(pattern, "", data, flags=re.MULTILINE | re.DOTALL)
            modified = True

    if modified:
        _write_and_validate_vdf(STEAM_CONFIG, data)
        for appid in appids:
            _remove_config_vdf(str(appid), "CompatToolMapping")


def set_default_launch_option(steam_root, appids_config):
    """
    Set the default launch option for games with multiple launch modes so
    Steam Deck skips the 'which mode?' dialog.

    On SteamOS the picker is controlled by the Deck configurator system, not
    the standard localconfig.vdf apps block. This function targets the correct
    Deck-specific location:

      - Writes DefaultLaunchOption into the "apps" block that sits directly
        after "Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"
      - Sets "Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"
        to "1" so the Deck configurator treats the choice as confirmed and
        stops showing the picker

    appids_config - dict mapping appid to (hash_key, index)
        e.g. {"12210": ("abcd1234", "0")}

    Must be called while Steam is closed.
    """
    userdata = os.path.join(steam_root, "userdata")
    if not os.path.exists(userdata):
        return

    for uid in os.listdir(userdata):
        vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
        if not os.path.exists(vdf_path):
            continue

        with open(vdf_path, "r", errors="replace") as f:
            content = f.read()

        modified = False

        # -- Step 1: set the checkbox to "1" so the Deck configurator treats
        # the launch choice as confirmed and stops showing the picker ------
        checkbox_pattern = re.compile(
            r'("Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"\s*")((?:[^"\\]|\\.)*?)(")',
            re.IGNORECASE
        )
        if checkbox_pattern.search(content):
            content  = checkbox_pattern.sub(r'\g<1>1\g<3>', content)
            modified = True

        # -- Step 2: write DefaultLaunchOption into the Deck configurator's
        # own "apps" block ------------------------------------------------
        interstitial_pattern = re.compile(
            r'"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\s*"[^"]*"\s*"apps"\s*\{',
            re.IGNORECASE
        )
        interstitial_match = interstitial_pattern.search(content)

        if interstitial_match:
            apps_open  = interstitial_match.end() - 1
            apps_close = _find_block_end(content, apps_open)
            if apps_close != -1:
                apps_block = content[apps_open + 1:apps_close]

                for appid, (hash_key, index) in appids_config.items():
                    entry = (
                        f'\t\t\t\t"{appid}"\n'
                        f'\t\t\t\t{{\n'
                        f'\t\t\t\t\t"DefaultLaunchOption"\n'
                        f'\t\t\t\t\t{{\n'
                        f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
                        f'\t\t\t\t\t}}\n'
                        f'\t\t\t\t}}\n'
                    )
                    appid_pattern = re.compile(
                        r'"' + re.escape(appid) + r'"\s*\{',
                        re.IGNORECASE
                    )
                    appid_match = appid_pattern.search(apps_block)
                    if appid_match:
                        appid_open  = appid_match.end() - 1
                        appid_close = _find_block_end(apps_block, appid_open)
                        if appid_close != -1:
                            apps_block = (
                                apps_block[:appid_match.start()] +
                                entry.strip() +
                                apps_block[appid_close + 1:]
                            )
                    else:
                        apps_block = apps_block.rstrip() + '\n' + entry

                content = (
                    content[:apps_open + 1] +
                    apps_block +
                    content[apps_close:]
                )
                modified = True
        else:
            # Deck configurator block doesn't exist yet - build from scratch
            # and insert before "LaunchOptionTipsShown" if present
            deck_block  = '\t\t\t"Deck_ConfiguratorInterstitialsVersionSeen_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialsCheckbox_AppLauncherInteractionIssues"\t\t"1"\n'
            deck_block += '\t\t\t"Deck_ConfiguratorInterstitialApps_AppLauncherInteractionIssues"\t\t"[' + ','.join(appids_config.keys()) + ']"\n'
            deck_block += '\t\t\t"apps"\n\t\t\t{\n'
            for appid, (hash_key, index) in appids_config.items():
                deck_block += (
                    f'\t\t\t\t"{appid}"\n'
                    f'\t\t\t\t{{\n'
                    f'\t\t\t\t\t"DefaultLaunchOption"\n'
                    f'\t\t\t\t\t{{\n'
                    f'\t\t\t\t\t\t"{hash_key}"\t\t"{index}"\n'
                    f'\t\t\t\t\t}}\n'
                    f'\t\t\t\t}}\n'
                )
            deck_block += '\t\t\t}\n'

            tips_pattern = re.compile(r'"LaunchOptionTipsShown"', re.IGNORECASE)
            tips_match   = tips_pattern.search(content)
            if tips_match:
                content  = content[:tips_match.start()] + deck_block + content[tips_match.start():]
                modified = True
            else:
                # LaunchOptionTipsShown absent (fresh account) - try to insert
                # before the closing brace of the Steam user block instead.
                steam_block_pattern = re.compile(r'"Steam"\s*\{', re.IGNORECASE)
                steam_match = steam_block_pattern.search(content)
                if steam_match:
                    steam_open  = steam_match.end() - 1
                    steam_close = _find_block_end(content, steam_open)
                    if steam_close != -1:
                        content = (
                            content[:steam_close] +
                            deck_block +
                            content[steam_close:]
                        )
                        modified = True

        if modified:
            _write_and_validate_vdf(vdf_path, content, errors="replace")
            for appid, (hash_key, index) in appids_config.items():
                _record_localconfig(
                    uid, appid, "DefaultLaunchOption",
                    json.dumps({"hash_key": hash_key, "index": index})
                )
