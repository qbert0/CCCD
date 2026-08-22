"""Move Prepaid Contract's 3 numbered footnotes out of the document body
and into real per-page footers -- same technique as
move_transfer_footnotes_to_footer.py / build_sim_change_template.py's
`_set_footer` (see either module's docstring for why: real OOXML
footnotes are broken under this project's actual render pipeline).

Unlike Transfer (all 3 footnote markers live in one section), this
template's own section break lands BETWEEN footnote 3's definition and
its own inline reference: footnotes 1/2/3 are all originally printed as
body paragraphs at the end of section index 3 (the customer/provider
identity block), but footnote 3's actual superscript "3" marker
("Điều 1: Nội dung Hợp đồng³") sits in section index 4, the next section.
Footnotes 1 and 2 annotate fields that live entirely within section 3
(the "Số QĐTL/.../GCNĐKDN" business-registration line and the "địa chỉ ...
đăng ký thông tin thuê bao" line) -- confirmed by their own wording, since
neither has an explicit inline superscript digit next to a specific line
the way footnote 3 does. So: footnotes 1+2 move to section 3's footer,
footnote 3 moves to section 4's footer -- same page-matching principle
`_set_footer(section, [1, 2])` / `_set_footer(section, [3])` already use
in build_sim_change_template.py.

Idempotent is NOT guaranteed -- re-running against an already-moved file
will fail its own assertions (the source paragraphs it looks for are
gone), by design, same as this session's other one-off template scripts.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/move_prepaid_footnotes_to_footer.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx"
BLACK = "000000"

SECTION_1_AND_2_FOOTNOTES = [
    (
        1,
        "Số Quyết định thành lập/Giấy chứng nhận đăng ký kinh doanh và đăng ký đầu tư/"
        "Giấy phép kinh doanh/Giấy chứng nhận đăng ký doanh nghiệp hoặc giấy tờ chứng "
        "minh pháp nhân khác.",
    ),
    (2, "Địa chỉ trên giấy tờ để đăng ký thông tin thuê bao."),
]
SECTION_3_FOOTNOTES = [
    (
        3,
        "Các nội dung bỏ trống tại phần này do hai bên thỏa thuận điền cụ thể khi ký "
        "kết Hợp đồng và phù hợp với quy định của pháp luật.",
    ),
]


def _format_note_run(run, *, italic: bool = False) -> None:
    run.font.size = Pt(7.5)
    run.font.italic = italic


def _new_paragraph_before(anchor: Paragraph) -> Paragraph:
    new_element = OxmlElement("w:p")
    anchor._p.addprevious(new_element)
    return Paragraph(new_element, anchor._parent)


def _add_footer_notes(section, notes: list[tuple[int, str]]) -> None:
    footer = section.footer
    # Unlinking a section's footer (`is_linked_to_previous = False`) makes
    # python-docx add a brand-new, genuinely BLANK footer part -- it does
    # NOT copy the inherited content. Capture the inherited image run
    # first, or the brand banner every other section's footer has just
    # disappears from this one (hit for real: section 3 here inherited
    # from section 2, unlinking silently dropped its banner image).
    was_linked = footer.is_linked_to_previous
    inherited_image_run = footer.paragraphs[0].runs[0] if was_linked else None
    footer.is_linked_to_previous = False
    image_paragraph = footer.paragraphs[0]
    if was_linked:
        from copy import deepcopy

        image_paragraph._p.append(deepcopy(inherited_image_run._r))

    border_paragraph = _new_paragraph_before(image_paragraph)
    border_paragraph.paragraph_format.space_after = Pt(2)
    borders = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single")
    top.set(qn("w:sz"), "4")
    top.set(qn("w:space"), "1")
    top.set(qn("w:color"), BLACK)
    borders.append(top)
    border_paragraph._p.get_or_add_pPr().append(borders)

    for number, text in notes:
        note_paragraph = _new_paragraph_before(image_paragraph)
        note_paragraph.paragraph_format.space_after = Pt(1)
        note_paragraph.paragraph_format.line_spacing = 1.0
        number_run = note_paragraph.add_run(str(number))
        _format_note_run(number_run)
        vert_align = OxmlElement("w:vertAlign")
        vert_align.set(qn("w:val"), "superscript")
        number_run._r.get_or_add_rPr().append(vert_align)
        text_run = note_paragraph.add_run(f" {text}")
        _format_note_run(text_run, italic=True)


def move_footnotes_to_footer(path: Path) -> None:
    document = Document(str(path))
    body_paragraphs = document.paragraphs

    targets: list[Paragraph] = []
    for paragraph in body_paragraphs:
        text = paragraph.text.strip()
        if (
            text.startswith("1 Số Quyết định thành lập")
            or text.startswith("2 Địa chỉ trên giấy tờ")
            or text.startswith("3Các nội dung bỏ trống")
        ):
            targets.append(paragraph)
    assert len(targets) == 3, f"expected exactly 3 footnote paragraphs, found {len(targets)}"

    for paragraph in targets:
        paragraph._p.getparent().remove(paragraph._p)

    assert len(document.sections) == 5, f"expected 5 sections, found {len(document.sections)}"
    _add_footer_notes(document.sections[3], SECTION_1_AND_2_FOOTNOTES)
    _add_footer_notes(document.sections[4], SECTION_3_FOOTNOTES)

    document.save(str(path))


if __name__ == "__main__":
    move_footnotes_to_footer(PATH)
    print(f"{PATH.name}: moved footnotes 1+2 into section 3's footer, footnote 3 into section 4's")
