#!/usr/bin/env python3
"""Cross-platform PyInstaller build script for Windows, Linux, and macOS."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPECS = ("mail-sender.spec", "mail-sender-gui.spec")


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.check_call(command, cwd=ROOT)


def main() -> int:
    py = sys.executable
    system = platform.system()

    print(f"Building on {system} ({platform.machine()})")
    print(f"Python: {sys.version.split()[0]}")
    print()

    for spec in SPECS:
        run([py, "-m", "PyInstaller", "--noconfirm", "--clean", spec])

    print()
    if system == "Windows":
        print("Build complete:")
        print(r"  CLI: dist\mail-sender.exe")
        print(r"  GUI: dist\mail-sender-gui.exe")
        print()
        print("Session data is stored at:")
        print(r"  %USERPROFILE%\.mailflow-pro\session.json")
    else:
        print("Build complete:")
        print("  CLI: dist/mail-sender")
        print("  GUI: dist/mail-sender-gui")
        print()
        print("Session data is stored at:")
        print("  ~/.mailflow-pro/session.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
