from __future__ import annotations

import io
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.dml.color import RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Emu, Mm, Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from PIL import Image

from desktop_app.backend.documents.font_embed import SIGNATURE_FONT_NAME
from desktop_app.backend.domain.models import DocumentType, ReportData


# Keep empty choices as an outlined square, but use a real check mark for the
# selected choice.  The previous ballot-box X looked like an error/cancellation.
EMPTY_BOX = "☐"
CHECKED_BOX = "☑"
PDF_CHECKMARK = "✓"

# The data-value placeholder font baked into each template's own runs by
# scripts/apply_value_font.py -- shared here so a still-blank field
# resolving to plain dots (see _is_blank_field_text below) can be
# detected and switched back to an ordinary font instead of printing the
# blank-line dots themselves in this heavier face.
VALUE_FONT_NAME = "JetBrainsMono NF ExtraBold"


def _date_parts(value: str) -> tuple[str, str, str]:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value or "")
    return match.groups() if match else ("....", "....", "........")


def _hour_only(value: str) -> str:
    """Accept legacy HH:MM state but print only the requested hour."""
    match = re.match(r"^\s*(\d{1,2})", str(value or ""))
    return match.group(1).zfill(2) if match else ""


def _expand_with_textboxes(paragraphs: Iterable[Paragraph]) -> Iterable[Paragraph]:
    """python-docx's Paragraph.text never includes text sitting inside a Word
    text box (<w:txbxContent>, used for floating signature blocks etc.) — it
    only walks direct runs. Yield those nested paragraphs too so placeholder
    substitution and the unresolved-token safety check both reach them."""
    for paragraph in paragraphs:
        yield paragraph
        for txbx_content in paragraph._p.findall(".//" + qn("w:txbxContent")):
            for p_element in txbx_content.findall(qn("w:p")):
                yield Paragraph(p_element, paragraph._parent)


def _iter_paragraphs(document: Document) -> Iterable[Paragraph]:
    yield from _expand_with_textboxes(document.paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _expand_with_textboxes(cell.paragraphs)
                for nested in cell.tables:
                    for nested_row in nested.rows:
                        for nested_cell in nested_row.cells:
                            yield from _expand_with_textboxes(nested_cell.paragraphs)
    for section in document.sections:
        yield from _expand_with_textboxes(section.header.paragraphs)
        yield from _expand_with_textboxes(section.footer.paragraphs)


_PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}")


def _empty_field_placeholder(name: str) -> str:
    """Return a readable dotted blank sized for the field's meaning."""
    lowered = str(name or "").casefold()
    if lowered.endswith(("_day", "_month")):
        length = 4
    elif lowered.endswith("_year"):
        length = 6
    elif any(part in lowered for part in ("address", "headquarters")):
        length = 36
    elif any(part in lowered for part in ("name", "representative", "issue_place")):
        length = 28
    elif any(part in lowered for part in ("email", "other_contact", "authorization")):
        length = 24
    elif any(part in lowered for part in ("id", "phone", "number", "serial", "code")):
        length = 16
    elif any(part in lowered for part in ("date", "birth", "time")):
        length = 12
    else:
        length = 16
    return "." * length


def _document_field_text(name: str, value: object, *, dotted_when_empty: bool = True) -> str:
    text = str(value or "")
    if text.strip():
        return text
    return _empty_field_placeholder(name) if dotted_when_empty else ""


def _is_blank_field_text(text: str) -> bool:
    """True for a still-empty field's placeholder filler, as opposed to a
    genuinely filled-in value -- so a blank field's own filler can be kept
    looking like ordinary body text instead of the bold+bigger emphasis
    scripts/bake_field_highlighting.py bakes into every placeholder run for
    a real, filled-in value. Two different blank conventions exist in this
    file: _empty_field_placeholder's length-based "...." (plain periods)
    and a handful of context values in _docx_context with their own
    hardcoded "…………"-style ellipsis fallback -- both are just filler
    characters, so both strip away to nothing here."""
    return not text.strip(". …")


def _paragraph_is_in_table(paragraph: Paragraph) -> bool:
    return any(ancestor.tag == qn("w:tc") for ancestor in paragraph._p.iterancestors())


def _given_name(full_name: str) -> str:
    """The last space-separated token of a Vietnamese full name -- the
    "tên" (given/call name) a person actually signs with, not the whole
    name. Printed in the Great Vibes script font as the "ký tên" stroke
    that sits above the full "ghi rõ họ tên" line (see SIGNATURE_GIVEN_NAME_SOURCES)."""
    parts = str(full_name or "").split()
    return parts[-1] if parts else ""


def _replace_placeholders(paragraph: Paragraph, context: dict[str, str]) -> None:
    """Replace tokens while retaining the formatting of the run where each starts.

    Word may split a token into several XML runs after a user edits the template.
    Working against the joined visible text makes that harmless without flattening
    the paragraph or changing the formatting of unrelated runs.

    Presentation (bold/size/dotted markers around a filled value) is NOT
    decided here -- it's baked directly into each template's own placeholder
    runs (see scripts/bake_field_highlighting.py) as real, permanent
    template content, so this function mostly just substitutes text and
    keeps whatever formatting was already there. Two narrow exceptions,
    both keyed off the actual resolved value rather than the field name:
    a still-blank field's own dots get de-emphasized back to plain text
    (see _is_blank_field_text) since the baked bold+bigger styling was
    meant for a real value, not its own placeholder; a Great Vibes
    signature run gets title-cased (see SIGNATURE_FONT_NAME below).
    """
    runs = paragraph.runs
    joined = "".join(run.text for run in runs)
    matches = list(_PLACEHOLDER.finditer(joined))
    for match in reversed(matches):
        name = match.group(1)
        if name not in context:
            raise ValueError(f"Placeholder không được hỗ trợ: {{{{ {name} }}}}")

        positions: list[tuple[int, int]] = []
        cursor = 0
        for run in runs:
            positions.append((cursor, cursor + len(run.text)))
            cursor += len(run.text)

        start_run = next(index for index, (_, end) in enumerate(positions) if match.start() < end)
        end_run = next(index for index, (start, end) in enumerate(positions) if start < match.end() <= end)
        start_offset = match.start() - positions[start_run][0]
        end_offset = match.end() - positions[end_run][0]
        prefix = runs[start_run].text[:start_offset]
        suffix = runs[end_run].text[end_offset:]
        replacement = _document_field_text(
            name,
            context[name],
            dotted_when_empty=not _paragraph_is_in_table(paragraph),
        )
        if runs[start_run].font.name == SIGNATURE_FONT_NAME:
            # Every name value in this codebase arrives already uppercased
            # (a fine, deliberate choice for the plain Times New Roman
            # identity blocks it's normally printed in) -- but a cursive
            # script face like Great Vibes is drawn assuming ordinary
            # capital+lowercase flow, and its connecting strokes were never
            # designed for all-caps: run through in full caps, the letters
            # visibly collide and tangle instead of reading as a signature.
            # Only the run actually carrying this font gets title-cased;
            # the exact same value used elsewhere (e.g. a plain-prose
            # mention of the same person) is untouched.
            replacement = replacement.title()
        if _is_blank_field_text(replacement):
            if runs[start_run].font.name == VALUE_FONT_NAME:
                # A still-blank field's own dots printed in the data-value
                # font (scripts/apply_value_font.py) read like JetBrains
                # Mono blank-fill dots -- wrong for a genuinely empty
                # field. Only the run resolving to plain dots gets this;
                # the same field elsewhere with a real value keeps the
                # data-value font untouched.
                runs[start_run].font.name = "Times New Roman"
                runs[start_run].font.size = Pt(10)
                r_pr = runs[start_run]._r.get_or_add_rPr()
                fonts = r_pr.get_or_add_rFonts()
                for key in ("ascii", "hAnsi", "eastAsia", "cs"):
                    fonts.set(qn(f"w:{key}"), "Times New Roman")
            if runs[start_run].font.bold:
                # A still-blank field's own dots landing in an already-baked
                # bold+bigger run (see bake_field_highlighting.py) read as if
                # something WAS filled in -- undo exactly the bump that script
                # applied (+1pt, unbold) so blank dots look like ordinary
                # surrounding text instead of emphasized content.
                size = runs[start_run].font.size
                runs[start_run].font.bold = False
                if size is not None:
                    runs[start_run].font.size = Pt(size.pt - 1)
        if start_run == end_run:
            runs[start_run].text = prefix + replacement + suffix
        else:
            runs[start_run].text = prefix + replacement
            for index in range(start_run + 1, end_run):
                runs[index].text = ""
            runs[end_run].text = suffix


