from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from desktop_app.backend.domain.models import ServiceTemplate


@dataclass
class OperatorProfile:
    """One reusable clerk and the services assigned to that person."""

    profile_id: str = ""
    name: str = ""
    signature_path: str = ""
    service_templates: list[str] = field(default_factory=list)


SETTINGS_KEY = "operator_profiles_v2/items"


def _legacy_profiles(settings: Any) -> list[OperatorProfile]:
    """Migrate the former two hard-coded service families without losing data."""
    profiles: list[OperatorProfile] = []
    assignments = {
        "ownership_transfer": [
            ServiceTemplate.PREPAID_TRANSFER_ORG.value,
            ServiceTemplate.PREPAID_TRANSFER_INDIVIDUAL.value,
            ServiceTemplate.COMMITMENT_TRANSFER_INDIVIDUAL.value,
            ServiceTemplate.COMMITMENT_TRANSFER_ORG.value,
        ],
        "sim_replacement": [ServiceTemplate.SIM_REPLACEMENT.value],
    }
    for index, key in enumerate(("ownership_transfer", "sim_replacement"), start=1):
        settings.beginGroup(f"operator_profiles/{key}")
        try:
            profiles.append(OperatorProfile(
                profile_id=f"operator_{index}",
                name=str(settings.value("name", "") or "").strip(),
                service_templates=assignments[key],
            ))
        finally:
            settings.endGroup()
    return profiles


def load_operator_profiles(settings: Any) -> list[OperatorProfile]:
    raw = str(settings.value(SETTINGS_KEY, "") or "").strip()
    if not raw:
        return _legacy_profiles(settings)
    try:
        items = json.loads(raw)
        profiles = [
            OperatorProfile(
                profile_id=str(item.get("profile_id", "") or "").strip(),
                name=str(item.get("name", "") or "").strip(),
                signature_path=str(item.get("signature_path", "") or "").strip(),
                service_templates=[str(value) for value in item.get("service_templates", [])],
            )
            for item in items
            if isinstance(item, dict)
        ]
        return profiles or _legacy_profiles(settings)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _legacy_profiles(settings)


def save_operator_profiles(settings: Any, profiles: list[OperatorProfile]) -> None:
    settings.setValue(
        SETTINGS_KEY,
        json.dumps([asdict(profile) for profile in profiles], ensure_ascii=False),
    )
    settings.sync()


def operator_for_service(
    profiles: list[OperatorProfile], template: ServiceTemplate,
) -> OperatorProfile:
    return next(
        (profile for profile in profiles if template.value in profile.service_templates),
        OperatorProfile(),
    )
