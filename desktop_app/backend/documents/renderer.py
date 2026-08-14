from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from desktop_app.backend.domain.models import DocumentType, ReportData


def _date_parts(value: str) -> tuple[str, str, str]:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value or "")
    return match.groups() if match else ("....", "....", "........")


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


def _docx_context(data: ReportData) -> dict[str, str]:
    customer, new_owner = data.customer, data.new_owner
    is_organization = customer.entity_type == "Tổ chức"
    day, month, year = _date_parts(data.document_date)
    def authorization(person) -> str:
        return " - ".join(value for value in (person.authorization_number, person.authorization_date) if value)

    def choice(label: str) -> str:
        return f"{'☒' if data.service_action == label else '☐'} {label}"

    def selected_value(action: str, value: str, blank: str = "……………………") -> str:
        return value if data.service_action == action else blank

    def organization(value: str) -> str:
        return value if is_organization else ""

    def individual(value: str) -> str:
        return value if not is_organization else ""

    def party_organization(person, value: str) -> str:
        return value if person.entity_type == "Tổ chức" else ""

    effective_day, effective_month, effective_year = _date_parts(data.transfer_effective_date)
    contract_day, contract_month, contract_year = _date_parts(data.source_contract_date)
    form_day, form_month, form_year = _date_parts(data.registration_form_date)
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
        "aftersale_document_date_line": f"Ngày {day} tháng {month} năm {year}",
        "document_day": f" {day}",
        "document_month": month,
        "document_year": year,
        "payment_method": data.payment_method,
        "source_contract_number": data.source_contract_number or "…………",
        "source_contract_day": contract_day,
        "source_contract_month": contract_month,
        "source_contract_year": f"{contract_year} ",
        "registration_form_day": f" {form_day}",
        "registration_form_month": form_month,
        "registration_form_year": form_year,
        "transfer_time": f"{data.transfer_time or '……'} ",
        "transfer_effective_day": effective_day,
        "transfer_effective_month": effective_month,
        "transfer_effective_year": effective_year,
        "shop_name": data.shop_name,
        "shop_address": data.shop_address,
        "shop_phone": data.shop_phone,
        "customer_name": customer.display_name().upper(),
        "customer_headquarters": party_organization(customer, customer.headquarters_address),
        "customer_business_number": party_organization(customer, customer.business_registration_number),
        "customer_representative": party_organization(customer, customer.representative_name.upper()),
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
        "new_owner_representative": party_organization(new_owner, new_owner.representative_name.upper()),
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
            f"{data.transfer_time or '……'} giờ, ngày {effective_day} tháng {effective_month} "
            f"năm {effective_year} (“Thời điểm Chuyển quyền”)."
        ),
        "attachment_checkboxes": (
            f"{'☒' if data.has_id_attachment else '☐'} CCCD/CMND    "
            f"{'☒' if data.has_original_sim else '☐'} SIM gốc"
        ),
        "other_attachment_line": f"{'☒' if data.other_attachment else '☐'} Giấy tờ khác: {data.other_attachment}",
        "update_information_choice": choice("Cập nhật thông tin"),
        "replace_sim_choice": choice("Thay SIM"),
        "transfer_choice": choice("Chuyển chủ quyền"),
        "update_information_commitment": (
            "Tôi xin cam kết là chủ sở hữu của số điện thoại Vietnamobile: "
            f"{selected_value('Cập nhật thông tin', data.subscriber_number)}. "
            "Tôi đã cung cấp cho cửa hàng SIM gốc và cam kết thuê bao không vướng bất kỳ tranh chấp nào."
        ),
        "replace_sim_commitment": (
            "Tôi xin cam kết là chủ sở hữu của số điện thoại Vietnamobile: "
            f"{selected_value('Thay SIM', data.subscriber_number)}. Trong trường hợp xảy ra bất kỳ "
            "tranh chấp về việc thay SIM cho số thuê bao này, tôi cam đoan sẽ phối hợp với "
            "Vietnamobile để giải quyết."
        ),
        "aftersale_transfer_commitment": (
            "Tôi đồng ý thanh lý Hợp đồng cung cấp và sử dụng dịch vụ thông tin di động mặt đất "
            f"Vietnamobile của thuê bao {selected_value('Chuyển chủ quyền', data.subscriber_number)} và "
            "chuyển quyền sử dụng số thuê bao này và dịch vụ điện thoại di động trả trước cho "
            f"{selected_value('Chuyển chủ quyền', new_owner.display_name())}, số CMND/CCCD "
            f"{selected_value('Chuyển chủ quyền', new_owner.id_number)}, ngày cấp "
            f"{selected_value('Chuyển chủ quyền', new_owner.issue_date)}, nơi cấp "
            f"{selected_value('Chuyển chủ quyền', new_owner.issue_place)} (“Chủ thuê bao mới”)."
        ),
        "aftersale_common_commitment": (
            f"Tôi ({'☐ Người yêu cầu hoặc ☒ Chủ thuê bao mới' if data.service_action == 'Chuyển chủ quyền' else '☒ Người yêu cầu hoặc ☐ Chủ thuê bao mới'}) "
            f"là chủ sở hữu của số thuê bao {data.subscriber_number}. Tôi đã được nhân viên tư vấn đầy đủ "
            "về các quyền và nghĩa vụ của gói cước đi kèm số thuê bao này và tôi đồng ý tiếp tục sử dụng "
            "và thực hiện các cam kết của gói cước theo quy định của Vietnamobile."
        ),
        "backup_phone_commitment": (
            "Tôi đồng ý để Vietnamobile thu hồi lại số thuê bao vô điều kiện hoặc áp dụng các biện pháp "
            "khác trong trường hợp tôi vi phạm điều khoản đã cam kết hoặc có bất kỳ khiếu nại nào từ chủ "
            "thuê bao cũ và/hoặc bên thứ ba khác và Vietnamobile không liên hệ được với tôi qua số điện "
            f"thoại 1: {data.backup_phone_1 or customer.phone} hoặc số điện thoại 2: {data.backup_phone_2} "
            "trong vòng 24 giờ. Tôi cam đoan sẽ phối hợp với Vietnamobile để giải quyết và chấp nhận quyết "
            "định cuối cùng của Vietnamobile."
        ),
        "contract_number": data.contract_number,
        "subscriber_code": data.subscriber_code or data.subscriber_number,
        "sim_serial": data.sim_serial,
        "activation_date": data.activation_date,
        "service_point_name": data.service_point_name,
        "provider_representative": data.provider_representative,
        "provider_position": data.provider_position,
        "registration_time": data.registration_time,
        "staff_name": data.staff_name,
        "prepaid_organization_name": organization(customer.organization_name.upper()),
        "prepaid_headquarters_address": organization(customer.headquarters_address),
        "prepaid_business_number": organization(customer.business_registration_number),
        "prepaid_business_issue_place": organization(customer.business_registration_issue_place),
        "prepaid_business_issue_date": organization(customer.business_registration_issue_date),
        "prepaid_representative_name": organization(customer.representative_name),
        "prepaid_representative_position": organization(customer.representative_position),
        "prepaid_authorization": organization(authorization(customer)),
        "prepaid_organization_id_number": organization(customer.id_number),
        "prepaid_organization_issue_place": organization(customer.issue_place),
        "prepaid_organization_issue_date": organization(customer.issue_date),
        "prepaid_organization_birth_date": organization(customer.date_of_birth),
        "prepaid_organization_phone": organization(customer.phone),
        "prepaid_organization_email": organization(customer.email),
        "prepaid_organization_other_contact": organization(customer.other_contact),
        "prepaid_individual_name": individual(customer.full_name.upper()),
        "prepaid_individual_id_number": individual(customer.id_number),
        "prepaid_individual_issue_place": individual(customer.issue_place),
        "prepaid_individual_issue_date": individual(customer.issue_date),
        "prepaid_individual_birth_date": individual(customer.date_of_birth),
        "prepaid_individual_address": individual(customer.address),
        "prepaid_individual_phone": individual(customer.phone),
        "prepaid_individual_email": individual(customer.email),
        "prepaid_individual_other_contact": individual(customer.other_contact),
        "prepaid_individual_nationality": individual(
            "☒ Việt Nam    ☐ Nước ngoài"
            if customer.nationality.casefold() == "việt nam"
            else f"☐ Việt Nam    ☒ Nước ngoài: {customer.foreign_country or customer.nationality}"
        ),
    }


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
    return {
        0: [
            (475, 113, data.document_date, 7.5, 95, 1),
            (245, 139, data.customer.full_name.upper(), 8, 235, 1),
            (505, 139, data.customer.id_number, 8, 80, 1),
            (130, 240, data.subscriber_number, 8.5, 75, 1),
            (230, 240, data.commitment_months, 8, 105, 2),
            (360, 240, data.monthly_fee, 8, 120, 2),
            (505, 240, data.commitment_note, 7.5, 65, 2),
        ],
        1: [(88, 720, data.customer.full_name.upper(), 8.5, 190, 1)],
    }


