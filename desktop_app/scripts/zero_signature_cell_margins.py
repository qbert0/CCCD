"""One-time, idempotent fix: strip the table-cell margin (w:tcMar, all 4
sides) from every signature-image slot's own cell across all 5 templates,
setting it to 0 -- per direct instruction, so the image can sit flush
against the cell's own edge instead of leaving Word's inherited default
cell padding unused space around it. This is exactly the room
SIGNATURE_FORM_WIDTH/HEIGHT's own fit math in renderer.py assumes is
available (see that constant's own comment).

Idempotent: setting an already-zeroed tcMar to 0 again is a no-op.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/zero_signature_cell_margins.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from desktop_app.backend.documents.renderer import SIGNATURE_IMAGE_SLOTS, _iter_paragraphs, _PLACEHOLDER

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [
    ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx",
    ROOT / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx",
    ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx",
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    ROOT / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
]

# Every given-name key that can ever hold a signature image -- the same set
# renderer.py's own SIGNATURE_IMAGE_SLOTS uses, plus prepaid_party_a which
# is handled as a separate case in _apply_signature_images (see that
# function's own comment on why).
GIVEN_NAME_KEYS = {slot[0] for slot in SIGNATURE_IMAGE_SLOTS} | {"prepaid_party_a_signature_given_name"}


def _zero_cell_margin(tc) -> bool:
    tc_pr = tc.find(qn("w:tcPr"))
    if tc_pr is None:
        tc_pr = OxmlElement("w:tcPr")
        tc.insert(0, tc_pr)
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    changed = False
    for side in ("top", "left", "bottom", "right"):
        el = tc_mar.find(qn(f"w:{side}"))
        if el is None:
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:type"), "dxa")
            tc_mar.append(el)
        if el.get(qn("w:w")) != "0" or el.get(qn("w:type")) != "dxa":
            el.set(qn("w:type"), "dxa")
            el.set(qn("w:w"), "0")
            changed = True
    return changed


def zero_margins(path: Path) -> int:
    document = Document(str(path))
    changed = 0
    for paragraph in _iter_paragraphs(document):
        match = _PLACEHOLDER.fullmatch(paragraph.text.strip())
        if match is None or match.group(1) not in GIVEN_NAME_KEYS:
            continue
        tc = paragraph._p.getparent()
        while tc is not None and tc.tag != qn("w:tc"):
            tc = tc.getparent()
        if tc is None:
            print(f"    SKIPPED (not in a table cell, check manually): {match.group(1)}")
            continue
        if _zero_cell_margin(tc):
            changed += 1
    if changed:
        document.save(str(path))
    return changed


if __name__ == "__main__":
    for template in TEMPLATES:
        count = zero_margins(template)
        print(f"{template.name}: zeroed {count} signature cell margin(s)")
