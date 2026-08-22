from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def source_data_dir() -> Path:
    return resource_path("desktop_app", "data", "source")


def default_output_dir() -> Path:
    configured = os.getenv("CCCD_REPORT_OUTPUT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    documents = Path.home() / "Documents"
    return (documents if documents.exists() else Path.home()) / "BaoCao_CCCD"


def local_output_dir() -> Path:
    """Repository output folder used by development and automated checks."""
    return resource_path("desktop_app", "data", "output")
