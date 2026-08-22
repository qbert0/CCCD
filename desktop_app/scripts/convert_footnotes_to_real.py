"""Replace the footer-based footnotes (move_transfer_footnotes_to_footer.py /
move_prepaid_footnotes_to_footer.py) with REAL OOXML footnotes
(w:footnoteReference + word/footnotes.xml), per direct instruction:
Word places a real footnote's text on whatever page its own reference
mark ends up on, which is what "footer that happens to match the right
page" was manually working around.

This reverses this session's earlier finding that real footnotes broke
under this project's actual render pipeline (see
build_sim_change_template.py's docstring) -- a fresh, deliberate
re-investigation this round (3 separate synthetic repro attempts: one
reference before a page break + two after; several references clustered
near a break; enough footnote TEXT volume to force the footnote area
itself to spill onto a following page) did NOT reproduce that bug under
the current LibreOffice install -- footnote numbering and text stayed
correctly paired across every page split tried. Real footnotes are used
here on that basis. If numbering/content ever looks wrong on a real
multi-page render again, that's the thing to re-check first.

python-docx has no native API for creating a footnotes part, so this
works in 2 passes: (1) normal python-docx edits (replace/insert the
w:footnoteReference elements in the body, remove the old footer note
paragraphs, keep the existing brand-banner image paragraph) saved
normally; (2) a raw zip post-process injecting word/footnotes.xml + the
relationship + content-type override, since a python-docx Document object
has no method for adding an unfamiliar part type. A python-docx
Document(path)->save(path) round trip DOES preserve an existing
footnotes.xml part unchanged (verified directly) -- so pass 2 only ever
needs to run once per template; renderer.py's normal generate-time
load/edit/save needs no changes at all, same as the embedded Great Vibes
font.

Footnote text size is 12pt (direct instruction) -- set via w:sz on both
the footnote paragraph's own run and its footnoteRef numeral. Re-running
after changing FOOTNOTE_SIZE is safe and picks up the new size everywhere
(footnotes.xml is always rewritten from scratch on every run; the
in-body w:footnoteReference anchor marks are re-formatted unconditionally
by _resize_existing_references() even though _build_transfer/_build_prepaid
only ever INSERT a missing one -- resizing and inserting are deliberately
separate steps so a pure size change doesn't need new anchor points).

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/convert_footnotes_to_real.py
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

ROOT = Path(__file__).resolve().parents[2]
TRANSFER_PATH = ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
PREPAID_PATH = ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx"

FOOTNOTE_SIZE = Pt(12)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# The superscript reference numeral (both the in-body anchor mark and the
# footnote's own leading digit) -- deliberately the SAME declared size as
# the note/body text, not shrunk further: w:vertAlign="superscript" is
# not just a baseline shift, LibreOffice already renders it visibly
# smaller on its own (confirmed directly -- stacking an extra explicit
# size reduction on TOP of that compounded into a barely-legible mark,
# nowhere near a normal "x²"-style superscript). Shared by both
# _footnote_reference_run (the in-body anchor, document.xml) and
# _inject_footnotes_part (the footnote's own digit, footnotes.xml) so the
# two always match.
REF_SIZE_HALF_POINTS = int(FOOTNOTE_SIZE.pt * 2)


def _footnote_reference_run(footnote_id: int):
    """Build the IN-BODY anchor mark (<w:footnoteReference/> in
    document.xml -- the small superscript number sitting next to the
    cited text, distinct from the footnote's OWN leading digit at the
    bottom of the page). Verified directly under this project's real
    soffice --headless PDF export: unlike <w:footnoteRef/> (see
    _inject_footnotes_part's comment -- that one ignores direct run
    formatting entirely and needs a named character style instead), THIS
    element type DOES honor direct w:rPr overrides in LibreOffice, so
    explicit i/vertAlign/sz here -- not just the (here, effectively
    decorative) rStyle reference -- is what actually renders it small."""
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    r_style = OxmlElement("w:rStyle")
    r_style.set(qn("w:val"), "FootnoteReference")
    r_pr.append(r_style)
    vert_align = OxmlElement("w:vertAlign")
    vert_align.set(qn("w:val"), "superscript")
    r_pr.append(vert_align)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), str(REF_SIZE_HALF_POINTS))
    r_pr.append(size)
    size_cs = OxmlElement("w:szCs")
    size_cs.set(qn("w:val"), str(REF_SIZE_HALF_POINTS))
    r_pr.append(size_cs)
    run.append(r_pr)
    ref = OxmlElement("w:footnoteReference")
    ref.set(qn("w:id"), str(footnote_id))
    run.append(ref)
    return run


def _replace_run_with_reference(run, footnote_id: int) -> None:
    new_run = _footnote_reference_run(footnote_id)
    run._r.addprevious(new_run)
    run._r.getparent().remove(run._r)


def _insert_reference_after_text(paragraph, anchor_text: str, footnote_id: int) -> None:
    if paragraph._p.findall(".//" + qn("w:footnoteReference")):
        return  # already inserted by an earlier run of this script
    for run in paragraph.runs:
        if anchor_text in run.text:
            new_run = _footnote_reference_run(footnote_id)
            run._r.addnext(new_run)
            return
    raise AssertionError(f"anchor not found: {anchor_text!r} in {paragraph.text!r}")


def _resize_existing_references(document) -> int:
    """Re-apply the current REF_SIZE_HALF_POINTS to every in-body
    <w:footnoteReference/> anchor mark, whether it was just inserted this
    run or already existed from an earlier one -- lets a pure size change
    (edit FOOTNOTE_SIZE, re-run) take effect without needing new anchor
    points, since _insert_reference_after_text only ever inserts once."""
    from desktop_app.backend.documents.renderer import _iter_paragraphs

    count = 0
    for paragraph in _iter_paragraphs(document):
        for run in paragraph.runs:
            if run._r.find(qn("w:footnoteReference")) is None:
                continue
            r_pr = run._r.find(qn("w:rPr"))
            if r_pr is None:
                r_pr = OxmlElement("w:rPr")
                run._r.insert(0, r_pr)
            for tag in ("w:rStyle", "w:vertAlign", "w:sz", "w:szCs"):
                existing = r_pr.find(qn(tag))
                if existing is not None:
                    r_pr.remove(existing)
            style = OxmlElement("w:rStyle")
            style.set(qn("w:val"), "FootnoteReference")
            r_pr.append(style)
            vert_align = OxmlElement("w:vertAlign")
            vert_align.set(qn("w:val"), "superscript")
            r_pr.append(vert_align)
            size = OxmlElement("w:sz")
            size.set(qn("w:val"), str(REF_SIZE_HALF_POINTS))
            r_pr.append(size)
            size_cs = OxmlElement("w:szCs")
            size_cs.set(qn("w:val"), str(REF_SIZE_HALF_POINTS))
            r_pr.append(size_cs)
            count += 1
    return count


def _remove_footer_notes(section) -> None:
    """Strip the border paragraph + note paragraphs added by the earlier
    move_*_footnotes_to_footer.py scripts, keeping the pre-existing
    brand-banner image paragraph exactly as it was."""
    footer = section.footer
    for paragraph in list(footer.paragraphs):
        has_image = paragraph._p.findall(".//" + qn("w:drawing"))
        has_border = paragraph._p.find(".//" + qn("w:pBdr")) is not None
        if has_image:
            continue
        if has_border or any(run.font.italic for run in paragraph.runs if run.font.italic):
            paragraph._p.getparent().remove(paragraph._p)


def _build_transfer(path: Path) -> list[tuple[int, str]]:
    document = Document(str(path))

    for paragraph in document.paragraphs:
        if paragraph.text.startswith("Điều 1: Bên A, Bên B và Bên C đồng ý"):
            # This paragraph has TWO separate "1" text runs -- the "Điều 1"
            # article heading number (plain text, must stay untouched) and
            # the real footnote marker right after "đồng ý" (also just the
            # digit "1", since it happens to be footnote #1). Matching on
            # bare text alone hits the heading's "1" first (document
            # order) -- disambiguate by requiring the immediately
            # preceding run to be "ý", true only for the real marker.
            runs = paragraph.runs
            for index, run in enumerate(runs):
                if (
                    run.text.strip() == "1"
                    and index > 0
                    and runs[index - 1].text.strip() == "ý"
                ):
                    _replace_run_with_reference(run, 1)
                    break

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    text = paragraph.text
                    if text.startswith("Số QĐTL/GCNĐKKD&ĐKĐT/GCNĐKDN"):
                        for run in paragraph.runs:
                            if run.text.strip() == "2":
                                _replace_run_with_reference(run, 2)
                                break
                    elif text.startswith("Số ĐDCN/ĐDĐT/HC"):
                        for run in paragraph.runs:
                            if run.text.strip() == "3":
                                _replace_run_with_reference(run, 3)
                                break

    _remove_footer_notes(document.sections[0])
    _resize_existing_references(document)
    document.save(str(path))

    return [
        (1, "Các nội dung bỏ trống tại Điều 1 do hai bên thỏa thuận điền cụ thể khi kí kết "
            "Biên bản và phù hợp với quy định của pháp luật"),
        (2, "Số Quyết định thành lập/Giấy chứng nhận đăng ký kinh doanh và đăng ký đầu tư/"
            "Giấy chứng nhận đăng ký doanh nghiệp"),
        (3, "Số Định danh cá nhân/Định danh điện tử /Hộ chiếu"),
    ]


def _build_prepaid(path: Path) -> list[tuple[int, str]]:
    document = Document(str(path))

    for paragraph in document.paragraphs:
        if paragraph.text.startswith("Số QĐTL/GCNĐKKD&ĐKĐT/GPĐT/GCNĐKDN:"):
            _insert_reference_after_text(paragraph, "GCNĐKDN: ", 1)
        elif paragraph.text.startswith("Địa chỉ theo CCCD/Căn cước/Hộ chiếu:"):
            _insert_reference_after_text(paragraph, "Hộ chiếu: ", 2)
        elif paragraph.text.startswith("Điều 1: Nội dung Hợp đồng"):
            for run in paragraph.runs:
                if run.text.strip() == "3":
                    _replace_run_with_reference(run, 3)
                    break

    _remove_footer_notes(document.sections[3])
    _remove_footer_notes(document.sections[4])
    _resize_existing_references(document)
    document.save(str(path))

    return [
        (1, "Số Quyết định thành lập/Giấy chứng nhận đăng ký kinh doanh và đăng ký đầu tư/"
            "Giấy phép kinh doanh/Giấy chứng nhận đăng ký doanh nghiệp hoặc giấy tờ chứng "
            "minh pháp nhân khác."),
        (2, "Địa chỉ trên giấy tờ để đăng ký thông tin thuê bao."),
        (3, "Các nội dung bỏ trống tại phần này do hai bên thỏa thuận điền cụ thể khi ký "
            "kết Hợp đồng và phù hợp với quy định của pháp luật."),
    ]


def _inject_footnotes_part(path: Path, footnotes: list[tuple[int, str]]) -> None:
    with zipfile.ZipFile(str(path)) as z:
        names = z.namelist()
        rels_xml = z.read("word/_rels/document.xml.rels").decode("utf-8")
        ct_xml = z.read("[Content_Types].xml").decode("utf-8")
        skip = ("word/_rels/document.xml.rels", "[Content_Types].xml", "word/footnotes.xml")
        others = {n: z.read(n) for n in names if n not in skip}

    size_half_points = int(FOOTNOTE_SIZE.pt * 2)
    ref_size_half_points = REF_SIZE_HALF_POINTS
    parts = [
        f'<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>',
        f'<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>',
    ]
    for footnote_id, text in footnotes:
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        parts.append(
            f'<w:footnote w:id="{footnote_id}"><w:p>'
            f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/><w:i/><w:iCs/>'
            f'<w:vertAlign w:val="superscript"/><w:sz w:val="{ref_size_half_points}"/><w:szCs w:val="{ref_size_half_points}"/></w:rPr><w:footnoteRef/></w:r>'
            f'<w:r><w:rPr><w:i/><w:iCs/><w:sz w:val="{size_half_points}"/><w:szCs w:val="{size_half_points}"/></w:rPr>'
            f'<w:t xml:space="preserve"> {escaped}</w:t></w:r>'
            f"</w:p></w:footnote>"
        )
    footnotes_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:footnotes xmlns:w="{W_NS}">' + "".join(parts) + "</w:footnotes>"
    )

    if 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"' not in rels_xml:
        rels_xml = rels_xml.replace(
            "</Relationships>",
            '<Relationship Id="rIdFootnotesRel" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" '
            'Target="footnotes.xml"/></Relationships>',
        )
    if "/word/footnotes.xml" not in ct_xml:
        ct_xml = ct_xml.replace(
            "</Types>",
            '<Override PartName="/word/footnotes.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>',
        )

    # The <w:footnoteRef/> field's own displayed size/position is NOT
    # controlled by direct w:rPr on the run that wraps it in footnotes.xml
    # -- verified directly: setting w:sz there (even to something absurd
    # like 40pt) had zero visible effect under this project's real
    # soffice --headless PDF export. LibreOffice instead resolves it by
    # looking up a character style named exactly "FootnoteReference" (the
    # same convention real Word documents rely on) -- these templates
    # never defined one, so it must be added here for the superscript/
    # smaller-size look to actually render. The direct rPr overrides
    # above are harmless and kept anyway as a Word-compatibility
    # fallback, since Word (unlike LibreOffice here) does honor them.
    styles_xml = others["word/styles.xml"].decode("utf-8")
    # Always DROP any existing FootnoteReference style and re-add a fresh
    # one matching the current REF_SIZE_HALF_POINTS -- an earlier version
    # of this script only added the style when totally absent, so a later
    # size change (e.g. switching FOOTNOTE_SIZE) silently left a stale
    # sz value baked in from whatever the FIRST run ever used, with no
    # visible sign anything was wrong (the in-body anchor mark, which
    # uses direct rPr overrides instead of this style, updated correctly
    # every time -- only the footnote's OWN leading digit, which can only
    # be sized via this named style, stayed stuck at the old value).
    styles_xml = re.sub(
        r'<w:style [^>]*w:styleId="FootnoteReference"[^>]*>.*?</w:style>',
        "",
        styles_xml,
        flags=re.DOTALL,
    )
    style_def = (
        '<w:style w:type="character" w:styleId="FootnoteReference">'
        '<w:name w:val="footnote reference"/>'
        '<w:basedOn w:val="DefaultParagraphFont"/>'
        f'<w:rPr><w:i/><w:iCs/><w:vertAlign w:val="superscript"/>'
        f'<w:sz w:val="{ref_size_half_points}"/><w:szCs w:val="{ref_size_half_points}"/></w:rPr>'
        "</w:style>"
    )
    styles_xml = styles_xml.replace("</w:styles>", style_def + "</w:styles>")
    others["word/styles.xml"] = styles_xml.encode("utf-8")

    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in others.items():
            z.writestr(name, data)
        z.writestr("word/_rels/document.xml.rels", rels_xml)
        z.writestr("[Content_Types].xml", ct_xml)
        z.writestr("word/footnotes.xml", footnotes_xml)


if __name__ == "__main__":
    for path, builder in [(TRANSFER_PATH, _build_transfer), (PREPAID_PATH, _build_prepaid)]:
        footnotes = builder(path)
        _inject_footnotes_part(path, footnotes)
        print(f"{path.name}: real footnotes 1-{len(footnotes)} added, footer notes removed")
