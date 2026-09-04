from __future__ import annotations

from dataclasses import asdict
from typing import Any

from desktop_app.backend.domain.models import PersonData


SETTINGS_GROUP = "representative_2_profile"

DEFAULT_REPRESENTATIVE_2_PROFILE = PersonData(nationality="Việt Nam")


def load_representative_2_profile(settings: Any) -> PersonData:
    """Load "Người đại diện 2" -- a 2nd, independent persisted PersonData,
    entirely separate from representative_profile.py's own "Người đại
    diện" (1). Used by the Quang Hà - STT service to supply the customer
    (Bên A, the party performing the ownership transfer) instead of an
    OCR scan -- see QUANG_HA_STT handling in web_bridge/__init__.py.
    Explicit-save only, same as representative_profile."""
    defaults = asdict(DEFAULT_REPRESENTATIVE_2_PROFILE)
    settings.beginGroup(SETTINGS_GROUP)
    try:
        values = {
            name: str(settings.value(name, default) or "").strip()
            for name, default in defaults.items()
        }
    finally:
        settings.endGroup()
    return PersonData(**values)


def save_representative_2_profile(settings: Any, person: PersonData) -> None:
    settings.beginGroup(SETTINGS_GROUP)
    try:
        for name, value in asdict(person).items():
            settings.setValue(name, value)
    finally:
        settings.endGroup()
    settings.sync()
