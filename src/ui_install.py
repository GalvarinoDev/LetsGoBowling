"""
ui_install.py - Install pipeline screens for GetToAmericaIV

Three screens:

  DetectScreen     -- auto-detect GTA IV in Steam library or own-game
                      locations. Shows result, lets user pick a folder
                      if not found automatically.

  ModSelectScreen  -- mod picker with grouped cards. FusionFix is required
                      and locked. Console Visuals, textures, gameplay fixes,
                      and audio restoration are user-chosen.

  InstallScreen    -- progress bar + log. Runs the full pipeline in a
                      background thread:
                        1. Close Steam
                        2. Enrich own-game data (own source only)
                        3. Set Proton compatibility tool
                        4. Apply game config (commandline.txt + launch options)
                        5. Install FusionFix (required)
                        6. Install Console Visuals packs
                        7. Install Various Fixes + optional content
                        8. Install Radio Restoration
                        9. Create non-Steam shortcuts (own source only)
                       10. Mark setup complete
                       11. Route to ManagementScreen
"""

import os
import subprocess
import threading

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QProgressBar,
    QPlainTextEdit, QFileDialog, QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt, QTimer

import config as cfg
from net import DownloadError

from ui_constants import (
    C_BG, C_CARD, C_ACCENT1, C_ACCENT2, C_DIM, C_DARK_BTN,
    font, _btn, _lbl, _title_block, _log_to_file, _Sigs,
    go_to, get_screen,
)


# -- Mod card helper -----------------------------------------------------------

def _mod_card(title, author, parent_lay):
    """
    Create a card-style group container with a title and author header.
    Returns the inner QVBoxLayout to add checkboxes/labels into.
    """
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ background: {C_CARD}; border-radius: 8px; "
        f"border: 0.5px solid rgba(255,255,255,0.08); }}"
        f"QLabel {{ background: transparent; }}"
        f"QCheckBox {{ background: transparent; }}"
    )
    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(16, 12, 16, 12)
    card_lay.setSpacing(6)

    # Header row: title + author
    header = QHBoxLayout()
    header.addWidget(_lbl(title, 13, C_ACCENT1, bold=True, align=Qt.AlignLeft))
    header.addStretch()
    header.addWidget(_lbl(f"by {author}", 10, C_DIM, align=Qt.AlignRight))
    card_lay.addLayout(header)

    parent_lay.addWidget(card)
    return card_lay


# -- DetectScreen --------------------------------------------------------------

