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

echo "Đã cài môi trường ứng dụng."
echo "Chạy: $project_dir/desktop_app/run.sh"
