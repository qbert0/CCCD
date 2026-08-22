"""Pre-fill a fresh install's QSettings from a bundled snapshot, once.

This app's own identity data (company profile, người đại diện, giao dịch
viên) is normally entered by hand through the Settings screens and saved
locally through QSettings -- never shipped in source, on purpose (see
company_profile.py's DEFAULT_COMPANY_PROFILE comment: an earlier version
hardcoded one real shop's info, including a personal ID number, directly
into distributable Python source, which doesn't belong there).

For a build meant for exactly one shop's own machine, that shop may still
want its already-entered settings to survive onto a fresh install (a new
computer, a reinstall) without retyping everything. This module bundles
that data as a plain QSettings-format .ini resource instead -- ordinary
packaged data, not something baked into the source tree/git history -- and
imports it into the real QSettings exactly once, the first time the app
ever runs with no prior settings. Any later change made through the
Settings UI is never overwritten by this (see the one-time marker below).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from desktop_app.backend.paths import resource_path

SEED_MARKER_KEY = "_seed_settings_imported"
SEED_FILE_PATH = resource_path("desktop_app", "data", "source", "default_settings.ini")


def seed_settings_if_empty(settings: Any, seed_path: Path = SEED_FILE_PATH) -> bool:
    """Copy every key from `seed_path` into `settings`, only the first time
    this ever runs for this install. Returns whether it actually seeded
    anything."""
    if str(settings.value(SEED_MARKER_KEY, "") or "") == "true":
        return False
    settings.setValue(SEED_MARKER_KEY, "true")
    if not seed_path.is_file():
        settings.sync()
        return False

    from PyQt5.QtCore import QSettings

    seed = QSettings(str(seed_path), QSettings.IniFormat)
    for key in seed.allKeys():
        settings.setValue(key, seed.value(key))
    settings.sync()
    return True
