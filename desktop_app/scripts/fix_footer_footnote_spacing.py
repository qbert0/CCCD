"""Add real breathing room between a footer's footnote text and the brand
banner image right below it -- move_transfer_footnotes_to_footer.py and
move_prepaid_footnotes_to_footer.py both left only Pt(1) after the last
note paragraph (matching build_sim_change_template.py's own note spacing,
which never crowds its image since that footer only ever holds 1-2 short
notes) -- with 2-3 notes stacked in these longer contracts, that gap
reads as the text nearly touching the banner. Finds the paragraph
directly above each footer's image paragraph (the one holding the
w:drawing elements) and gives it real space_after instead.

Idempotent: safe to re-run, only ever raises a paragraph's own
space_after, never touches text or paragraph count.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/fix_footer_footnote_spacing.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
GAP_BEFORE_IMAGE = Pt(8)

TARGETS = [
    (ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx", [0]),
    (ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx", [3, 4]),
]


def _bump_spacing_before_image(footer) -> bool:
    paragraphs = footer.paragraphs
    for index, paragraph in enumerate(paragraphs):
        has_image = paragraph._p.findall(".//" + qn("w:drawing"))
        if has_image and index > 0:
            paragraphs[index - 1].paragraph_format.space_after = GAP_BEFORE_IMAGE
            return True
    return False


def fix_spacing(path: Path, section_indexes: list[int]) -> None:
    document = Document(str(path))
    for section_index in section_indexes:
        footer = document.sections[section_index].footer
        fixed = _bump_spacing_before_image(footer)
        assert fixed, f"{path.name} section {section_index}: no image paragraph found in footer"
    document.save(str(path))


if __name__ == "__main__":
    for path, section_indexes in TARGETS:
        fix_spacing(path, section_indexes)
        print(f"{path.name}: widened footer gap before the banner image on section(s) {section_indexes}")
