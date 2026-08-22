"""Extract the exact provider seal/signature composition from the source DOCX.

The DOCX stores the red seal and blue signature as separate transparent PNGs.
Their sizes and offsets below are the original Word group's own geometry,
not a visual approximation and not generated artwork.
"""

from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "desktop_app" / "data" / "source" / "original_documents" / "chuyen chu quyen" / "Biên bản chuyển chủ quyền 2025.docx"
OUTPUT = ROOT / "desktop_app" / "data" / "source" / "signatures" / "vietnamobile_provider_stamp_signature.png"

# Original VML group: coordsize 29013 x 15640.
# Seal: left 0, top 0, width 16276, height 15636.
# Signature: left 896, top 2352, width 28116, height 11818.
CANVAS = (580, 313)
SEAL_BOX = (0, 0, 325, 313)
SIGNATURE_BOX = (18, 47, 562, 236)


def extract(source: Path = SOURCE, output: Path = OUTPUT) -> Path:
    with ZipFile(source) as archive:
        seal = Image.open(io.BytesIO(archive.read("word/media/image3.png"))).convert("RGBA")
        signature = Image.open(io.BytesIO(archive.read("word/media/image4.png"))).convert("RGBA")
    seal = seal.resize(SEAL_BOX[2:], Image.Resampling.LANCZOS)
    signature = signature.resize(SIGNATURE_BOX[2:], Image.Resampling.LANCZOS)
    result = Image.new("RGBA", CANVAS, "white")
    result.alpha_composite(seal, SEAL_BOX[:2])
    result.alpha_composite(signature, SIGNATURE_BOX[:2])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.convert("RGB").save(output, optimize=True)
    return output


if __name__ == "__main__":
    print(extract())
