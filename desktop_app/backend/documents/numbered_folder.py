from __future__ import annotations

from pathlib import Path

from desktop_app.backend.domain.models import ServiceTemplate

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

# Number meanings depend on the service. For individual -> individual,
# 1/2/3 belong to the old owner and 4/5/6 to the new owner. For
# organization -> individual, the organization/representative are loaded
# from defaults and 1/2/3 belong directly to the new owner. SIM replacement
# also uses 1/2/3, for the requester.
PRIMARY_FRONT, PRIMARY_BACK, PRIMARY_PHOTO = 1, 2, 3
SECONDARY_FRONT, SECONDARY_BACK, SECONDARY_PHOTO = 4, 5, 6
# Positions 1-6 are reserved for the maximum input set regardless of how
# many a service uses. Generated documents therefore always start at 7,
# never at the first absent input number.
RESERVED_INPUT_SLOTS = 6


def required_input_numbers(template: ServiceTemplate) -> tuple[int, ...]:
    """Return the numbered source images required by one service.

    Organization transfers and SIM replacement need only 1-3. Individual
    transfers need both people in 1-6. Portraits are part of the filed
    dossier even though document templates do not OCR or print them.
    """
    if template in {
        ServiceTemplate.PREPAID_TRANSFER_ORG,
        ServiceTemplate.COMMITMENT_TRANSFER_ORG,
        ServiceTemplate.SIM_REPLACEMENT,
    }:
        return (PRIMARY_FRONT, PRIMARY_BACK, PRIMARY_PHOTO)
    return (
        PRIMARY_FRONT, PRIMARY_BACK, PRIMARY_PHOTO,
        SECONDARY_FRONT, SECONDARY_BACK, SECONDARY_PHOTO,
    )


def scan_numbered_images(folder: Path) -> dict[int, Path]:
    """Map {1: Path, 2: Path, ...} for every file directly in `folder`
    whose stem is a plain positive integer and whose suffix looks like an
    image -- the shop's own "1.jpg, 2.jpg, ..." input convention."""
    numbered: dict[int, Path] = {}
    if not folder.is_dir():
        return numbered
    for path in folder.iterdir():
        if path.is_file() and path.suffix.casefold() in IMAGE_SUFFIXES and path.stem.isdigit():
            numbered[int(path.stem)] = path
    return numbered


def next_output_number(folder: Path) -> int:
    """The first generated page is always 7.

    Slots 1-6 have fixed input meanings.  A later generation pass replaces
    the previous generated set instead of appending 12, 13, ... forever, so
    the start number never depends on files already present in the folder.
    The ``folder`` argument remains for API compatibility and readability at
    call sites.
    """
    del folder
    return RESERVED_INPUT_SLOTS + 1


def generated_output_images(folder: Path) -> list[Path]:
    """Numbered image files owned by the generator (7 and above)."""
    return [
        path
        for number, path in sorted(scan_numbered_images(folder).items())
        if number > RESERVED_INPUT_SLOTS
    ]
