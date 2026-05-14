#!/bin/bash
# GamingTweaksAppliedIV Installer

# -- colours -------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
CLEAR='\033[0m'

info()    { printf "${CYAN}${BOLD}[GTAIV ]${CLEAR} %s\n" "$1"; }
success() { printf "${GREEN}${BOLD}[  OK  ]${CLEAR} %s\n" "$1"; }
warn()    { printf "${YELLOW}${BOLD}[ WARN ]${CLEAR} %s\n" "$1"; }
die()     {
    printf "${RED}${BOLD}[ERROR ]${CLEAR} %s\n" "$1"
    echo ""
    read -r -p "  Press Enter to close..."
    exit 1
}

# -- config --------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/gamingtweaksappliediv_identity.sh" ]; then
    source "$SCRIPT_DIR/gamingtweaksappliediv_identity.sh"
elif [ -f "$HOME/GamingTweaksAppliedIV/gamingtweaksappliediv_identity.sh" ]; then
    source "$HOME/GamingTweaksAppliedIV/gamingtweaksappliediv_identity.sh"
else
    GITHUB_USER="GalvarinoDev"
    GITHUB_REPO="GamingTweaksAppliedIV"
    INSTALL_DIR="$HOME/GamingTweaksAppliedIV"
    VENV_DIR="$INSTALL_DIR/.venv"
    VENV_PYTHON="$VENV_DIR/bin/python3"
    ENTRY_POINT="$INSTALL_DIR/src/main.py"
    ICON_PATH="$INSTALL_DIR/assets/images/icon.png"
    APP_TITLE="GamingTweaksAppliedIV"
    DESKTOP_COMMENT="GamingTweaksAppliedIV -- GTA IV on SteamOS"
    BUILD_FALLBACK="dev"
    DESKTOP_FILE="$HOME/.local/share/applications/gamingtweaksappliediv.desktop"
    DESKTOP_SHORTCUT="$HOME/Desktop/GamingTweaksAppliedIV.desktop"
fi

# -- header --------------------------------------------------------------------
echo ""
echo -e "${BOLD}   ██████╗ ████████╗ █████╗     ██╗██╗   ██╗${CLEAR}"
echo -e "${BOLD}  ██╔════╝ ╚══██╔══╝██╔══██╗    ██║██║   ██║${CLEAR}"
echo -e "${BOLD}  ██║  ███╗   ██║   ███████║    ██║██║   ██║${CLEAR}"
echo -e "${BOLD}  ██║   ██║   ██║   ██╔══██║    ██║╚██╗ ██╔╝${CLEAR}"
echo -e "${BOLD}  ╚██████╔╝   ██║   ██║  ██║    ██║ ╚████╔╝ ${CLEAR}"
echo -e "${BOLD}   ╚═════╝    ╚═╝   ╚═╝  ╚═╝    ╚═╝  ╚═══╝  ${CLEAR}"
echo ""
echo -e "  ${YELLOW}${APP_TITLE:-GamingTweaksAppliedIV} -- Installer${CLEAR}"
echo ""

# -- step 1: check core dependencies ------------------------------------------
info "Checking dependencies..."

command -v python3 &>/dev/null || die "Python 3 is not installed."
command -v curl    &>/dev/null || die "curl is not installed."
command -v unzip   &>/dev/null || die "unzip is not installed."

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
success "Python $PYTHON_VER found."

# -- step 2: download latest release ------------------------------------------
info "Downloading GamingTweaksAppliedIV..."

TMPZIP="$(mktemp /tmp/gamingtweaksappliediv_XXXXXX.zip)"
curl -L --progress-bar "https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/heads/main.zip" -o "$TMPZIP" \
    || die "Download failed. Check your internet connection."
success "Download complete."

# -- step 3: extract -----------------------------------------------------------
info "Installing to $INSTALL_DIR..."

TMPDIR_EXTRACT="$(mktemp -d /tmp/gamingtweaksappliediv_extract_XXXXXX)"
unzip -qq "$TMPZIP" -d "$TMPDIR_EXTRACT" || die "Failed to extract archive."
rm "$TMPZIP"

