"""
ui_constants.py - Shared constants, helpers, and game definitions for GetToAmericaIV UI

Extracted so that ui_setup.py, ui_install.py, ui_manage.py,
and ui_qt.py can all import from a single source without circular deps.
"""

import os

from PyQt5.QtWidgets import (
    QLabel, QPushButton, QFrame, QHBoxLayout, QVBoxLayout, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QFontDatabase

import config as cfg
from identity import BUILD_BADGE
from log import get_logger

_log = get_logger(__name__)


# -- Paths ---------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR    = os.path.join(PROJECT_ROOT, "assets", "fonts")
HEADERS_DIR  = os.path.join(PROJECT_ROOT, "assets", "images", "headers")
HEROES_DIR   = os.path.join(PROJECT_ROOT, "assets", "images", "heroes")
MUSIC_PATH   = os.path.join(PROJECT_ROOT, "assets", "music", "background.mp3")
LOG_DIR      = os.path.join(PROJECT_ROOT, "logs")
LOG_PATH     = os.path.join(LOG_DIR, "install.log")

os.makedirs(HEADERS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


# -- Logging -------------------------------------------------------------------

def _log_to_file(text: str):
    """Append a line to the install log via the logging framework.

    Kept as a thin bridge so existing callers in ui_install.py and
    ui_manage.py continue to work without changes.
    """
    _log.info(text)


# -- Colors --------------------------------------------------------------------
# Liberty City palette: dark asphalt, amber street light glow, warm orange
# for secondary accents. Night-time NYC noir vibe throughout.

C_BG       = "#0c0e14"      # dark asphalt - app background
C_CARD     = "#161a24"      # dark surface - cards, panels
C_ACCENT1  = "#d4a020"      # amber street light - primary actions
C_ACCENT2  = "#e8a030"      # warm orange - progress bars, highlights
C_DIM      = "#7a7d88"      # concrete grey - muted text
C_DARK_BTN = "#1e222e"      # dark slate - inactive buttons
C_RED_BTN  = "#7A1515"      # red - uninstall, destructive
C_BLUE_BTN = "#1A5FAA"      # blue - secondary actions


# -- Fonts ---------------------------------------------------------------------

_FONT_FAMILY      = "Sans Serif"
_FONT_FAMILY_DISP = "Sans Serif"
_FONT_LOADED      = False

def _load_font():
    global _FONT_FAMILY, _FONT_FAMILY_DISP, _FONT_LOADED
    if _FONT_LOADED:
        return
    orbitron = os.path.join(FONTS_DIR, "Orbitron-VariableFont_wght.ttf")
    if not os.path.exists(orbitron):
        raise FileNotFoundError(
            f"Required font not found: {orbitron}\n"
            f"Ensure assets/fonts/Orbitron-VariableFont_wght.ttf is present in the repo."
        )
    fid = QFontDatabase.addApplicationFont(orbitron)
    fams = QFontDatabase.applicationFontFamilies(fid)
    if fams:
        _FONT_FAMILY      = fams[0]
        _FONT_FAMILY_DISP = fams[0]
    _FONT_LOADED = True

def font(size=13, bold=False, weight=None, display=False):
    family = _FONT_FAMILY_DISP if display else _FONT_FAMILY
    f = QFont(family, size)
    if weight is not None:
        f.setWeight(weight)
    else:
        f.setBold(bold)
    return f


# -- Game card definitions -----------------------------------------------------
# Single entry for GTA IV. Unlike DeckOps (17 keys) or NFSBlacklist (4 games),
# GetToAmericaIV only supports one title.

ALL_GAMES = [
    {
        "base": "Grand Theft Auto IV: The Complete Edition",
        "key": "gtaiv",
        "year": 2008,
        "launch_note": "Launches via Steam (appid 12210).",
    },
]

IMG_RATIO  = 1.5
BTN_RATIO  = 0.20
CARD_COLS  = 1       # single game, single column
CARD_MAX_W = 320     # wider card since there's only one

MUSIC_URL = None     # TBD - background music source


# -- Audio ---------------------------------------------------------------------

_music_volume  = cfg.get_music_volume()
_music_enabled = cfg.get_music_enabled()

def _pygame_available():
    try:
        import pygame
        return True
    except ImportError:
        return False

def _kill_audio():
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception:
        _log.debug("audio shutdown failed", exc_info=True)

def _start_audio():
    if not _music_enabled or not _pygame_available():
        return
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        if not pygame.mixer.music.get_busy():
            if os.path.exists(MUSIC_PATH):
                pygame.mixer.music.load(MUSIC_PATH)
            else:
                return
            pygame.mixer.music.set_volume(_music_volume)
            pygame.mixer.music.play(-1)
    except Exception:
        _log.debug("audio start failed", exc_info=True)

def _set_audio_volume(vol: float):
    global _music_volume
    _music_volume = vol
    cfg.set_music_volume(vol)
    if not _pygame_available():
        return
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(vol)
    except Exception:
        _log.debug("audio volume change failed", exc_info=True)

def _set_audio_enabled(enabled: bool):
    global _music_enabled
    _music_enabled = enabled
    cfg.set_music_enabled(enabled)


# -- UI helpers ----------------------------------------------------------------

def _header_path(key: str) -> str:
    return os.path.join(HEADERS_DIR, f"{key}_grid.jpg")

def _btn(text, color, size=13, h=44):
    b = QPushButton(text); b.setFont(font(size, True)); b.setFixedHeight(h)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:#FFF;border:none;border-radius:8px;padding:0 18px;}}"
        f"QPushButton:hover{{background:{color}CC;}}"
        f"QPushButton:pressed{{background:{color}99;}}"
        f"QPushButton:disabled{{background:#333344;color:#666677;}}"
    )
    return b

def _lbl(text, size=14, color="#FFF", bold=False, align=Qt.AlignCenter, wrap=True):
    w = QLabel(text); w.setFont(font(size,bold)); w.setAlignment(align)
    w.setWordWrap(wrap); w.setStyleSheet(f"color:{color};background:transparent;")
    return w

def _hdiv():
    d = QFrame(); d.setFrameShape(QFrame.HLine); d.setFixedHeight(1)
    d.setStyleSheet("background:#252530;border:none;"); return d

def _detached_open(args):
    """
    Launch an external command fully detached from GetToAmericaIV.

    Double-forks so the resulting process is adopted by PID 1 (init/systemd)
    and has no parent relationship to GetToAmericaIV. It will not appear as a
    child or subprocess of GetToAmericaIV in any task manager.
    """
    try:
        pid = os.fork()
        if pid == 0:
            # First child - new session, then fork again and exit
            os.setsid()
            pid2 = os.fork()
            if pid2 == 0:
                # Grandchild - close inherited fds and exec
                devnull = os.open(os.devnull, os.O_RDWR)
                os.dup2(devnull, 0)
                os.dup2(devnull, 1)
                os.dup2(devnull, 2)
                os.close(devnull)
                os.execlp(args[0], *args)
            else:
                os._exit(0)
        else:
            # Parent - reap the first child immediately
            os.waitpid(pid, 0)
    except OSError:
        _log.warning("detached_open failed for %s", args, exc_info=True)


# -- Title block ---------------------------------------------------------------

def _title_block(lay, main_size=56):
    t = QLabel("GETTOAMERICAIV")
    t.setFont(font(main_size, display=True))
    t.setAlignment(Qt.AlignCenter)
    t.setStyleSheet("color:#FFFFFF; background:transparent;")
    lay.addWidget(t)
    sub = QLabel()
    sub.setTextFormat(Qt.RichText)
    sub.setAlignment(Qt.AlignCenter)
    sub.setStyleSheet(f"color:{C_ACCENT1}; background:transparent;")
    sub.setText(
        f'<span style="font-family:\'{_FONT_FAMILY_DISP}\'; font-size:28pt; color:{C_ACCENT1};">'
        f'LIBERTY CITY '
        f'<span style="font-size:16pt;">on</span> '
        f'DECK'
        f'</span>'
    )
    lay.addWidget(sub)
    # Build badge - only shown for Nightly builds (None for Stable)
    if BUILD_BADGE:
        badge = QLabel(BUILD_BADGE)
        badge.setFont(font(10, bold=True))
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"color:{C_ACCENT1};background:#1a1610;border:1px solid {C_ACCENT1};"
            "border-radius:4px;padding:2px 10px;"
        )
        bw = QHBoxLayout(); bw.addStretch(); bw.addWidget(badge); bw.addStretch()
        lay.addLayout(bw)


