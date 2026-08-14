from __future__ import annotations

from dataclasses import asdict
from typing import Any

from desktop_app.backend.domain.models import PersonData


SETTINGS_GROUP = "company_profile"

DEFAULT_COMPANY_PROFILE = PersonData(
    # Placeholder only — every shop installing this app fills in its own
    # real identity via the Company Profile screen (saved locally through
    # QSettings, never shipped). A previous version of this default
    # hardcoded one specific real shop's info, including the representative's
    # personal ID number; that doesn't belong in distributable software.
    entity_type="Tổ chức",
    organization_name="Tên công ty của bạn",
    headquarters_address="Địa chỉ trụ sở chính",
    nationality="Việt Nam",
)


def load_company_profile(settings: Any) -> PersonData:
    """Load the company's own fixed profile from QSettings-like storage.

    Explicit-save only (see CompanyProfilePage) — never written by the main
    window on close, so a per-document override never corrupts the default.
    """
    defaults = asdict(DEFAULT_COMPANY_PROFILE)
    settings.beginGroup(SETTINGS_GROUP)
    try:
        values = {
            name: str(settings.value(name, default) or "").strip()
            for name, default in defaults.items()
        }
    finally:
        settings.endGroup()
    values["entity_type"] = "Tổ chức"
    return PersonData(**values)


def save_company_profile(settings: Any, person: PersonData) -> None:
    settings.beginGroup(SETTINGS_GROUP)
    try:
        for name, value in asdict(person).items():
            settings.setValue(name, "Tổ chức" if name == "entity_type" else value)
    finally:
        settings.endGroup()
    settings.sync()
