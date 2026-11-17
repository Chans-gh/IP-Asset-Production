#!/usr/bin/env python3
"""Release gate for style preview images; requires Pillow only when validating actual images."""

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "styles" / "preview_manifest.json").read_text(encoding="utf-8"))
by_style = defaultdict(list)
for item in manifest["items"]:
    if item["status"] != "approved" or not item.get("actual_file"):
        continue
    if (item.get("provider") or "").lower() == "mock":
        continue  # mock placeholders never count toward the release gate (ADR-011)
    by_style[item["style_id"]].append(item)
expected = {f"STYLE-{i:03d}" for i in range(1, 49)}
missing = sorted(expected - set(by_style))
if missing:
    raise SystemExit(f"NOT RELEASE READY: {len(missing)} styles have no approved real preview: {', '.join(missing)}")
try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required to verify actual image dimensions for release") from exc
for style_id, items in by_style.items():
    ok = False
    for item in items:
        p = (ROOT / item["actual_file"]).resolve()
        if not p.is_relative_to(ROOT.resolve()) or not p.is_file():
            continue
        try:
            with Image.open(p) as im:
                valid = im.format == "PNG" and im.size == (1024, 1024) and im.info.get("ipap:mock") != "true"
            if valid and item.get("license_review") in ("cleared", "approved"):
                ok = True
                break
        except (OSError, ValueError):
            continue
    if not ok:
        raise SystemExit(f"NOT RELEASE READY: {style_id} has no verified 1024x1024 PNG or rights review")
print(f"RELEASE READY: {len(expected)} styles have verified approved previews")
