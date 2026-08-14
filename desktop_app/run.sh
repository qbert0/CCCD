#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$app_dir")"
venv_dir="$project_dir/.venv-desktop"

# uv mirrors the target platform's own venv layout: bin/python on
# Linux/macOS, Scripts/python.exe on Windows.
if [[ -x "$venv_dir/bin/python" ]]; then
    python_bin="$venv_dir/bin/python"
else
    python_bin="$venv_dir/Scripts/python.exe"
fi

if [[ ! -x "$python_bin" ]]; then
    echo "Ứng dụng chưa được cài. Chạy desktop_app/install.sh trước."
    exit 1
fi

cd "$project_dir"
exec "$python_bin" -m desktop_app.main
