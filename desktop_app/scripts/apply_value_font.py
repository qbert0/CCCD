"""Set every DATA-VALUE placeholder's own run across all 5 templates to
JetBrainsMono NF ExtraBold, size 12 -- per direct instruction, applies only
to placeholders holding free text/prose, a number, or a name. Left alone:
date/day/month/year/time values (DATE_FIELD_NAMES), checkbox marks (any
"_mark"-suffixed field, plus prepaid_individual_nationality's own embedded
CHECKED_BOX/EMPTY_BOX glyphs), and signature-name runs (already styled in
the embedded Great Vibes script font -- see font_embed.py).

Only targets the placeholder's OWN run, not surrounding template prose --
safe to do directly because `bake_field_highlighting.py` already isolates
every `{{ }}` token into its own dedicated run (see that script), so a
placeholder's run never shares characters with static text around it.
This script asserts that isolation still holds and skips (with a printed
warning, not a silent mis-style) rather than assume it if it doesn't.

Font is referenced by name only, not embedded into the .docx (unlike Great
Vibes) -- embedding wasn't asked for here. If these documents need to look
right on a machine without this font installed, apply the same embedding
technique from font_embed.py to this font too.

Idempotent: safe to re-run, it only ever sets font attributes on the same
runs, never inserts/removes text or runs.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/apply_value_font.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from desktop_app.backend.documents.font_embed import SIGNATURE_FONT_NAME
from desktop_app.backend.documents.renderer import VALUE_FONT_NAME, _PLACEHOLDER, _iter_paragraphs

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [
    ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx",
    ROOT / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx",
    ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx",
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    ROOT / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
    ROOT / "desktop_app/backend/documents/ownership_confirmation/00_MAU_GIAY_CAM_KET_XAC_NHAN_QUYEN.docx",
]

VALUE_FONT_SIZE = Pt(12)

# "ngày tháng năm" fields, verbatim from the user's own instruction: every
# placeholder whose value is a day/month/year fragment or a full date/time
# value (cross-checked against renderer.py::_docx_context's actual value
# construction for each name, not guessed from the name alone).
DATE_FIELD_NAMES = {
    "document_day", "document_month", "document_year", "document_date_line",
    "aftersale_day", "aftersale_month", "aftersale_year", "aftersale_customer_issue_date",
    "transfer_new_owner_issue_date",
    "registration_form_day", "registration_form_month", "registration_form_year",
    "source_contract_day", "source_contract_month", "source_contract_year",
    "transfer_time",
    "transfer_effective_day", "transfer_effective_month", "transfer_effective_year",
    "customer_birth_date", "customer_issue_date",
    "new_owner_birth_date", "new_owner_issue_date",
    "beautiful_number_day", "beautiful_number_month", "beautiful_number_year",
    "activation_date", "registration_time",
    "prepaid_business_issue_date",
    "prepaid_organization_issue_date", "prepaid_organization_birth_date",
    "prepaid_individual_issue_date", "prepaid_individual_birth_date",
    "sim_customer_birth_date", "sim_customer_issue_date",
    "sim_request_date_line", "sim_document_date_line",
    "ownership_day", "ownership_month", "ownership_year",
    "ownership_customer_issue_date",
}

# renderer.py's prepaid_individual_nationality bakes a CHECKED_BOX/EMPTY_BOX
# glyph pair directly into its own value text -- a checkbox choice, not a
# "_mark"-suffixed token, but the same "it's a tick, not data" reasoning.
CHECKBOX_EMBEDDED_FIELD_NAMES = {"prepaid_individual_nationality"}


def _skip_field(name: str) -> bool:
    return (
        name.casefold().endswith("_mark")
        or name in DATE_FIELD_NAMES
        or name in CHECKBOX_EMBEDDED_FIELD_NAMES
    )


def _set_value_font(run: Run) -> None:
    run.font.name = VALUE_FONT_NAME
    run.font.size = VALUE_FONT_SIZE
    run.font.bold = False
    r_pr = run._r.get_or_add_rPr()  # noqa: SLF001 -- matches font_embed.py's own rFonts pattern
    fonts = r_pr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{key}"), VALUE_FONT_NAME)


def _apply_paragraph(paragraph: Paragraph) -> int:
    runs = paragraph.runs
    joined = "".join(run.text for run in runs)
    applied = 0

    for match in _PLACEHOLDER.finditer(joined):
        name = match.group(1)
        if _skip_field(name):
            continue

        positions: list[tuple[int, int]] = []
        cursor = 0
        for run in runs:
            positions.append((cursor, cursor + len(run.text)))
            cursor += len(run.text)

        start_run = next(i for i, (_, end) in enumerate(positions) if match.start() < end)
        end_run = next(i for i, (start, end) in enumerate(positions) if start < match.end() <= end)
        start_offset = match.start() - positions[start_run][0]
        end_offset = match.end() - positions[end_run][0]
        prefix = runs[start_run].text[:start_offset]
        suffix = runs[end_run].text[end_offset:]

        if start_run != end_run or prefix or suffix:
            print(f"    SKIPPED (not isolated in its own run, check manually): {name}")
            continue
        if runs[start_run].font.name == SIGNATURE_FONT_NAME:
            continue

        _set_value_font(runs[start_run])
        applied += 1

    return applied


# Beautiful Number's subscriber-table row has no {{ }} tokens to match --
# see bake_field_highlighting.py's own note on this table -- its data
# cells (subscriber_number/commitment_months/monthly_fee/commitment_note)
# are genuinely empty runs, filled only at generation time. Column 0 is
# the STT row-index cell, bookkeeping not data, left alone.
BEAUTIFUL_NUMBER_SUBSCRIBER_ROW = (
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    0, 1, (1, 2, 3, 4),
)


def _apply_known_table_row(path: Path, table_index: int, row_index: int, columns: tuple[int, ...]) -> int:
    document = Document(str(path))
    row = document.tables[table_index].rows[row_index]
    applied = 0
    for column in columns:
        cell = row.cells[column]
        paragraph = cell.paragraphs[0]
        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run("")
        _set_value_font(run)
        applied += 1
    document.save(str(path))
    return applied


def apply_font(path: Path) -> int:
    document = Document(str(path))
    total = sum(_apply_paragraph(paragraph) for paragraph in _iter_paragraphs(document))
    document.save(str(path))
    return total


if __name__ == "__main__":
    for template in TEMPLATES:
        count = apply_font(template)
        print(f"{template.name}: styled {count} placeholder(s)")

    extra = _apply_known_table_row(*BEAUTIFUL_NUMBER_SUBSCRIBER_ROW)
    print(f"{BEAUTIFUL_NUMBER_SUBSCRIBER_ROW[0].name}: styled {extra} subscriber-row cell(s) (no {{{{ }}}} tokens)")
