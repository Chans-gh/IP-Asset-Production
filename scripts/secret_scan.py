#!/usr/bin/env python3
"""Privacy/secret scan before any public push. Works without installing the package."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ip_asset_production.security.secret_scan import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--root", str(ROOT), *sys.argv[1:]]))
