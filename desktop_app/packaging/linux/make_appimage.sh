#!/usr/bin/env bash
set -euo pipefail

# Wraps product/CCCDReport (the onedir PyInstaller build) into a portable
# .AppImage: no root needed, no distro-specific package format, works on
# most desktop Linux out of the box.

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "$app_dir/../../.." && pwd)"
version="${1:-0.0.0-dev}"

product_dir="$project_dir/product/CCCDReport"
out_dir="$project_dir/dist_installers"
work_dir="$project_dir/build/appimage"
appdir="$work_dir/CCCDReport.AppDir"

if [[ ! -x "$product_dir/CCCDReport" ]]; then
    echo "Không tìm thấy $product_dir/CCCDReport - hãy build trước (./desktop_app/build.sh)" >&2
    exit 1
fi

rm -rf "$appdir"
mkdir -p "$appdir/usr/bin" "$out_dir"
cp -R "$product_dir/." "$appdir/usr/bin/"
cp "$app_dir/../../assets/icon-1024.png" "$appdir/CCCDReport.png"

cat > "$appdir/CCCDReport.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CCCD Report
Comment=Đọc thông tin CCCD, kiểm tra và tạo tài liệu theo mẫu
Exec=CCCDReport
Icon=CCCDReport
Categories=Office;
Terminal=false
EOF

cat > "$appdir/AppRun" <<'EOF'
#!/usr/bin/env bash
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$here/usr/bin/CCCDReport" "$@"
EOF
chmod +x "$appdir/AppRun"

appimagetool_bin="$work_dir/appimagetool"
if [[ ! -x "$appimagetool_bin" ]]; then
    curl -L -o "$appimagetool_bin" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$appimagetool_bin"
fi

out_file="$out_dir/CCCDReport-${version}-linux-x86_64.AppImage"
rm -f "$out_file"
ARCH=x86_64 "$appimagetool_bin" --appimage-extract-and-run "$appdir" "$out_file"

echo "Đã tạo $out_file"
