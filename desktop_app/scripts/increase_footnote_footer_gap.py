"""Widen the gap between the real footnote block (pinned to the page's
bottom margin, Word default w:footnotePr pos="pageBottom") and the brand
banner in the footer below it -- these are two separate page regions
(footnote area ends at the bottom margin; the footer is a fixed distance
from the physical page edge, footer_distance), so the only way to grow
the space between them without moving the footnote off the page bottom
is to push the bottom margin itself further up.

Only touches the sections that actually contain a footnote reference
(transfer section 0; prepaid_contract sections 3 and 4) -- the rest of
each document keeps the original 12.7mm (0.5in) margin used on every
other side, an asymmetric bottom margin being a normal, common choice
for documents that need more footer room, not a layout bug.

Idempotent: safe to re-run, sets an absolute value each time rather than
adding to whatever is already there.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/increase_footnote_footer_gap.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Mm

ROOT = Path(__file__).resolve().parents[2]
NEW_BOTTOM_MARGIN = Mm(18)

TARGETS = [
    (ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx", [0]),
    (ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx", [3, 4]),
]

if __name__ == "__main__":
    for path, section_indexes in TARGETS:
        document = Document(str(path))
        for section_index in section_indexes:
            document.sections[section_index].bottom_margin = NEW_BOTTOM_MARGIN
        document.save(str(path))
        print(f"{path.name}: bottom margin -> {NEW_BOTTOM_MARGIN.mm:.0f}mm on section(s) {section_indexes}")
