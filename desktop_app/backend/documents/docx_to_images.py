from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable


class ConversionToolsMissing(RuntimeError):
    pass


def _require_tools() -> None:
    missing = [name for name in ("soffice", "pdftoppm") if not shutil.which(name)]
    if missing:
        raise ConversionToolsMissing(
            "Cần cài LibreOffice (lệnh 'soffice') và poppler-utils (lệnh 'pdftoppm') "
            f"trên máy để xuất ảnh -- thiếu: {', '.join(missing)}"
        )


def _convert_pdfs_to_images(
    docx_paths: list[Path], tmp_dir: Path, output_dir: Path, dpi: int,
    filename_for: Callable[[Path, int], str] | None,
) -> list[Path]:
    outputs: list[Path] = []
    for docx_path in docx_paths:
        pdf_path = tmp_dir / f"{docx_path.stem}.pdf"
        if not pdf_path.exists():
            raise RuntimeError(f"Không chuyển được {docx_path.name} sang PDF")

        prefix = tmp_dir / docx_path.stem
        try:
            subprocess.run(
                ["pdftoppm", "-jpeg", "-r", str(dpi), str(pdf_path), str(prefix)],
                check=True, capture_output=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Xuất ảnh cho {docx_path.name} quá thời gian chờ") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(f"Không xuất được ảnh cho {docx_path.name}: {detail}") from exc

        pages = sorted(
            tmp_dir.glob(f"{docx_path.stem}-*.jpg"),
            key=lambda p: int(p.stem.rsplit("-", 1)[-1]),
        )
        if not pages:
            raise RuntimeError(f"Không xuất được trang ảnh nào cho {docx_path.name}")
        for index, page in enumerate(pages, start=1):
            name = (
                filename_for(docx_path, index)
                if filename_for
                else f"{docx_path.stem}_trang{index}.jpg"
            )
            target = output_dir / name
            shutil.copy2(page, target)
            outputs.append(target)
    return outputs


def convert_docx_batch_to_images(
    docx_paths: Iterable[Path], output_dir: Path, dpi: int = 150,
    filename_for: Callable[[Path, int], str] | None = None,
) -> list[Path]:
    """Convert a complete document set with one LibreOffice process.

    Starting a new headless office process for each file was both slow and
    intermittently failed on the second file with an empty error message.
    One isolated process converts the whole batch consistently and also
    makes it possible for the caller to stage every page before replacing an
    older numbered result set.
    """
    paths = [Path(path) for path in docx_paths]
    if not paths:
        return []
    _require_tools()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        last_error = ""
        for attempt in range(2):
            profile_dir = tmp_dir / f"lo_profile_{attempt}"
            try:
                completed = subprocess.run(
                    [
                        "soffice", "--headless", "--norestore", "--nodefault", "--nolockcheck",
                        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                        "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(tmp_dir),
                        *[str(path) for path in paths],
                    ],
                    check=True, capture_output=True, timeout=180,
                )
                missing = [path.name for path in paths if not (tmp_dir / f"{path.stem}.pdf").exists()]
                if not missing:
                    return _convert_pdfs_to_images(paths, tmp_dir, output_dir, dpi, filename_for)
                last_error = "thiếu PDF: " + ", ".join(missing)
                if completed.stdout:
                    last_error += " · " + completed.stdout.decode("utf-8", "replace").strip()
            except subprocess.TimeoutExpired as exc:
                last_error = "quá thời gian chờ"
                if attempt == 1:
                    raise RuntimeError("Chuyển bộ tài liệu sang PDF quá thời gian chờ") from exc
            except subprocess.CalledProcessError as exc:
                last_error = (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"Không chuyển được bộ tài liệu sang PDF: {last_error}")


def convert_docx_to_images(
    docx_path: Path, output_dir: Path, dpi: int = 150, filename_for: Callable[[int], str] | None = None,
) -> list[Path]:
    """Convert one .docx into one JPG per page, written into output_dir.

    By default each page is named "<docx stem>_trang<N>.jpg" (JPG, not PNG,
    by explicit request). Pass `filename_for(page_number) -> str` to control
    naming instead -- e.g. the numbered-sequence output folder feature names
    pages by continuing a shop-supplied 1.jpg..6.jpg input sequence, not by
    the source docx's own name.

    Not bundled into the packaged app -- LibreOffice/poppler would add
    500MB-1GB+ to every installer for a feature that only needs to run on
    the shop's own machine, which realistically already has an office
    suite. Raises ConversionToolsMissing with a clear message when either
    tool isn't found, instead of failing silently or half-way through.

    Uses an isolated, disposable LibreOffice profile
    (-env:UserInstallation) for the headless conversion so it can never
    contend with (or get blocked by a stale lock from) the user's own,
    already-open LibreOffice windows -- hit exactly that class of bug
    earlier this session with the user's real profile.
    """
    namer = (
        (lambda _path, index: filename_for(index))
        if filename_for
        else None
    )
    return convert_docx_batch_to_images([docx_path], output_dir, dpi, namer)
