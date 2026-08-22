#!/usr/bin/env bash
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$app_dir")"
product_bin="$project_dir/product/CCCDReport/CCCDReport"
launcher_dir="${XDG_DATA_HOME:-/home/qbert/.local/share}/applications"

if [[ ! -x "$product_bin" ]]; then
    "$app_dir/build.sh"
fi

install -D -m 0644 "$app_dir/cccd-report.desktop" "$launcher_dir/cccd-report.desktop"
echo "Đã cài CCCD Report vào menu ứng dụng."
