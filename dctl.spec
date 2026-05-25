# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for dctl CLI — builds a single-directory bundle.

block_cipher = None

a = Analysis(
    ['dctl/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'dctl',
        'dctl.cli',
        'dctl.models',
        'dctl.errors',
        'dctl.output',
        'dctl.selector',
        'dctl.locator',
        'dctl.capabilities',
        'dctl.doctor',
        'dctl.platform',
        'dctl.platform.base',
        'dctl.platform.detect',
        'dctl.platform.manager',
        'dctl.platform.linux',
        'dctl.platform.linux.accessibility_atspi',
        'dctl.platform.linux.input',
        'dctl.platform.linux.launch',
        'dctl.platform.linux.windowing',
        'dctl.platform.linux.windowing_kwin',
        'dctl.platform.macos',
        'dctl.platform.macos.backend',
        'dctl.platform.windows',
        'dctl.platform.windows.backend',
        'dctl.platform.windows.accessibility_uia',
        'dctl.platform.windows.input_sendinput',
        'dctl.platform.windows.capture_gdi',
        'dctl.platform.windows.launch',
        'dctl.platform.windows.windowing_win32',
        'dctl.adapters',
        'dctl.adapters.browser_cdp',
        'dctl.adapters.clipboard',
        'dctl.adapters.docx_files',
        'dctl.adapters.xlsx_files',
        'dctl.adapters.libreoffice_uno',
        'websockets',
        'docx',
        'openpyxl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter', 'unittest', 'pytest', 'test'],
    noarchive=False,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='dctl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    name='dctl',
)