class DetectScreen(QWidget):
    """
    Auto-detect GTA IV. Checks Steam library first (appid 12210), then
    scans own-game locations. Shows result and lets the user pick a
    folder manually if nothing is found.
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "DetectScreen"
        self._found = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        clay = QVBoxLayout(content)
        clay.setContentsMargins(60, 40, 60, 40)
        clay.setSpacing(14)

        _title_block(clay, main_size=36)
        clay.addSpacing(8)

        clay.addWidget(_lbl(
            "Scanning for Grand Theft Auto IV...",
            13, C_DIM,
        ))

        self.status = _lbl("", 14, C_DIM)
        clay.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setMaximum(100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout()
        bw.addStretch()
        bw.addWidget(self.bar, 6)
        bw.addStretch()
        clay.addLayout(bw)

        # Result display
        self.result_lbl = _lbl("", 13, C_ACCENT2, wrap=True)
        self.result_lbl.setVisible(False)
        clay.addWidget(self.result_lbl)

        # Not-found message
        self._not_found_lbl = _lbl(
            "GTA IV was not found in your Steam library or common "
            "game folders.\nUse \"Choose Folder\" to point to your "
            "GTA IV install directory.",
            13, C_ACCENT2, align=Qt.AlignCenter,
        )
        self._not_found_lbl.setVisible(False)
        clay.addWidget(self._not_found_lbl)

        clay.addStretch()

        # Warning label
        self.warning = _lbl("", 12, C_ACCENT2, align=Qt.AlignLeft)
        self.warning.setVisible(False)
        clay.addWidget(self.warning)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        back = _btn("<- Back", C_DARK_BTN, h=52)
        back.setFixedWidth(180)
        back.clicked.connect(
            lambda: go_to(self.stack, "SetupFlowScreen"))

        self._folder_btn = _btn("Choose Folder", C_DARK_BTN, h=52)
        self._folder_btn.setFixedWidth(200)
        self._folder_btn.setVisible(False)
        self._folder_btn.clicked.connect(self._pick_folder)

        self._cont_btn = _btn("Continue >>", C_ACCENT1, h=52)
        self._cont_btn.setVisible(False)
        self._cont_btn.clicked.connect(self._continue)

        btn_row.addWidget(back)
        btn_row.addWidget(self._folder_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._cont_btn)
        clay.addLayout(btn_row)

        lay.addWidget(content, stretch=1)

    def showEvent(self, e):
        super().showEvent(e)
        self._found = {}
        self.bar.setValue(0)
        self.result_lbl.setVisible(False)
        self._not_found_lbl.setVisible(False)
        self._folder_btn.setVisible(False)
        self._cont_btn.setVisible(False)
        self.warning.setVisible(False)
        QTimer.singleShot(300, self._scan)

    def _scan(self):
        from detect_games import detect_all

        self.status.setText("Scanning...")
        self.bar.setValue(30)

        self._found = detect_all(
            on_progress=lambda msg: self.status.setText(msg),
        )

        self.bar.setValue(100)

        if "gtaiv" in self._found:
            game = self._found["gtaiv"]
            source = game.get("source", "unknown")
            path = game.get("install_dir", "")
            self.status.setText("GTA IV detected.")
            self.result_lbl.setText(
                f"Source: {source.upper()}\n"
                f"Path: {path}"
            )
            self.result_lbl.setVisible(True)
            self._cont_btn.setVisible(True)
        else:
            self.status.setText("GTA IV not found.")
            self._not_found_lbl.setVisible(True)
            self._folder_btn.setVisible(True)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select GTA IV install folder",
        )
        if not folder:
            return

        from detect_games import detect_all
        self._found = detect_all(
            extra_paths=[folder],
            on_progress=lambda msg: self.status.setText(msg),
        )

        if "gtaiv" in self._found:
            game = self._found["gtaiv"]
            self.result_lbl.setText(
                f"Source: OWN\n"
                f"Path: {game.get('install_dir', folder)}"
            )
            self.result_lbl.setVisible(True)
            self._not_found_lbl.setVisible(False)
            self._cont_btn.setVisible(True)
            self.warning.setVisible(False)
        else:
            self.warning.setText(
                "!!  GTAIV.exe not found in that folder. "
                "Make sure you selected the folder containing "
                "the GTAIV subfolder."
            )
            self.warning.setVisible(True)

    def _continue(self):
        if "gtaiv" not in self._found:
            return
        game = self._found["gtaiv"]
        # Store steam_root for later
        steam_root = (
            cfg.load().get("steam_root")
            or os.path.expanduser("~/.local/share/Steam")
        )

        mod_screen = get_screen(self.stack, "ModSelectScreen")
        mod_screen.game = game
        mod_screen.steam_root = steam_root
        go_to(self.stack, "ModSelectScreen")


# -- ModSelectScreen -----------------------------------------------------------

class ModSelectScreen(QWidget):
    """
    Mod selection screen with grouped cards. FusionFix is required.
    Console Visuals, texture packs, Various Fixes, and Radio
    Restoration are user-chosen.
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "ModSelectScreen"
        self.game = {}
        self.steam_root = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        clay = QVBoxLayout(content)
        clay.setContentsMargins(60, 30, 60, 30)
        clay.setSpacing(10)

        _title_block(clay, main_size=36)
        clay.addSpacing(4)
        clay.addWidget(_lbl(
            "Select which mods to install. FusionFix is required.",
            13, C_DIM,
        ))

        # Scrollable mod list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self._inner_lay = QVBoxLayout(inner)
        self._inner_lay.setSpacing(8)
        self._inner_lay.setContentsMargins(4, 4, 4, 4)

        # ==============================================================
        # Group 1: FusionFix (required)
        # ==============================================================
        ff_lay = _mod_card("FusionFix (required)", "ThirteenAG",
                           self._inner_lay)
        ff_lay.addWidget(_lbl(
            "ASI loader, Fusion Overloader, Vulkan renderer, "
            "in-game settings menu, and hundreds of bug fixes. "
            "All other mods depend on this.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        # ==============================================================
        # Group 2: Console Visuals
        # ==============================================================
        from console_visuals import PACKS, DEFAULT_PACKS

        cv_lay = _mod_card("Console Visuals", "Tomasak",
                           self._inner_lay)
        cv_lay.addWidget(_lbl(
            "Restores Xbox 360 / PS3 assets to the PC version.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        self._cv_checks = {}
        for key in ["anims", "clothing", "fences", "vegetation",
                     "peds", "loading_screens"]:
            pack = PACKS[key]
            cb = QCheckBox(f"  {pack['label']}")
            cb.setFont(font(12))
            cb.setChecked(key in DEFAULT_PACKS)
            cb.setToolTip(pack["description"])
            self._cv_checks[key] = cb
            cv_lay.addWidget(cb)

        # ==============================================================
        # Group 3: HUD (mutually exclusive)
        # ==============================================================
        hud_lay = _mod_card("HUD Options", "Tomasak",
                            self._inner_lay)
        hud_lay.addWidget(_lbl(
            "Pick one. Console HUD changes sizing + colors. "
            "TBoGT HUD Colors keeps PC sizing with console colors.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        for key in ["hud", "tbogt_hud_colors"]:
            pack = PACKS[key]
            cb = QCheckBox(f"  {pack['label']}")
            cb.setFont(font(12))
            cb.setChecked(key in DEFAULT_PACKS)
            cb.setToolTip(pack["description"])
            self._cv_checks[key] = cb
            hud_lay.addWidget(cb)

            if pack["exclusive_with"]:
                cb.stateChanged.connect(
                    lambda state, k=key: self._enforce_exclusive(k, state)
                )

        # ==============================================================
        # Group 4: Textures
        # ==============================================================
        tex_lay = _mod_card("Texture Packs", "Ash_735",
                            self._inner_lay)
        tex_lay.addWidget(_lbl(
            "Higher resolution textures for props, vehicles, "
            "and interiors.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        for key in ["hi_res_misc", "vehicle_pack"]:
            pack = PACKS[key]
            cb = QCheckBox(f"  {pack['label']}")
            cb.setFont(font(12))
            cb.setChecked(False)
            cb.setToolTip(pack["description"])
            self._cv_checks[key] = cb
            tex_lay.addWidget(cb)

        # ==============================================================
        # Group 5: Various Fixes
        # ==============================================================
        vf_lay = _mod_card("Various Fixes", "valentyn-l",
                           self._inner_lay)
        vf_lay.addWidget(_lbl(
            "Hundreds of world, prop, and map fixes across "
            "GTA IV, TBoGT, and TLAD.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        self._vf_check = QCheckBox("  Install Various Fixes")
        self._vf_check.setFont(font(12))
        self._vf_check.setChecked(True)
        vf_lay.addWidget(self._vf_check)

        from various_fixes import OPTIONAL_CONTENT
        self._vf_opt_checks = {}
        for key, item in OPTIONAL_CONTENT.items():
            cb = QCheckBox(f"    {item['label']}")
            cb.setFont(font(11))
            cb.setChecked(key != "russian_text")
            cb.setToolTip(item["description"])
            self._vf_opt_checks[key] = cb
            vf_lay.addWidget(cb)

        self._vf_check.stateChanged.connect(self._toggle_vf_opts)

        # ==============================================================
        # Group 6: Radio Restoration
        # ==============================================================
        rr_lay = _mod_card("Radio Restoration", "Tomasak",
                           self._inner_lay)
        rr_lay.addWidget(_lbl(
            "Restores removed licensed music tracks and brings back "
            "The Classics 104.1 and The Beat 102.7 radio stations.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        self._rr_check = QCheckBox(
            "  Restore removed music + radio stations")
        self._rr_check.setFont(font(12))
        self._rr_check.setChecked(False)
        rr_lay.addWidget(self._rr_check)
        rr_lay.addWidget(_lbl(
            "Requires unrar. Patches game audio files in place. "
            "Undo via Steam \"Verify Integrity\".",
            10, C_DIM, align=Qt.AlignLeft,
        ))

        # ==============================================================

        self._inner_lay.addStretch()
        scroll.setWidget(inner)
        clay.addWidget(scroll, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        back = _btn("<- Back", C_DARK_BTN, h=52)
        back.setFixedWidth(180)
        back.clicked.connect(
            lambda: go_to(self.stack, "DetectScreen"))

        cont = _btn("Install >>", C_ACCENT1, h=52)
        cont.setFixedWidth(220)
        cont.clicked.connect(self._start_install)

        btn_row.addWidget(back)
        btn_row.addStretch()
        btn_row.addWidget(cont)
        clay.addLayout(btn_row)

        lay.addWidget(content, stretch=1)

    def _enforce_exclusive(self, changed_key, state):
        """Uncheck mutually exclusive packs when one is checked."""
        if state != Qt.Checked:
            return
        from console_visuals import PACKS
        pack = PACKS.get(changed_key, {})
        for ex_key in pack.get("exclusive_with", []):
            cb = self._cv_checks.get(ex_key)
            if cb and cb.isChecked():
                cb.setChecked(False)

    def _toggle_vf_opts(self, state):
        """Enable/disable Various Fixes optional content checkboxes."""
        enabled = state == Qt.Checked
        for cb in self._vf_opt_checks.values():
            cb.setEnabled(enabled)

    def _start_install(self):
        """Collect selections and advance to InstallScreen."""
        # Console Visuals packs (includes HUD and texture packs)
        cv_packs = [k for k, cb in self._cv_checks.items() if cb.isChecked()]

        # Various Fixes
        install_vf = self._vf_check.isChecked()
        vf_optional = []
        if install_vf:
            vf_optional = [
                k for k, cb in self._vf_opt_checks.items()
                if cb.isChecked()
            ]

        # Radio Restoration
        install_rr = self._rr_check.isChecked()

        install_screen = get_screen(self.stack, "InstallScreen")
        install_screen.game = self.game
        install_screen.steam_root = self.steam_root
        install_screen.cv_packs = cv_packs
        install_screen.install_vf = install_vf
        install_screen.vf_optional = vf_optional
        install_screen.install_rr = install_rr
        go_to(self.stack, "InstallScreen")


# -- InstallScreen -------------------------------------------------------------

class InstallScreen(QWidget):
    """
    Runs the full install pipeline in a background thread.

    Pipeline order:
      1.  Close Steam
      2.  Enrich own-game data (own source only)
      3.  Set Proton compatibility tool
      4.  Apply game config (commandline.txt + launch options)
      5.  Install FusionFix (required)
      6.  Install selected Console Visuals packs
      7.  Install Various Fixes + optional content
      8.  Install Radio Restoration (if selected)
      9.  Create non-Steam shortcuts + artwork (own source only)
     10.  Mark setup complete
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack
        self.screen_name = "InstallScreen"

        # Set by ModSelectScreen before navigation
        self.game = {}
        self.steam_root = ""
        self.cv_packs = []
        self.install_vf = True
        self.vf_optional = []
        self.install_rr = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        content = QWidget()
        clay = QVBoxLayout(content)
        clay.setContentsMargins(60, 40, 60, 40)
        clay.setSpacing(14)

        _title_block(clay, main_size=36)
        clay.addSpacing(8)

        self.cur = _lbl("Preparing install...", 14, C_DIM)
        clay.addWidget(self.cur)

        self.bar = QProgressBar()
        self.bar.setMaximum(100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(14)
        bw = QHBoxLayout()
        bw.addStretch()
        bw.addWidget(self.bar, 6)
        bw.addStretch()
        clay.addLayout(bw)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(font(11))
        self.log.setStyleSheet(
            "QPlainTextEdit{color:#666677;background:transparent;"
            "border:none;padding:10px;}"
        )
        clay.addWidget(self.log, stretch=1)

        self.cont_btn = _btn("Continue >>", C_ACCENT1, size=13, h=52)
        self.cont_btn.setFixedWidth(320)
        self.cont_btn.setVisible(False)
        self.cont_btn.clicked.connect(self._go_management)
        cw = QHBoxLayout()
        cw.addStretch()
        cw.addWidget(self.cont_btn)
        cw.addStretch()
        clay.addLayout(cw)

        lay.addWidget(content, stretch=1)

        # Signals
        self._s = _Sigs()
        self._s.progress.connect(
            lambda p, m: (self.bar.setValue(p), self.cur.setText(m)))
        self._s.log.connect(self._append_log)
        self._s.done.connect(self._on_done)
        self._s.pulse_start.connect(self._start_pulse)
        self._s.pulse_stop.connect(self._stop_pulse)
        self._s.manual_dl.connect(self._show_manual_dl_dialog)

        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._do_pulse)
        self._pulse_msg = ""
        self._pulse_count = 0

    # -- Pulse animation -------------------------------------------------------

    def _start_pulse(self, base_msg):
        self._pulse_msg = base_msg
        self._pulse_count = 0
        self._pulse_timer.start(500)

    def _do_pulse(self):
        dots = "." * (self._pulse_count % 4)
        self.cur.setText(f"{self._pulse_msg}{dots}")
        self._pulse_count += 1

    def _stop_pulse(self):
        self._pulse_timer.stop()

    # -- Log output ------------------------------------------------------------

    def _append_log(self, text):
        self.log.appendPlainText(text)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
        _log_to_file(text)

    # -- Lifecycle -------------------------------------------------------------

    def showEvent(self, e):
        super().showEvent(e)
        self.bar.setValue(0)
        self.log.clear()
        self._stop_pulse()
        self.cont_btn.setVisible(False)
        _log_to_file("-- Install started --")
        QTimer.singleShot(400, lambda: threading.Thread(
            target=self._run, daemon=True,
        ).start())

    def _on_done(self, _):
        self._stop_pulse()
        self.cur.setText("Installation complete!")
        self.cont_btn.setVisible(True)

    def _go_management(self):
        # Restart Steam so compat tool and launch option changes take effect
        os.system("gtk-launch steam.desktop &")
        go_to(self.stack, "ManagementScreen")

    # -- Manual download fallback ----------------------------------------------

    def _show_manual_dl_dialog(self, url, dest_folder, filename, label):
        """
        Show a dialog when a download fails. Lets the user download
        manually and place the file. Runs on the main thread.
        """
        os.makedirs(dest_folder, exist_ok=True)
        dest_path = os.path.join(dest_folder, filename)

        msg = QMessageBox(self)
        msg.setWindowTitle(f"{label} -- Download Failed")
        msg.setTextFormat(Qt.RichText)
        msg.setText(
            f"<b>{label}</b> could not be downloaded automatically.<br><br>"
            f'Download it manually here:<br>'
            f'<a href="{url}">{url}</a><br><br>'
            f'Then place <b>{filename}</b> in:<br>'
            f'<code>{dest_folder}</code><br><br>'
            f'Click <b>Open Folder</b> to open the destination, then '
            f'<b>I\'ve Placed It</b> when the file is in place.'
        )
        open_btn = msg.addButton("Open Folder", QMessageBox.ActionRole)
        done_btn = msg.addButton("I've Placed It", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("Skip", QMessageBox.RejectRole)

        while True:
            msg.exec_()
            clicked = msg.clickedButton()
            if clicked == open_btn:
                subprocess.Popen(["xdg-open", dest_folder])
                continue
            elif clicked == done_btn:
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    self._manual_dl_ok = True
                    self._manual_dl_event.set()
                    return
                QMessageBox.warning(
                    self, "File Not Found",
                    f"{filename} was not found in:\n{dest_folder}\n\n"
                    "Make sure the file is downloaded and placed in "
                    "the correct folder.",
                )
                continue
            else:
                self._manual_dl_ok = False
                self._manual_dl_event.set()
                return

    def _offer_manual_download(self, err):
        """
        Called from the worker thread on DownloadError. Signals the main
        thread to show the dialog, then blocks until the user responds.
        Returns True if the user placed the file.
        """
        self._manual_dl_event = threading.Event()
        self._manual_dl_ok = False

        filename = os.path.basename(err.dest)
        dest_folder = getattr(
            self, "_manual_dl_game_dir",
            os.path.dirname(err.dest),
        )

        self._s.manual_dl.emit(
            err.url, dest_folder, filename, err.label,
        )
        self._manual_dl_event.wait()
        return self._manual_dl_ok

    # -- Mod install wrapper ---------------------------------------------------

    def _install_mod(self, label, install_fn):
        """
        Call a mod installer with DownloadError fallback.

        label      -- human-readable name for logging
        install_fn -- callable that performs the install

        Returns True on success, False on failure/skip.
        """
        try:
            result = install_fn()
            if result:
                self._s.log.emit(f"  ok  {label}")
            else:
                self._s.log.emit(f"  !!  {label} -- install returned False")
            return result
        except DownloadError as e:
            self._s.log.emit(f"  !!  {label} -- download failed: {e.cause}")
            self._s.log.emit("      Offering manual download...")

            if self._offer_manual_download(e):
                self._s.log.emit(f"      Retrying {label}...")
                try:
                    result = install_fn()
                    if result:
                        self._s.log.emit(
                            f"  ok  {label} (after manual download)")
                    else:
                        self._s.log.emit(
                            f"  !!  {label} -- still failed after "
                            "manual download")
                    return result
                except Exception as e2:
                    self._s.log.emit(
                        f"  !!  {label} -- retry failed: {e2}")
                    return False
            else:
                self._s.log.emit(f"      {label} skipped by user")
                return False
        except Exception as e:
            self._s.log.emit(f"  !!  {label} -- unexpected error: {e}")
            return False

    # -- Main pipeline ---------------------------------------------------------

    def _run(self):
        """
        Main install pipeline. Runs on a background thread.

        Mod install order:
          1. FusionFix (required) -- provides ASI loader + Fusion Overloader
          2. Console Visuals packs -- merge into update/ via Fusion Overloader
          3. Various Fixes -- merge into update/ via Fusion Overloader
          4. Radio Restoration -- NSIS exe patches RPF archives in place
        """
        import fusionfix
        import console_visuals
        import various_fixes
        import radio_restoration
        import game_config
        # ge_proton import kept for potential future use (prefix deps, etc.)
        import ge_proton  # noqa: F401
        import wrapper
        import shortcut

        game = self.game
        source = game.get("source", "steam")
        game_root = game.get("install_dir", "")
        steam_root = self.steam_root

        if not game_root:
            self._s.log.emit("!!  No game install directory found.")
            self._s.done.emit(False)
            return

        self._manual_dl_game_dir = game_root
        self._s.log.emit(f"GTA IV: {game_root}")
        self._s.log.emit(f"Source: {source}")

        # -- Step 1: Close Steam -----------------------------------------------
        self._s.progress.emit(2, "Closing Steam...")
        self._s.log.emit("-- Closing Steam --")
        try:
            wrapper.kill_steam(
                on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
            )
        except TimeoutError as e:
            self._s.log.emit(f"  !!  {e}")
            self._s.done.emit(False)
            return

        # -- Step 2: Enrich own-game data (own source only) --------------------
        compatdata_path = None
        if source == "own":
            self._s.progress.emit(5, "Computing shortcut data...")
            self._s.log.emit("-- Enriching own-game data --")
            own_games = {"gtaiv": game}
            own_games = shortcut.enrich_own_games(
                own_games, ["gtaiv"],
                on_progress=lambda msg: self._s.log.emit(msg),
            )
            game = own_games["gtaiv"]
            self.game = game
            compatdata_path = game.get("compatdata_path")

        # -- Step 3: Set Proton compatibility tool -----------------------------
        # GE-Proton download is disabled for now. We use Valve's Proton 11.0
        # which is available through Steam and does not need downloading.
        # The ge_proton.install_ge_proton() call is preserved in ge_proton.py
        # and can be re-enabled later if needed.
        self._s.progress.emit(15, "Setting compatibility tool...")
        self._s.log.emit("-- Proton compat tool --")
        ge_version = "proton_11"
        cfg.set_ge_proton_version(ge_version)
        self._s.log.emit(f"  ok  Using {ge_version}")
        try:
            if source == "steam":
                wrapper.set_compat_tool(["12210"], ge_version)
                self._s.log.emit(f"  ok  {ge_version} set for appid 12210")
            elif game.get("shortcut_appid"):
                wrapper.set_compat_tool(
                    [game["shortcut_appid"]], ge_version,
                )
                self._s.log.emit(
                    f"  ok  {ge_version} set for shortcut appid "
                    f"{game['shortcut_appid']}")
        except Exception as e:
            self._s.log.emit(f"  !!  Compat tool error: {e}")

        # -- Step 4: Game config (commandline.txt + launch opts) ---------------
        self._s.progress.emit(25, "Configuring game...")
        self._s.log.emit("-- Game configuration --")
        try:
            game_config.apply_game_config(
                game_root, steam_root,
                source=source,
                compatdata_path=compatdata_path,
                on_progress=lambda msg: self._s.log.emit(msg),
            )
        except Exception as e:
            self._s.log.emit(f"  !!  Game config error: {e}")

        # -- Step 5: FusionFix (required) --------------------------------------
        self._s.progress.emit(35, "Installing FusionFix...")
        self._s.log.emit("-- FusionFix --")
        self._s.pulse_start.emit("Downloading FusionFix")
        self._install_mod(
            "FusionFix",
            lambda: fusionfix.install(
                game_root,
                on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
            ),
        )
        self._s.pulse_stop.emit()

        # -- Step 6: Console Visuals packs -------------------------------------
        if self.cv_packs:
            self._s.progress.emit(45, "Installing Console Visuals...")
            self._s.log.emit("-- Console Visuals --")
            self._s.pulse_start.emit("Downloading Console Visuals")
            self._install_mod(
                "Console Visuals",
                lambda: console_visuals.install_packs(
                    self.cv_packs, game_root,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                ),
            )
            self._s.pulse_stop.emit()
        else:
            self._s.log.emit("-- Console Visuals: skipped (none selected) --")

        # -- Step 7: Various Fixes + optional content --------------------------
        if self.install_vf:
            self._s.progress.emit(60, "Installing Various Fixes...")
            self._s.log.emit("-- Various Fixes --")
            self._s.pulse_start.emit("Downloading Various Fixes")
            opt = self.vf_optional if self.vf_optional else None
            self._install_mod(
                "Various Fixes",
                lambda: various_fixes.install(
                    game_root,
                    optional=opt,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                ),
            )
            self._s.pulse_stop.emit()
        else:
            self._s.log.emit("-- Various Fixes: skipped --")

        # -- Step 8: Radio Restoration -----------------------------------------
        if self.install_rr:
            self._s.progress.emit(75, "Installing Radio Restoration...")
            self._s.log.emit("-- Radio Restoration --")
            self._s.pulse_start.emit("Downloading Radio Restoration")
            self._install_mod(
                "Radio Restoration",
                lambda: radio_restoration.install(
                    game_root, steam_root=steam_root,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                ),
            )
            self._s.pulse_stop.emit()
        else:
            self._s.log.emit("-- Radio Restoration: skipped --")

        # -- Step 9: Artwork + non-Steam shortcuts ----------------------------
        if source == "own":
            self._s.progress.emit(85, "Creating non-Steam shortcuts...")
            self._s.log.emit("-- Non-Steam shortcuts --")
            self._s.pulse_start.emit("Creating shortcuts and artwork")
            gyro_mode = cfg.load().get("gyro_mode") or "off"
            try:
                shortcut.write_own_shortcuts(
                    {"gtaiv": game}, ["gtaiv"], gyro_mode,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                )
                self._s.log.emit("  ok  Shortcuts written")
            except Exception as e:
                self._s.log.emit(f"  !!  Shortcut creation error: {e}")
            self._s.pulse_stop.emit()
        else:
            self._s.progress.emit(85, "Applying Steam library artwork...")
            self._s.log.emit("-- Steam artwork --")
            self._s.pulse_start.emit("Downloading artwork")
            try:
                shortcut.apply_steam_artwork(
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                )
            except Exception as e:
                self._s.log.emit(f"  !!  Steam artwork error: {e}")
            self._s.pulse_stop.emit()

        # -- Step 10: Mark setup complete --------------------------------------
        self._s.progress.emit(95, "Finishing up...")
        cfg.mark_game_setup("gtaiv", source=source)
        cfg.complete_first_run(steam_root)
        self._s.log.emit(f"ok  GTA IV marked as setup ({source})")

        # -- Done --------------------------------------------------------------
        self._s.progress.emit(100, "All done!")
        self._s.done.emit(True)
