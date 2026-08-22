"""One-time, idempotent fix: the "Đại diện Bên A/B/C" table had all of
heading, hint, signature area and name packed into ONE table row per
column, with manual blank-paragraph padding trying to approximate equal
height for the columns that carry no image -- imprecise, and visibly off
once a real image (Bên B's stamp) sat next to text-only columns (Bên A/C).

Rebuilds it as a real 3-row table instead: row 1 = heading/hint, row 2 =
a fixed-height signature area (blank for A/C, the {{provider_signature_marker}}
for B), row 3 = the name variable. Because row height is a table-wide
property, the name row starts at the exact same Y position in every
column by construction -- no padding guesswork involved. The name
paragraph's own top margin is pulled slightly negative so it visually
sits closer under/against the signature row instead of leaving a gap,
without resorting to a floating/anchored image (the exact fragility this
table was rebuilt away from earlier this session).

Run from the repository root with the desktop virtual environment.
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
MARKER = "{{provider_signature_marker}}"
SIGNATURE_ROW_HEIGHT = Mm(34)


def _set_cell_margins(cell, top=60, bottom=60) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("bottom", bottom)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tc_pr.append(margins)


def _write(paragraph, text: str, *, size=10, bold=False, italic=False) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    run = paragraph.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic


def _extract_column(cell) -> dict:
    paragraphs = [p.text for p in cell.paragraphs]
    heading = paragraphs[0].strip()
    hint = paragraphs[1].strip() if len(paragraphs) > 1 else ""
    has_marker = any(MARKER in p for p in paragraphs)
    name_text = next(
        (p.strip() for p in reversed(paragraphs) if p.strip() and MARKER not in p and p.strip() not in (heading, hint)),
        "",
    )
    return {"heading": heading, "hint": hint, "has_marker": has_marker, "name": name_text}


def build(template: Path = TEMPLATE) -> bool:
    document = Document(str(template))
    old_table = next(
        (t for t in document.tables if any("Đại diện Bên" in cell.text.splitlines()[0] for cell in t.rows[0].cells)),
        None,
    )
    if old_table is None:
        return False

    columns = [_extract_column(cell) for cell in old_table.rows[0].cells]

    new_table = document.add_table(rows=3, cols=len(columns))
    new_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    new_table.rows[1].height = SIGNATURE_ROW_HEIGHT
    new_table.rows[1].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY

    for col_index, info in enumerate(columns):
        heading_cell = new_table.cell(0, col_index)
        heading_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_margins(heading_cell)
        _write(heading_cell.paragraphs[0], info["heading"], bold=True)
        hint_p = heading_cell.add_paragraph()
        _write(hint_p, info["hint"], size=8.5, italic=True)

        signature_cell = new_table.cell(1, col_index)
        signature_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _set_cell_margins(signature_cell, top=20, bottom=20)
        if info["has_marker"]:
            _write(signature_cell.paragraphs[0], MARKER, size=9, bold=True)
        # A/C: left blank on purpose -- this row's HEIGHT is what keeps the
        # name row below aligned, not its content.

        name_cell = new_table.cell(2, col_index)
        name_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        # OOXML's w:spacing/before can't go negative, so tightness against
        # the signature row above comes from a small top margin instead of
        # a pulled-up paragraph -- not a true overlap, but close and, unlike
        # a floating/anchored image, never breaks when this table gets
        # hand-edited later (see the module docstring).
        _set_cell_margins(name_cell, top=10, bottom=60)
        _write(name_cell.paragraphs[0], info["name"], size=9.5, bold=True)

    old_table._tbl.addprevious(new_table._tbl)
    old_table._tbl.getparent().remove(old_table._tbl)
    document.save(template)
    return True


if __name__ == "__main__":
    print(f"rebuilt signature table into 3 rows: {build()}")
