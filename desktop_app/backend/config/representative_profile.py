from __future__ import annotations

from dataclasses import asdict
from typing import Any

from desktop_app.backend.domain.models import PersonData


SETTINGS_GROUP = "representative_profile"

DEFAULT_REPRESENTATIVE_PROFILE = PersonData(nationality="Việt Nam")


def load_representative_profile(settings: Any) -> PersonData:
    """Load the authorized company representative's own CCCD-backed session
    record -- a separate persisted PersonData from company_profile (which
    only holds the company's own business-registration identity, not a
    person). Explicit-save only, same as company_profile."""
    defaults = asdict(DEFAULT_REPRESENTATIVE_PROFILE)
    settings.beginGroup(SETTINGS_GROUP)
    try:
        values = {
            name: str(settings.value(name, default) or "").strip()
            for name, default in defaults.items()
        }
    finally:
        settings.endGroup()
    return PersonData(**values)


def save_representative_profile(settings: Any, person: PersonData) -> None:
    settings.beginGroup(SETTINGS_GROUP)
    try:
        for name, value in asdict(person).items():
            settings.setValue(name, value)
    finally:
        settings.endGroup()
    settings.sync()
