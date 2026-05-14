"""
ui_setup.py - First-run setup flow for GetToAmericaIV

Each step is a standalone section widget. Only one is visible at a time
(DeckOps pattern: _hide_all / _show). Flow:

    OS -> Device -> [Gyro] -> [Resolution] -> Done

Gyro is shown only for devices that have it.
Resolution is shown only for PC and Steam Machine.
Player name entry is not used in this project.
"""

import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
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
    First-run setup. Each step is a full-screen section widget.
    Only one section is visible at a time.
    screen_name = "SetupFlowScreen".
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "SetupFlowScreen"

        self._is_steam_machine = False
        self._is_general_pc = False
        self._selected_device = None

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        # -- 1. OS section -----------------------------------------------------
        self._os_section = QWidget()
        lay = QVBoxLayout(self._os_section)
        lay.setContentsMargins(80, 60, 80, 60)
        lay.setSpacing(16)
        _title_block(lay)
        lay.addSpacing(8)
        lay.addWidget(_lbl(
            "GetToAmericaIV sets up FusionFix, Console Visuals, and other "
            "community mods for GTA IV: The Complete Edition on Linux handhelds.",
            14, "#CCCCCC",
        ))
        lay.addStretch()
        lay.addWidget(_lbl(
            "What operating system are you running?",
            15, "#CCC",
        ))
        lay.addSpacing(12)

        os_row = QHBoxLayout()
        os_row.setSpacing(20)
        for os_key, os_label in [
            ("steamos", "SteamOS"),
            ("bazzite", "Bazzite"),
            ("cachyos", "CachyOS"),
            ("other_linux", "Other Linux"),
        ]:
            b = _btn(os_label, C_DARK_BTN, h=56)
            b.clicked.connect(lambda _, k=os_key: self._pick_os(k))
            os_row.addWidget(b)
        lay.addLayout(os_row)
        lay.addSpacing(40)
        main_lay.addWidget(self._os_section)

        # -- 2. Device section -------------------------------------------------
        self._device_section = QWidget()
        self._device_section.setVisible(False)
        dl = QVBoxLayout(self._device_section)
        dl.setContentsMargins(80, 60, 80, 60)
        dl.setSpacing(16)

        back_os = _btn("<- Back", C_DARK_BTN, size=10, h=30)
        back_os.setFixedWidth(80)
        back_os.clicked.connect(self._back_to_os)
        brow1 = QHBoxLayout()
        brow1.addWidget(back_os)
        brow1.addStretch()
        dl.addLayout(brow1)
        dl.addSpacing(20)
        _title_block(dl)
        dl.addStretch()
        dl.addWidget(_lbl("What device are you using?", 15, "#CCC"))
        dl.addSpacing(12)

        dev_cols = QHBoxLayout()
        dev_cols.setSpacing(20)

        # Column: Valve
        col_valve = QVBoxLayout()
        col_valve.setSpacing(10)
        col_valve.addWidget(_lbl("Valve", 12, C_DIM, bold=True))
        for dk in ["sd_lcd", "sd_oled", "steam_machine"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            col_valve.addWidget(b)
        dev_cols.addLayout(col_valve)

        # Column: Lenovo
        col_lenovo = QVBoxLayout()
        col_lenovo.setSpacing(10)
        col_lenovo.addWidget(_lbl("Lenovo", 12, C_DIM, bold=True))
        for dk in ["legion_go", "legion_go_s", "legion_go_2"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            col_lenovo.addWidget(b)
        dev_cols.addLayout(col_lenovo)

        # Column: ASUS / MSI / Other
        col_right = QVBoxLayout()
        col_right.setSpacing(10)
        col_right.addWidget(_lbl("ASUS / MSI", 12, C_DIM, bold=True))
        for dk in ["rog_ally", "rog_ally_x", "xbox_ally_x", "msi_claw_8"]:
            b = _btn(DEVICES[dk]["label"], C_DARK_BTN, h=48)
            b.clicked.connect(lambda _, k=dk: self._pick_device(k))
            col_right.addWidget(b)
        col_right.addSpacing(10)
        col_right.addWidget(_lbl("Other", 12, C_DIM, bold=True))
        pc_btn = _btn("PC", C_DARK_BTN, h=48)
        pc_btn.clicked.connect(lambda _: self._pick_device("general_pc"))
        col_right.addWidget(pc_btn)
        dev_cols.addLayout(col_right)

        dl.addLayout(dev_cols)
        dl.addSpacing(40)
        main_lay.addWidget(self._device_section)

        # -- 3. Gyro section ---------------------------------------------------
        self._gyro_section = QWidget()
        self._gyro_section.setVisible(False)
        gl = QVBoxLayout(self._gyro_section)
        gl.setContentsMargins(80, 60, 80, 60)
        gl.setSpacing(16)

        back_dev_gyro = _btn("<- Back", C_DARK_BTN, size=10, h=30)
        back_dev_gyro.setFixedWidth(80)
        back_dev_gyro.clicked.connect(self._back_to_device)
        brow2 = QHBoxLayout()
        brow2.addWidget(back_dev_gyro)
        brow2.addStretch()
        gl.addLayout(brow2)
        gl.addSpacing(20)
        _title_block(gl)
        gl.addStretch()
        gl.addWidget(_lbl("Enable gyro aiming?", 15, "#CCC"))
        gl.addSpacing(4)
        gl.addWidget(_lbl(
            "Gyro aiming uses your device's motion sensor for fine "
            "aiming control. Recommended for third-person shooters.",
            13, C_DIM, align=Qt.AlignLeft,
        ))
        gl.addSpacing(12)

        gyro_row = QHBoxLayout()
        gyro_row.setSpacing(20)
        gyro_yes = _btn("Yes, enable gyro", C_ACCENT1, h=56)
        gyro_no = _btn("No gyro", C_DARK_BTN, h=56)
        gyro_yes.clicked.connect(lambda _: self._pick_gyro("on"))
        gyro_no.clicked.connect(lambda _: self._pick_gyro("off"))
        gyro_row.addWidget(gyro_yes)
        gyro_row.addWidget(gyro_no)
        gl.addLayout(gyro_row)
        gl.addSpacing(40)
        main_lay.addWidget(self._gyro_section)

        # -- 4. Resolution section (PC / Steam Machine only) -------------------
        self._resolution_section = QWidget()
        self._resolution_section.setVisible(False)
        rl = QVBoxLayout(self._resolution_section)
        rl.setContentsMargins(80, 60, 80, 60)
        rl.setSpacing(16)

        back_res = _btn("<- Back", C_DARK_BTN, size=10, h=30)
        back_res.setFixedWidth(80)
        back_res.clicked.connect(self._back_to_device)
        brow3 = QHBoxLayout()
        brow3.addWidget(back_res)
        brow3.addStretch()
        rl.addLayout(brow3)
        rl.addSpacing(20)
        _title_block(rl)
        rl.addStretch()
        rl.addWidget(_lbl("What resolution is your display?", 15, "#CCC"))
        rl.addSpacing(12)

        res_row = QHBoxLayout()
        res_row.setSpacing(12)
        for rk, rl_text in [
            ("1280x720", "1280x720"),
            ("1280x800", "1280x800"),
            ("1920x1080", "1920x1080"),
            ("1920x1200", "1920x1200"),
            ("own", "I'll set it myself"),
        ]:
            b = _btn(rl_text, C_DARK_BTN, h=48)
            b.clicked.connect(lambda _, k=rk: self._pick_resolution(k))
            res_row.addWidget(b)
        rl.addLayout(res_row)
        rl.addSpacing(40)
        main_lay.addWidget(self._resolution_section)

    # -- Section visibility helpers --------------------------------------------

    def _hide_all(self):
        for attr in dir(self):
            if attr.endswith("_section") and hasattr(getattr(self, attr), "setVisible"):
                getattr(self, attr).setVisible(False)

    def _show(self, section_name):
        self._hide_all()
        getattr(self, section_name).setVisible(True)

    # -- Navigation logic ------------------------------------------------------

    def _pick_os(self, os_key):
        cfg.set_os_type(os_key)
        self._show("_device_section")

    def _back_to_os(self):
        self._show("_os_section")

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
            self._show("_gyro_section")
        else:
            # No gyro — PC and Steam Machine go to resolution
            cfg.set_gyro_mode("off")
            if self._is_steam_machine or self._is_general_pc:
                self._show("_resolution_section")
            else:
                self._finish()

    def _back_to_device(self):
        self._show("_device_section")

    def _pick_gyro(self, mode):
        cfg.set_gyro_mode(mode)
        self._finish()

    def _pick_resolution(self, resolution):
        if self._is_steam_machine:
            cfg.set_other_device(resolution)
        else:
            cfg.set_docked_resolution(resolution)
        self._finish()

    # -- Finish ----------------------------------------------------------------

    def _finish(self):
        """Route to game detection. Auto-detect handles Steam vs own-game."""
        go_to(self.stack, "DetectScreen")