def _set_symbol_font(run: Run, size: Pt = Pt(15)) -> None:
    # The source placeholder may live in a horizontally scaled or tightly
    # spaced run (for example w:w=115% or w:spacing=-2). Copying that rPr
    # made nominally identical 15 pt checkbox glyphs render at visibly
    # different widths. A checkbox is a standalone UI symbol, so start from
    # a clean run-format record instead of inheriting those text tweaks.
    properties = run._r.get_or_add_rPr()
    for child in list(properties):
        properties.remove(child)
    run.bold = False
    run.italic = False
    run.font.name = "DejaVu Sans"
    run.font.size = size
    run.font.color.rgb = RGBColor(0, 0, 0)
    properties = run._r.get_or_add_rPr()
    fonts = properties.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{key}"), "DejaVu Sans")
    complex_size = properties.find(qn("w:szCs"))
    if complex_size is None:
        complex_size = OxmlElement("w:szCs")
        properties.append(complex_size)
    complex_size.set(qn("w:val"), str(int(size.pt * 2)))


def _style_docx_checkbox_symbols(paragraph: Paragraph) -> None:
    """Render checkboxes as monochrome line glyphs, never colored emoji/icons.

    A single U+2611/U+2610 glyph each, same as before -- the "filled/painted
    square" look this used to have wasn't the glyph, it was the font: most
    fonts fall back to a colored emoji-style box+check for U+2611 when they
    don't carry it natively. DejaVu Sans (bundled with LibreOffice, verified
    by rendering a real generated document) draws U+2611 as a hollow outline
    box with a small check mark actually inside it -- exactly the checked
    state's real anatomy, no manual two-run overlay needed.
    """
    for run in list(paragraph.runs):
        if CHECKED_BOX not in run.text and EMPTY_BOX not in run.text:
            continue
        parts = re.split(
            f"({re.escape(CHECKED_BOX)}|{re.escape(EMPTY_BOX)})",
            run.text,
        )
        run.text = parts[0]
        anchor = run._r
        for part in parts[1:]:
            if not part:
                continue
            new_element = deepcopy(run._r)
            new_run = Run(new_element, paragraph)
            new_run.text = part
            anchor.addnext(new_element)
            anchor = new_element
            if part in {CHECKED_BOX, EMPTY_BOX}:
                _set_symbol_font(new_run)


# Every printed signature has 2 lines: "ký tên" (the given name alone, in
# the Great Vibes script font -- the actual signature stroke) above "ghi
# rõ họ tên" (the full name, same font). Real signature images used to
# stand in for the "ký tên" line; now that a script font can do the job,
# each of these source keys (already a full name, already computed above)
# gets a "_given_name" companion holding just the last word.
SIGNATURE_GIVEN_NAME_SOURCES = (
    ("customer_signature_name", "customer_signature_given_name"),
    ("customer_representative_signature_name", "customer_representative_signature_given_name"),
    ("new_owner_signature_name", "new_owner_signature_given_name"),
    ("aftersale_requester_signature_name", "aftersale_requester_signature_given_name"),
    ("aftersale_new_owner_signature_name", "aftersale_new_owner_signature_given_name"),
    ("aftersale_clerk_signature_name", "aftersale_clerk_signature_given_name"),
    ("prepaid_party_a_signature_name", "prepaid_party_a_signature_given_name"),
    # NOT "provider_representative" itself -- that key is ALSO printed
    # as a plain info mention in prepaid_contract ("Người đại diện: {{
    # provider_representative }}  Chức vụ: ..."), and a signature-block
    # key must never be shared with a plain-info one (see
    # provider_representative_signature below: same value, own key, so
    # the image/blanking logic in _apply_signature_images can never
    # reach the info mention no matter how paragraph shapes shift).
    ("provider_representative_signature", "provider_representative_signature_given_name"),
)

# Signature slots that can OPTIONALLY be a real image instead of the
# script-font text lines above -- (given_name key, full_name key, the
# ReportData attribute holding the image path). Per direct instruction,
# the image replaces BOTH the "ký tên" (given-name) line and the "họ tên"
# (full name) line entirely -- no text remains under the image. (An
# intermediate design kept the full-name line as ordinary script-font
# text below the image; reversed back to this simpler look per direct
# instruction.) A floating image OVERLAYING the text was also considered
# and rejected: this exact codebase already tried floating/anchored
# images for signatures once before (round 11, the "đè lên" request) and
# reverted away from them for fragility; replacing the runs outright
# avoids that class of problem.
SIGNATURE_IMAGE_SLOTS = (
    (
        "provider_representative_signature_given_name", "provider_representative_signature",
        "provider_signature_path",
    ),
    (
        "aftersale_clerk_signature_given_name", "aftersale_clerk_signature_name",
        "operator_signature_path",
    ),
    (
        "sim_operator_signature_given_name", "sim_operator_signature_name",
        "operator_signature_path",
    ),
    # The old owner's own org representative -- genuinely per-case (a
    # different real organization/signer every time), so unlike the 3
    # above this is never pre-configured in Settings; it's attached fresh
    # per case (see choose_customer_representative_signature) and lives
    # on customer itself, not a flat ReportData attribute.
    (
        "customer_representative_signature_given_name", "customer_representative_signature_name",
        "customer.signature_path",
    ),
    # Aftersale's "Người yêu cầu" -- same role and same per-case image
    # source as customer_representative_signature_name above (an org's
    # own representative, or the individual customer themselves), just
    # under aftersale's own field names.
    (
        "aftersale_requester_signature_given_name", "aftersale_requester_signature_name",
        "customer.signature_path",
    ),
)
SIGNATURE_IMAGE_HEIGHT = Mm(32)  # doubled from the original Mm(16) per direct instruction; the x1.5 bump to 48 was reverted as too large

# The fixed crop rectangle the signature-upload UI now crops every image
# into before it ever reaches this module (see web_bridge's
# save_cropped_signature) -- 58mm fits every real signature slot's own
# <w:tcW> across all 5 templates with room to spare, the tightest being
# aftersale's 3-signatures-in-one-row layout (61.7mm/cell, 58mm leaves
# 3.7mm) -- confirmed against real measured cell widths, not guessed.
# Deliberately its own constant rather than reusing SIGNATURE_IMAGE_HEIGHT
# (32mm) for the height: that constant is the *other* session's own
# visually-tuned value for the aspect-preserving fallback fit just below
# (used only for a signature file that predates this crop step), a
# different purpose that shouldn't silently move just because this one
# changed. zero_signature_cell_margins.py (desktop_app/scripts/) strips
# each of these cells' own tcMar to 0 on all sides -- matched here so the
# UI's crop-tool math sees exactly what the template will actually give
# the image, no invisible cell padding eating into the fit.
SIGNATURE_FORM_WIDTH = Mm(58)
SIGNATURE_FORM_HEIGHT = Mm(36)

