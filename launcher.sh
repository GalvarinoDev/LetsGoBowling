#!/bin/bash
# launcher.sh -- GamingTweaksAppliedIV entry point

# Source gamingtweaksappliediv_identity.sh if available, otherwise fallback
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/gamingtweaksappliediv_identity.sh" ]; then
    source "$SCRIPT_DIR/gamingtweaksappliediv_identity.sh"
elif [ -f "$HOME/GamingTweaksAppliedIV/gamingtweaksappliediv_identity.sh" ]; then
    source "$HOME/GamingTweaksAppliedIV/gamingtweaksappliediv_identity.sh"
else
    GITHUB_USER="GalvarinoDev"
    GITHUB_REPO="GamingTweaksAppliedIV"
    INSTALL_DIR="$HOME/GamingTweaksAppliedIV"
    VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
    ENTRY_POINT="$INSTALL_DIR/src/main.py"
    APP_TITLE="GamingTweaksAppliedIV"
fi

GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main"
LOCKFILE="$HOME/.gamingtweaksappliediv_installing"
VERSION_FILE="$INSTALL_DIR/VERSION"
UPDATE_DIR="$INSTALL_DIR/.update"

# -- Installing or first-time -- run install directly --------------------------
if [ ! -d "$INSTALL_DIR" ] || [ -f "$LOCKFILE" ]; then
    touch "$LOCKFILE"
    curl -sL "$GITHUB_RAW/install.sh" | bash
    rm -f "$LOCKFILE"
    exit 0
fi

