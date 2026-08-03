# -*- mode: python ; coding: utf-8 -*-

import os

# 编译期可选预览数据：设置 WIT_PREVIEW_DATA=<目录> 时，将该目录下全部文件
# （含子目录）打包进 EXE 内部资源，并附带 PREVIEW_NOTICE.txt 署名说明。
# 仅用于开发/群友预览构建；未设置时 datas 为空，正式版不含任何规则数据。
PREVIEW_DATA = os.environ.get("WIT_PREVIEW_DATA", "").strip()

datas = []
if PREVIEW_DATA:
    for dirpath, _dirnames, filenames in os.walk(PREVIEW_DATA):
        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_dir = os.path.relpath(dirpath, PREVIEW_DATA)
            datas.append((abs_path, rel_dir))
    notice_template = os.path.join(SPECPATH, "PREVIEW_NOTICE.template")
    if os.path.isfile(notice_template):
        datas.append((notice_template, "PREVIEW_NOTICE.txt"))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['openpyxl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WIT-Combat-Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='WIT-Combat-Manager.manifest',
)
