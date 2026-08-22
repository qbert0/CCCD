"""Bake bold + one-size-bigger + a short dotted marker directly into each
document template's own {{ }} placeholder runs, as real, permanent template
content -- per direct instruction, this presentation belongs in the
template files themselves (business-owned, hand-editable in Word), not
computed by Python at render time. `renderer.py::_replace_placeholders` and
`_set_cell_text_preserving_style` now do nothing but substitute text and
keep whatever formatting a run already has -- this script is what gives
those runs the formatting to keep.

Rules, matching the earlier (now-reverted) runtime version's reasoning:
- A field ending in "_mark" drives a checkbox glyph (choice_mark()), never
  real data -- skipped entirely, untouched.
- A field ending in _day/_month/_year/_hour/_time is a fragment of one
  idiom ("ngày X tháng Y năm Z", "Nhãn: 21 / 08 / 2026") -- bold+bigger,
  no dots (wrapping every fragment in dots clutters more than it clarifies).
- Inside a table cell: bold+bigger only, never dots -- a fixed-width
  column (a signature-name cell, for one) has no spare room for 5+ extra
  characters and wraps an already-bold, now-bigger name mid-word.
- Otherwise: dotted on both sides if the token sits mid-sentence, trailing
  only if it's preceded by a ":" (a "Nhãn: {{ }}" line). A real space
  always separates the dots from the value itself -- "{{ x }} ....", never
  "{{ x }}....." stuck directly onto the text.
- When the placeholder is the run's ENTIRE content (no static prefix/
  suffix sharing that run -- true for every subscriber-table cell, which
  `_set_cell_text_preserving_style` always treats as index-0-and-only),
  formatting is applied to that SAME run in place rather than inserting a
  new one, since that function always overwrites `runs[0]` and clears the
  rest -- inserting a separate run there would just get wiped at
  generation time and silently lose the baked formatting.

Idempotency: NOT idempotent by design, same as this session's other
one-time template-migration scripts -- re-running against an
already-baked template would double the dots and re-bump the size. Run
once per template edit, from a known-good state (diff before committing).

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/bake_field_highlighting.py
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from desktop_app.backend.documents.font_embed import SIGNATURE_FONT_NAME
from desktop_app.backend.documents.renderer import _PLACEHOLDER, _iter_paragraphs

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [
    ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx",
    ROOT / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx",
    ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx",
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    ROOT / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
]

DOTS = "....."
FRAGMENT_SUFFIXES = ("_day", "_month", "_year")
# "_time"/"_hour" aren't safe as suffix rules: `registration_time` is a
# complete standalone value (e.g. "09:30 ngày 11/08/2026"), not a fragment
# of a surrounding sentence, and would wrongly lose its dots to a blind
# suffix match. `transfer_time` is the one genuine hour:minute fragment
# ("... vào lúc {{ transfer_time }} ngày ...") -- named explicitly instead.
FRAGMENT_FIELD_NAMES = {"transfer_time"}


def _is_checkbox_field(name: str) -> bool:
    return name.casefold().endswith("_mark")


def _is_fragment_field(name: str) -> bool:
    return name.casefold().endswith(FRAGMENT_SUFFIXES) or name in FRAGMENT_FIELD_NAMES


def _is_in_table(paragraph: Paragraph) -> bool:
    return any(ancestor.tag == qn("w:tc") for ancestor in paragraph._p.iterancestors())


def _effective_size(run: Run, paragraph: Paragraph) -> Pt:
    size = run.font.size
    if size is None:
        style = paragraph.style
        while style is not None and style.font.size is None:
            style = style.base_style
        size = style.font.size if style is not None else None
    return size or Pt(11)


def _has_custom_font(run: Run) -> bool:
    # Every signature-name placeholder across all 5 templates already
    # carries the embedded "Great Vibes" cursive script (see
    # backend/documents/font_embed.py -- SIGNATURE_FONT_NAME/SIZE, a real,
    # actively-maintained feature: prints these names to look like a
    # genuine handwritten signature, font embedded into the template bytes
    # for cross-machine reliability). That run was already made maximally
    # distinct on purpose, at its own deliberately large size -- forcing
    # bold on top of a script face typically makes it heavier and less
    # legible, not clearer, so leave it completely alone. An explicit but
    # ORDINARY font name (Times New Roman et al., set directly rather than
    # inherited -- common throughout these templates) is not this case and
    # still gets the normal treatment.
    return run.font.name == SIGNATURE_FONT_NAME


def _insert_run_after(anchor: Run, paragraph: Paragraph, text: str) -> Run:
    new_element = deepcopy(anchor._r)
    new_run = Run(new_element, paragraph)
    new_run.text = text
    anchor._r.addnext(new_element)
    return new_run


def _bake_paragraph(paragraph: Paragraph) -> int:
    runs = paragraph.runs
    joined = "".join(run.text for run in runs)
    matches = list(_PLACEHOLDER.finditer(joined))
    baked = 0
    in_table = _is_in_table(paragraph)

    for match in reversed(matches):
        name = match.group(1)
        if _is_checkbox_field(name):
            continue

        positions: list[tuple[int, int]] = []
        cursor = 0
        for run in runs:
            positions.append((cursor, cursor + len(run.text)))
            cursor += len(run.text)

        start_run = next(i for i, (_, end) in enumerate(positions) if match.start() < end)
        end_run = next(i for i, (start, end) in enumerate(positions) if start < match.end() <= end)
        if _has_custom_font(runs[start_run]):
            continue
        start_offset = match.start() - positions[start_run][0]
        end_offset = match.end() - positions[end_run][0]
        prefix = runs[start_run].text[:start_offset]
        token = joined[match.start():match.end()]
        suffix = runs[end_run].text[end_offset:]

        want_dots = not in_table and not _is_fragment_field(name)
        preceding = joined[:match.start()].rstrip()
        is_label = preceding.endswith(":")

        base_size = _effective_size(runs[start_run], paragraph)
        bigger = Pt(base_size.pt + 1)

        if not want_dots and start_run == end_run and not prefix and not suffix:
            # The placeholder is this run's entire content (every
            # subscriber-table cell looks like this) -- format in place so
            # it stays `runs[0]`, since `_set_cell_text_preserving_style`
            # always overwrites index 0 and clears everything else.
            runs[start_run].font.bold = True
            runs[start_run].font.size = bigger
            baked += 1
            continue

        runs[start_run].text = prefix
        anchor = runs[start_run]

        if want_dots and not is_label:
            anchor = _insert_run_after(anchor, paragraph, f"{DOTS} ")
            anchor.font.bold = False
            anchor.font.size = base_size

        token_run = _insert_run_after(anchor, paragraph, token)
        token_run.font.bold = True
        token_run.font.size = bigger
        anchor = token_run

        if want_dots:
            anchor = _insert_run_after(anchor, paragraph, f" {DOTS}")
            anchor.font.bold = False
            anchor.font.size = base_size

        if end_run == start_run:
            if suffix:
                _insert_run_after(anchor, paragraph, suffix)
        else:
            for index in range(start_run + 1, end_run):
                runs[index].text = ""
            runs[end_run].text = suffix
        baked += 1

    return baked


# Beautiful Number's subscriber-table row (unlike Transfer's/Prepaid
# Contract's own subscriber rows, both of which still carry literal
# {{ }} tokens the paragraph scan above finds directly) was rebuilt with
# genuinely EMPTY data cells -- one empty run each, no placeholder text at
# all, filled in purely by `_set_cell_text_preserving_style` at generation
# time. There's no {{ }} for the general pass to match, so this table's
# column 0 (STT, a row index -- bookkeeping, not data) is skipped and
# columns 1-4 (subscriber_number/commitment_months/monthly_fee/
# commitment_note) get bold+bigger baked onto their existing empty run
# directly, by known position, same as everywhere else.
BEAUTIFUL_NUMBER_SUBSCRIBER_ROW = (
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    0, 1, (1, 2, 3, 4),
)


def _bake_known_table_row(path: Path, table_index: int, row_index: int, columns: tuple[int, ...]) -> int:
    document = Document(str(path))
    row = document.tables[table_index].rows[row_index]
    baked = 0
    for column in columns:
        cell = row.cells[column]
        paragraph = cell.paragraphs[0]
        run = paragraph.runs[0] if paragraph.runs else paragraph.add_run("")
        size = _effective_size(run, paragraph)
        run.font.bold = True
        run.font.size = Pt(size.pt + 1)
        baked += 1
    document.save(str(path))
    return baked


def bake(path: Path) -> int:
    document = Document(str(path))
    total = sum(_bake_paragraph(paragraph) for paragraph in _iter_paragraphs(document))
    document.save(str(path))
    return total


if __name__ == "__main__":
    for template in TEMPLATES:
        count = bake(template)
        print(f"{template.name}: baked {count} placeholder(s)")

    extra = _bake_known_table_row(*BEAUTIFUL_NUMBER_SUBSCRIBER_ROW)
    print(f"{BEAUTIFUL_NUMBER_SUBSCRIBER_ROW[0].name}: baked {extra} subscriber-row cell(s) (no {{{{ }}}} tokens)")
