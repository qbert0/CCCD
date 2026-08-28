"""One-time, idempotent fix for sim_change_form's placeholder reuse.

The template's "Tên cơ quan, tổ chức hoặc cá nhân" (organization) block and its
"Người đại diện/ủy quyền" (representative) block used the exact same
{{ sim_customer_name }} / {{ sim_customer_address }} / {{ sim_customer_id_number }} /
{{ sim_customer_issue_place }} / {{ sim_customer_issue_date }} tokens, even though
the org block must always stay blank while the representative block (and the
"Nơi gửi thông báo cước" line, which reuses the same address token) should
print the real customer data when available. A single dict-driven value can't
satisfy both, so the org block's own occurrences are renamed here to distinct
sim_customer_org_* tokens, freeing the original names to mean "the customer's
own data" everywhere else in the template.

Run once from the repository root with the desktop virtual environment.
"""

from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / (
    "desktop_app/backend/documents/sim_change_form/"
    "00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx"
)


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


def _iter_all_paragraphs(document: Document):
    for paragraph in document.paragraphs:
        yield paragraph
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph
                for nested_table in cell.tables:
                    for nested_row in nested_table.rows:
                        for nested_cell in nested_row.cells:
                            for paragraph in nested_cell.paragraphs:
                                yield paragraph


def main() -> None:
    document = Document(TEMPLATE)
    paragraphs = list(_iter_all_paragraphs(document))

    org_name_paragraph = next(
        p for p in paragraphs
        if p.text.startswith("Tên cơ quan, tổ chức hoặc cá nhân") and "{{sim_customer_name}}" in p.text
    )
    replace_tokens(org_name_paragraph, {"{{sim_customer_name}}": "{{sim_customer_org_name}}"})

    org_address_paragraph = next(
        p for p in paragraphs
        if p.text.startswith("Địa chỉ trụ sở chính") and "{{sim_customer_address}}" in p.text
    )
    replace_tokens(org_address_paragraph, {"{{sim_customer_address}}": "{{sim_customer_org_address}}"})

    org_business_paragraph = next(
        p for p in paragraphs
        if p.text.startswith("- Số QĐTL/GCNĐKKD&ĐKĐT/GPĐT/GCNĐKDN")
        and "{{sim_customer_id_number}}" in p.text
    )
    replace_tokens(org_business_paragraph, {
        "{{sim_customer_id_number}}": "{{sim_customer_org_id_number}}",
        "{{sim_customer_issue_place}}": "{{sim_customer_org_issue_place}}",
        "{{sim_customer_issue_date}}": "{{sim_customer_org_issue_date}}",
    })

    document.save(TEMPLATE)
    print("Done: split sim_change_form's organization-block placeholders.")


if __name__ == "__main__":
    main()
