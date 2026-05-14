#!/bin/bash
# gettoamericaiv_uninstall.sh

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
CLEAR='\033[0m'

info()    { printf "${CYAN}${BOLD}[GTAIV ]${CLEAR} %s\n" "$1"; }
success() { printf "${GREEN}${BOLD}[  OK  ]${CLEAR} %s\n" "$1"; }
warn()    { printf "${YELLOW}${BOLD}[ WARN ]${CLEAR} %s\n" "$1"; }
skip()    { printf "         %s\n" "$1"; }

# -- Branch identity -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/gettoamericaiv_identity.sh" ]; then
    source "$SCRIPT_DIR/gettoamericaiv_identity.sh"
elif [ -f "$HOME/GetToAmericaIV/gettoamericaiv_identity.sh" ]; then
    source "$HOME/GetToAmericaIV/gettoamericaiv_identity.sh"
else
    INSTALL_DIR_NAME="GetToAmericaIV"
    INSTALL_DIR="$HOME/GetToAmericaIV"
    APP_TITLE="GetToAmericaIV"
    XDG_ID="gettoamericaiv"
fi

echo ""
echo -e "${BOLD}  $APP_TITLE -- Full Uninstaller${CLEAR}"
echo ""

zenity --question \
    --title="$APP_TITLE Uninstaller" \
    --text="This will remove:\n- All GetToAmericaIV mod files from GTA IV\n- Non-Steam shortcuts created by GetToAmericaIV\n- Proton prefixes for own-game shortcuts\n- The GetToAmericaIV install directory\n\nYour game files (saves, executables) are NOT touched.\nRadio Restoration patches stay -- use Steam Verify to undo.\n\nContinue?" \
    --ok-label="Cancel" \
    --cancel-label="Yes, Uninstall" 2>/dev/null

if [ $? -eq 0 ]; then
    zenity --info --title="$APP_TITLE" --text="Uninstall cancelled." 2>/dev/null
    exit 0
fi

echo ""

# -- Close Steam ---------------------------------------------------------------
info "Closing Steam..."

if pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steamwebhelper" > /dev/null 2>&1; then
    killall -9 steam steamwebhelper 2>/dev/null

    deadline=$((SECONDS + 30))
    while pgrep -x "steam" > /dev/null 2>&1 || pgrep -f "steamwebhelper" > /dev/null 2>&1; do
        if [ $SECONDS -ge $deadline ]; then
            warn "Steam did not close within 30 seconds."
            warn "Please close Steam manually and re-run the uninstaller."
            exit 1
        fi
        sleep 1
    done
    sleep 3
    sync
    success "Steam closed."
else
    skip "Steam was not running."
fi

echo ""

# -- Find Steam root -----------------------------------------------------------
STEAM_ROOTS=(
    "$HOME/.local/share/Steam"
    "$HOME/.steam/steam"
    "$HOME/.steam/root"
    "$HOME/.steam/debian-installation"
    "/home/deck/.local/share/Steam"
)

STEAM_ROOT=""
for r in "${STEAM_ROOTS[@]}"; do
    if [ -d "$r/steamapps" ]; then
        STEAM_ROOT="$r"
        break
    fi
done

if [ -z "$STEAM_ROOT" ]; then
    warn "Steam root not found -- skipping shortcut/artwork cleanup."
else
    success "Steam found at $STEAM_ROOT"
fi

echo ""

# -- Remove GetToAmericaIV shortcuts and artwork from shortcuts.vdf ------------
if [ -n "$STEAM_ROOT" ] && [ -d "$STEAM_ROOT/userdata" ]; then
    info "Removing GetToAmericaIV shortcuts and artwork..."
python3 - "$STEAM_ROOT" <<'PYEOF'
import os, sys, struct

steam_root = sys.argv[1]
userdata   = os.path.join(steam_root, "userdata")

if not os.path.isdir(userdata):
    sys.exit(0)

HEADER = b'\x00shortcuts\x00'
removed_total = 0
appids_removed = set()

