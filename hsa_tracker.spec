# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ
from PyInstaller.utils.hooks import collect_all
import charset_normalizer

block_cipher = None

binaries = []
datas = [("templates", "templates")]
hiddenimports = []

# Ensure charset_normalizer compiled artifacts are bundled
cn_datas, cn_binaries, cn_hiddenimports = collect_all("charset_normalizer")
datas += cn_datas
binaries += cn_binaries
hiddenimports += cn_hiddenimports

# Explicitly bundle any mypyc-built charset_normalizer extensions with hashed names
cn_pkg_path = Path(charset_normalizer.__file__).parent
for mypyc_ext in cn_pkg_path.glob("*__mypyc.*"):
    binaries.append((str(mypyc_ext), "charset_normalizer"))
    mod_name = f"charset_normalizer.{mypyc_ext.stem}"
    if mod_name not in hiddenimports:
        hiddenimports.append(mod_name)

a = Analysis(
    ["app.py"],
    pathex=[str(Path(".").resolve())],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="hsa-tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
