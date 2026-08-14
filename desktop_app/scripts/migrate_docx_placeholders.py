"""One-time, idempotent migration of editable DOCX templates to placeholders.

Run from the repository root with the desktop virtual environment.  The generated
templates remain normal Word files: users can edit their layout and formatting as
long as the ``{{ placeholder_name }}`` tokens are retained.
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph


ROOT = Path(__file__).resolve().parents[2]


def set_text(paragraph: Paragraph, text: str) -> None:
    """Change visible text while retaining paragraph and first-run formatting."""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def set_text_after_column_break(paragraph: Paragraph, text: str) -> None:
    """Keep the section's column break before replacing its visible heading."""
    for run in paragraph.runs:
        run.text = ""
    if paragraph.runs:
        paragraph.runs[0].add_break(WD_BREAK.COLUMN)
    else:
        paragraph.add_run().add_break(WD_BREAK.COLUMN)
    paragraph.add_run(text)


def replace_tokens(paragraph: Paragraph, replacements: dict[str, str]) -> None:
    """Rename placeholders even when Word has split a token across runs."""
    runs = paragraph.runs
    joined = "".join(run.text for run in runs)
    for old, new in replacements.items():
        while old in joined:
            start = joined.index(old)
            end = start + len(old)
            positions: list[tuple[int, int]] = []
            cursor = 0
            for run in runs:
                positions.append((cursor, cursor + len(run.text)))
                cursor += len(run.text)
            start_run = next(index for index, (_, stop) in enumerate(positions) if start < stop)
            end_run = next(index for index, (begin, stop) in enumerate(positions) if begin < end <= stop)
            start_offset = start - positions[start_run][0]
            end_offset = end - positions[end_run][0]
            prefix = runs[start_run].text[:start_offset]
            suffix = runs[end_run].text[end_offset:]
            if start_run == end_run:
                runs[start_run].text = prefix + new + suffix
            else:
                runs[start_run].text = prefix + new
                for index in range(start_run + 1, end_run):
                    runs[index].text = ""
                runs[end_run].text = suffix
            joined = "".join(run.text for run in runs)


def migrate_transfer() -> None:
    source = ROOT / (
        "desktop_app/backend/documents/transfer/"
        "Biên bản chuyển chủ quyền 2025.docx"
    )
    path = ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
    document = Document(source)
    paragraphs = document.paragraphs
    common = {
        "{{pay_method}}": "{{ payment_method }}",
        "{{hop_dong_so}}": "{{ source_contract_number }}",
        "{{date_1}}": "{{ source_contract_day }}",
        "{{month_1}}": "{{ source_contract_month }}",
        "{{year_1}}": "{{ source_contract_year }}",
        "{{date_2}}": "{{ registration_form_day }}",
        "{{month_2}}": "{{ registration_form_month }}",
        "{{year_2}}": "{{ registration_form_year }}",
        "{{number}}": "{{ subscriber_number }}",
        "{{time}}": "{{ transfer_time }}",
    }
    for paragraph in paragraphs:
        replace_tokens(paragraph, common)
    replace_tokens(
        paragraphs[7],
        {
            "{{date_3}}": "{{ document_day }}",
            "{{month_3}}": "{{ document_month }}",
            "{{year_3}}": "{{ document_year }}",
        },
    )
    replace_tokens(
        paragraphs[12],
        {
            "{{date_3}}": "{{ transfer_effective_day }}",
            "{{month_3}}": "{{ transfer_effective_month }}",
            "{{year_3}}": "{{ transfer_effective_year }}",
        },
    )
    # The editable file used wide character spacing for the blank time field.
    # A real value such as 10:30 must remain normally spaced when printed.
    for run in paragraphs[12].runs:
        if "{{ transfer_time }}" not in run.text or run._r.rPr is None:
            continue
        spacing = run._r.rPr.find(qn("w:spacing"))
        if spacing is not None:
            run._r.rPr.remove(spacing)

    document.save(path)


def migrate_aftersale() -> None:
    source = ROOT / "desktop_app/data/source/original_documents/ck sau/CK Sau ban hang.docx"
    path = ROOT / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx"
    document = Document(source)
    paragraphs = document.paragraphs
    values = {
        3: "{{ aftersale_document_date_line }}",
        5: "Cửa hàng: {{ shop_name }}",
        6: "Địa chỉ: {{ shop_address }}",
        7: "Điện thoại: {{ shop_phone }}",
        11: "Họ và tên: {{ customer_name }}",
        12: "Số CMND/CCCD: {{ customer_id_number }}    Ngày cấp: {{ customer_issue_date }}    Nơi cấp: {{ customer_issue_place }}",
        13: "Địa chỉ: {{ customer_address }}",
        14: "Điện thoại liên hệ cần thiết: {{ customer_phone }}",
        15: "Giấy tờ kèm theo:",
        16: "{{ attachment_checkboxes }}",
        17: "{{ other_attachment_line }}",
        18: "",
        22: "{{ update_information_choice }}",
        23: "{{ update_information_commitment }}",
        24: "{{ replace_sim_choice }}",
        25: "{{ replace_sim_commitment }}",
        26: "{{ transfer_choice }}",
        27: "{{ aftersale_transfer_commitment }}",
        29: "{{ aftersale_common_commitment }}",
        31: "{{ backup_phone_commitment }}",
        32: "",
    }
    for index, value in values.items():
        set_text(paragraphs[index], value)
    set_text_after_column_break(paragraphs[38], "GIAO DỊCH VIÊN\n{{ staff_name }}")

    # Word's original list numbering draws its own empty square.  The selected
    # square is data-driven now, so keeping numPr would render two checkboxes.
    for index in (22, 24, 26):
        properties = paragraphs[index]._p.pPr
        if properties is not None and properties.numPr is not None:
            properties.remove(properties.numPr)

    # Long, reviewed customer data must still fit the one-page legal form.
    # Only body runs are compacted; headings, logo, columns and footer retain
    # the source template formatting.
    for index in range(11, 40):
        paragraph = paragraphs[index]
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        if index not in (20, 21, 28, 34, 36, 38):
            paragraph.paragraph_format.line_spacing = 0.86
        for run in paragraph.runs:
            if index in (20, 21, 28, 34, 36, 38):
                run.font.size = Pt(9)
            else:
                run.font.size = Pt(8.5)
    for run in paragraphs[3].runs:
        run.font.size = Pt(8.5)
    document.save(path)


