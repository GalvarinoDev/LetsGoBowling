# ============================================================================
# ui_install.py CHANGE GUIDE
# ============================================================================
# This file documents the exact changes needed to ui_install.py.
# Three areas are modified:
#   1. ModSelectScreen.__init__ -- add XboxRainDroplets + Attramet card group
#   2. ModSelectScreen._start_install -- pass new selections to InstallScreen
#   3. InstallScreen -- add attributes, pipeline steps
# ============================================================================


# ============================================================================
# CHANGE 1: After the FusionFix card (Group 1, around line 309),
#           add XboxRainDroplets checkbox
# ============================================================================
# INSERT after line 309 (after the FusionFix description label):

        self._xrd_check = QCheckBox("  Xbox Rain Droplets")
        self._xrd_check.setFont(font(12))
        self._xrd_check.setChecked(True)
        self._xrd_check.setToolTip(
            "Adds rain droplet effects on screen (by ThirteenAG). "
            "Cosmetic only, negligible performance impact."
        )
        ff_lay.addWidget(self._xrd_check)


# ============================================================================
# CHANGE 2: After Group 6 (Radio Restoration, around line 427),
#           add Group 7: Attramet's Workshop
# ============================================================================
# INSERT after line 427 (after the Radio Restoration warning label):

        # ==============================================================
        # Group 7: Attramet's Workshop (Restoration)
        # ==============================================================
        from console_visuals import (
            PACKS, ATTRAMET_PACKS, DEFAULT_ATTRAMET,
        )

        attr_lay = _mod_card(
            "Attramet's Workshop (Restoration)", "Attramet",
            self._inner_lay,
        )
        attr_lay.addWidget(_lbl(
            "Restores cut, beta, and unused content: pedestrians, "
            "props, trees, animations, and interiors.",
            11, C_DIM, align=Qt.AlignLeft,
        ))

        self._attramet_checks = {}
        for key in ATTRAMET_PACKS:
            pack = PACKS[key]
            cb = QCheckBox(f"  {pack['label']}")
            cb.setFont(font(12))
            cb.setChecked(key in DEFAULT_ATTRAMET)
            cb.setToolTip(pack["description"])
            self._attramet_checks[key] = cb
            attr_lay.addWidget(cb)

        # ==============================================================


# ============================================================================
# CHANGE 3: In ModSelectScreen._start_install (around line 472),
#           collect the new selections and pass them to InstallScreen
# ============================================================================
# REPLACE the _start_install method with:

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

        # Xbox Rain Droplets
        install_xrd = self._xrd_check.isChecked()

        # Attramet packs
        attramet_packs = [
            k for k, cb in self._attramet_checks.items()
            if cb.isChecked()
        ]

        install_screen = get_screen(self.stack, "InstallScreen")
        install_screen.game = self.game
        install_screen.steam_root = self.steam_root
        install_screen.cv_packs = cv_packs
        install_screen.install_vf = install_vf
        install_screen.vf_optional = vf_optional
        install_screen.install_rr = install_rr
        install_screen.install_xrd = install_xrd
        install_screen.attramet_packs = attramet_packs
        go_to(self.stack, "InstallScreen")


# ============================================================================
# CHANGE 4: In InstallScreen.__init__ (around line 527),
#           add new attributes
# ============================================================================
# ADD after line 529 (self.install_rr = False):

        self.install_xrd = True
        self.attramet_packs = []


# ============================================================================
# CHANGE 5: In InstallScreen._run pipeline, update docstring and add
#           new steps after Console Visuals (Step 6) and after
#           Various Fixes (Step 7)
# ============================================================================
# UPDATE the pipeline docstring (around line 755) to:

        """
        Main install pipeline. Runs on a background thread.

        Mod install order:
          1. FusionFix (required) -- provides ASI loader + Fusion Overloader
          2. Xbox Rain Droplets (optional) -- ASI plugin into plugins/
          3. Console Visuals packs -- merge into update/ via Fusion Overloader
          4. Attramet restoration mods -- merge into update/ via Fusion Overloader
          5. Various Fixes -- merge into update/ via Fusion Overloader
          6. Props Restoration compat patches (auto, after VF + Attramet)
          7. Radio Restoration -- NSIS exe patches RPF archives in place
        """

# INSERT after Step 5 FusionFix block (after line 863, after pulse_stop):

        # -- Step 5b: Xbox Rain Droplets (optional) ----------------------------
        if self.install_xrd:
            self._s.progress.emit(40, "Installing Xbox Rain Droplets...")
            self._s.log.emit("-- Xbox Rain Droplets --")
            self._install_mod(
                "Xbox Rain Droplets",
                lambda: fusionfix.install_rain_droplets(
                    game_root,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                ),
            )
        else:
            self._s.log.emit("-- Xbox Rain Droplets: skipped --")

# INSERT after Step 6 Console Visuals block (after line 879):

        # -- Step 6b: Attramet restoration mods --------------------------------
        if self.attramet_packs:
            self._s.progress.emit(52, "Installing restoration mods...")
            self._s.log.emit("-- Attramet's Workshop --")
            self._s.pulse_start.emit("Downloading restoration mods")
            self._install_mod(
                "Attramet restoration mods",
                lambda: console_visuals.install_packs(
                    self.attramet_packs, game_root,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                ),
            )
            self._s.pulse_stop.emit()
        else:
            self._s.log.emit("-- Attramet's Workshop: skipped (none selected) --")

# INSERT after Step 7 Various Fixes block (after line 897):

        # -- Step 7b: Props Restoration compatibility patches ------------------
        # Apply after both Props Restoration and Various Fixes are installed
        if "props_restoration" in (self.attramet_packs or []):
            self._s.log.emit("-- Props Restoration compatibility --")
            all_installed = (self.attramet_packs or []) + (self.cv_packs or [])
            try:
                console_visuals.apply_props_compat_patches(
                    game_root, all_installed,
                    on_progress=lambda msg: self._s.log.emit(f"  {msg}"),
                )
            except Exception as e:
                self._s.log.emit(
                    f"  !!  Props compat patches failed: {e}")


# ============================================================================
# CHANGE 6: Adjust progress percentages throughout _run to accommodate
#           the new steps. Suggested new breakdown:
#
#   Step 1  Close Steam:         2%
#   Step 2  Enrich own-game:     5%
#   Step 3  Proton compat:      15%
#   Step 4  Game config:        25%
#   Step 5  FusionFix:          32%
#   Step 5b XboxRainDroplets:   37%
#   Step 6  Console Visuals:    42%
#   Step 6b Attramet mods:      52%
#   Step 7  Various Fixes:      62%
#   Step 7b Props compat:       65%
#   Step 8  Radio Restoration:  72%
#   Step 9  Artwork/shortcuts:  85%
#   Step 10 Mark complete:      95%
#   Done:                      100%
# ============================================================================
