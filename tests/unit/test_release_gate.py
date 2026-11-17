"""T25/T26: the style release gate fails while previews are only planned or mock."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo


def run_gate(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "check_style_release.py")], capture_output=True, text=True
    )


def test_gate_fails_on_planned_manifest(root: Path) -> None:
    proc = run_gate(root)
    assert proc.returncode != 0
    assert "NOT RELEASE READY: 48 styles" in proc.stderr + proc.stdout


def _approve_all(repo: Path, *, provider: str, mock_marker: bool) -> None:
    manifest_path = repo / "styles" / "preview_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for item in manifest["items"]:
        if item["style_id"] in seen:
            continue
        seen.add(item["style_id"])
        target = repo / item["expected_file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        info = PngInfo()
        if mock_marker:
            info.add_text("ipap:mock", "true")
        buf = io.BytesIO()
        Image.new("RGB", (1024, 1024), (240, 230, 220)).save(buf, format="PNG", pnginfo=info)
        target.write_bytes(buf.getvalue())
        item.update(status="approved", actual_file=item["expected_file"], provider=provider, license_review="cleared")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _gate_copy(tmp_path: Path, root: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(root / "scripts" / "check_style_release.py", repo / "scripts")
    shutil.copytree(root / "styles", repo / "styles")
    return repo


def test_gate_rejects_mock_provider_entries(tmp_path: Path, root: Path) -> None:
    repo = _gate_copy(tmp_path, root)
    _approve_all(repo, provider="mock", mock_marker=False)
    assert run_gate(repo).returncode != 0


def test_gate_rejects_mock_marked_png(tmp_path: Path, root: Path) -> None:
    repo = _gate_copy(tmp_path, root)
    _approve_all(repo, provider="some-real-provider", mock_marker=True)
    assert run_gate(repo).returncode != 0


def test_gate_passes_with_real_approved_previews(tmp_path: Path, root: Path) -> None:
    # Synthetic stand-ins for real images, only to prove the gate can turn green.
    repo = _gate_copy(tmp_path, root)
    _approve_all(repo, provider="some-real-provider", mock_marker=False)
    proc = run_gate(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
