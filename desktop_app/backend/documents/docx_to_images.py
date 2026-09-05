from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from desktop_app.backend.paths import resource_path


class ConversionToolsMissing(RuntimeError):
    pass


# subprocess.run() on Windows spawns a new visible console window for a
# console-subsystem child (soffice.exe/pdftoppm.exe both are) whenever the
# parent process itself has none -- true here, since the app's own EXE is
# built with console=False (see CCCDReportApp.spec's EXE(...)). Without this
# flag, every docx->image conversion flashed a black cmd window on screen.
_NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# Windows-only bundled copies (see CCCDReportApp.spec's datas list, fetched
# into runtime_tools/win/ by desktop_app/install.sh) so a packaged build
# never depends on the end user's own machine having LibreOffice/poppler
# installed. Only used in a frozen build -- running from source still uses
# whatever's on the developer's own PATH, same as before.
_BUNDLED_TOOL_PATHS = {
    "soffice": ("runtime_tools", "win", "libreoffice", "program", "soffice.exe"),
    "pdftoppm": ("runtime_tools", "win", "poppler", "bin", "pdftoppm.exe"),
}


def _bundled_tool_path(name: str) -> Path | None:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    parts = _BUNDLED_TOOL_PATHS.get(name)
    if not parts:
        return None
    path = resource_path(*parts)
    return path if path.is_file() else None


def _tool_path(name: str) -> str:
    """Resolve a tool to invoke via subprocess: the bundled copy if this is
    a frozen Windows build and it's actually present, otherwise whatever
    `name` resolves to on PATH (or just `name` itself, unresolved --
    _require_tools() has already turned that case into a clear error by the
    time any of this runs)."""
    bundled = _bundled_tool_path(name)
    return str(bundled) if bundled else (shutil.which(name) or name)


def _require_tools() -> None:
    missing = [
        name for name in ("soffice", "pdftoppm")
        if not _bundled_tool_path(name) and not shutil.which(name)
    ]
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
                [_tool_path("pdftoppm"), "-jpeg", "-r", str(dpi), str(pdf_path), str(prefix)],
                check=True, capture_output=True, timeout=120, creationflags=_NO_WINDOW_FLAGS,
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
                        _tool_path("soffice"), "--headless", "--norestore", "--nodefault", "--nolockcheck",
                        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                        "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(tmp_dir),
                        *[str(path) for path in paths],
                    ],
                    check=True, capture_output=True, timeout=180, creationflags=_NO_WINDOW_FLAGS,
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

    On a Windows frozen build, LibreOffice/poppler are bundled (see
    CCCDReportApp.spec + _bundled_tool_path above) despite adding ~1.5GB to
    the installer -- an end user's machine can't be assumed to already have
    either tool. Running from source (any platform) still relies on
    whatever's on the developer's own PATH. Raises ConversionToolsMissing
    with a clear message when neither the bundled copy nor PATH has the
    tool, instead of failing silently or half-way through.

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
