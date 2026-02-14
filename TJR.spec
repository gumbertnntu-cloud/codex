# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/tjr/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('assets/icons/TJR-icon-1024.png', 'assets/icons'),
        ('assets/illustrations/left-hero-v1.png', 'assets/illustrations'),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='TJR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TJR',
)
app = BUNDLE(
    coll,
    name='TJR.app',
    icon='assets/icons/TJR.icns',
    bundle_identifier='com.tjr.desktop',
)
