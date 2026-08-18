#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$app_dir")"
venv_dir="$project_dir/.venv-desktop"

# uv mirrors the target platform's own venv layout: bin/python on
# Linux/macOS, Scripts/python.exe on Windows (even when this script itself
# runs under git-bash there). Re-checked after install.sh runs, since which
# one exists is only known once the venv has actually been created.
venv_python() {
    if [[ -x "$venv_dir/bin/python" ]]; then
        echo "$venv_dir/bin/python"
    elif [[ -x "$venv_dir/Scripts/python.exe" ]]; then
        echo "$venv_dir/Scripts/python.exe"
    fi
}

python_bin="$(venv_python)"
if [[ -z "$python_bin" ]]; then
    "$app_dir/install.sh"
    python_bin="$(venv_python)"
fi

export PYINSTALLER_CONFIG_DIR="$project_dir/.pyinstaller"
cd "$project_dir"
"$python_bin" -m PyInstaller \
    --clean \
    --noconfirm \
    --distpath "$project_dir/product" \
    --workpath "$project_dir/build/cccd-report" \
    "$app_dir/CCCDReportApp.spec"

echo "Sản phẩm đã được tạo tại: $project_dir/product/CCCDReport"
