from __future__ import annotations

import html
import re
import unicodedata


LABELS = {
    "full_name": ("họ và tên", "ho va ten", "full name"),
    "date_of_birth": ("ngày sinh", "ngay sinh", "date of birth", "dob"),
    "gender": ("giới tính", "gioi tinh", "sex"),
    "nationality": ("quốc tịch", "quoc tich", "nationality"),
    "hometown": ("quê quán", "que quan", "place of origin", "hometown"),
    "address": ("nơi thường trú", "noi thuong tru", "place of residence", "address"),
    "issue_date": ("ngày cấp", "ngay cap", "date of issue", "issue date"),
    "issue_place": ("nơi cấp", "noi cap", "place of issue"),
    "expiry_date": ("có giá trị đến", "co gia tri den", "date of expiry", "expiry date"),
}


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn").replace("đ", "d")


def _plain(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|tr|h[1-6])>", "\n", value)
    # Vietnamese chip-ID MRZ lines are full of bare "<<<<" filler characters.
    # A greedy `<[^>]+>` can treat a filler run as an opening tag and eat
    # everything up to the next ">" anywhere later in the text (even a
    # stray one from an OCR misread several lines down), silently deleting
    # real MRZ content. Require an actual tag shape (starts with a letter
    # or "/") and stay within one line so filler runs are left alone.
    value = re.sub(r"<[a-zA-Z/][^>\n]*>", " ", value)
    return "\n".join(
        line
        for raw in html.unescape(value).splitlines()
        if (line := re.sub(r"\s+", " ", raw).strip(" \t|:-"))
    )


def parse_qr(raw: str) -> dict[str, str]:
    parts = [part.strip() for part in raw.split("|")]
    if len(parts) < 6:
        return {}

    def qr_date(value: str) -> str:
        digits = re.sub(r"\D", "", value)
        return f"{digits[:2]}/{digits[2:4]}/{digits[4:8]}" if len(digits) == 8 else value

    return {
        "id_number": parts[0],
        "old_id_number": parts[1],
        "full_name": parts[2],
        "date_of_birth": qr_date(parts[3]),
        "gender": parts[4],
        "address": parts[5],
        "issue_date": qr_date(parts[6]) if len(parts) > 6 else "",
        "nationality": "Việt Nam",
    }


def _line_value(
    lines: list[str],
    aliases: tuple[str, ...],
    multiline: bool = False,
    min_length: int = 0,
) -> str:
    folded_aliases = tuple(_fold(alias) for alias in aliases)
    all_aliases = tuple(_fold(alias) for values in LABELS.values() for alias in values)
    for index, line in enumerate(lines):
        folded = _fold(line)
        matches = [
            (pos, pos + len(alias))
            for alias in folded_aliases
            if (pos := folded.find(alias)) >= 0
        ]
        if not matches:
            continue
        end = max(matches, key=lambda item: item[1])[1]
        tail = folded[end:]
        next_positions = [pos for alias in all_aliases if (pos := tail.find(alias)) >= 0]
        stop = min(next_positions) if next_positions else len(tail)
        first = line[end : end + stop].strip(" \t|/:-")
        values = [first] if first else []
        if multiline:
            cursor = index + 1
            while cursor < len(lines) and len(values) < 2:
                candidate = lines[cursor]
                if any(alias in _fold(candidate) for alias in all_aliases):
                    break
                values.append(candidate)
                cursor += 1
        elif min_length and len(first) < min_length and index + 1 < len(lines):
            # Same-line extraction is empty or implausibly short (e.g. a
            # decoration glyph fused right onto the label, like "Full
            # namera" -> "ra") — box detection now reliably keeps the
            # printed value on the very next line when it isn't on this
            # one, so try that instead of returning noise. Only trust it
            # if it doesn't itself look like the start of another field.
            candidate = lines[index + 1].strip()
            if len(candidate) >= min_length and not any(alias in _fold(candidate) for alias in all_aliases):
                values = [candidate]
        return ", ".join(value for value in values if value)
    return ""


def parse_ocr_text(raw: str) -> dict[str, str]:
    text = _plain(raw)
    lines = text.splitlines()
    id_match = re.search(r"(?<!\d)(\d{12})(?!\d)", text)
    if not id_match:
        id_match = re.search(r"(?<!\d)(\d{9})(?!\d)", text)
    result = {
        key: _line_value(
            lines,
            aliases,
            multiline=key in {"hometown", "address"},
            min_length=3 if key == "full_name" else 0,
        )
        for key, aliases in LABELS.items()
    }
    result["id_number"] = id_match.group(1) if id_match else ""

    # ICAO-style machine-readable zone on the back of Vietnamese chip IDs.
    mrz_id = re.search(r"(\d{12})<{2,}", text)
    if mrz_id:
        result["id_number"] = mrz_id.group(1)
    mrz_name = next((line for line in lines if "<<" in line and re.search(r"[A-Z]{3}", line)), "")
    if not result["full_name"] and mrz_name:
        name = re.sub(r"[^A-Z<]", "", mrz_name.upper()).replace("<<", " ").replace("<", " ")
        result["full_name"] = re.sub(r"\s+", " ", name).strip().title()
    # Scoped to an actual MRZ-shaped line (real "<<" filler present on that
    # same line), same as mrz_name above — otherwise a plain 12-digit
    # id_number elsewhere in the text (present on every card) spuriously
    # matches this digit pattern too and silently overwrites an
    # already-correct date_of_birth pulled from the "Ngày sinh / Date of
    # birth" label with garbage.
    mrz_dates = next(
        (match for line in lines if "<<" in line and (match := re.search(r"\b(\d{6})\d?([MF])?(\d{6})", line))),
        None,
    )
    if mrz_dates:
        birth = mrz_dates.group(1)
        year = int(birth[:2])
        full_year = 2000 + year if year <= date_today_two_digits() else 1900 + year
        result["date_of_birth"] = f"{birth[4:6]}/{birth[2:4]}/{full_year}"
        if mrz_dates.group(2):
            result["gender"] = "Nam" if mrz_dates.group(2) == "M" else "Nữ"
        result["nationality"] = result["nationality"] or "Việt Nam"
        expiry = mrz_dates.group(3)
        expiry_year = int(expiry[:2])
        expiry_full_year = 2000 + expiry_year if expiry_year < 70 else 1900 + expiry_year
        result["expiry_date"] = f"{expiry[4:6]}/{expiry[2:4]}/{expiry_full_year}"
    if not result["issue_date"]:
        issue_match = re.search(r"(?:date[^\d]{0,20})?(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if issue_match:
            result["issue_date"] = issue_match.group(1)
    if result["id_number"]:
        result["issue_place"] = result["issue_place"] or "Cục Cảnh sát QLHC về TTXH"
    # Nationality is read the same way as any other same-line label value,
    # so a watermark/decoration word stuck right after "Việt Nam" on that
    # line (e.g. "Việt Nam Thuận") rides along as trailing noise. The
    # overwhelming majority of cards processed here are Vietnamese citizens
    # ("Việt Nam" is what parse_qr and the MRZ fallback above both already
    # hardcode too), so once the recognized text is clearly that, normalize
    # away anything trailing rather than print it into the document as-is.
    if _fold(result["nationality"]).startswith("viet nam"):
        result["nationality"] = "Việt Nam"
    return result


def date_today_two_digits() -> int:
    from datetime import date

    return date.today().year % 100
