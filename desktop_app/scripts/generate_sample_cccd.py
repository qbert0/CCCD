#!/usr/bin/env python3
"""Regenerate the synthetic CCCD sample images used by main.py's
--self-test / --self-test-full and by desktop_app/data/source/samples/.

These are entirely fictional (no real person's data or photo), rendered
flat with a "DỮ LIỆU THỬ NGHIỆM" watermark so they can't be mistaken for a
real ID even by accident. A real photographed ID was used here previously
and had to be removed — it belonged to an actual customer and this repo is
public. Keep it that way: never replace these with a real scan.

Run: .venv-desktop/bin/python desktop_app/scripts/generate_sample_cccd.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "desktop_app/data/source/samples"

WIDTH, HEIGHT = 1600, 1010
BG = (248, 247, 242)
INK = (35, 40, 40)
MUTED = (95, 100, 100)
ACCENT = (176, 40, 40)

FONT_DIR = Path("/usr/share/fonts/noto")
MONO_DIR = Path("/usr/share/fonts/noto")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def regular(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_DIR / "NotoSans-Regular.ttf", size)


def bold(size: int) -> ImageFont.FreeTypeFont:
    return font(FONT_DIR / "NotoSans-Bold.ttf", size)


def mono(size: int) -> ImageFont.FreeTypeFont:
    return font(MONO_DIR / "NotoSansMono-Regular.ttf", size)


# Fictional identity used only to exercise the OCR/QR pipeline in tests.
ID_NUMBER = "001099999999"
OLD_ID_NUMBER = "199999999"
FULL_NAME = "NGUYỄN VĂN TEST"
DOB_DIGITS = "01011999"
DOB_TEXT = "01/01/1999"
GENDER = "Nam"
ADDRESS = "Số 1 Đường Mẫu, Phường Mẫu, Quận Mẫu, Thành phố Mẫu"
HOMETOWN = "Phường Mẫu, Thành phố Mẫu"
ISSUE_DIGITS = "01012021"
ISSUE_TEXT = "01/01/2021"
EXPIRY_TEXT = "01/01/2036"


def watermark(canvas: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    text = "DỮ LIỆU THỬ NGHIỆM · KHÔNG PHẢI THẬT / SAMPLE DATA · NOT REAL   "
    f = bold(34)
    for y in range(-HEIGHT, HEIGHT * 2, 130):
        odraw.text((-200, y), text * 3, font=f, fill=(120, 120, 120, 60))
    rotated = overlay.rotate(-20, resample=Image.BICUBIC, center=(WIDTH // 2, HEIGHT // 2))
    return Image.alpha_composite(canvas.convert("RGBA"), rotated).convert("RGB")


def avatar_placeholder(canvas: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(canvas)
    draw.rectangle(box, fill=(224, 226, 222), outline=(190, 192, 188), width=2)
    cx = (x0 + x1) // 2
    head_r = (x1 - x0) // 6
    head_cy = y0 + (y1 - y0) // 3
    draw.ellipse(
        (cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r),
        fill=(200, 202, 198),
    )
    shoulder_w = (x1 - x0) // 2
    draw.pieslice(
        (cx - shoulder_w, y1 - shoulder_w, cx + shoulder_w, y1 + shoulder_w // 2),
        180, 360, fill=(200, 202, 198),
    )


def qr_image(text: str, size_px: int) -> Image.Image:
    barcode = zxingcpp.create_barcode(text, zxingcpp.QRCode)
    bitmap = zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=True)
    array = np.array(bitmap)
    return Image.fromarray(array).convert("L").resize((size_px, size_px), Image.NEAREST)


def make_front() -> Image.Image:
    # Watermark the blank background first so it never overlaps (and can
    # never corrupt) the QR code or any OCR-relevant text drawn afterward.
    canvas = watermark(Image.new("RGB", (WIDTH, HEIGHT), BG))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=(180, 182, 178), width=3)

    draw.text((WIDTH / 2, 50), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", font=regular(28), fill=INK, anchor="mm")
    draw.text((WIDTH / 2, 86), "Độc lập - Tự do - Hạnh phúc", font=regular(22), fill=MUTED, anchor="mm")
    draw.line((WIDTH / 2 - 140, 106, WIDTH / 2 + 140, 106), fill=MUTED, width=1)
    draw.text((WIDTH / 2, 150), "CĂN CƯỚC CÔNG DÂN", font=bold(44), fill=ACCENT, anchor="mm")
    draw.text((WIDTH / 2, 192), "Citizen Identity Card", font=regular(22), fill=MUTED, anchor="mm")

    avatar_box = (70, 240, 330, 560)
    avatar_placeholder(canvas, avatar_box)

    left = 360
    y = 250
    rows = [
        ("Số / No.:", ID_NUMBER),
        ("Họ và tên / Full name:", FULL_NAME),
        ("Ngày sinh / Date of birth:", DOB_TEXT),
        ("Giới tính / Sex:  " + GENDER + "     Quốc tịch / Nationality:", "Việt Nam"),
        ("Quê quán / Place of origin:", HOMETOWN),
        ("Nơi thường trú / Place of residence:", ADDRESS),
    ]
    for label, value in rows:
        draw.text((left, y), label, font=regular(22), fill=MUTED)
        y += 32
        draw.text((left, y), value, font=bold(28), fill=INK)
        y += 46

    qr = qr_image(
        f"{ID_NUMBER}|{OLD_ID_NUMBER}|{FULL_NAME}|{DOB_DIGITS}|{GENDER}|{ADDRESS}|{ISSUE_DIGITS}",
        220,
    )
    canvas.paste(qr, (WIDTH - 300, HEIGHT - 300))
    return canvas


def make_back() -> Image.Image:
    canvas = watermark(Image.new("RGB", (WIDTH, HEIGHT), BG))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=(180, 182, 178), width=3)

    draw.text((60, 50), "Đặc điểm nhận dạng / Personal identification:", font=regular(24), fill=INK)
    draw.text((60, 86), "Sẹo chấm ngay đuôi mắt phải", font=regular(22), fill=MUTED)

    # Simple flat chip graphic placeholder (no security-feature detail).
    draw.rounded_rectangle((60, 170, 200, 260), radius=14, fill=(198, 168, 96), outline=(150, 120, 60), width=2)

    draw.text((230, 175), "Ngày, tháng, năm / Date, month, year:", font=regular(22), fill=INK)
    draw.text((230, 205), ISSUE_TEXT, font=bold(28), fill=INK)
    draw.text((230, 250), "CỤC TRƯỞNG CỤC CẢNH SÁT QLHC VỀ TTXH", font=regular(18), fill=MUTED)
    draw.text((230, 275), "Director General of the Police Department", font=regular(16), fill=MUTED)
    draw.text((230, 293), "for Administrative Management of Social Order", font=regular(16), fill=MUTED)

    draw.text((60, 340), "Có giá trị đến / Date of expiry:", font=regular(22), fill=INK)
    draw.text((60, 370), EXPIRY_TEXT, font=bold(28), fill=INK)

    # parser.py's mrz_name extraction takes the FIRST line containing "<<"
    # and 3+ consecutive uppercase letters — the ID line below also matches
    # that shape ("IDV", "VNM"), so the name line must be drawn first or it
    # gets shadowed and full_name parses as garbage.
    mrz_lines = [
        "NGUYEN<<VAN<TEST<<<<<<<<<<<<<<<<<<<<",
        "9901019M3601014VNM<<<<<<<<<<<<<<<",
        f"IDVNM{ID_NUMBER}8{OLD_ID_NUMBER}<<<<<<<<<<<2",
    ]
    mrz_font = mono(34)
    y = HEIGHT - 200
    for line in mrz_lines:
        draw.text((60, y), line, font=mrz_font, fill=INK)
        y += 46

    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    make_front().convert("RGB").save(OUT_DIR / "cccd_front.jpg", quality=92)
    make_back().convert("RGB").save(OUT_DIR / "cccd_back.jpg", quality=92)
    print(f"wrote {OUT_DIR / 'cccd_front.jpg'}")
    print(f"wrote {OUT_DIR / 'cccd_back.jpg'}")


if __name__ == "__main__":
    main()