# "Người đại diện" (representative_profile) has no dedicated ký-tên/họ-tên
# signature block anywhere in prepaid_contract -- its name only appears
# inline, sharing a paragraph with static label text ("Người đại
# diện/ủy quyền: {{ prepaid_representative_name }}  Chức vụ: ...", same
# for "Họ tên nhân viên giao dịch: {{ staff_name }}"). Confirmed directly
# against the template: no image belongs on either -- they are plain
# informational fields, not a place anyone actually signs.


def _resolve_path_attr(data: ReportData, dotted_attr: str) -> str:
    value: object = data
    for part in dotted_attr.split("."):
        value = getattr(value, part, "")
    return str(value or "")


def _signature_image_size(image_path: str) -> tuple[Emu, Emu]:
    """Fit `image_path` inside the (SIGNATURE_FORM_WIDTH, SIGNATURE_FORM_HEIGHT)
    box, preserving its own aspect ratio. Every signature uploaded through
    the crop tool (SignatureCropModal, js/components.js) already IS that
    exact box, so this resolves to that same size unchanged for the common
    case -- it only actually reshapes anything for a file that predates
    the crop tool (an old upload still sitting in Settings, not yet
    replaced). 58x36mm already fits every real signature slot's own cell
    with room to spare (see SIGNATURE_FORM_WIDTH's own note), so unlike
    before this no longer needs to measure the containing table cell at
    all -- one fixed target box for every slot, everywhere."""
    with Image.open(image_path) as image:
        source_width, source_height = image.size
    if source_width <= 0 or source_height <= 0:
        return SIGNATURE_FORM_WIDTH, SIGNATURE_FORM_HEIGHT

    aspect_ratio = source_width / source_height
    max_width, max_height = int(SIGNATURE_FORM_WIDTH), int(SIGNATURE_FORM_HEIGHT)
    width, height = max_width, int(max_width / aspect_ratio)
    if height > max_height:
        height = max_height
        width = int(max_height * aspect_ratio)
    return Emu(width), Emu(height)


def _insert_signature_image(paragraph: Paragraph, image_path: str) -> None:
    for run in list(paragraph.runs):
        run.text = ""
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    width, height = _signature_image_size(image_path)
    run.add_picture(image_path, width=width, height=height)


def _clear_paragraph_text(paragraph: Paragraph) -> None:
    for run in list(paragraph.runs):
        run.text = ""


def _apply_signature_images(paragraphs: list[Paragraph], data: ReportData) -> None:
    """Runs BEFORE the general placeholder substitution loop, while these
    paragraphs/runs still hold their raw {{ }} tokens -- an image, when
    set, replaces the given-name ("ký tên") line AND blanks out the
    full-name ("họ tên") line right below it, so the image alone stands in
    for the whole signature block."""
    for given_key, full_key, path_attr in SIGNATURE_IMAGE_SLOTS:
        image_path = _resolve_path_attr(data, path_attr)
        if not image_path or not os.path.isfile(image_path):
            continue
        for paragraph in paragraphs:
            match = _PLACEHOLDER.fullmatch(paragraph.text.strip())
            if match is None:
                continue
            if match.group(1) == given_key:
                _insert_signature_image(paragraph, image_path)
            elif match.group(1) == full_key:
                _clear_paragraph_text(paragraph)

    # prepaid_contract's Bên A signs as new_owner in structured mode
    # (org -> individual takeover) or as customer itself in legacy mode --
    # same split _docx_context uses to compute prepaid_party_a_signature_name's
    # own text, so the image has to follow the same person.
    prepaid_structured = (
        data.document_type == DocumentType.PREPAID_CONTRACT
        and data.prepaid_structured_parties
    )
    prepaid_party_a = data.new_owner if prepaid_structured else data.customer
    image_path = prepaid_party_a.signature_path
    if image_path and os.path.isfile(image_path):
        for paragraph in paragraphs:
            match = _PLACEHOLDER.fullmatch(paragraph.text.strip())
            if match is None:
                continue
            if match.group(1) == "prepaid_party_a_signature_given_name":
                _insert_signature_image(paragraph, image_path)
            elif match.group(1) == "prepaid_party_a_signature_name":
                _clear_paragraph_text(paragraph)


