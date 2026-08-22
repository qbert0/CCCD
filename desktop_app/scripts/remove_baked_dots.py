"""Remove the "....." decoration bake_field_highlighting.py inserted
around every non-checkbox/non-fragment/non-table placeholder -- per
direct instruction, the user no longer wants dots before/after a
placeholder's own value. Only strips that literal baked 5-dot marker
(with the one adjacent space it was always inserted with, `DOTS = "....."`
in bake_field_highlighting.py, `f"{DOTS} "` / `f" {DOTS}"`) -- leaves the
placeholder's own value run, its bold+bigger baked emphasis, and every
OTHER dotted convention in this codebase alone:
  - the still-blank-field fallback dots (renderer.py's
    `_empty_field_placeholder`/`dotted()`, computed at generation time
    from the field's own value, never exactly 5 characters long -- see
    that function's length table) stay exactly as they are.
  - the ellipsis-style "…………" fallbacks scattered through
    `_docx_context()` are a different character (U+2026) entirely, not
    touched by this script's plain-period pattern.

Some of these dot runs ended up merged with adjacent static template
text into one run on an earlier save (observed directly: transfer's
"{{ payment_method }}" is followed by a single run reading
" .....) số: ", not an isolated dots-only run) -- so this substitutes the
dot pattern OUT of each run's text rather than assuming a dots run is
always its own isolated run.

Idempotent: safe to re-run, finds nothing to remove on a second pass.

Run from the repository root with the desktop virtual environment:
    python desktop_app/scripts/remove_baked_dots.py
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from desktop_app.backend.documents.renderer import _iter_paragraphs

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [
    ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx",
    ROOT / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx",
    ROOT / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx",
    ROOT / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx",
    ROOT / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx",
]

# The exact literal baked marker, with its one adjacent space optional so
# a whole-run "..... " / " ....." and a merged-run "...... ) số: " both match.
DOT_PATTERN = re.compile(r"\.{5}\s?|\s?\.{5}")


def remove_dots(path: Path) -> int:
    document = Document(str(path))
    removed = 0
    empty_runs = []
    for paragraph in _iter_paragraphs(document):
        for run in paragraph.runs:
            new_text, count = DOT_PATTERN.subn("", run.text)
            if count:
                run.text = new_text
                removed += count
                if new_text == "":
                    empty_runs.append(run)
    for run in empty_runs:
        run._r.getparent().remove(run._r)
    document.save(str(path))
    return removed


if __name__ == "__main__":
    for template in TEMPLATES:
        count = remove_dots(template)
        print(f"{template.name}: removed {count} dot marker(s)")