def _prepaid_commands(data: ReportData) -> dict[int, list[tuple]]:
    customer = data.customer
    is_organization = customer.entity_type == "Tổ chức"

    def organization(value: str) -> str:
        return value if is_organization else ""

    def individual(value: str) -> str:
        return value if not is_organization else ""

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
            (205, 271, organization(customer.representative_name), 7.5, 230, 1),
            (475, 271, organization(customer.representative_position), 7.5, 90, 1),
            (190, 285, organization(customer.authorization_number), 7.5, 170, 1),
            (430, 285, organization(customer.authorization_date), 7.5, 130, 1),
            (300, 299, organization(customer.id_number), 7.5, 260, 1),
            (95, 313, organization(customer.issue_place), 7.5, 180, 1),
            (335, 313, organization(customer.issue_date), 7.5, 130, 1),
            (190, 327, organization(customer.date_of_birth), 7.5, 180, 1),
            (155, 341, organization(customer.phone), 7.5, 115, 1),
            (305, 341, organization(customer.email), 7.5, 130, 1),
            (495, 341, organization(customer.other_contact), 7.5, 70, 1),
            (165, 366, individual(customer.full_name.upper()), 8.2, 395, 1),
            (280, 380, individual(customer.id_number), 8.2, 285, 1),
            (100, 394, individual(customer.issue_place), 7.8, 155, 1),
            (315, 394, individual(customer.issue_date), 8, 120, 1),
            (145, 408, individual(customer.date_of_birth), 8, 160, 1),
            (45, 433, individual(customer.address), 7.7, 515, 2),
            (125, 447, individual(customer.phone), 8, 120, 1),
            (310, 447, individual(customer.email), 7.5, 130, 1),
            (500, 447, individual(customer.other_contact), 7.5, 65, 1),
            (99, 461, individual("X") if customer.nationality.casefold() == "việt nam" else "", 9, 12, 1),
            (390, 461, individual(customer.foreign_country), 7.5, 165, 1),
            (80, 545, data.shop_address, 7.5, 470, 1),
            (115, 559, data.provider_representative, 7.5, 250, 1),
            (470, 559, data.provider_position, 7.5, 90, 1),
            (200, 614, data.service_point_name, 7.5, 350, 1),
            (155, 628, data.staff_name, 7.5, 350, 1),
        ],
        1: [
            (150, 56, data.shop_address, 7.5, 410, 1),
            (195, 70, data.shop_phone, 7.5, 365, 1),
            (255, 84, data.registration_time, 7.5, 300, 1),
            (78, 202, data.subscriber_number, 8, 120, 1),
            (245, 202, data.sim_serial, 8, 130, 1),
            (420, 202, data.activation_date, 8, 120, 1),
            (80, 690, customer.display_name().upper(), 8.5, 190, 1),
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