def _docx_context(data: ReportData) -> dict[str, str]:
    customer, new_owner = data.customer, data.new_owner
    prepaid_structured = (
        data.document_type == DocumentType.PREPAID_CONTRACT
        and data.prepaid_structured_parties
    )
    prepaid_representative = data.representative if prepaid_structured else customer
    prepaid_individual = new_owner if prepaid_structured else customer
    is_organization = customer.entity_type == "Tổ chức"
    day, month, year = _date_parts(data.document_date)
    sim_request_day, sim_request_month, sim_request_year = _date_parts(data.document_date)
    def authorization(person) -> str:
        return " - ".join(value for value in (person.authorization_number, person.authorization_date) if value)

    def organization(value: str) -> str:
        return value if prepaid_structured or is_organization else ""

    def individual(value: str) -> str:
        return value if prepaid_structured or not is_organization else ""

    def party_organization(person, value: str) -> str:
        return value if person.entity_type == "Tổ chức" else ""

    def dotted(value: str, length: int = 20) -> str:
        text = str(value or "").strip()
        return text if text else "." * length

    def action_value(action: str, value: str, length: int = 20) -> str:
        return dotted(value, length) if data.service_action == action else "." * length

    def choice_mark(selected: bool) -> str:
        return CHECKED_BOX if selected else EMPTY_BOX

    # Up to 3 ordered organization contact numbers, joined into the single
    # "Điện thoại: ..." slot every template already has -- shop_phone_2/3
    # simply don't add anything to the line when left blank.
    organization_phones = " - ".join(
        value for value in (data.shop_phone, data.shop_phone_2, data.shop_phone_3) if value
    )
    # The mẫu (ServiceTemplate) workflow's canonical subscriber list, joined
    # into one string -- Transfer and Aftersale each only ever had room for
    # ONE number's worth of prose per blank, so "gộp chung khi có thể" for
    # them means joining every number into that same blank (same idea as
    # organization_phones above), not inserting a table (Aftersale has none)
    # or cloning prose paragraphs. Falls back to the legacy scalar field
    # when the list is empty, so old saved cases/tests render identically.
    subscriber_numbers_joined = (
        ", ".join(
            str(row.get("subscriber_number", "")).strip()
            for row in data.subscribers
            if str(row.get("subscriber_number", "")).strip()
        )
        or data.subscriber_number
    )

    effective_day, effective_month, effective_year = _date_parts(data.transfer_effective_date)
    contract_day, contract_month, contract_year = _date_parts(data.source_contract_date)
    form_day, form_month, form_year = _date_parts(data.registration_form_date)
    aftersale_day, aftersale_month, aftersale_year = _date_parts(data.document_date)
    transfer_basis = []
    if data.source_contract_number:
        transfer_basis.append(
            "Căn cứ hợp đồng cung cấp và sử dụng dịch vụ thông tin di động mặt đất "
            f"Vietnamobile (hình thức thanh toán {dotted(data.payment_method, 12)}) số: "
            f"{data.source_contract_number}, ngày {contract_day} tháng {contract_month} năm {contract_year}"
        )
    if data.registration_form_date:
        transfer_basis.append(
            "Phiếu đăng ký dịch vụ và bản xác nhận thông tin thuê bao Vietnamobile trả trước "
            f"ngày {form_day} tháng {form_month} năm {form_year}"
        )

    context = {
        "document_date_line": f"Ngày {day} tháng {month} năm {year}",
        # Aftersale keeps every legal sentence in the DOCX.  These values only
        # fill individual blanks; missing values deliberately become dotted lines.
        "aftersale_day": dotted(aftersale_day, 4),
        "aftersale_month": dotted(aftersale_month, 4),
        "aftersale_year": dotted(aftersale_year, 6),
        "aftersale_shop_address": dotted(data.shop_address, 42),
        "aftersale_shop_phone": dotted(
            " - ".join(value for value in (data.shop_phone, data.shop_phone_2) if value), 24
        ),
        # This is the form's "Khách hàng / Người yêu cầu" identity, not an
        # unconditional shop identity. Organization services naturally use
        # the saved company profile; individual transfers and SIM
        # replacement use the scanned current owner.
        "aftersale_customer_name": dotted(customer.display_name().upper(), 46),
        "aftersale_customer_id_number": dotted(
            customer.business_registration_number if is_organization else customer.id_number, 18
        ),
        "aftersale_customer_issue_date": dotted(
            customer.business_registration_issue_date if is_organization else customer.issue_date, 14
        ),
        "aftersale_customer_issue_place": dotted(
            customer.business_registration_issue_place if is_organization else customer.issue_place, 26
        ),
        "aftersale_customer_address": dotted(
            customer.headquarters_address if is_organization else customer.address, 48
        ),
        "aftersale_customer_phone": dotted(
            " - ".join(value for value in (customer.phone, customer.phone_2) if value), 24
        ),
        "aftersale_representative_name": dotted(data.provider_representative, 30),
        # The 3 aftersale signature-table names. "Người yêu cầu" is
        # deliberately NOT always the customer: when the old owner is an
        # organization (customer.entity_type == "Tổ chức"), an org can't
        # physically sign, so its own representative_name signs on its
        # behalf; when the old owner is an individual, they sign for
        # themselves. "Chủ thuê bao mới" is always the new owner, in both
        # cases -- confirmed directly by the shop's own usage.
        "aftersale_requester_signature_name": (
            customer.representative_name if is_organization else customer.display_name()
        ).upper(),
        "aftersale_new_owner_signature_name": new_owner.display_name().upper(),
        "aftersale_clerk_signature_name": data.staff_name.upper(),
        "id_attachment_mark": choice_mark(data.has_id_attachment),
        "sim_attachment_mark": choice_mark(data.has_original_sim),
        "other_attachment_mark": choice_mark(bool(data.other_attachment.strip())),
        "other_attachment_value": dotted(data.other_attachment, 48),
        "update_information_mark": choice_mark(data.service_action == "Cập nhật thông tin"),
        "update_subscriber_number": action_value(
            "Cập nhật thông tin", subscriber_numbers_joined, 30
        ),
        "replace_sim_mark": choice_mark(data.service_action == "Thay SIM"),
        "replace_sim_subscriber_number": action_value("Thay SIM", subscriber_numbers_joined, 30),
        "transfer_mark": choice_mark(data.service_action == "Chuyển chủ quyền"),
        "transfer_subscriber_number": action_value(
            "Chuyển chủ quyền", subscriber_numbers_joined, 22
        ),
        "transfer_new_owner_name": action_value(
            "Chuyển chủ quyền", new_owner.display_name().upper(), 28
        ),
        "transfer_new_owner_id_number": action_value(
            "Chuyển chủ quyền", new_owner.id_number, 20
        ),
        "transfer_new_owner_issue_date": action_value(
            "Chuyển chủ quyền", new_owner.issue_date, 14
        ),
        "transfer_new_owner_issue_place": action_value(
            "Chuyển chủ quyền", new_owner.issue_place, 24
        ),
        "requester_role_mark": choice_mark(data.service_action != "Chuyển chủ quyền"),
        "new_owner_role_mark": choice_mark(data.service_action == "Chuyển chủ quyền"),
        "common_subscriber_number": dotted(subscriber_numbers_joined, 24),
        "backup_phone_1_line": dotted(data.backup_phone_1 or customer.phone, 20),
        "backup_phone_2_line": dotted(data.shop_phone_2, 20),
        "aftersale_staff_name": dotted(data.staff_name, 24),
        "document_day": f" {day}",
        "document_month": month,
        "document_year": year,
        "beautiful_number_day": day,
        "beautiful_number_month": month,
        "beautiful_number_year": year,
        "beautiful_number_customer_name": customer.display_name().title(),
        "beautiful_number_customer_id": customer.id_number,
        "payment_method": data.payment_method,
        "source_contract_number": data.source_contract_number or "…………",
        "source_contract_day": contract_day,
        "source_contract_month": contract_month,
        "source_contract_year": f"{contract_year} ",
        "registration_form_day": f" {form_day}",
        "registration_form_month": form_month,
        "registration_form_year": form_year,
        "transfer_time": f"{_hour_only(data.transfer_time) or '……'} ",
        "transfer_effective_day": effective_day,
        "transfer_effective_month": effective_month,
        "transfer_effective_year": effective_year,
        "shop_name": data.shop_name,
        "shop_address": data.provider_unit_address if prepaid_structured else data.shop_address,
        "shop_phone": data.service_point_phone if prepaid_structured else organization_phones,
        "customer_signature_name": customer.display_name().upper(),
        "customer_representative_signature_name": (
            customer.full_name or customer.representative_name
        ).upper(),
        "new_owner_signature_name": new_owner.display_name().upper(),
        "customer_name": customer.display_name().upper(),
        "customer_headquarters": party_organization(customer, customer.headquarters_address),
        "customer_business_number": party_organization(customer, customer.business_registration_number),
        "customer_representative": party_organization(
            customer, (customer.full_name or customer.representative_name).upper()
        ),
        "customer_authorization": party_organization(customer, authorization(customer)),
        "customer_id_number": customer.id_number,
        "customer_issue_date": customer.issue_date,
        "customer_issue_place": customer.issue_place,
        "customer_birth_date": customer.date_of_birth,
        "customer_address": customer.address,
        "customer_nationality": customer.nationality,
        "customer_phone": customer.phone,
        "new_owner_name": new_owner.display_name().upper(),
        "new_owner_headquarters": party_organization(new_owner, new_owner.headquarters_address),
        "new_owner_business_number": party_organization(new_owner, new_owner.business_registration_number),
        "new_owner_representative": party_organization(
            new_owner, (new_owner.representative_name or new_owner.full_name).upper()
        ),
        "new_owner_authorization": party_organization(new_owner, authorization(new_owner)),
        "new_owner_id_number": new_owner.id_number,
        "new_owner_issue_date": new_owner.issue_date,
        "new_owner_issue_place": new_owner.issue_place,
        "new_owner_birth_date": new_owner.date_of_birth,
        "new_owner_address": new_owner.address,
        "new_owner_nationality": new_owner.nationality,
        "subscriber_number": subscriber_numbers_joined,
        "transfer_contract_basis": (
            "- " + ("; ".join(transfer_basis) if transfer_basis else "." * 48)
            + " (sau đây gọi chung là “Hợp đồng”)."
        ),
        "transfer_document_intro": (
            f"Hôm nay, ngày {day} tháng {month} năm {year}, các bên thỏa thuận ký kết biên bản "
            "chuyển quyền sử dụng dịch vụ thông tin di động mặt đất và thanh lý hợp đồng (“Biên bản”) như sau:"
        ),
        "transfer_agreement_intro": (
            f"Bên A, Bên B và bên thứ ba (“Bên C”) đồng ý Bên A sẽ chuyển quyền sử dụng số thuê bao "
            f"{dotted(data.subscriber_number, 16)} cho Bên C theo các thông tin như sau:"
        ),
        "transfer_effective_sentence": (
            "Thời điểm thanh lý Hợp đồng và chuyển quyền sử dụng số thuê bao nói trên sẽ từ "
            f"{_hour_only(data.transfer_time) or '……'} giờ, ngày {effective_day} tháng {effective_month} "
            f"năm {effective_year} (“Thời điểm Chuyển quyền”)."
        ),
        "contract_number": data.contract_number,
        "subscriber_code": data.subscriber_code or data.subscriber_number,
        "sim_serial": data.sim_serial,
        "activation_date": data.activation_date,
        "service_point_name": data.service_point_name,
        "provider_representative": data.provider_representative,
        # Same value as above, own key -- reserved for the Great Vibes
        # signature-block cell specifically (see SIGNATURE_IMAGE_SLOTS),
        # kept separate from the plain-info "provider_representative"
        # mention above so an image can never land on the wrong one.
        "provider_representative_signature": data.provider_representative,
        "provider_position": data.provider_position,
        "provider_phone": data.provider_phone,
        "provider_email": data.provider_email,
        "registration_time": data.registration_time,
        "staff_name": data.staff_name.upper(),
        "sim_customer_name": customer.display_name().upper(),
        "sim_customer_birth_date": customer.date_of_birth,
        "sim_customer_gender": customer.gender,
        "sim_customer_nationality": customer.nationality,
        "sim_customer_id_number": customer.id_number,
        "sim_customer_issue_date": customer.issue_date,
        "sim_customer_issue_place": customer.issue_place,
        "sim_customer_address": customer.address,
        # Unlike the other customer fields on this row, this is the shop's
        # OWN contact number (data.shop_phone, already auto-defaulted for
        # every mẫu from the saved company profile) -- not something the
        # clerk types in per case. Giới tính/Email have no UI input at all
        # and are left to render as their template's own blank line.
        "sim_customer_phone": data.shop_phone,
        "sim_customer_email": customer.email,
        "sim_subscriber_number": subscriber_numbers_joined,
        # For SIM replacement the shared subscriber editor's serial is the
        # NEW card serial. This keeps that editor identical for all services.
        "sim_new_serial": data.sim_serial,
        "sim_current_serial": data.sim_current_serial,
        "sim_reason_lost_mark": choice_mark(data.sim_replacement_reason == "Mất SIM"),
        "sim_reason_damaged_mark": choice_mark(data.sim_replacement_reason == "Hỏng SIM"),
        "sim_reason_other_mark": choice_mark(data.sim_replacement_reason == "Lý do khác"),
        "sim_reason_other_value": data.sim_replacement_other_reason,
        "sim_request_day": sim_request_day,
        "sim_request_month": sim_request_month,
        "sim_request_year": sim_request_year,
        "sim_request_date_line": (
            f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}"
        ),
        "sim_document_date_line": (
            f"ngày {sim_request_day} tháng {sim_request_month} năm {sim_request_year}"
        ),
        "frequent_phone_1": data.frequent_phone_1,
        "frequent_phone_2": data.frequent_phone_2,
        "frequent_phone_3": data.frequent_phone_3,
        "frequent_phone_4": data.frequent_phone_4,
        "frequent_phone_5": data.frequent_phone_5,
        "recent_topup_value": data.recent_topup_value,
        "recent_topup_method": data.recent_topup_method,
        "remaining_validity": data.remaining_validity,
        "account_balance": data.account_balance,
        "last_changed_service": data.last_changed_service,
        "prepaid_organization_name": organization(customer.organization_name.upper()),
        "prepaid_headquarters_address": organization(customer.headquarters_address),
        "prepaid_business_number": organization(customer.business_registration_number),
        "prepaid_business_issue_place": organization(customer.business_registration_issue_place),
        "prepaid_business_issue_date": organization(customer.business_registration_issue_date),
        "prepaid_representative_name": organization(
            prepaid_representative.full_name or customer.representative_name
        ),
        "prepaid_representative_position": organization(prepaid_representative.representative_position),
        "prepaid_authorization": organization(authorization(prepaid_representative)),
        "prepaid_organization_id_number": organization(prepaid_representative.id_number),
        "prepaid_organization_issue_place": organization(prepaid_representative.issue_place),
        "prepaid_organization_issue_date": organization(prepaid_representative.issue_date),
        "prepaid_organization_birth_date": organization(prepaid_representative.date_of_birth),
        "prepaid_organization_phone": organization(prepaid_representative.phone),
        "prepaid_organization_email": organization(prepaid_representative.email),
        "prepaid_organization_other_contact": organization(prepaid_representative.other_contact),
        "prepaid_individual_name": individual(prepaid_individual.full_name.upper()),
        "prepaid_individual_id_number": individual(prepaid_individual.id_number),
        "prepaid_individual_issue_place": individual(prepaid_individual.issue_place),
        "prepaid_individual_issue_date": individual(prepaid_individual.issue_date),
        "prepaid_individual_birth_date": individual(prepaid_individual.date_of_birth),
        "prepaid_individual_address": individual(prepaid_individual.address),
        "prepaid_individual_phone": individual(prepaid_individual.phone),
        "prepaid_individual_email": individual(prepaid_individual.email),
        "prepaid_individual_other_contact": individual(prepaid_individual.other_contact),
        "prepaid_individual_nationality": individual(
            (
                f"{CHECKED_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
                if prepaid_individual.nationality.casefold() == "việt nam"
                else (
                    f"{EMPTY_BOX} Việt Nam    {CHECKED_BOX} Nước ngoài: "
                    f"{prepaid_individual.foreign_country or prepaid_individual.nationality}"
                )
            )
            if prepaid_individual.nationality.strip()
            else ""
        ),
        # Bên A's signature is the person actually taking over the
        # subscription: the new owner in the structured (org->individual
        # transfer) mode, or the customer signing for themselves in legacy
        # mode (their own representative when they're an organization) --
        # same org-vs-individual split as aftersale_requester_signature_name.
        # Bên B stays provider_representative (Vietnamobile's own fixed
        # signer); the two used to share one token, printing identically.
        "prepaid_party_a_signature_name": (
            new_owner.display_name() if prepaid_structured
            else (customer.representative_name if is_organization else customer.display_name())
        ).upper(),
        # sim_change_form has no separate "ghi rõ họ tên" line for its
        # operator/giao dịch viên yet (it used to just insert a signature
        # image there) -- give it the same 2-line shape as every other
        # signature in the app.
        "sim_operator_signature_name": data.staff_name.upper(),
    }
    for source_key, given_key in SIGNATURE_GIVEN_NAME_SOURCES:
        context[given_key] = _given_name(context[source_key])
    context["sim_operator_signature_given_name"] = _given_name(context["sim_operator_signature_name"])
    return context


