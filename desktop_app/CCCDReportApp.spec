# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

project_dir = Path(SPECPATH).parent
sys.path.insert(0, str(project_dir))
from desktop_app.packaging.make_icons import build_icons

icon_ico, icon_icns = build_icons()

datas = [
    (
        str(project_dir / "desktop_app/backend/documents/transfer/00_MAU_BIEN_BAN_CHUYEN_CHU_QUYEN.docx"),
        "desktop_app/backend/documents/transfer",
    ),
    (
        str(project_dir / "desktop_app/backend/documents/aftersale/00_MAU_CAM_KET_SAU_BAN_HANG.docx"),
        "desktop_app/backend/documents/aftersale",
    ),
    (
        str(project_dir / "desktop_app/backend/documents/beautiful_number/00_MAU_PHU_LUC_CAM_KET_SO_DEP_editable.docx"),
        "desktop_app/backend/documents/beautiful_number",
    ),
    (
        str(project_dir / "desktop_app/backend/documents/prepaid_contract/00_MAU_HOP_DONG_TRA_TRUOC.docx"),
        "desktop_app/backend/documents/prepaid_contract",
    ),
    (
        str(project_dir / "desktop_app/backend/documents/sim_change_form/00_MAU_PHIEU_THAY_DOI_DICH_VU_TRA_TRUOC.docx"),
        "desktop_app/backend/documents/sim_change_form",
    ),
    (str(project_dir / "desktop_app/data/source/samples"), "desktop_app/data/source/samples"),
    (str(project_dir / "desktop_app/data/source/signatures"), "desktop_app/data/source/signatures"),
    (
        str(project_dir / "desktop_app/data/source/default_settings.ini"),
        "desktop_app/data/source",
    ),
    (str(project_dir / "desktop_app/assets"), "desktop_app/assets"),
    (str(project_dir / "runtime_models/paddle"), "runtime_models/paddle"),
    (str(project_dir / "runtime_models/vietocr"), "runtime_models/vietocr"),
    # The HTML/CSS/JS view layer -- static assets Analysis can't discover by
    # following imports, since nothing in Python ever `import`s them.
    (str(project_dir / "desktop_app/frontend/web"), "desktop_app/frontend/web"),
]
datas += collect_data_files("Cython", includes=["Utility/*"])
datas += copy_metadata("imageio")
binaries = []
hiddenimports = collect_submodules("paddleocr")
hiddenimports += collect_submodules("backports")
# QtWebEngine: PyInstaller's own hook-PyQt5.QtWebEngineWidgets/Core.py
# (bundled with PyInstaller itself) collects QtWebEngineProcess,
# resources*.pak, icudtl.dat, and qtwebengine_locales/*.pak automatically
# once these modules are statically importable -- but only if something
# actually imports them, so they're listed here explicitly rather than left
# to be discovered transitively. QtNetwork/QtPrintSupport are QtWebEngine's
# own runtime dependencies. Verify this is sufficient with a real onedir
# build (this spec has already needed manual collect_all() fixes for
# paddle/paddleocr before -- hook coverage gaps are not hypothetical here).
hiddenimports += [
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngineCore",
    "PyQt5.QtWebChannel",
    "PyQt5.QtNetwork",
    "PyQt5.QtPrintSupport",
]

for package in (
    "paddle",
    "paddleocr",
    "docx",
    "reportlab",
    "pypdf",
    "backports.tarfile",
    "torch",
    "torchvision",
    "vietocr",
):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

binaries += collect_dynamic_libs("paddle")
binaries += collect_dynamic_libs("torch")

a = Analysis(
    [str(project_dir / "desktop_app/main.py")],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # torch/torchvision are now a real runtime dependency (VietOCR
    # recognizer, see desktop_app/backend/ocr/engines/paddle.py) and must
    # NOT be excluded here — they're explicitly collect_all()'d above instead.
    excludes=["tensorflow", "ultralytics", "PySide6"],
    noarchive=False,
)

if sys.platform == "win32":
    # PyQt5's Qt5 SDK build vendors its own (older, VC++2019-era) copy of
    # MSVCP140.dll alongside its own bin/. torch (built against a newer MSVC
    # toolchain) also needs MSVCP140.dll, resolved by bare name from its
    # import table, and the PyInstaller-bootloader-registered search path
    # finds PyQt5's older copy before the newer one collected at the bundle
    # root (via torch's own collect_all()). The two aren't ABI-compatible:
    # whichever object code actually runs against the older copy segfaults
    # (0xc0000005) inside MSVCP140.dll's own code the moment torch calls
    # into it -- confirmed via Windows Event Viewer's Application log on a
    # real onedir build, not a hypothetical.
    #
    # Only MSVCP140.dll itself is excluded here, deliberately -- torch does
    # NOT bundle its own MSVCP140_1.dll/VCRUNTIME140*.dll (torch/lib has no
    # such files; collect_dynamic_libs("torch") only supplies MSVCP140.dll
    # via the root-level copy), so PyQt5's copies of those are the only
    # ones in the whole bundle. Excluding them too was tried and made
    # things worse: with no bundled copy left, MSVCP140_1.dll resolution
    # fell through to whatever's in C:\Windows\System32, an older build
    # incompatible with torch's shm.dll -- shm.dll loaded fine (no crash)
    # but failed a specific GetProcAddress lookup ("WinError 127: The
    # specified procedure could not be found"). Microsoft's redistributable
    # is binary-compatible across the whole 14.x (VS2015-2022) line, so the
    # newer root-level MSVCP140.dll works for every consumer including Qt5;
    # there's no equivalent newer fallback to rely on for MSVCP140_1.dll.
    a.binaries = [
        entry
        for entry in a.binaries
        if not (
            "PyQt5" in entry[0].replace("\\", "/").split("/")
            and Path(entry[0]).name.lower() == "msvcp140.dll"
        )
    ]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CCCDReport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_ico),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CCCDReport",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="CCCDReport.app",
        icon=str(icon_icns),
        bundle_identifier="vn.vietnamobile.cccdreport",
        info_plist={"NSHighResolutionCapable": True},
    )
