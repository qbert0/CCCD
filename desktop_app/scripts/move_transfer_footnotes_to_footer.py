"""Move the transfer template's 3 numbered footnotes out of the document
body and into a real per-page footer -- same technique as
build_sim_change_template.py's `_set_footer` (see that module's docstring
for why: real OOXML footnotes are broken under this project's actual
render pipeline). The 3 footnote reference markers (superscript 1/2/3,
already present inline in "Điều 1...", the subscriber table's
"...GCNĐKDN2" and "...HC 3" cells) are untouched -- only the note TEXT,
which used to sit as full-width body paragraphs right after the
subscriber table (wrapping onto 2 lines each, visually overflowing the
page since it was ordinary body text, not footer content) moves.

All 3 markers live within the document's own first section (paragraph 20,
the "3 Số Định danh..." note, already carries that section's own
w:sectPr) -- so this only ever touches sections[0]'s footer. That footer
already has one paragraph holding the brand-banner images (2 w:drawing
elements); the 3 new note paragraphs are inserted directly above it, with
a thin top border above them, matching the sim_change_form footer layout
exactly.

Idempotent is NOT guaranteed -- re-running against an already-moved file
will fail its own assertions (the source paragraphs it looks for are
gone), by design, same as this session's other one-off template scripts.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/move_transfer_footnotes_to_footer.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
BLACK = "000000"

# Original wording, exactly as it stood in the body (just reflowed from
# its 2 wrapped lines back into one string where it wrapped).
FOOTNOTES = [
    (
        1,
        "Các nội dung bỏ trống tại Điều 1 do hai bên thỏa thuận điền cụ thể khi kí kết "
        "Biên bản và phù hợp với quy định của pháp luật",
    ),
    (
        2,
        "Số Quyết định thành lập/Giấy chứng nhận đăng ký kinh doanh và đăng ký đầu tư/"
        "Giấy chứng nhận đăng ký doanh nghiệp",
    ),
    (3, "Số Định danh cá nhân/Định danh điện tử /Hộ chiếu"),
]


def _format_note_run(run, *, italic: bool = False) -> None:
    run.font.size = Pt(7.5)
    run.font.italic = italic


def _new_paragraph_before(anchor: Paragraph) -> Paragraph:
    new_element = OxmlElement("w:p")
    anchor._p.addprevious(new_element)
    return Paragraph(new_element, anchor._parent)


def move_footnotes_to_footer(path: Path) -> None:
    document = Document(str(path))
    body_paragraphs = document.paragraphs

    targets: list[tuple[int, int, Paragraph]] = []
    for index, paragraph in enumerate(body_paragraphs):
        text = paragraph.text.strip()
        if text.startswith("1 Các nội dung bỏ trống"):
            targets.append((1, index, paragraph))
        elif text.startswith("2 Số Quyết định thành lập"):
            targets.append((2, index, paragraph))
        elif text.startswith("3 Số Định danh cá nhân"):
            targets.append((3, index, paragraph))
    assert [marker for marker, _, _ in targets] == [1, 2, 3], (
        f"expected exactly footnotes 1, 2, 3 in that order, found {targets}"
    )
    (_, index_1, p1), (_, index_2, p2), (_, index_3, p3) = targets

    continuation_1 = body_paragraphs[index_1 + 1]
    continuation_2 = body_paragraphs[index_2 + 1]
    assert continuation_1.text == "định của pháp luật", continuation_1.text
    assert continuation_2.text == "doanh nghiệp", continuation_2.text

    for paragraph, continuation in ((p1, continuation_1), (p2, continuation_2)):
        paragraph._p.getparent().remove(paragraph._p)
        continuation._p.getparent().remove(continuation._p)
    # p3 alone carries this section's w:sectPr in its own pPr -- keep the
    # paragraph (and the section break with it), just drop its text.
    for run in list(p3.runs):
        run._r.getparent().remove(run._r)

    section = document.sections[0]
    footer = section.footer
    image_paragraph = footer.paragraphs[0]

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

    for number, text in FOOTNOTES:
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

    document.save(str(path))


if __name__ == "__main__":
    move_footnotes_to_footer(PATH)
    print(f"{PATH.name}: moved 3 footnotes from the body into section 0's footer")