def _prepaid_rows(data: ReportData) -> list[dict[str, str]]:
    if data.prepaid_structured_parties and data.prepaid_subscribers:
        return [
            {
                "subscriber_number": str(row.get("subscriber_number", "") or ""),
                "sim_serial": str(row.get("sim_serial", "") or ""),
                "activation_date": str(row.get("activation_date", "") or ""),
            }
            for row in data.prepaid_subscribers[:5]
        ]
    return [{
        "subscriber_number": data.subscriber_number,
        "sim_serial": data.sim_serial,
        "activation_date": data.activation_date,
    }]


def _set_cell_text_preserving_style(cell, value: str, field_name: str = "") -> None:
    # Bold/bigger for these cells (when wanted) is baked into the TEMPLATE
    # row that gets cloned per subscriber entry -- see
    # scripts/bake_field_highlighting.py -- since this just overwrites
    # `.text` and leaves each run's existing formatting alone, a cloned
    # row's own baked-in styling carries through automatically.
    paragraph = cell.paragraphs[0]
    text = (
        _document_field_text(field_name, value, dotted_when_empty=False)
        if field_name else str(value or "")
    )
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _fill_prepaid_sim_table(document: Document, data: ReportData) -> None:
    rows = _prepaid_rows(data)
    for table in document.tables:
        if not table.rows:
            continue
        header = " | ".join(cell.text for cell in table.rows[0].cells)
        if "Số thuê bao" not in header or "Số sê-ri SIM" not in header:
            continue
        for index, table_row in enumerate(table.rows[1:6]):
            values = rows[index] if index < len(rows) else {}
            for cell, name in zip(
                table_row.cells,
                ("subscriber_number", "sim_serial", "activation_date"),
            ):
                _set_cell_text_preserving_style(cell, values.get(name, ""), name)
        break