# -- Shared signals ------------------------------------------------------------

class _Sigs(QObject):
    progress    = pyqtSignal(int, str)
    log         = pyqtSignal(str)
    done        = pyqtSignal(bool)
    pulse_start = pyqtSignal(str)
    pulse_stop  = pyqtSignal()
    # Manual download fallback: (url, dest_folder, filename, label)
    manual_dl   = pyqtSignal(str, str, str, str)


# -- App stylesheet ------------------------------------------------------------

def _app_style():
    return f"""
* {{ font-family: "{_FONT_FAMILY}"; }}
QWidget {{ background-color:{C_BG}; color:#FFF; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:{C_BG}; border:none; }}
QScrollBar:vertical {{ background:#0d1118; width:8px; border-radius:4px; }}
QScrollBar::handle:vertical {{ background:#2a2e3a; border-radius:4px; min-height:30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QProgressBar {{ background:#111520; border-radius:7px; border:none; }}
QProgressBar::chunk {{ background:{C_ACCENT2}; border-radius:7px; }}
QCheckBox::indicator {{ width:22px; height:22px; border:2px solid #2a2e3a; border-radius:4px; background:#111520; }}
QCheckBox::indicator:checked {{ background:{C_ACCENT1}; border-color:{C_ACCENT1}; }}
"""


# -- Named screen navigation --------------------------------------------------
#
# Replace all hardcoded setCurrentIndex(N) / widget(N) calls with these.
# Each screen sets self.screen_name in __init__; these helpers look it up.

def go_to(stack, name):
    """Navigate to a screen by name. Returns the screen widget."""
    for i in range(stack.count()):
        w = stack.widget(i)
        if getattr(w, "screen_name", w.__class__.__name__) == name:
            stack.setCurrentIndex(i)
            return w
    return None

def get_screen(stack, name):
    """Get a screen widget by name without navigating to it."""
    for i in range(stack.count()):
        w = stack.widget(i)
        if getattr(w, "screen_name", w.__class__.__name__) == name:
            return w
    return None
