"""Extract the real Vietnamobile header/footer banner images from the
transfer template's DOCX, so other templates (currently sim_change_form)
can reuse the actual branded graphics instead of approximating them with
plain shaded table cells.

Run from the repository root with the desktop virtual environment.
"""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"
OUTPUT_DIR = ROOT / "desktop_app/data/source/branding"
HEADER_OUTPUT = OUTPUT_DIR / "vietnamobile_header.png"
FOOTER_OUTPUT = OUTPUT_DIR / "vietnamobile_footer.png"


def extract(source: Path = SOURCE) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as archive:
        HEADER_OUTPUT.write_bytes(archive.read("word/media/image1.png"))
        FOOTER_OUTPUT.write_bytes(archive.read("word/media/image2.png"))
    return HEADER_OUTPUT, FOOTER_OUTPUT


if __name__ == "__main__":
    print(extract())
