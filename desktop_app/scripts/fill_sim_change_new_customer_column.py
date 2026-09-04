"""One-time, surgical edit to the ALREADY-SHIPPED sim_change_form
template: the page-1 party table's right column ("Thông tin khách hàng
thay đổi (Nếu có)") was pure static dots -- never filled by any data.
Per direct instruction, QUANG_HA_STT's version of this document needs
that column filled with the actual new subscriber's info (new_owner),
since the LEFT column ("Thông tin khách hàng đã cung cấp") is Bên A /
"Người đại diện 2"'s fixed registered identity, not the physical walk-in
customer.

Deliberately NOT a regeneration via build_sim_change_template.py: the
currently shipped .docx already carries state (measured directly: 12pt
JetBrainsMono NF ExtraBold value runs, not the 8.6pt the build script's
own `_write(..., size=8.6)` calls would produce) that predates or
diverges from what that script would currently emit -- regenerating from
scratch would silently discard it. This script only rewrites the 6 right-
column cells that need new {{ }} tokens, then bakes+fonts ONLY those same
cells directly (via bake_field_highlighting.py/apply_value_font.py's own
paragraph-level functions, not their whole-document TEMPLATES lists) --
every other paragraph in the file, including the already-baked LEFT
column, is left completely untouched.

Run once, from the repository root, with the desktop virtual environment:
    python desktop_app/scripts/fill_sim_change_new_customer_column.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from desktop_app.scripts.apply_value_font import _apply_paragraph  # noqa: E402
from desktop_app.scripts.bake_field_highlighting import _bake_paragraph  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx"
)

# (row index, new text) -- row 0 is the header, row 3 is the ORG-identity
# block (footnote-marked, dead for every current caller -- all 3 services
# using this template are individual-only, see
# SERVICE_TEMPLATE_CUSTOMER_ENTITY_TYPE) and is deliberately left alone.
NEW_RIGHT_COLUMN_TEXT = {
    1: "Tên cơ quan, tổ chức hoặc cá nhân (viết in hoa):\n{{sim_customer_new_name}}",
    2: "Địa chỉ trụ sở chính/Địa chỉ theo CCCD/Căn cước/Hộ chiếu:\n{{sim_customer_new_address}}",
    4: (
        "- Người đại diện/ủy quyền: {{sim_customer_new_name}}\n"
        "- Số ĐDCN/ĐDĐT/Hộ chiếu: {{sim_customer_new_id_number}}\n"
        "- Ngày tháng năm sinh: {{sim_customer_new_birth_date}}\n"
        "- Giới tính: {{sim_customer_new_gender}}\n"
        "- Ngày cấp: {{sim_customer_new_issue_date}}\n"
        "- Nơi cấp/Đơn vị cấp: {{sim_customer_new_issue_place}}\n"
        "- Địa chỉ theo giấy tờ dùng để đăng ký thông tin thuê bao: {{sim_customer_new_address}}\n"
        "- Quốc tịch: {{sim_customer_new_nationality}}"
    ),
    5: "- Nơi gửi thông báo cước và thanh toán: {{sim_customer_new_address}}",
    6: "- Số điện thoại liên hệ: {{sim_customer_new_phone}}",
    7: "- Email: {{sim_customer_new_email}}",
}


def _set_base_run_format(paragraph) -> None:
    """Match the cell's own pre-existing look (measured directly from the
    file: inherited Times New Roman, 12pt, not bold) before baking -- the
    same starting point _write(..., size=8.6) used to give this cell,
    just reflecting what the shipped file actually carries today."""
    for run in paragraph.runs:
        run.font.size = Pt(12)
        run.font.bold = False


def fill() -> int:
    document = Document(str(TEMPLATE))
    table = document.tables[0]
    header = " | ".join(cell.text for cell in table.rows[0].cells)
    assert "Thông tin khách hàng thay đổi" in header, f"Unexpected table header: {header}"

    baked = 0
    styled = 0
    for row_index, text in NEW_RIGHT_COLUMN_TEXT.items():
        cell = table.rows[row_index].cells[1]
        cell.text = text
        paragraph = cell.paragraphs[0]
        _set_base_run_format(paragraph)
        baked += _bake_paragraph(paragraph)
        styled += _apply_paragraph(paragraph)

    document.save(str(TEMPLATE))
    return baked, styled


if __name__ == "__main__":
    baked, styled = fill()
    print(f"{TEMPLATE.name}: baked {baked} placeholder(s), styled {styled} placeholder(s)")
