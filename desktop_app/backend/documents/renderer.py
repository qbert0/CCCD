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
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from desktop_app.backend.domain.models import DocumentType, ReportData


# Keep empty choices as an outlined square, but use a real check mark for the
# selected choice.  The previous ballot-box X looked like an error/cancellation.
EMPTY_BOX = "☐"
CHECKED_BOX = "☑"
PDF_CHECKMARK = "✓"


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


def _replace_placeholders(paragraph: Paragraph, context: dict[str, str]) -> None:
    """Replace tokens while retaining the formatting of the run where each starts.

    Word may split a token into several XML runs after a user edits the template.
    Working against the joined visible text makes that harmless without flattening
    the paragraph or changing the formatting of unrelated runs.
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
        if start_run == end_run:
            runs[start_run].text = prefix + str(context[name] or "") + suffix
        else:
            runs[start_run].text = prefix + str(context[name] or "")
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


def _docx_context(data: ReportData) -> dict[str, str]:
    customer, new_owner = data.customer, data.new_owner
    prepaid_structured = (
        data.document_type == DocumentType.PREPAID_CONTRACT
        and data.prepaid_structured_parties
    )
    prepaid_representative = data.representative if prepaid_structured else customer
    prepaid_individual = new_owner if prepaid_structured else customer
    aftersale_organization = data.document_type == DocumentType.AFTERSALE and customer.entity_type == "Tổ chức"
    signing_customer = new_owner if aftersale_organization else customer
    is_organization = customer.entity_type == "Tổ chức"
    day, month, year = _date_parts(data.document_date)
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

    effective_day, effective_month, effective_year = _date_parts(data.transfer_effective_date)
    contract_day, contract_month, contract_year = _date_parts(data.source_contract_date)
    form_day, form_month, form_year = _date_parts(data.registration_form_date)
    aftersale_day, aftersale_month, aftersale_year = _date_parts(data.document_date)
    transfer_basis = []
    if data.source_contract_number:
        transfer_basis.append(
            "Căn cứ hợp đồng cung cấp và sử dụng dịch vụ thông tin di động mặt đất "
            f"Vietnamobile (hình thức thanh toán {data.payment_method}) số: "
            f"{data.source_contract_number}, ngày {contract_day} tháng {contract_month} năm {contract_year}"
        )
    if data.registration_form_date:
        transfer_basis.append(
            "Phiếu đăng ký dịch vụ và bản xác nhận thông tin thuê bao Vietnamobile trả trước "
            f"ngày {form_day} tháng {form_month} năm {form_year}"
        )

    return {
        "document_date_line": f"Ngày {day} tháng {month} năm {year}",
        # Aftersale keeps every legal sentence in the DOCX.  These values only
        # fill individual blanks; missing values deliberately become dotted lines.
        "aftersale_day": dotted(aftersale_day, 4),
        "aftersale_month": dotted(aftersale_month, 4),
        "aftersale_year": dotted(aftersale_year, 6),
        "aftersale_shop_address": dotted(
            customer.headquarters_address if aftersale_organization else data.shop_address, 42
        ),
        "aftersale_shop_phone": dotted(
            " - ".join(
                value
                for value in (
                    (customer.phone, customer.phone_2)
                    if aftersale_organization
                    else (data.shop_phone, data.shop_phone_2)
                )
                if value
            ),
            24,
        ),
        # By explicit request, this identity block prints the COMPANY's own
        # registration identity (not the actual customer) -- the customer's
        # own name still appears via customer_signature_name below, near
        # their signature line. shop_id_number/issue_date/issue_place come
        # from the company profile's business_registration_* fields (see
        # WebBridge._default_report_dict()); aftersale_customer_phone joins
        # the document's 2 contact numbers, same pattern as shop_phone/2/3.
        "aftersale_customer_name": dotted(
            (customer.organization_name if aftersale_organization else data.shop_name).upper(), 46
        ),
        "aftersale_customer_id_number": dotted(
            customer.business_registration_number if aftersale_organization else data.shop_id_number, 18
        ),
        "aftersale_customer_issue_date": dotted(
            customer.business_registration_issue_date if aftersale_organization else data.shop_issue_date, 14
        ),
        "aftersale_customer_issue_place": dotted(
            customer.business_registration_issue_place if aftersale_organization else data.shop_issue_place, 26
        ),
        "aftersale_customer_address": dotted(
            customer.headquarters_address if aftersale_organization else data.shop_address, 48
        ),
        "aftersale_customer_phone": dotted(
            " - ".join(
                value
                for value in (
                    (customer.phone, customer.phone_2)
                    if aftersale_organization
                    else (data.shop_phone, data.shop_phone_2)
                )
                if value
            ),
            24,
        ),
        "aftersale_representative_name": dotted(data.provider_representative, 30),
        "id_attachment_mark": choice_mark(data.has_id_attachment),
        "sim_attachment_mark": choice_mark(data.has_original_sim),
        "other_attachment_mark": choice_mark(bool(data.other_attachment.strip())),
        "other_attachment_value": dotted(data.other_attachment, 48),
        "update_information_mark": choice_mark(data.service_action == "Cập nhật thông tin"),
        "update_subscriber_number": action_value(
            "Cập nhật thông tin", data.subscriber_number, 30
        ),
        "replace_sim_mark": choice_mark(data.service_action == "Thay SIM"),
        "replace_sim_subscriber_number": action_value("Thay SIM", data.subscriber_number, 30),
        "transfer_mark": choice_mark(data.service_action == "Chuyển chủ quyền"),
        "transfer_subscriber_number": action_value(
            "Chuyển chủ quyền", data.subscriber_number, 22
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
        "common_subscriber_number": dotted(data.subscriber_number, 24),
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
        "customer_signature_name": signing_customer.display_name().upper(),
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
        "subscriber_number": data.subscriber_number,
        "transfer_contract_basis": "- " + "; ".join(transfer_basis) + " (sau đây gọi chung là “Hợp đồng”).",
        "transfer_document_intro": (
            f"Hôm nay, ngày {day} tháng {month} năm {year}, các bên thỏa thuận ký kết biên bản "
            "chuyển quyền sử dụng dịch vụ thông tin di động mặt đất và thanh lý hợp đồng (“Biên bản”) như sau:"
        ),
        "transfer_agreement_intro": (
            f"Bên A, Bên B và bên thứ ba (“Bên C”) đồng ý Bên A sẽ chuyển quyền sử dụng số thuê bao "
            f"{data.subscriber_number} cho Bên C theo các thông tin như sau:"
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
        "provider_position": data.provider_position,
        "provider_phone": data.provider_phone,
        "provider_email": data.provider_email,
        "registration_time": data.registration_time,
        "staff_name": data.staff_name,
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
            f"{CHECKED_BOX} Việt Nam    {EMPTY_BOX} Nước ngoài"
            if prepaid_individual.nationality.casefold() == "việt nam"
            else (
                f"{EMPTY_BOX} Việt Nam    {CHECKED_BOX} Nước ngoài: "
                f"{prepaid_individual.foreign_country or prepaid_individual.nationality}"
            )
        ),
    }


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


def _set_cell_text_preserving_style(cell, value: str) -> None:
    paragraph = cell.paragraphs[0]
    if paragraph.runs:
        paragraph.runs[0].text = str(value or "")
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(str(value or ""))


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
                _set_cell_text_preserving_style(cell, values.get(name, ""))
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
                _set_cell_text_preserving_style(cell, values.get(name, ""))
        break


def _replace_service_point_address(document: Document, data: ReportData) -> None:
    if not data.prepaid_structured_parties:
        return
    for paragraph in _iter_paragraphs(document):
        if "Địa chỉ điểm giao dịch:" not in paragraph.text:
            continue
        prefix = paragraph.text.split("Địa chỉ điểm giao dịch:", 1)[0] + "Địa chỉ điểm giao dịch:"
        if paragraph.runs:
            paragraph.runs[0].text = prefix + data.service_point_address
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(prefix + data.service_point_address)
        break


def _align_aftersale_signature_columns(document: Document) -> None:
    """Normalize the three handwritten-signature columns in the new form.

    The template already contains real column breaks, but the first two
    columns inherit left/start alignment while the third is centered.  Set
    all six visible paragraphs explicitly and keep the final section at
    three equal columns so Word and LibreOffice produce the same row.
    """
    signature_texts = {
        "NGƯỜI YÊU CẦU",
        "CHỦ THUÊ BAO MỚI",
        "GIAO DỊCH VIÊN",
        "(Ký và ghi rõ họ tên)",
    }
    for paragraph in document.paragraphs:
        if paragraph.text.strip() not in signature_texts:
            continue
        properties = paragraph._p.get_or_add_pPr()
        justification = properties.get_or_add_jc()
        justification.set(qn("w:val"), "center")

    section_properties = document.sections[-1]._sectPr
    columns = section_properties.find(qn("w:cols"))
    if columns is not None:
        columns.set(qn("w:num"), "3")
        columns.set(qn("w:equalWidth"), "1")


def _generate_docx(
    data: ReportData,
    template: Path,
    output: Path,
    expected_placeholders: frozenset[str],
) -> None:
    document = Document(str(template))
    template_paragraphs = list(_iter_paragraphs(document))
    actual_placeholders = {
        match.group(1)
        for paragraph in template_paragraphs
        for match in _PLACEHOLDER.finditer(paragraph.text)
    }
    if expected_placeholders and actual_placeholders != expected_placeholders:
        missing = sorted(expected_placeholders - actual_placeholders)
        unexpected = sorted(actual_placeholders - expected_placeholders)
        details = []
        if missing:
            details.append("thiếu: " + ", ".join(missing))
        if unexpected:
            details.append("không hỗ trợ: " + ", ".join(unexpected))
        raise ValueError("Placeholder trong file mẫu không đúng (" + "; ".join(details) + ")")
    malformed = []
    for paragraph in template_paragraphs:
        residue = _PLACEHOLDER.sub("", paragraph.text)
        if "{{" in residue or "}}" in residue:
            malformed.append(paragraph.text)
    if malformed:
        raise ValueError("Placeholder sai cú pháp trong file mẫu: " + malformed[0])

    context = _docx_context(data)
    for paragraph in template_paragraphs:
        _replace_placeholders(paragraph, context)
        _style_docx_checkbox_symbols(paragraph)

    if data.document_type == DocumentType.PREPAID_CONTRACT:
        _replace_service_point_address(document, data)
        _fill_prepaid_sim_table(document, data)
    elif data.document_type == DocumentType.AFTERSALE:
        _align_aftersale_signature_columns(document)
    elif data.document_type == DocumentType.BEAUTIFUL_NUMBER:
        _fill_beautiful_number_table(document, data)

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
) -> None:
    """Render one document; routing and lifecycle live in document modules."""
    if output.suffix.casefold() == ".docx":
        _generate_docx(data, template, output, expected_placeholders)
    else:
        _generate_pdf(data, template, output)
