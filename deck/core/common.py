"""Shared constants: repo root, no-console creation flag."""

import os
from pathlib import Path

# Background subprocesses (powershell scans, taskkill) must not flash a
# console window when the deck runs under pythonw (no console to
# inherit, so Windows pops a visible terminal on EVERY scan otherwise).
# Works launched via run_work() are EXCLUDED -- those must stay VISIBLE.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

HERE = Path(__file__).resolve().parents[2]  # repo root
