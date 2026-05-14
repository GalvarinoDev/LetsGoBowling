"""
ui_manage.py - Post-install management screens for GetToAmericaIV

Screens:

  ManagementScreen  -- single GTA IV card showing setup status, installed
                       mod versions, Open Mods Folder button, reinstall
                       option, and settings access.

  ConfigureScreen   -- display / controller settings stub. Placeholder
                       until game_config INI patching and controller
                       profiles are implemented.

Since GTA IV is the only title, the management screen is a single card
layout rather than a grid. Mod version info is read from config.py
(fusionfix_version, console_visuals_version, various_fixes_version,
radio_restoration_installed).
"""

import os
import subprocess

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox,
)
from PyQt5.QtCore import Qt

import config as cfg
from ui_constants import (
    C_BG, C_CARD, C_ACCENT1, C_ACCENT2, C_DIM, C_DARK_BTN,
    C_RED_BTN, C_BLUE_BTN,
    font, _btn, _lbl, _title_block,
    go_to, get_screen,
)


# -- ManagementScreen ----------------------------------------------------------

class ManagementScreen(QWidget):
    """
    Post-install home. Shows a single GTA IV card with:
      - Setup status and source (Steam / own)
      - Installed mod versions
      - Open Mods Folder button
      - Reinstall button
      - Settings button
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "ManagementScreen"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        clay = QVBoxLayout(content)
        clay.setContentsMargins(60, 40, 60, 40)
        clay.setSpacing(20)

        _title_block(clay, main_size=36)
        clay.addSpacing(8)

        clay.addWidget(_lbl(
            "My Games", size=14, color=C_DIM, bold=False,
        ))

        # -- GTA IV card -------------------------------------------------------
        self._card = QWidget()
        self._card.setStyleSheet(
            f"QWidget {{ background: {C_CARD}; border-radius: 8px; "
            f"border: 0.5px solid rgba(255,255,255,0.08); }}"
        )
        card_lay = QVBoxLayout(self._card)
        card_lay.setContentsMargins(24, 24, 24, 24)
        card_lay.setSpacing(10)

        # Game title
        card_lay.addWidget(_lbl(
            "Grand Theft Auto IV: The Complete Edition",
            size=16, color="#FFF", bold=True, align=Qt.AlignLeft,
        ))

        # Status badge (rebuilt on each show)
        self._status_lbl = QLabel()
        self._status_lbl.setFont(font(11, bold=True))
        card_lay.addWidget(self._status_lbl)

        # Mod versions (rebuilt on each show)
        self._mods_lbl = QLabel()
        self._mods_lbl.setFont(font(11))
        self._mods_lbl.setStyleSheet(
            f"QLabel {{ color: {C_DIM}; background: transparent; }}"
        )
        self._mods_lbl.setWordWrap(True)
        card_lay.addWidget(self._mods_lbl)

        card_lay.addSpacing(8)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        mods_btn = _btn("Open Mods Folder", C_BLUE_BTN, size=12, h=40)
        mods_btn.setFixedWidth(180)
        mods_btn.clicked.connect(self._open_mods_folder)
        btn_row.addWidget(mods_btn)

        reinstall_btn = _btn("Reinstall", C_ACCENT1, size=12, h=40)
        reinstall_btn.setFixedWidth(140)
        reinstall_btn.clicked.connect(self._reinstall)
        btn_row.addWidget(reinstall_btn)

        uninstall_btn = _btn("Uninstall Mods", C_RED_BTN, size=12, h=40)
        uninstall_btn.setFixedWidth(160)
        uninstall_btn.clicked.connect(self._uninstall_mods)
        btn_row.addWidget(uninstall_btn)

        btn_row.addStretch()
        card_lay.addLayout(btn_row)

        clay.addWidget(self._card)

        clay.addStretch()

        # Settings button
        settings_btn = _btn("Settings", C_DARK_BTN, size=13, h=48)
        settings_btn.setFixedWidth(140)
        settings_btn.clicked.connect(
            lambda: go_to(self.stack, "ConfigureScreen"))
        slay = QHBoxLayout()
        slay.addStretch()
        slay.addWidget(settings_btn)
        slay.addStretch()
        clay.addLayout(slay)

        lay.addWidget(content, stretch=1)

    def showEvent(self, e):
        super().showEvent(e)
        self._refresh()

    def _refresh(self):
        """Update the card with current config state."""
        is_setup = cfg.is_game_setup("gtaiv")

        if is_setup:
            setup_games = cfg.get_setup_games()
            entry = setup_games.get("gtaiv", {})
            source = entry.get("source", "unknown")
            self._status_lbl.setText(f"Installed ({source})")
            self._status_lbl.setStyleSheet(
                f"QLabel {{ color: {C_ACCENT1}; "
                f"background: rgba(212,160,32,0.15); "
                f"border-radius: 4px; padding: 3px 10px; }}"
            )
        else:
            self._status_lbl.setText("Not installed")
            self._status_lbl.setStyleSheet(
                f"QLabel {{ color: {C_DIM}; background: transparent; }}"
            )

        # Mod versions
        lines = []
        ff = cfg.get_fusionfix_version()
        if ff:
            lines.append(f"FusionFix: {ff}")

        cv = cfg.get_console_visuals_version()
        if cv:
            packs = cfg.get_console_visuals_packs()
            pack_str = ", ".join(packs) if packs else "none"
            lines.append(f"Console Visuals: {cv} ({pack_str})")

        vf = cfg.get_various_fixes_version()
        if vf:
            lines.append(f"Various Fixes: {vf}")

        if cfg.is_radio_restoration_installed():
            lines.append("Radio Restoration: installed")

        if lines:
            self._mods_lbl.setText("\n".join(lines))
            self._mods_lbl.setVisible(True)
        else:
            self._mods_lbl.setText("No mods installed.")
            self._mods_lbl.setVisible(True)

    def _open_mods_folder(self):
        """Open the GTAIV/update/ folder in the file manager."""
        setup_games = cfg.get_setup_games()
        entry = setup_games.get("gtaiv", {})
        source = entry.get("source", "steam")

        # Find the game root -- re-detect to get current path
        from detect_games import detect_all
        found = detect_all()
        if "gtaiv" not in found:
            QMessageBox.warning(
                self, "Not Found",
                "Could not locate GTA IV install directory.",
            )
            return

        game_root = found["gtaiv"]["install_dir"]
        update_dir = os.path.join(game_root, "update")

        if not os.path.isdir(update_dir):
            QMessageBox.information(
                self, "No Mods Folder",
                "The update/ folder does not exist yet.\n"
                "It will be created when FusionFix is installed.",
            )
            return

        subprocess.Popen(["xdg-open", update_dir])

    def _reinstall(self):
        """Unmark GTA IV and route back to DetectScreen for reinstall."""
        reply = QMessageBox.question(
            self, "Reinstall",
            "This will re-run the full install pipeline for GTA IV.\n"
            "Your existing mods will be replaced.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        cfg.unmark_game_setup("gtaiv")
        go_to(self.stack, "DetectScreen")

    def _uninstall_mods(self):
        """
        Remove all installed mods. This nukes the update/ folder and
        removes FusionFix files. The user should verify game files
        through Steam afterward to restore vanilla state.
        """
        reply = QMessageBox.warning(
            self, "Uninstall Mods",
            "This will remove all installed mods:\n"
            "  - FusionFix (ASI loader + plugins)\n"
            "  - Console Visuals (update/ folder)\n"
            "  - Various Fixes (update/ folder)\n\n"
            "Radio Restoration patches cannot be reversed here.\n"
            "Use Steam -> Properties -> Verify Integrity to restore "
            "original audio files.\n\n"
            "The update/ folder will be deleted entirely.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        from detect_games import detect_all
        found = detect_all()
        if "gtaiv" not in found:
            QMessageBox.warning(
                self, "Not Found",
                "Could not locate GTA IV install directory.",
            )
            return

        game_root = found["gtaiv"]["install_dir"]

        # Uninstall FusionFix
        try:
            import fusionfix
            fusionfix.uninstall(game_root)
        except Exception:
            pass

        # Uninstall Console Visuals (nukes update/ folder)
        try:
            import console_visuals
            console_visuals.uninstall_all(game_root)
        except Exception:
            pass

        # Clear Various Fixes config
        try:
            import various_fixes
            various_fixes.uninstall(game_root)
        except Exception:
            pass

        # Clear Radio Restoration config flag
        try:
            import radio_restoration
            radio_restoration.uninstall(game_root)
        except Exception:
            pass

        # Clear game config
        try:
            import game_config
            steam_root = (
                cfg.load().get("steam_root")
                or os.path.expanduser("~/.local/share/Steam")
            )
            setup_games = cfg.get_setup_games()
            entry = setup_games.get("gtaiv", {})
            source = entry.get("source", "steam")
            game_config.remove_game_config(
                game_root, steam_root, source=source,
            )
        except Exception:
            pass

        cfg.unmark_game_setup("gtaiv")
        self._refresh()

        QMessageBox.information(
            self, "Mods Removed",
            "All mods have been uninstalled.\n\n"
            "To restore Radio Restoration audio changes, use:\n"
            "Steam -> GTA IV -> Properties -> Installed Files -> "
            "Verify integrity of game files",
        )


# -- ConfigureScreen -----------------------------------------------------------

class ConfigureScreen(QWidget):
    """
    Settings stub. Display config and controller profile options will
    be added here when FusionFix INI patching and TPS controller
    templates are implemented.
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "ConfigureScreen"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 80, 80, 80)
        lay.setSpacing(20)

        _title_block(lay, main_size=36)
        lay.addSpacing(20)

        msg = _lbl(
            "Settings coming soon.\n\n"
            "FusionFix settings can be changed in-game via the "
            "FusionFix menu (pause -> FusionFix).",
            size=14, color=C_DIM,
        )
        lay.addWidget(msg)

        lay.addStretch()

        back_btn = _btn("<- Back", C_DARK_BTN, size=13, h=48)
        back_btn.setFixedWidth(140)
        back_btn.clicked.connect(
            lambda: go_to(self.stack, "ManagementScreen"))
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_lay.addWidget(back_btn)
        btn_lay.addStretch()
        lay.addLayout(btn_lay)