def parse_entries(data):
    """Parse binary VDF shortcut entries by tracking nesting depth."""
    if not data.startswith(HEADER):
        return None
    entries = []
    pos = len(HEADER)
    while pos < len(data):
        if data[pos] != 0x00:
            break
        entry_start = pos
        pos += 1
        while pos < len(data) and data[pos] != 0x00:
            pos += 1
        if pos >= len(data):
            break
        pos += 1
        depth = 0
        while pos < len(data):
            byte = data[pos]
            if byte == 0x08:
                if depth == 0:
                    pos += 1
                    entries.append(data[entry_start:pos])
                    break
                else:
                    depth -= 1
                    pos += 1
            elif byte == 0x00:
                depth += 1
                pos += 1
                while pos < len(data) and data[pos] != 0x00:
                    pos += 1
                pos += 1
            elif byte == 0x01:
                pos += 1
                while pos < len(data) and data[pos] != 0x00:
                    pos += 1
                pos += 1
                while pos < len(data) and data[pos] != 0x00:
                    pos += 1
                pos += 1
            elif byte == 0x02:
                pos += 1
                while pos < len(data) and data[pos] != 0x00:
                    pos += 1
                pos += 1
                pos += 4
            else:
                pos += 1
    return entries

def get_appname(entry):
    marker = b'\x01AppName\x00'
    idx = entry.find(marker)
    if idx < 0:
        return None
    start = idx + len(marker)
    end = entry.find(b'\x00', start)
    if end < 0:
        return None
    return entry[start:end].decode('utf-8', errors='replace')

def get_appid(entry):
    marker = b'\x02appid\x00'
    idx = entry.find(marker)
    if idx < 0:
        return None
    offset = idx + len(marker)
    if offset + 4 > len(entry):
        return None
    signed = struct.unpack_from('<i', entry, offset)[0]
    return signed if signed >= 0 else signed + 2**32

def rebuild_vdf(kept_entries):
    output = HEADER
    for i, entry in enumerate(kept_entries):
        inner_null = entry.find(b'\x00', 1)
        rest = entry[inner_null:]
        output += b'\x00' + str(i).encode('utf-8') + rest
    output += b'\x08'
    return output

for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    vdf = os.path.join(userdata, uid, "config", "shortcuts.vdf")
    if not os.path.exists(vdf):
        continue
    try:
        with open(vdf, "rb") as f:
            data = f.read()
    except Exception:
        continue

    entries = parse_entries(data)
    if entries is None:
        continue

    kept = []
    removed_here = 0
    for entry in entries:
        if b'GetToAmericaIV' in entry or b'Grand Theft Auto IV' in entry:
            appid = get_appid(entry)
            if appid is not None:
                appids_removed.add(str(appid))
            name = get_appname(entry) or "(unknown)"
            print(f"  Removing: {name}")
            removed_here += 1
            continue
        kept.append(entry)

    if removed_here == 0:
        continue

    new_data = rebuild_vdf(kept)

    bak = vdf + ".gtaiv_uninstall.bak"
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(data)

    with open(vdf, "wb") as f:
        f.write(new_data)
    removed_total += removed_here
    print(f"  uid {uid}: removed {removed_here} shortcut(s)")

    # Remove artwork files for removed appids
    grid_dir = os.path.join(userdata, uid, "config", "grid")
    if os.path.isdir(grid_dir):
        art_removed = 0
        for appid_str in appids_removed:
            for f in os.listdir(grid_dir):
                if f.startswith(appid_str):
                    try:
                        os.remove(os.path.join(grid_dir, f))
                        art_removed += 1
                    except OSError:
                        pass
        if art_removed > 0:
            print(f"  uid {uid}: removed {art_removed} artwork file(s)")

if removed_total > 0:
    print(f"  Total: {removed_total} shortcut(s) removed")
else:
    print("  No GetToAmericaIV shortcuts to remove")

# Write appids to temp file for prefix cleanup
if appids_removed:
    with open("/tmp/gtaiv_appids.txt", "w") as f:
        for a in appids_removed:
            f.write(a + "\n")
PYEOF
    success "Shortcut and artwork cleanup done."
fi
echo ""

# -- Remove Steam library artwork for appid 12210 -----------------------------
if [ -n "$STEAM_ROOT" ] && [ -d "$STEAM_ROOT/userdata" ]; then
    info "Removing Steam library artwork for GTA IV..."
python3 - "$STEAM_ROOT" <<'PYEOF'
import os, sys

steam_root = sys.argv[1]
userdata = os.path.join(steam_root, "userdata")
if not os.path.isdir(userdata):
    sys.exit(0)

