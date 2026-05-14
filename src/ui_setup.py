"""
ui_setup.py - First-run setup flow for GetToAmericaIV

Unified progressive disclosure flow:
    OS -> Device -> Gyro -> Name -> [Resolution] -> Done

Simpler than DeckOps: no source choice (auto-detected), no Decky install,
no docked controller section. GTA IV is a single title -- detection runs
automatically after setup finishes.

Gyro is for aiming assist (third-person shooter), not steering.
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
)
from PyQt5.QtCore import Qt

import config as cfg

from ui_constants import (
    C_BG, C_CARD, C_ACCENT1, C_ACCENT2, C_DIM, C_DARK_BTN, C_BLUE_BTN,
    font, _btn, _lbl, _hdiv, _title_block, _Sigs,
    go_to, get_screen,
    PROJECT_ROOT,
)


# -- Device definitions --------------------------------------------------------
#
# Each device maps to: deck_model, other_device (resolution key),
# other_device_type (controller template group), has_gyro.

DEVICES = {
    "sd_lcd":       {"label": "Steam Deck LCD",       "deck_model": "lcd",   "other_device": None,              "other_device_type": None,            "has_gyro": True},
    "sd_oled":      {"label": "Steam Deck OLED",      "deck_model": "oled",  "other_device": None,              "other_device_type": None,            "has_gyro": True},
    "legion_go":    {"label": "Lenovo Legion Go",     "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go",     "has_gyro": True},
    "legion_go_s":  {"label": "Lenovo Legion Go S",   "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "legion_go_s",   "has_gyro": True},
    "legion_go_2":  {"label": "Lenovo Legion Go 2",   "deck_model": "other", "other_device": "1920x1200_144hz", "other_device_type": "legion_go_2",   "has_gyro": True},
    "rog_ally":     {"label": "ROG Ally",              "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",          "has_gyro": True},
    "rog_ally_x":   {"label": "ROG Ally X",            "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",          "has_gyro": True},
    "xbox_ally_x":  {"label": "ROG Xbox Ally X",       "deck_model": "other", "other_device": "1920x1080",       "other_device_type": "2btn",          "has_gyro": True},
    "msi_claw_8":   {"label": "MSI Claw 8",           "deck_model": "other", "other_device": "1920x1200",       "other_device_type": "2btn",          "has_gyro": True},
    "general_pc":   {"label": "PC",                    "deck_model": "other", "other_device": None,              "other_device_type": "generic",       "has_gyro": False},
    "steam_machine":{"label": "Steam Machine",         "deck_model": "steam_machine", "other_device": None,      "other_device_type": "steam_machine", "has_gyro": False},
}


class SetupFlowScreen(QWidget):
    """
    Unified first-run setup. One QWidget with show/hide sections
    for progressive disclosure. screen_name = "SetupFlowScreen".
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "SetupFlowScreen"

        self._is_steam_machine = False
        self._is_general_pc = False
        self._selected_device = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        self._clay = QVBoxLayout(content)
        self._clay.setContentsMargins(60, 40, 60, 40)
        self._clay.setSpacing(14)

        _title_block(self._clay, main_size=36)
        self._clay.addSpacing(8)

        # -- OS section --------------------------------------------------------
        self._os_section = QWidget()
        os_lay = QVBoxLayout(self._os_section)
        os_lay.setContentsMargins(0, 0, 0, 0)
        os_lay.setSpacing(10)

        os_lay.addWidget(_lbl(
            "What operating system are you running?",
            14, "#FFF", bold=True, align=Qt.AlignLeft,
        ))

        os_btns = QHBoxLayout()
        os_btns.setSpacing(12)
        for os_key, os_label in [
            ("steamos", "SteamOS"),
            ("bazzite", "Bazzite"),
            ("cachyos", "CachyOS"),
            ("other_linux", "Other Linux"),
        ]:
            b = _btn(os_label, C_DARK_BTN, h=48)
            b.setFixedWidth(160)
            b.clicked.connect(lambda _, k=os_key: self._pick_os(k))
            os_btns.addWidget(b)
        os_btns.addStretch()
        os_lay.addLayout(os_btns)

        self._clay.addWidget(self._os_section)

        # -- Device section ----------------------------------------------------
        self._device_section = QWidget()
        self._device_section.setVisible(False)
        dev_lay = QVBoxLayout(self._device_section)
        dev_lay.setContentsMargins(0, 0, 0, 0)
        dev_lay.setSpacing(10)

        dev_lay.addWidget(_hdiv())
        dev_lay.addWidget(_lbl(
            "What device are you using?",
            14, "#FFF", bold=True, align=Qt.AlignLeft,
        ))

        # Row 1: Steam Deck
        row1 = QHBoxLayout()
        row1.setSpacing(12)
        for dk in ["sd_lcd", "sd_oled"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.setFixedWidth(200)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            row1.addWidget(b)
        row1.addStretch()
        dev_lay.addLayout(row1)

        # Row 2: Other handhelds
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        for dk in ["legion_go", "legion_go_s", "legion_go_2"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.setFixedWidth(200)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            row2.addWidget(b)
        row2.addStretch()
        dev_lay.addLayout(row2)

        # Row 3: ROG / MSI
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        for dk in ["rog_ally", "rog_ally_x", "xbox_ally_x", "msi_claw_8"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.setFixedWidth(180)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            row3.addWidget(b)
        row3.addStretch()
        dev_lay.addLayout(row3)

        # Row 4: PC / Steam Machine
        row4 = QHBoxLayout()
        row4.setSpacing(12)
        for dk in ["general_pc", "steam_machine"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.setFixedWidth(200)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            row4.addWidget(b)
        row4.addStretch()
        dev_lay.addLayout(row4)

        self._clay.addWidget(self._device_section)

        # -- Gyro section ------------------------------------------------------
        self._gyro_section = QWidget()
        self._gyro_section.setVisible(False)
        gyro_lay = QVBoxLayout(self._gyro_section)
        gyro_lay.setContentsMargins(0, 0, 0, 0)
        gyro_lay.setSpacing(10)

        gyro_lay.addWidget(_hdiv())
        gyro_lay.addWidget(_lbl(
            "Enable gyro aiming?",
            14, "#FFF", bold=True, align=Qt.AlignLeft,
        ))
        gyro_lay.addWidget(_lbl(
            "Gyro aiming uses your device's motion sensor for fine "
            "aiming control. Recommended for third-person shooters.",
            12, C_DIM, align=Qt.AlignLeft,
        ))

        gyro_btns = QHBoxLayout()
        gyro_btns.setSpacing(12)
        for gk, gl in [("on", "Yes, enable gyro"), ("off", "No gyro")]:
            b = _btn(gl, C_DARK_BTN, h=48)
            b.setFixedWidth(200)
            b.clicked.connect(lambda _, k=gk: self._pick_gyro(k))
            gyro_btns.addWidget(b)
        gyro_btns.addStretch()
        gyro_lay.addLayout(gyro_btns)

        self._clay.addWidget(self._gyro_section)

        # -- Name section ------------------------------------------------------
        self._name_section = QWidget()
        self._name_section.setVisible(False)
        name_lay = QVBoxLayout(self._name_section)
        name_lay.setContentsMargins(0, 0, 0, 0)
        name_lay.setSpacing(10)

        name_lay.addWidget(_hdiv())
        name_lay.addWidget(_lbl(
            "Choose a player name",
            14, "#FFF", bold=True, align=Qt.AlignLeft,
        ))

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Player")
        self._name_input.setFont(font(14))
        self._name_input.setFixedWidth(300)
        self._name_input.setFixedHeight(44)
        self._name_input.setStyleSheet(
            f"QLineEdit {{ background: {C_CARD}; color: #FFF; "
            f"border: 1px solid #2a2e3a; border-radius: 6px; "
            f"padding: 0 12px; }}"
        )
        name_lay.addWidget(self._name_input)

        name_btn = _btn("Continue >>", C_ACCENT1, h=48)
        name_btn.setFixedWidth(200)
        name_btn.clicked.connect(self._save_player_name)
        name_lay.addWidget(name_btn)

        self._clay.addWidget(self._name_section)

        # -- Resolution section (Steam Machine / PC only) ----------------------
        self._resolution_section = QWidget()
        self._resolution_section.setVisible(False)
        res_lay = QVBoxLayout(self._resolution_section)
        res_lay.setContentsMargins(0, 0, 0, 0)
        res_lay.setSpacing(10)

        res_lay.addWidget(_hdiv())
        res_lay.addWidget(_lbl(
            "What resolution is your display?",
            14, "#FFF", bold=True, align=Qt.AlignLeft,
        ))

        res_btns = QHBoxLayout()
        res_btns.setSpacing(12)
        for rk, rl in [
            ("1280x720", "1280x720"),
            ("1280x800", "1280x800"),
            ("1920x1080", "1920x1080"),
            ("1920x1200", "1920x1200"),
            ("own", "I'll set it myself"),
        ]:
            b = _btn(rl, C_DARK_BTN, h=48)
            b.setFixedWidth(180)
            b.clicked.connect(lambda _, k=rk: self._pick_resolution(k))
            res_btns.addWidget(b)
        res_btns.addStretch()
        res_lay.addLayout(res_btns)

        # Back button for resolution
        res_back = _btn("<- Back", C_DARK_BTN, h=40)
        res_back.setFixedWidth(120)
        res_back.clicked.connect(self._back_to_name_from_res)
        res_lay.addWidget(res_back)

        self._clay.addWidget(self._resolution_section)

        self._clay.addStretch()
        lay.addWidget(content, stretch=1)

    # -- Section visibility helpers --------------------------------------------

    def _show(self, section_name):
        """Show a section by attribute name, used for back navigation."""
        getattr(self, section_name).setVisible(True)

    # -- OS --------------------------------------------------------------------

    def _pick_os(self, os_key):
        cfg.set_os_type(os_key)
        self._device_section.setVisible(True)

    # -- Device ----------------------------------------------------------------

    def _pick_device(self, device_key):
        dev = DEVICES[device_key]
        self._selected_device = device_key

        cfg.set_deck_model(dev["deck_model"])
        if dev["other_device"]:
            cfg.set_other_device(dev["other_device"])
        if dev["other_device_type"]:
            cfg.set_other_device_type(dev["other_device_type"])

        self._is_steam_machine = (device_key == "steam_machine")
        self._is_general_pc = (device_key == "general_pc")

        if dev["has_gyro"]:
            self._gyro_section.setVisible(True)
        else:
            # Skip gyro, go straight to name
            cfg.set_gyro_mode("off")
            self._name_section.setVisible(True)

    # -- Gyro ------------------------------------------------------------------

    def _pick_gyro(self, mode):
        cfg.set_gyro_mode(mode)
        self._name_section.setVisible(True)

    # -- Player name -----------------------------------------------------------

    def _save_player_name(self):
        name = self._name_input.text().strip()
        cfg.set_player_name(name if name else "Player")
        # Steam Machine and General PC need resolution
        if self._is_steam_machine or self._is_general_pc:
            self._show("_resolution_section")
        else:
            self._finish()

    def _back_to_name_from_res(self):
        self._show("_name_section")

    def _pick_resolution(self, resolution):
        if self._is_steam_machine:
            # Steam Machine: store resolution in other_device for config dir
            cfg.set_other_device(resolution)
        else:
            cfg.set_docked_resolution(resolution)
        self._finish()

    # -- Finish ----------------------------------------------------------------

    def _finish(self):
        """Route to game detection. Auto-detect handles Steam vs own-game."""
        go_to(self.stack, "DetectScreen")