def migrate_prepaid_contract() -> None:
    source = ROOT / (
        "desktop_app/data/source/original_documents/tra truoc/"
        "0.1. Trả trước_Hợp đồng theo mẫu trả trước (Sep 2025).docx"
    )
    destination = ROOT / (
        "desktop_app/backend/documents/prepaid_contract/"
        "00_MAU_HOP_DONG_TRA_TRUOC.docx"
    )
    document = Document(source)
    paragraphs = document.paragraphs
    values = {
        5: "Hợp đồng số: {{ contract_number }}    Mã thuê bao: {{ subscriber_code }}",
        12: "{{ document_date_line }}",
        14: "Tên cơ quan/tổ chức (Viết in hoa): {{ prepaid_organization_name }}",
        15: "Địa chỉ trụ sở chính: {{ prepaid_headquarters_address }}",
        16: (
            "Số QĐTL/GCNĐKKD&ĐKĐT/GPĐT/GCNĐKDN: {{ prepaid_business_number }}    "
            "Nơi cấp: {{ prepaid_business_issue_place }}    Ngày cấp: {{ prepaid_business_issue_date }}"
        ),
        17: (
            "Người đại diện/ủy quyền: {{ prepaid_representative_name }}    "
            "Chức vụ: {{ prepaid_representative_position }}    "
            "Giấy ủy quyền: {{ prepaid_authorization }}"
        ),
        18: (
            "Số định danh cá nhân/Số định danh điện tử/Hộ chiếu: {{ prepaid_organization_id_number }}    "
            "Nơi cấp: {{ prepaid_organization_issue_place }}    "
            "Ngày cấp: {{ prepaid_organization_issue_date }}"
        ),
        19: "Ngày, tháng, năm sinh: {{ prepaid_organization_birth_date }}",
        20: (
            "Điện thoại liên hệ: {{ prepaid_organization_phone }}    "
            "Email: {{ prepaid_organization_email }}    Liên hệ khác: {{ prepaid_organization_other_contact }}"
        ),
        22: "Họ tên (Viết in hoa): {{ prepaid_individual_name }}",
        23: (
            "Số định danh cá nhân/Số định danh điện tử/Hộ chiếu: {{ prepaid_individual_id_number }}    "
            "Nơi cấp: {{ prepaid_individual_issue_place }}    Ngày cấp: {{ prepaid_individual_issue_date }}"
        ),
        24: "Ngày, tháng, năm sinh: {{ prepaid_individual_birth_date }}",
        25: "Địa chỉ theo CCCD/Căn cước/Hộ chiếu: {{ prepaid_individual_address }}",
        26: "",
        27: (
            "Điện thoại liên hệ: {{ prepaid_individual_phone }}    "
            "Email: {{ prepaid_individual_email }}    Liên hệ khác: {{ prepaid_individual_other_contact }}"
        ),
        28: "Quốc tịch: {{ prepaid_individual_nationality }}",
        32: "Địa chỉ: {{ shop_address }}",
        33: "Người đại diện: {{ provider_representative }}    Chức vụ: {{ provider_position }}",
        37: "Điểm cung cấp dịch vụ viễn thông: {{ service_point_name }}",
        38: "Họ tên nhân viên giao dịch: {{ staff_name }}",
        44: "Địa chỉ điểm giao dịch: {{ shop_address }}",
        45: "Số điện thoại của điểm giao dịch: {{ shop_phone }}",
        46: (
            "Thời gian thực hiện đăng ký thông tin thuê bao: {{ registration_time }}. "
            "Bên A và Bên B đồng ý giao kết hợp đồng cung cấp và sử dụng dịch vụ thông tin di động "
            "mặt đất Vietnamobile (hình thức thanh toán trả trước) (“Hợp đồng”) với các nội dung sau đây:"
        ),
    }
    for index, value in values.items():
        set_text(paragraphs[index], value)

    subscriber_table = document.tables[0]
    for cell, placeholder in zip(
        subscriber_table.rows[1].cells,
        ("subscriber_number", "sim_serial", "activation_date"),
    ):
        set_text(cell.paragraphs[0], "{{ " + placeholder + " }}")

    document.save(destination)


if __name__ == "__main__":
    migrate_transfer()
    migrate_aftersale()
    migrate_prepaid_contract()
    print("Đã chuyển 3 mẫu DOCX sang placeholder.")
