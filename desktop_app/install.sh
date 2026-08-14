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

UV_CACHE_DIR="$cache_dir" uv pip install \
    --python "$(venv_python)" \
    -r "$app_dir/requirements.txt"

echo "Đã cài môi trường ứng dụng."
echo "Chạy: $project_dir/desktop_app/run.sh"
