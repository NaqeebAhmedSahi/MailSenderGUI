# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MailFlow Pro GUI (Windows/Linux/macOS)."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")
tkhtml_datas, tkhtml_binaries, tkhtml_hidden = collect_all("tkhtmlview")

hiddenimports = (
    ctk_hidden
    + tkhtml_hidden
    + collect_submodules("openpyxl")
    + [
        "mail_core",
        "html_editor",
        "session_store",
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.colorchooser",
        "tkinter.simpledialog",
        "tkinter.ttk",
        "PIL",
        "PIL._tkinter_finder",
        "tkhtmlview",
        "tkhtmlview.html_parser",
    ]
)

a = Analysis(
    ["mail_sender_gui.py"],
    pathex=[],
    binaries=ctk_binaries + tkhtml_binaries,
    datas=ctk_datas + tkhtml_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
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
    name="mail-sender-gui",
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
)