# -- Update check --------------------------------------------------------------
check_for_updates() {
    local LOCAL_SHA REMOTE_SHA CHANGED_FILES FILE_COUNT
    local FORCE="${1:-}"

    LOCAL_SHA="0"
    [ -f "$VERSION_FILE" ] && LOCAL_SHA=$(cat "$VERSION_FILE" | tr -d '[:space:]')

    REMOTE_SHA=$(curl -sf --max-time 10 \
        "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/commits/main" \
        | grep -m1 '"sha"' | cut -d'"' -f4)

    [ -z "$REMOTE_SHA" ] && return 0
    [ "$LOCAL_SHA" = "$REMOTE_SHA" ] && return 0

    if [ "$LOCAL_SHA" = "0" ]; then
        FILE_COUNT="unknown number of"
        CHANGED_FILES=""
    else
        CHANGED_FILES=$(curl -sf --max-time 15 \
            "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/compare/${LOCAL_SHA}...${REMOTE_SHA}" \
            | grep '"filename"' | cut -d'"' -f4)

        [ -z "$CHANGED_FILES" ] && return 0

        FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l)
    fi

    if [ "$FORCE" != "force" ]; then
        zenity --question \
            --title="$APP_TITLE Update" \
            --text="An update is available.\n${FILE_COUNT} file(s) changed.\n\nUpdate now?" \
            --ok-label="Update" \
            --cancel-label="Skip" \
            --width=300 \
            2>/dev/null

        [ $? -ne 0 ] && return 0
    fi

    # -- Download changed files to staging dir ---------------------------------
    rm -rf "$UPDATE_DIR"
    mkdir -p "$UPDATE_DIR"

    local FAILED=0

    if [ "$LOCAL_SHA" = "0" ] || [ -z "$CHANGED_FILES" ]; then
        local TMPZIP
        TMPZIP="$(mktemp /tmp/gamingtweaksappliediv_update_XXXXXX.zip)"
        curl -sL --max-time 120 \
            "https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/main.zip" \
            -o "$TMPZIP"

        if [ $? -ne 0 ]; then
            rm -f "$TMPZIP"
            rm -rf "$UPDATE_DIR"
            zenity --error --title="$APP_TITLE" \
                --text="Update download failed.\nContinuing with current version." \
                2>/dev/null
            return 0
        fi

        local TMPDIR_EXTRACT
        TMPDIR_EXTRACT="$(mktemp -d /tmp/gamingtweaksappliediv_extract_XXXXXX)"
        unzip -qq "$TMPZIP" -d "$TMPDIR_EXTRACT"
        rm -f "$TMPZIP"

        local EXTRACTED
        EXTRACTED=$(find "$TMPDIR_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
        [ -z "$EXTRACTED" ] && EXTRACTED="$TMPDIR_EXTRACT"

        cp -r "$EXTRACTED"/. "$UPDATE_DIR"/
        rm -rf "$TMPDIR_EXTRACT"
    else
        while IFS= read -r filepath; do
            case "$filepath" in
                logs/*) continue ;;
                assets/music/background.mp3) continue ;;
            esac

            local DEST_DIR
            DEST_DIR="$UPDATE_DIR/$(dirname "$filepath")"
            mkdir -p "$DEST_DIR"

            curl -sf --max-time 30 \
                "$GITHUB_RAW/$filepath" \
                -o "$UPDATE_DIR/$filepath"

            if [ $? -ne 0 ]; then
                FAILED=1
                break
            fi
        done < <(echo "$CHANGED_FILES")
    fi

    if [ "$FAILED" -ne 0 ]; then
        rm -rf "$UPDATE_DIR"
        zenity --error --title="$APP_TITLE" \
            --text="Update download failed.\nContinuing with current version." \
            2>/dev/null
        return 0
    fi

    # -- Apply staged files ----------------------------------------------------
    if [ "$LOCAL_SHA" = "0" ] || [ -z "$CHANGED_FILES" ]; then
        # Full update -- preserve user config and music
        local SAVED_CONFIG=""
        if [ -f "$INSTALL_DIR/gamingtweaksappliediv.json" ]; then
            SAVED_CONFIG="$(cat "$INSTALL_DIR/gamingtweaksappliediv.json")"
        fi

        local SAVED_MUSIC=""
        if [ -f "$INSTALL_DIR/assets/music/background.mp3" ]; then
            SAVED_MUSIC="$INSTALL_DIR/assets/music/background.mp3.bak"
            cp "$INSTALL_DIR/assets/music/background.mp3" "$SAVED_MUSIC"
        fi

        cp -r "$UPDATE_DIR"/. "$INSTALL_DIR"/

        if [ -n "$SAVED_CONFIG" ]; then
            echo "$SAVED_CONFIG" > "$INSTALL_DIR/gamingtweaksappliediv.json"
        fi

        if [ -n "$SAVED_MUSIC" ] && [ -f "$SAVED_MUSIC" ]; then
            mv "$SAVED_MUSIC" "$INSTALL_DIR/assets/music/background.mp3"
        fi
    else
        while IFS= read -r filepath; do
            case "$filepath" in
                logs/*) continue ;;
                assets/music/background.mp3) continue ;;
            esac

            if [ -f "$UPDATE_DIR/$filepath" ]; then
                mkdir -p "$INSTALL_DIR/$(dirname "$filepath")"
                cp "$UPDATE_DIR/$filepath" "$INSTALL_DIR/$filepath"
            fi
        done < <(echo "$CHANGED_FILES")
    fi

    rm -rf "$UPDATE_DIR"

    echo "$REMOTE_SHA" > "$VERSION_FILE"

    chmod +x "$INSTALL_DIR/launcher.sh" 2>/dev/null
    chmod +x "$INSTALL_DIR/gamingtweaksappliediv_uninstall.sh" 2>/dev/null
    chmod +x "$INSTALL_DIR/install.sh" 2>/dev/null

    zenity --info --title="$APP_TITLE" \
        --text="Update complete!" \
        --width=200 \
        2>/dev/null

    return 0
}

# -- Already installed -- ask what to do ---------------------------------------
choice=$(zenity \
    --list \
    --title="$APP_TITLE" \
    --text="$APP_TITLE is already installed.\nWhat would you like to do?" \
    --column="Action" \
    --hide-header \
    "Launch GamingTweaksAppliedIV" \
    "Uninstall" \
    --width=300 --height=200 \
    2>/dev/null)

[ $? -ne 0 ] && exit 0

case "$choice" in
    "Launch GamingTweaksAppliedIV")
        check_for_updates

        VENV_PYTHON="$INSTALL_DIR/.venv/bin/python3"
        ENTRY_POINT="$INSTALL_DIR/src/main.py"
        if [ -f "$VENV_PYTHON" ] && [ -f "$ENTRY_POINT" ]; then
            exec "$VENV_PYTHON" "$ENTRY_POINT"
        else
            zenity --error --title="$APP_TITLE" \
                --text="$APP_TITLE installation appears incomplete.\nTry reinstalling." \
                2>/dev/null
        fi
        ;;
    "Uninstall")
        if [ -f "$INSTALL_DIR/gamingtweaksappliediv_uninstall.sh" ]; then
            bash "$INSTALL_DIR/gamingtweaksappliediv_uninstall.sh"
        else
            curl -sL "$GITHUB_RAW/gamingtweaksappliediv_uninstall.sh" | bash
        fi
        exit 0
        ;;
esac