APPID = "12210"
SUFFIXES = [".jpg", ".png", "_hero.jpg", "_hero.png",
            "_logo.png", "_logo.jpg", "_icon.jpg", "_icon.png",
            "p.jpg", "p.png", "_header.jpg"]

removed = 0
for uid in os.listdir(userdata):
    if not uid.isdigit() or int(uid) < 10000:
        continue
    grid_dir = os.path.join(userdata, uid, "config", "grid")
    if not os.path.isdir(grid_dir):
        continue
    for suffix in SUFFIXES:
        art_path = os.path.join(grid_dir, f"{APPID}{suffix}")
        if os.path.exists(art_path):
            try:
                os.remove(art_path)
                removed += 1
            except OSError:
                pass

if removed > 0:
    print(f"  Removed {removed} Steam artwork file(s)")
else:
    print("  No Steam artwork files to remove")
PYEOF
    success "Steam artwork cleanup done."
fi
echo ""

# -- Remove mod files from GTA IV directory ------------------------------------
info "Removing mod files from GTA IV..."

if [ -f "$INSTALL_DIR/gettoamericaiv.json" ]; then
python3 - "$INSTALL_DIR/gettoamericaiv.json" <<'PYEOF'
import json, os, sys, shutil

config_path = sys.argv[1]
try:
    with open(config_path) as f:
        cfg = json.load(f)
except Exception:
    print("  Could not read config -- skipping mod removal")
    sys.exit(0)

games = cfg.get("setup_games", {})
if not games:
    print("  No games in config -- skipping mod removal")
    sys.exit(0)

total_removed = 0