def _beautiful_number_months(value: str) -> str:
    amount = re.sub(r"\s*tháng\s*$", "", str(value or "").strip(), flags=re.IGNORECASE)
    return f"{amount} tháng" if amount else ""


def _beautiful_number_fee(value: str) -> str:
    """Format the editor's thousand-VND unit as a full VND amount.

    New UI values contain digits only: ``500`` means 500 thousand VND and
    prints as ``500.000đ``. Older saved drafts may already contain a full
    amount such as ``500.000 đồng``; recognize that representation instead
    of multiplying it by another thousand.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        amount = int(text) * 1000
    else:
        legacy = re.sub(r"\s*(?:đồng|đ)\s*$", "", text, flags=re.IGNORECASE)
        if not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", legacy):
            return text
        amount = int(re.sub(r"[.,]", "", legacy))
    return f"{amount:,}".replace(",", ".") + "đ"


def _beautiful_number_rows(data: ReportData) -> list[dict[str, str]]:
    """Flatten either data source into a plain row list, newest/richest
    first: the unlimited web editor (data.beautiful_subscribers) if it has
    real content, else the legacy fixed row-1/row-2 fields (old saved
    cases, or the dead QWidget path)."""
    if data.beautiful_subscribers:
        rows = [
            {
                "subscriber_number": str(row.get("subscriber_number", "") or ""),
                "commitment_months": _beautiful_number_months(str(row.get("commitment_months", "") or "")),
                "monthly_fee": _beautiful_number_fee(str(row.get("monthly_fee", "") or "")),
                "commitment_note": str(row.get("commitment_note", "") or ""),
            }
            for row in data.beautiful_subscribers
        ]
        rows = [row for row in rows if any(row.values())]
        if rows:
            return rows
    rows = [
        {
            "subscriber_number": data.subscriber_number_1 or data.subscriber_number,
            "commitment_months": _beautiful_number_months(data.commitment_months),
            "monthly_fee": _beautiful_number_fee(data.monthly_fee),
            "commitment_note": data.commitment_note,
        }
    ]
    if data.subscriber_number_2 or data.commitment_months_2 or data.monthly_fee_2 or data.commitment_note_2:
        rows.append(
            {
                "subscriber_number": data.subscriber_number_2,
                "commitment_months": _beautiful_number_months(data.commitment_months_2),
                "monthly_fee": _beautiful_number_fee(data.monthly_fee_2),
                "commitment_note": data.commitment_note_2,
            }
        )
    return rows


def _fill_beautiful_number_table(document: Document, data: ReportData) -> None:
    """Clone the template's single data row for every subscriber entry.

    Unlike the old PDF template (a flat scan with zero room for a 2nd row,
    forcing an ugly "row1 / row2" joined-cell workaround), this is a real
    docx table -- cloning a real <w:tr> and letting the page reflow is not
    just possible but the whole reason this document moved to docx.
    """
    rows = _beautiful_number_rows(data)
    for table in document.tables:
        if len(table.rows) < 2:
            continue
        header = " | ".join(cell.text for cell in table.rows[0].cells)
        if "Thời gian cam kết" not in header or "Cước cam kết tối thiểu" not in header:
            continue
        template_row = table.rows[1]
        for index, values in enumerate(rows):
            if index == 0:
                target_row = template_row
            else:
                new_tr = deepcopy(template_row._tr)
                table._tbl.append(new_tr)
                target_row = table.rows[-1]
            cells = target_row.cells
            _set_cell_text_preserving_style(cells[0], str(index + 1))
            for cell, name in zip(
                cells[1:], ("subscriber_number", "commitment_months", "monthly_fee", "commitment_note")
            ):
                _set_cell_text_preserving_style(cell, values.get(name, ""), name)
        break


def _fill_transfer_subscriber_table(document: Document, data: ReportData) -> None:
    """Clone the party table's "Số thuê bao" row for every subscriber entry.

    Transfer's table is oriented attribute-per-row / party-per-column
    (Bên A | Bên C), not one-row-per-subscriber like Beautiful Number's --
    only its LAST row happens to hold a subscriber number, in both party
    columns (the same number changing hands from Bên A to Bên C). Anchored
    on that row's own first-cell text ("Số thuê bao"), not the table
    header, since the header doesn't name columns per-subscriber the way
    Beautiful Number's/Prepaid's do.
    """
    numbers = [
        str(row.get("subscriber_number", "")).strip()
        for row in data.subscribers
        if str(row.get("subscriber_number", "")).strip()
    ] or [data.subscriber_number]
    for table in document.tables:
        subscriber_row_index = next(
            (i for i, row in enumerate(table.rows) if row.cells[0].text.strip() == "Số thuê bao"),
            None,
        )
        if subscriber_row_index is None:
            continue
        template_row = table.rows[subscriber_row_index]
        for index, number in enumerate(numbers):
            if index == 0:
                target_row = template_row
            else:
                new_tr = deepcopy(template_row._tr)
                table._tbl.append(new_tr)
                target_row = table.rows[-1]
            label = "Số thuê bao" if len(numbers) == 1 else f"Số thuê bao {index + 1}"
            _set_cell_text_preserving_style(target_row.cells[0], label)
            _set_cell_text_preserving_style(target_row.cells[1], number, "subscriber_number")
            _set_cell_text_preserving_style(target_row.cells[2], number, "subscriber_number")
        break


def _replace_service_point_address(document: Document, data: ReportData) -> None:
    if not data.prepaid_structured_parties:
        return
    for paragraph in _iter_paragraphs(document):
        if "Địa chỉ điểm giao dịch:" not in paragraph.text:
            continue
        prefix = paragraph.text.split("Địa chỉ điểm giao dịch:", 1)[0] + "Địa chỉ điểm giao dịch:"
        address = _document_field_text("service_point_address", data.service_point_address)
        if paragraph.runs:
            paragraph.runs[0].text = prefix + address
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(prefix + address)
        break


def _generate_docx(
    data: ReportData,
    template: Path,
    output: Path,
    expected_placeholders: frozenset[str],
    *,
    allow_missing_placeholders: bool = False,
) -> None:
    document = Document(str(template))
    template_paragraphs = list(_iter_paragraphs(document))
    actual_placeholders = {
        match.group(1)
        for paragraph in template_paragraphs
        for match in _PLACEHOLDER.finditer(paragraph.text)
    }
    if expected_placeholders:
        missing = sorted(expected_placeholders - actual_placeholders)
        unexpected = sorted(actual_placeholders - expected_placeholders)
        details = []
        if missing and not allow_missing_placeholders:
            details.append("thiếu: " + ", ".join(missing))
        if unexpected:
            details.append("không hỗ trợ: " + ", ".join(unexpected))
        if details:
            raise ValueError("Placeholder trong file mẫu không đúng (" + "; ".join(details) + ")")
    malformed = []
    for paragraph in template_paragraphs:
        residue = _PLACEHOLDER.sub("", paragraph.text)
        if "{{" in residue or "}}" in residue:
            malformed.append(paragraph.text)
    if malformed:
        raise ValueError("Placeholder sai cú pháp trong file mẫu: " + malformed[0])

    _apply_signature_images(template_paragraphs, data)

    context = _docx_context(data)
    for paragraph in template_paragraphs:
        _replace_placeholders(paragraph, context)
        _style_docx_checkbox_symbols(paragraph)

    if data.document_type == DocumentType.PREPAID_CONTRACT:
        _replace_service_point_address(document, data)
        _fill_prepaid_sim_table(document, data)
    elif data.document_type == DocumentType.BEAUTIFUL_NUMBER:
        _fill_beautiful_number_table(document, data)
    elif data.document_type == DocumentType.TRANSFER:
        _fill_transfer_subscriber_table(document, data)

    if data.document_type == DocumentType.TRANSFER and document.tables:
        table_size = 8.5 if (
            data.customer.entity_type == "Tổ chức" or data.new_owner.entity_type == "Tổ chức"
        ) else 10
        for row in document.tables[0].rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(table_size)

    unresolved = [
        match.group(0)
        for paragraph in _iter_paragraphs(document)
        for match in _PLACEHOLDER.finditer(paragraph.text)
    ]
    if unresolved:
        raise ValueError("Còn placeholder chưa được fill: " + ", ".join(sorted(set(unresolved))))

    core = document.core_properties
    core.title = f"{data.safe_stem()} - tạo bởi CCCD Report"
    core.subject = "Tài liệu được tạo từ thông tin CCCD đã kiểm tra"
    document.save(str(output))


_FONT_NAME: str | None = None


def _font_name() -> str:
    global _FONT_NAME
    if _FONT_NAME:
        return _FONT_NAME
    windows = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = [
        Path("/usr/share/fonts/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/TTF/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
        windows / "Fonts" / "arial.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            pdfmetrics.registerFont(TTFont("CCCDUnicode", str(path)))
            _FONT_NAME = "CCCDUnicode"
            return _FONT_NAME
    _FONT_NAME = "Helvetica"
    return _FONT_NAME


def _wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or pdfmetrics.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_top(
    pdf: canvas.Canvas,
    page_height: float,
    x: float,
    top: float,
    text: str,
    size: float = 8.5,
    max_width: float = 260,
    max_lines: int = 2,
) -> None:
    if not str(text or "").strip():
        return
    font = _font_name()
    pdf.setFont(font, size)
    pdf.setFillColorRGB(0.02, 0.08, 0.18)
    lines = _wrap_text(str(text).strip(), font, size, max_width)[:max_lines]
    for offset, line in enumerate(lines):
        pdf.drawString(x, page_height - top - size - offset * (size + 1.5), line)


def _beautiful_number_commands(data: ReportData) -> dict[int, list[tuple]]:
    # The template's "1. Sản Phẩm" table is a flat scanned image (not vector
    # content -- confirmed by inspecting the page's content stream), and its
    # single printed data row leaves no real gap before the next numbered
    # heading below it. There's no room to draw a genuine second row, so a
    # 2nd subscriber entry is folded into the SAME row instead -- each cell
    # prints "row 1 / row 2" (smaller, 2 lines) exactly the way shop_phone_2/
    # 3 already fold into one "Điện thoại: ..." line elsewhere. When there's
    # no 2nd entry, sizing is unchanged from before this feature existed.
    list_mode = bool(data.beautiful_subscribers)
    has_row2 = not list_mode and bool(
        data.subscriber_number_2 or data.commitment_months_2 or data.monthly_fee_2 or data.commitment_note_2
    )

    def cell(row1: str, row2: str, size: float, small_size: float, width: float) -> tuple:
        if has_row2:
            text = f"{row1} / {row2}" if row2 else row1
            return (text, small_size, width, 2)
        return (row1, size, width, 1)

    def months(value: str) -> str:
        amount = re.sub(r"\s*tháng\s*$", "", str(value or "").strip(), flags=re.IGNORECASE)
        return f"{amount} tháng" if amount else ""

    first = data.beautiful_subscribers[0] if list_mode else {}
    subscriber = (
        str(first.get("subscriber_number", ""))
        if list_mode else data.subscriber_number_1 or data.subscriber_number
    )
    first_months = str(first.get("commitment_months", "")) if list_mode else data.commitment_months
    first_fee = str(first.get("monthly_fee", "")) if list_mode else data.monthly_fee
    first_note = str(first.get("commitment_note", "")) if list_mode else data.commitment_note

    return {
        0: [
            (475, 113, data.document_date, 7.5, 95, 1),
            (245, 139, data.customer.full_name.upper(), 8, 235, 1),
            (505, 139, data.customer.id_number, 8, 80, 1),
            (130, 240, *cell(subscriber, data.subscriber_number_2, 8.5, 7, 75)),
            (230, 240, *cell(months(first_months), data.commitment_months_2, 8, 7, 105)),
            (360, 240, *cell(first_fee, data.monthly_fee_2, 8, 7, 120)),
            (505, 240, *cell(first_note, data.commitment_note_2, 7.5, 6.5, 65)),
        ],
        1: [(88, 720, data.customer.full_name.upper(), 8.5, 190, 1)],
    }


def _beautiful_continuation_pages(data: ReportData, width: float, height: float) -> list:
    """Build as many clean continuation sheets as needed for rows 2..N.

    The source PDF's product table is a flat scan with one physical data row,
    so adding real pages is the only way to keep many entries readable and
    legally attached without shrinking them into an illegible single cell.
    """
    extra_rows = data.beautiful_subscribers[1:]
    if not extra_rows:
        return []

    pages = []
    rows_per_page = 16
    font = _font_name()
    columns = [
        ("STT", 34), ("Số thuê bao", 105), ("Thời gian cam kết", 105),
        ("Cước tối thiểu/tháng", 145), ("Ghi chú", width - 96 - 389),
    ]
    for page_index, start in enumerate(range(0, len(extra_rows), rows_per_page)):
        chunk = extra_rows[start:start + rows_per_page]
        packet = io.BytesIO()
        pdf = canvas.Canvas(packet, pagesize=(width, height))
        pdf.setFillColorRGB(0.02, 0.08, 0.18)
        pdf.setFont(font, 13)
        pdf.drawCentredString(width / 2, height - 52, "DANH SÁCH SỐ THUÊ BAO CAM KẾT (TIẾP THEO)")
        pdf.setFont(font, 8.5)
        pdf.drawString(48, height - 76, f"Khách hàng: {data.customer.full_name.upper()}")
        pdf.drawRightString(width - 48, height - 76, f"Trang bổ sung {page_index + 1}")

        left = 48
        top = height - 98
        header_height = 30
        row_height = 34
        total_width = sum(column_width for _label, column_width in columns)
        pdf.setFillColorRGB(0.94, 0.95, 0.96)
        pdf.rect(left, top - header_height, total_width, header_height, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.35, 0.38, 0.42)
        pdf.setFillColorRGB(0.02, 0.08, 0.18)

        x = left
        pdf.setFont(font, 8)
        for label, column_width in columns:
            pdf.rect(x, top - header_height, column_width, header_height, fill=0, stroke=1)
            pdf.drawCentredString(x + column_width / 2, top - 19, label)
            x += column_width

        for local_index, row in enumerate(chunk):
            y_top = top - header_height - local_index * row_height
            values = [
                str(start + local_index + 2),
                str(row.get("subscriber_number", "") or ""),
                (
                    str(row.get("commitment_months", "") or "").replace(" tháng", "").strip() + " tháng"
                    if str(row.get("commitment_months", "") or "").strip() else ""
                ),
                str(row.get("monthly_fee", "") or ""),
                str(row.get("commitment_note", "") or ""),
            ]
            x = left
            for value, (_label, column_width) in zip(values, columns):
                pdf.rect(x, y_top - row_height, column_width, row_height, fill=0, stroke=1)
                lines = _wrap_text(value, font, 7.5, column_width - 8)[:2]
                for line_index, line in enumerate(lines):
                    pdf.drawString(x + 4, y_top - 13 - line_index * 10, line)
                x += column_width
        pdf.save()
        packet.seek(0)
        pages.append(PdfReader(packet).pages[0])
    return pages


def _prepaid_commands(data: ReportData) -> dict[int, list[tuple]]:
    customer = data.customer
    structured = data.prepaid_structured_parties
    representative = data.representative if structured else customer
    individual_customer = data.new_owner if structured else customer
    is_organization = customer.entity_type == "Tổ chức"

    def organization(value: str) -> str:
        return value if structured or is_organization else ""

    def individual(value: str) -> str:
        return value if structured or not is_organization else ""

    organization_phones = " - ".join(
        value for value in (data.shop_phone, data.shop_phone_2, data.shop_phone_3) if value
    )
    sim_commands: list[tuple] = []
    for index, row in enumerate(_prepaid_rows(data)):
        top = 202 + index * 14.5
        sim_commands.extend([
            (78, top, row["subscriber_number"], 8, 120, 1),
            (245, top, row["sim_serial"], 8, 130, 1),
            (420, top, row["activation_date"], 8, 120, 1),
        ])

    return {
        0: [
            (520, 58, data.contract_number, 7.5, 70, 1),
            (510, 73, data.subscriber_code or data.subscriber_number, 7.5, 80, 1),
            (465, 173, data.document_date, 8, 110, 1),
            (265, 215, organization(customer.organization_name.upper()), 7.5, 300, 1),
            (165, 229, organization(customer.headquarters_address), 7.5, 395, 1),
            (300, 243, organization(customer.business_registration_number), 7.5, 250, 1),
            (95, 257, organization(customer.business_registration_issue_place), 7.5, 180, 1),
            (335, 257, organization(customer.business_registration_issue_date), 7.5, 130, 1),
            (205, 271, organization(representative.full_name or customer.representative_name), 7.5, 230, 1),
            (475, 271, organization(representative.representative_position), 7.5, 90, 1),
            (190, 285, organization(representative.authorization_number), 7.5, 170, 1),
            (430, 285, organization(representative.authorization_date), 7.5, 130, 1),
            (300, 299, organization(representative.id_number), 7.5, 260, 1),
            (95, 313, organization(representative.issue_place), 7.5, 180, 1),
            (335, 313, organization(representative.issue_date), 7.5, 130, 1),
            (190, 327, organization(representative.date_of_birth), 7.5, 180, 1),
            (155, 341, organization(representative.phone), 7.5, 115, 1),
            (305, 341, organization(representative.email), 7.5, 130, 1),
            (495, 341, organization(representative.other_contact), 7.5, 70, 1),
            (165, 366, individual(individual_customer.full_name.upper()), 8.2, 395, 1),
            (280, 380, individual(individual_customer.id_number), 8.2, 285, 1),
            (100, 394, individual(individual_customer.issue_place), 7.8, 155, 1),
            (315, 394, individual(individual_customer.issue_date), 8, 120, 1),
            (145, 408, individual(individual_customer.date_of_birth), 8, 160, 1),
            (45, 433, individual(individual_customer.address), 7.7, 515, 2),
            (125, 447, individual(individual_customer.phone), 8, 120, 1),
            (310, 447, individual(individual_customer.email), 7.5, 130, 1),
            (500, 447, individual(individual_customer.other_contact), 7.5, 65, 1),
            # Draw a large tick over the checkbox already present in the PDF.
            (98, 458, individual(PDF_CHECKMARK) if individual_customer.nationality.casefold() == "việt nam" else "", 13, 16, 1),
            (390, 461, individual(individual_customer.foreign_country), 7.5, 165, 1),
            (80, 545, data.provider_unit_address if structured else data.shop_address, 7.5, 470, 1),
            (115, 559, data.provider_representative, 7.5, 250, 1),
            (470, 559, data.provider_position, 7.5, 90, 1),
            (200, 614, data.service_point_name, 7.5, 350, 1),
            (155, 628, data.staff_name, 7.5, 350, 1),
        ],
        1: [
            (150, 56, data.service_point_address if structured else data.shop_address, 7.5, 410, 1),
            (195, 70, data.service_point_phone if structured else organization_phones, 7.5, 365, 1),
            (255, 84, data.registration_time, 7.5, 300, 1),
            *sim_commands,
            (80, 690, (individual_customer if structured else customer).display_name().upper(), 8.5, 190, 1),
        ],
    }


def _generate_pdf(data: ReportData, template: Path, output: Path) -> None:
    source = PdfReader(str(template))
    writer = PdfWriter()
    commands = (
        _beautiful_number_commands(data)
        if data.document_type == DocumentType.BEAUTIFUL_NUMBER
        else _prepaid_commands(data)
    )

    for index, page in enumerate(source.pages):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        packet = io.BytesIO()
        overlay_canvas = canvas.Canvas(packet, pagesize=(width, height))
        for command in commands.get(index, []):
            _draw_top(overlay_canvas, height, *command)
        overlay_canvas.save()
        packet.seek(0)
        overlay = PdfReader(packet).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
        if data.document_type == DocumentType.BEAUTIFUL_NUMBER and index == 0:
            for continuation in _beautiful_continuation_pages(data, width, height):
                writer.add_page(continuation)

    writer.add_metadata(
        {
            "/Title": data.safe_stem(),
            "/Subject": "Tài liệu tạo từ thông tin CCCD đã kiểm tra",
            "/Creator": "CCCD Report Desktop 1.0",
        }
    )
    with output.open("wb") as stream:
        writer.write(stream)


def render_document(
    data: ReportData,
    template: Path,
    output: Path,
    expected_placeholders: frozenset[str] = frozenset(),
    *,
    allow_missing_placeholders: bool = False,
) -> None:
    """Render one document; routing and lifecycle live in document modules."""
    if output.suffix.casefold() == ".docx":
        _generate_docx(
            data,
            template,
            output,
            expected_placeholders,
            allow_missing_placeholders=allow_missing_placeholders,
        )
    else:
        _generate_pdf(data, template, output)
