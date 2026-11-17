from __future__ import annotations

import os
from pathlib import Path

import pytest

from ip_asset_production.paths import UnsafePathError, repo_root, safe_join
from ip_asset_production.units import mm_to_px, print_canvas_px, print_pixels


def test_app02_door_sign_canvas() -> None:
    # SPEC §8.2: 300x120 mm trim, 3 mm bleed, 300 ppi -> about 3614x1488 px.
    assert print_pixels(300, 3, 300) == 3614
    assert print_pixels(120, 3, 300) == 1488
    assert print_canvas_px((300, 120), 3, 300) == (3614, 1488)


@pytest.mark.parametrize(
    ("mm", "bleed", "ppi", "expected"),
    [(25.4, 0, 300, 300), (100, 0, 72, 283), (85, 2, 600, 2102), (210, 3, 300, 2551)],
)
def test_print_pixels_formula(mm: float, bleed: float, ppi: float, expected: int) -> None:
    assert print_pixels(mm, bleed, ppi) == expected == round((mm + 2 * bleed) / 25.4 * ppi)


@pytest.mark.parametrize(("mm", "bleed", "ppi"), [(0, 3, 300), (-1, 3, 300), (300, -1, 300), (300, 3, 0)])
def test_print_pixels_rejects_invalid(mm: float, bleed: float, ppi: float) -> None:
    with pytest.raises(ValueError):
        print_pixels(mm, bleed, ppi)


def test_mm_to_px() -> None:
    assert mm_to_px(8, 300) == 94  # default APP-02 safe margin


def test_repo_root_found(root: Path) -> None:
    assert repo_root() == root


def test_repo_root_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IPAP_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        repo_root()


def test_safe_join_allows_children(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/b.png") == (tmp_path / "a" / "b.png").resolve()


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd"])
def test_safe_join_rejects_escape(tmp_path: Path, bad: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, bad)


@pytest.mark.skipif(os.name == "nt", reason="symlinks")
def test_safe_join_rejects_symlink_escape(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(UnsafePathError):
        safe_join(base, "link/outside.txt")