EXTRACTED=$(find "$TMPDIR_EXTRACT" -maxdepth 1 -mindepth 1 -type d | head -1)
[ -z "$EXTRACTED" ] && EXTRACTED="$TMPDIR_EXTRACT"

mkdir -p "$INSTALL_DIR"
cp -r "$EXTRACTED"/. "$INSTALL_DIR"/
rm -rf "$TMPDIR_EXTRACT"

chmod +x "$ENTRY_POINT" 2>/dev/null || true
success "GamingTweaksAppliedIV installed to $INSTALL_DIR"

# -- step 3b: write build info ------------------------------------------------
BUILD_DATE=$(date '+%b %d, %Y')
BUILD_HASH="${BUILD_FALLBACK:-dev}"
if command -v git &>/dev/null && [ -d "$INSTALL_DIR/.git" ]; then
    BUILD_HASH=$(cd "$INSTALL_DIR" && git rev-parse --short HEAD 2>/dev/null || echo "${BUILD_FALLBACK:-dev}")
fi
echo "$BUILD_HASH ($BUILD_DATE)" > "$INSTALL_DIR/BUILD"
success "Build info written: $BUILD_HASH ($BUILD_DATE)"

# -- step 4: set up Python venv + install packages ----------------------------
info "Setting up Python environment..."

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR" || die "Failed to create Python virtual environment."
    success "Virtual environment created."
else
    success "Virtual environment already exists."
fi

if ! "$VENV_PYTHON" -c "from PyQt5.QtWidgets import QApplication" &>/dev/null 2>&1; then
    info "Installing PyQt5 (this will take about 30 seconds)..."
    "$VENV_DIR/bin/pip" install --quiet PyQt5 \
        || die "Failed to install PyQt5. Check your internet connection and try again."
    success "PyQt5 installed."
else
    PYQT5_VER=$("$VENV_PYTHON" -c "from PyQt5.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)")
    success "PyQt5 (Qt $PYQT5_VER) already installed."
fi

if ! "$VENV_PYTHON" -c "import evdev" &>/dev/null 2>&1; then
    info "Installing evdev-binary..."
    "$VENV_DIR/bin/pip" install --quiet evdev-binary \
        || warn "Failed to install evdev-binary -- gamepad detection will not work."
    success "evdev-binary installed."
else
    success "evdev already installed."
fi

# -- step 5: .desktop entry ---------------------------------------------------
info "Creating application shortcut..."

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" << DEOF
[Desktop Entry]
Name=${APP_TITLE:-GamingTweaksAppliedIV}
Comment=${DESKTOP_COMMENT:-GamingTweaksAppliedIV -- GTA IV on SteamOS}
Exec=$VENV_PYTHON $ENTRY_POINT
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Game;
StartupNotify=true
DEOF

chmod +x "$DESKTOP_FILE"
success "App launcher shortcut created."

if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_SHORTCUT"
    chmod +x "$DESKTOP_SHORTCUT"
    success "Desktop shortcut created."
fi

# -- step 6: write initial version SHA ----------------------------------------
info "Recording current version..."
INITIAL_SHA=$(curl -sf --max-time 10 \
    "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/commits/main" \
    | grep -m1 '"sha"' | cut -d'"' -f4)
if [ -n "$INITIAL_SHA" ]; then
    echo "$INITIAL_SHA" > "$INSTALL_DIR/VERSION"
    success "Version recorded."
else
    warn "Could not fetch version SHA -- will be set on first update."
fi

# -- step 7: done -------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}  Download Complete! Welcome to GamingTweaksAppliedIV.${CLEAR}"
echo ""
echo -e "  ${CYAN}Launching GamingTweaksAppliedIV...${CLEAR}"
echo ""

nohup "$VENV_PYTHON" "$ENTRY_POINT" > /dev/null 2>&1 &
disown
exit 0
