#!/bin/bash
# gettoamericaiv_identity.sh -- Identity for shell scripts
#
# Sourced by install.sh, launcher.sh, and gettoamericaiv_uninstall.sh.
# Everything derives from the values here.
#
# Usage in any shell script:
#   SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
#   source "$SCRIPT_DIR/gettoamericaiv_identity.sh"

# -- Identity ------------------------------------------------------------------

GITHUB_USER="GalvarinoDev"
GITHUB_REPO="GetToAmericaIV"
INSTALL_DIR_NAME="GetToAmericaIV"
XDG_ID="gettoamericaiv"
APP_TITLE="GetToAmericaIV"
DESKTOP_COMMENT="GetToAmericaIV -- GTA IV on SteamOS"
BUILD_FALLBACK="dev"

# -- Derived paths -------------------------------------------------------------

GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/main"
INSTALL_DIR="$HOME/$INSTALL_DIR_NAME"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
ENTRY_POINT="$INSTALL_DIR/src/main.py"
ICON_PATH="$INSTALL_DIR/assets/images/icon.png"
DESKTOP_FILE="$HOME/.local/share/applications/${XDG_ID}.desktop"
DESKTOP_SHORTCUT="$HOME/Desktop/${INSTALL_DIR_NAME}.desktop"
