"""
nbsetup.py — environment bootstrap for the notebook.

Pure standard library (no third-party imports) so it can run on a fresh kernel and
install whatever is missing before the notebook imports numpy / braket / towers.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

# (import name, pip name) for everything the notebook needs.
REQUIRED = [
    ("numpy", "numpy"),
    ("scipy", "scipy"),
    ("pandas", "pandas"),
    ("networkx", "networkx"),
    ("matplotlib", "matplotlib"),
    ("braket", "amazon-braket-sdk"),
]


def _installed(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def ensure_environment(required=REQUIRED, quiet: bool = True) -> None:
    """pip-install any missing packages so the notebook runs top-to-bottom on a
    fresh qBraid Lab kernel with no manual setup."""
    missing = [pip for mod, pip in required if not _installed(mod)]
    if missing:
        print("installing:", missing)
        cmd = [sys.executable, "-m", "pip", "install", *(["-q"] if quiet else []), *missing]
        subprocess.run(cmd, check=False)
    else:
        print("environment ready — all packages present")
