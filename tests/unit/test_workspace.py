"""Atomic delivery: real files with measured metadata; a prompt is not an image."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from ip_asset_production.models import TaskStatus
from ip_asset_production.paths import UnsafePathError
from ip_asset_production.providers import MockProvider, ProviderImage
from ip_asset_production.providers.mock import MOCK_PNG_MARKER_KEY
from ip_asset_production.schemas import SchemaRegistry
from ip_asset_production.workspace import DeliveryError, commit_image, execute_once, inspect_image

from .test_providers import make_request


def test_execute_once_writes_real_file(tmp_path: Path) -> None:
    req = make_request(output_spec={"width_px": 1024, "height_px": 1024, "format": "PNG", "alpha_required": True})
    result = execute_once(MockProvider(), req, tmp_path)

    assert result.status is TaskStatus.QA_PENDING  # no QA in M0, so never "passed"
    assert result.qa_summary == {"is_mock": True, "model": "mock-deterministic-v1", "seed": result.qa_summary["seed"]}
    (out,) = result.outputs
    path = tmp_path / out.path
    assert path.is_file()
    assert out.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (out.width_px, out.height_px, out.format) == (1024, 1024, "PNG")
    assert out.alpha_verified is True
    with Image.open(path) as im:
        assert im.info.get(MOCK_PNG_MARKER_KEY) == "true"
    SchemaRegistry().validate("generation_result", result.to_contract())
    assert not list(path.parent.glob(".tmp-*"))


def test_measured_facts(tmp_path: Path) -> None:
    result = execute_once(MockProvider(), make_request(), tmp_path)
    facts = inspect_image(tmp_path / result.outputs[0].path)
    assert facts.mode == "RGB" and not facts.has_alpha_channel and result.outputs[0].alpha_verified is None


def _png(w: int, h: int) -> bytes:
    import io

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def test_commit_rejects_lying_size(tmp_path: Path) -> None:
    img = ProviderImage(data=_png(64, 64), width_px=2048, height_px=2048, format="PNG", has_alpha=False)
    with pytest.raises(DeliveryError, match="declared 2048x2048"):
        commit_image(img, tmp_path, "x.png")
    assert not any(tmp_path.rglob("*.png"))


def test_commit_rejects_lying_alpha(tmp_path: Path) -> None:
    img = ProviderImage(data=_png(8, 8), width_px=8, height_px=8, format="PNG", has_alpha=True)
    with pytest.raises(DeliveryError, match="alpha"):
        commit_image(img, tmp_path, "x.png")


def test_commit_rejects_garbage(tmp_path: Path) -> None:
    img = ProviderImage(data=b"{{prompt only}}", width_px=8, height_px=8, format="PNG", has_alpha=False)
    with pytest.raises(DeliveryError, match="not a readable image"):
        commit_image(img, tmp_path, "x.png")


def test_commit_rejects_traversal(tmp_path: Path) -> None:
    img = ProviderImage(data=_png(8, 8), width_px=8, height_px=8, format="PNG", has_alpha=False)
    with pytest.raises(UnsafePathError):
        commit_image(img, tmp_path / "out", "../escape.png")
    assert not (tmp_path / "escape.png").exists()
