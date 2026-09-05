#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$app_dir")"
venv_dir="$project_dir/.venv-desktop"
cache_dir="${UV_CACHE_DIR:-$project_dir/.uv-cache}"

# uv mirrors the target platform's own venv layout: bin/python on
# Linux/macOS, Scripts/python.exe on Windows (even when this script itself
# runs under git-bash there).
venv_python() {
    if [[ -x "$venv_dir/bin/python" ]]; then
        echo "$venv_dir/bin/python"
    else
        echo "$venv_dir/Scripts/python.exe"
    fi
}

if ! command -v uv >/dev/null 2>&1; then
    echo "Không tìm thấy uv. Xem https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

if [[ ! -x "$(venv_python)" ]]; then
    UV_CACHE_DIR="$cache_dir" uv venv --python 3.11 "$venv_dir"
fi

# requirements.txt lists torch/torchvision twice, gated by a sys_platform
# marker (PyTorch's "+cpu" build only exists for Linux/Windows) -- both
# lines resolve against the same package name "torch", and uv's default
# dependency-confusion guard stops at the first index that knows that name
# (the pytorch.org CPU index) even for the darwin-only line, which has no
# wheel there. unsafe-best-match lets it fall through to PyPI for that line
# instead; every other package here only ever has one candidate anyway, so
# this doesn't loosen anything for them.
UV_CACHE_DIR="$cache_dir" uv pip install \
    --python "$(venv_python)" \
    --index-strategy unsafe-best-match \
    -r "$app_dir/requirements.txt" \
    --overrides "$app_dir/overrides.txt"

# VietOCR's pretrained weights (~150MB) are too large for a normal git blob
# (GitHub's 100MB hard limit), unlike the small PaddleOCR det/rec/cls models
# that are committed directly — so they're fetched once here instead and
# cached under runtime_models/, exactly where OCRConfig expects to find them.
vietocr_dir="$project_dir/runtime_models/vietocr"
vietocr_weights="$vietocr_dir/vgg_transformer.pth"
if [[ ! -f "$vietocr_weights" ]]; then
    echo "Đang tải trọng số VietOCR (~150MB, chỉ tải lần đầu)..."
    mkdir -p "$vietocr_dir"
    curl -fL "https://vocr.vn/data/vietocr/vgg_transformer.pth" -o "$vietocr_weights.part"
    mv "$vietocr_weights.part" "$vietocr_weights"
fi

