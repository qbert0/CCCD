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
    value = re.sub(r"<[^>]+>", " ", value)
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


def _line_value(lines: list[str], aliases: tuple[str, ...], multiline: bool = False) -> str:
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
        return ", ".join(value for value in values if value)
    return ""


def parse_ocr_text(raw: str) -> dict[str, str]:
    text = _plain(raw)
    lines = text.splitlines()
    id_match = re.search(r"(?<!\d)(\d{12})(?!\d)", text)
    if not id_match:
        id_match = re.search(r"(?<!\d)(\d{9})(?!\d)", text)
    result = {key: _line_value(lines, aliases, key in {"hometown", "address"}) for key, aliases in LABELS.items()}
    result["id_number"] = id_match.group(1) if id_match else ""

    # ICAO-style machine-readable zone on the back of Vietnamese chip IDs.
    mrz_id = re.search(r"(\d{12})<{2,}", text)
    if mrz_id:
        result["id_number"] = mrz_id.group(1)
    mrz_name = next((line for line in lines if "<<" in line and re.search(r"[A-Z]{3}", line)), "")
    if not result["full_name"] and mrz_name:
        name = re.sub(r"[^A-Z<]", "", mrz_name.upper()).replace("<<", " ").replace("<", " ")
        result["full_name"] = re.sub(r"\s+", " ", name).strip().title()
    mrz_dates = re.search(r"\b(\d{6})\d?([MF])?(\d{6})", text)
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
    return result


def date_today_two_digits() -> int:
    from datetime import date

    return date.today().year % 100