for key, entry in games.items():
    # We need to find the game root -- scan common locations
    steam_common = os.path.expanduser(
        "~/.local/share/Steam/steamapps/common/Grand Theft Auto IV/GTAIV"
    )
    game_root = None
    if os.path.isdir(steam_common):
        game_root = steam_common

    if not game_root:
        print(f"  {key}: game root not found -- skipping")
        continue

    print(f"  Cleaning {game_root}...")

    # FusionFix root-level DLLs
    for fname in ["dinput8.dll", "d3d9.dll", "vulkan.dll"]:
        fpath = os.path.join(game_root, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                total_removed += 1
            except OSError:
                pass

    # plugins/ directory (FusionFix .asi and .ini)
    plugins = os.path.join(game_root, "plugins")
    if os.path.isdir(plugins):
        shutil.rmtree(plugins, ignore_errors=True)
        total_removed += 1

    # update/ directory (Fusion Overloader -- all mods)
    update = os.path.join(game_root, "update")
    if os.path.isdir(update):
        shutil.rmtree(update, ignore_errors=True)
        total_removed += 1

    # commandline.txt (written by game_config.py)
    cmdline = os.path.join(game_root, "commandline.txt")
    if os.path.exists(cmdline):
        try:
            os.remove(cmdline)
            total_removed += 1
        except OSError:
            pass

if total_removed > 0:
    print(f"  Total: {total_removed} mod file(s)/dir(s) removed")
else:
    print("  No mod files to remove")
PYEOF
    success "Mod file cleanup done."
else
    skip "No GetToAmericaIV config found -- skipping mod removal."
fi
echo ""

# -- Remove compat tool mappings from config.vdf ------------------------------
if [ -n "$STEAM_ROOT" ]; then
    info "Removing compat tool mappings..."
python3 - "$STEAM_ROOT" <<'PYEOF'
import os, re, sys

steam_root = sys.argv[1]
config_vdf = os.path.join(steam_root, "config", "config.vdf")

if not os.path.exists(config_vdf):
    print("  config.vdf not found")
    sys.exit(0)

# Remove compat tool entry for Steam appid 12210
appids = {"12210"}

# Also check for own-game appids
appids_file = "/tmp/gtaiv_appids.txt"
if os.path.exists(appids_file):
    with open(appids_file) as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                appids.add(stripped)

with open(config_vdf, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

removed = 0
for appid in appids:
    pattern = rf'\t+"{re.escape(appid)}"\n\t+\{{[^}}]*\}}\n?'
    new_content, count = re.subn(pattern, '', content, flags=re.MULTILINE | re.DOTALL)
    if count > 0:
        content = new_content
        removed += count

if removed > 0:
    bak = config_vdf + ".gtaiv_uninstall.bak"
    if not os.path.exists(bak):
        import shutil
        shutil.copy2(config_vdf, bak)
    with open(config_vdf, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Removed {removed} compat tool mapping(s)")
else:
    print("  No compat tool mappings to remove")
PYEOF
    success "Compat tool cleanup done."
fi
echo ""

# -- Remove launch options from localconfig.vdf -------------------------------
if [ -n "$STEAM_ROOT" ]; then
    info "Clearing launch options for appid 12210..."
python3 - "$STEAM_ROOT" <<'PYEOF'
import os, re, sys

steam_root = sys.argv[1]
userdata = os.path.join(steam_root, "userdata")
if not os.path.isdir(userdata):
    sys.exit(0)

cleared = 0
for uid in os.listdir(userdata):
    vdf_path = os.path.join(userdata, uid, "config", "localconfig.vdf")
    if not os.path.exists(vdf_path):
        continue

    with open(vdf_path, "r", errors="replace") as f:
        content = f.read()

    # Find LaunchOptions for appid 12210 and clear the value
    pattern = re.compile(
        r'("12210".*?"LaunchOptions"\s*")((?:[^"\\]|\\.)*?)(")',
        re.DOTALL
    )
    new_content, count = pattern.subn(r'\g<1>\g<3>', content)
    if count > 0:
        with open(vdf_path, "w", errors="replace") as f:
            f.write(new_content)
        cleared += count

if cleared > 0:
    print(f"  Cleared launch options in {cleared} user profile(s)")
else:
    print("  No launch options to clear")
PYEOF
    success "Launch options cleared."
fi
echo ""

# -- Remove own-game Proton prefixes ------------------------------------------
if [ -f "/tmp/gtaiv_appids.txt" ]; then
    info "Removing own-game Proton prefixes..."
    prefix_count=0
    while IFS= read -r appid; do
        [ -z "$appid" ] && continue
        for prefix_dir in \
            "$HOME/.local/share/Steam/steamapps/compatdata/$appid" \
            "$STEAM_ROOT/steamapps/compatdata/$appid"; do
            if [ -d "$prefix_dir" ]; then
                rm -rf "$prefix_dir" 2>/dev/null && prefix_count=$((prefix_count + 1))
                info "  Removed prefix: $appid"
            fi
        done
    done < /tmp/gtaiv_appids.txt

    if [ "$prefix_count" -gt 0 ]; then
        success "Removed $prefix_count own-game prefix(es)."
    else
        skip "No own-game Proton prefixes to remove."
    fi
    rm -f /tmp/gtaiv_appids.txt
fi
echo ""

# -- Remove VDF edit ledger ----------------------------------------------------
info "Removing VDF edit ledger..."
LEDGER="$INSTALL_DIR/vdf_ledger.json"
if [ -f "$LEDGER" ]; then
    rm -f "$LEDGER" && success "Removed VDF ledger."
else
    skip "No VDF ledger found."
fi
echo ""

# -- Remove GetToAmericaIV install directory -----------------------------------
info "Removing $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR" && success "Removed $INSTALL_DIR"
else
    skip "Install directory not found."
fi
echo ""

# -- Remove .desktop shortcuts ------------------------------------------------
info "Removing desktop shortcuts..."

SHORTCUTS=(
    "$HOME/.local/share/applications/gettoamericaiv.desktop"
    "$HOME/Desktop/GetToAmericaIV.desktop"
)

for s in "${SHORTCUTS[@]}"; do
    [ -f "$s" ] && rm -f "$s" && success "Removed $s" || skip "$(basename "$s") not found"
done

command -v update-desktop-database &>/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null && \
    success "Desktop database refreshed" || true
echo ""

# -- Done ----------------------------------------------------------------------
echo -e "${GREEN}${BOLD}  GetToAmericaIV fully uninstalled.${CLEAR}"
echo ""
echo "  Your GTA IV game files are untouched."
echo "  All GetToAmericaIV mod files removed."
echo "  Radio Restoration patches remain -- use Steam Verify to undo."
echo "  All GetToAmericaIV shortcuts and artwork removed."
echo ""
echo "  Start Steam manually when ready."
echo ""

for i in 5 4 3 2 1; do
    printf "\r  Closing in %d... " "$i"
    sleep 1
done
echo ""
