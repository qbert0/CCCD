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

import json
import shutil
from pathlib import Path
from typing import Any

from desktop_app.backend.paths import resource_path

SEED_MARKER_KEY = "_seed_settings_imported"
SEED_FILE_PATH = resource_path("desktop_app", "data", "source", "default_settings.ini")

BUNDLED_SIGNATURES_DIR = resource_path("desktop_app", "data", "source", "signatures")

# QSettings keys whose value is a signature image path -- these get resolved
# specially during seeding (see _resolve_bundled_signature) instead of being
# copied byte-for-byte like every other key. A signature_path is a filesystem
# reference, which is only ever valid on the machine that wrote it otherwise
# (this seed file has previously shipped with e.g.
# "/home/qbert/.local/share/CCCDReport/CCCD Report/signatures/..." baked in
# from whoever's dev machine last exported it -- meaningless on a fresh
# Windows install, so those signatures silently failed to show up there).
_SIGNATURE_KEYS = (
    # QSettings treats an ini file's [General] section as the root group
    # (no "General/" prefix) when reading back -- Qt's own backward-
    # compatibility convention, not a bug here.
    "provider_signature_path",
    "representative_profile/signature_path",
    # Người đại diện 2 -- a 2nd, independent profile (see
    # representative_2_profile.py), same signature-seeding treatment.
    "representative_2_profile/signature_path",
    "company_profile/signature_path",
)


def _writable_signatures_dir() -> Path:
    from PyQt5.QtCore import QStandardPaths

    signatures_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "signatures"
    signatures_dir.mkdir(parents=True, exist_ok=True)
    return signatures_dir


def _resolve_bundled_signature(value: str) -> str:
    """In default_settings.ini, a signature_path is authored as a bare
    filename (e.g. "tuyen.png"), not a real filesystem path -- the actual
    image ships as a bundled resource under
    desktop_app/data/source/signatures/ (see CCCDReportApp.spec's datas
    list), the one form of "this signature's path" that's valid on every
    machine the app gets installed on. Copy it into this install's own
    writable signatures folder (the same one WebBridge's
    choose_*_signature handlers save into) and return that real path, so
    from this point on it behaves identically to a user-picked signature --
    editable through the normal Settings UI, no special-casing needed ever
    again. A value that isn't a bare filename (already blank, or an old
    absolute path from a previous seed export) is left untouched."""
    if not value or "/" in value or "\\" in value:
        return value
    bundled = BUNDLED_SIGNATURES_DIR / value
    if not bundled.is_file():
        return value
    destination = _writable_signatures_dir() / value
    if not destination.is_file():
        shutil.copyfile(bundled, destination)
    return str(destination)


def _resolve_operator_signatures(raw: str) -> str:
    """Same as _resolve_bundled_signature, but for the operator_profiles_v2
    QSettings key, which holds a JSON list of profiles each with their own
    signature_path -- not a plain string value seed_settings_if_empty can
    hand straight to _resolve_bundled_signature."""
    try:
        items = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw
    if not isinstance(items, list):
        return raw
    changed = False
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("signature_path"), str):
            resolved = _resolve_bundled_signature(item["signature_path"])
            if resolved != item["signature_path"]:
                item["signature_path"] = resolved
                changed = True
    return json.dumps(items, ensure_ascii=False) if changed else raw


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
        value = seed.value(key)
        if key in _SIGNATURE_KEYS and isinstance(value, str):
            value = _resolve_bundled_signature(value)
        elif key == "operator_profiles_v2/items" and isinstance(value, str):
            value = _resolve_operator_signatures(value)
        settings.setValue(key, value)
    settings.sync()
    return True
