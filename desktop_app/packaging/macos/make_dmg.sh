#!/usr/bin/env bash
set -euo pipefail

# Wraps product/CCCDReport.app (built by build.sh, which adds the BUNDLE
# step on darwin) into a distributable .dmg with a drag-to-Applications
# shortcut. Uses only hdiutil, which ships with macOS.

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$app_dir/../../.." && pwd)"
version="${1:-0.0.0-dev}"

app_bundle="$project_dir/product/CCCDReport.app"
out_dir="$project_dir/dist_installers"

if [[ ! -d "$app_bundle" ]]; then
    echo "Không tìm thấy $app_bundle - hãy build trước (./desktop_app/build.sh)" >&2
    exit 1
fi

mkdir -p "$out_dir"
staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT

cp -R "$app_bundle" "$staging_dir/"
ln -s /Applications "$staging_dir/Applications"

dmg_path="$out_dir/CCCDReport-${version}-macos.dmg"
rm -f "$dmg_path"
hdiutil create -volname "CCCD Report" -srcfolder "$staging_dir" -ov -format UDZO "$dmg_path"

echo "Đã tạo $dmg_path"