# Windows-only: docx->PDF->image conversion
# (desktop_app/backend/documents/docx_to_images.py) shells out to
# LibreOffice's `soffice` and poppler's `pdftoppm`. Bundled into the frozen
# build (see CCCDReportApp.spec) so end users never install anything
# themselves -- fetched here into runtime_tools/, same reasoning as the
# VietOCR weights above (too large to commit; GitHub's 100MB blob limit).
if [[ "${OS:-}" == "Windows_NT" ]]; then
    tools_dir="$project_dir/runtime_tools/win"
    lo_dir="$tools_dir/libreoffice"
    poppler_dir="$tools_dir/poppler"

    if [[ ! -x "$lo_dir/program/soffice.exe" ]]; then
        echo "Đang tải và giải nén LibreOffice (~350MB tải về, chỉ lần đầu)..."
        mkdir -p "$tools_dir"
        lo_msi="$tools_dir/LibreOffice.msi"
        curl -fL "https://download.documentfoundation.org/libreoffice/stable/26.2.5/win/x86_64/LibreOffice_26.2.5_Win_x86-64.msi" -o "$lo_msi"
        lo_extract="$tools_dir/libreoffice_extract"
        rm -rf "$lo_extract"
        # `/a` is an "administrative install": unpacks every file into
        # TARGETDIR without registering anything system-wide (no registry,
        # no Start Menu, no real install). LibreOffice has no official
        # portable build, but this extraction runs standalone from any
        # path it's moved to afterwards -- verified by hand against every
        # docx template in this project before relying on it here.
        msiexec.exe /a "$(cygpath -w "$lo_msi")" /qn "TARGETDIR=$(cygpath -w "$lo_extract")"
        rm -f "$lo_msi"
        # Not needed for headless --convert-to (help/System*/the MSI's own
        # embedded copy of itself are never touched by that code path).
        rm -rf "$lo_extract/help" "$lo_extract/readmes" "$lo_extract/LibreOffice.msi" \
            "$lo_extract/System" "$lo_extract/System64" "$lo_extract/CREDITS.fodt" "$lo_extract/NOTICE"
        # `/a` (administrative install) unpacks EVERY optional
        # locale/feature unconditionally, unlike a normal install where the
        # user picks a language -- ~120 UI languages' worth of resource
        # strings, spelling dictionaries, and config, most of it never
        # relevant to a single-language shop's own machine. This isn't
        # just dead weight: measured directly, headless --convert-to on
        # the untrimmed ~1.6GB extraction took 8-11s per document set
        # (vs. ~3s for a normal single-language install) -- LibreOffice
        # appears to do real work scanning/registering all of it at every
        # startup, not just at first run (repeat invocations stayed slow).
        # Trimming to just English+Vietnamese brings a document set back
        # down to ~2.3s, verified against multiple docx templates in this
        # project including one with Vietnamese diacritics rendered
        # correctly in the resulting PDF page image.
        find "$lo_extract/program/resource" -maxdepth 1 -mindepth 1 -type d \
            ! -name common ! -name vi ! -name en_GB ! -name en_ZA -exec rm -rf {} +
        find "$lo_extract/share/registry" -maxdepth 1 -name "Langpack-*.xcd" \
            ! -name "Langpack-vi.xcd" ! -name "Langpack-en-GB.xcd" \
            ! -name "Langpack-en-US.xcd" ! -name "Langpack-en-ZA.xcd" -delete
        find "$lo_extract/share/registry/res" -maxdepth 1 -type f \
            \( -name "fcfg_langpack_*.xcd" -o -name "registry_*.xcd" \) \
            ! -name "fcfg_langpack_vi.xcd" ! -name "registry_vi.xcd" \
            ! -name "fcfg_langpack_en-GB.xcd" ! -name "fcfg_langpack_en-US.xcd" ! -name "fcfg_langpack_en-ZA.xcd" \
            ! -name "registry_en-GB.xcd" ! -name "registry_en-ZA.xcd" -delete
        # Spelling dictionaries and toolbar icon themes: never touched by
        # headless --convert-to (no spellcheck, no UI ever shown).
        rm -rf "$lo_extract/share/extensions"/dict-*
        rm -f "$lo_extract/share/config"/images_*.zip
        mv "$lo_extract" "$lo_dir"
    fi

    if [[ ! -x "$poppler_dir/bin/pdftoppm.exe" ]]; then
        echo "Đang tải poppler (~15MB, chỉ lần đầu)..."
        mkdir -p "$poppler_dir"
        poppler_zip="$tools_dir/poppler.zip"
        curl -fL "https://github.com/oschwartz10612/poppler-windows/releases/download/v26.02.0-0/Release-26.02.0-0.zip" -o "$poppler_zip"
        poppler_extract="$tools_dir/poppler_extract"
        rm -rf "$poppler_extract"
        mkdir -p "$poppler_extract"
        (cd "$poppler_extract" && unzip -q "$poppler_zip")
        # The zip's own top-level folder is versioned (e.g.
        # "poppler-26.02.0/"); only Library/bin (the .exe's + their .dll
        # dependencies) is needed, not Library/include or Library/share.
        versioned_dir="$(find "$poppler_extract" -maxdepth 1 -mindepth 1 -type d | head -n1)"
        mv "$versioned_dir/Library/bin" "$poppler_dir/bin"
        rm -rf "$poppler_zip" "$poppler_extract"
    fi
fi

echo "Đã cài môi trường ứng dụng."
echo "Chạy: $project_dir/desktop_app/run.sh"
