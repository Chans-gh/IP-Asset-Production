"""Atomic delivery of provider images into a local workspace (SPEC §9.3: temp -> validate -> commit).

M0 only stores the provider's native output and measures it; resizing to the target
spec, alpha matting and QA belong to M2. Results therefore stop at ``qa_pending``.
"""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .models import GenerationRequest, GenerationResult, OutputFile, TaskStatus
from .paths import safe_join
from .providers.base import ImageProvider, ProviderImage, check_request_allowed

ALPHA_MODES = {"RGBA", "LA", "PA", "RGBa", "La"}


class DeliveryError(ValueError):
    """A provider image failed validation and was not committed."""


@dataclass(frozen=True)
class ImageFacts:
    """Measured (not claimed) properties of an image file."""

    width_px: int
    height_px: int
    format: str
    mode: str
    has_alpha_channel: bool
    has_transparency: bool


def inspect_image_bytes(data: bytes) -> ImageFacts:
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            mode = im.mode
            has_channel = mode in ALPHA_MODES or "transparency" in im.info
            transparent = False
            if has_channel:
                rgba = im.convert("RGBA")
                extrema = rgba.getchannel("A").getextrema()
                transparent = isinstance(extrema[0], int | float) and extrema[0] < 255
            fmt = im.format or "UNKNOWN"
            return ImageFacts(im.width, im.height, fmt, mode, has_channel, transparent)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DeliveryError(f"not a readable image: {exc}") from exc


def inspect_image(path: Path) -> ImageFacts:
    return inspect_image_bytes(path.read_bytes())


def commit_image(image: ProviderImage, out_dir: Path, relative_name: str) -> OutputFile:
    """Validate ``image`` against its own declared metadata, then atomically write it."""
    facts = inspect_image_bytes(image.data)
    if (facts.width_px, facts.height_px) != (image.width_px, image.height_px):
        raise DeliveryError(
            f"provider declared {image.width_px}x{image.height_px} but file is {facts.width_px}x{facts.height_px}"
        )
    if facts.format.upper() != image.format.upper():
        raise DeliveryError(f"provider declared {image.format} but file is {facts.format}")
    if image.has_alpha and not facts.has_alpha_channel:
        raise DeliveryError("provider declared alpha but file has no alpha channel")

    out_dir.mkdir(parents=True, exist_ok=True)
    target = safe_join(out_dir, relative_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(image.data)
            fh.flush()
            os.fsync(fh.fileno())
        if inspect_image(Path(tmp_name)) != facts:  # re-read what actually hit the disk
            raise DeliveryError("written file differs from validated bytes")
        os.replace(tmp_name, target)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise

    return OutputFile(
        path=target.relative_to(out_dir.resolve()).as_posix(),
        sha256=hashlib.sha256(image.data).hexdigest(),
        width_px=facts.width_px,
        height_px=facts.height_px,
        format=facts.format,
        alpha_verified=facts.has_transparency if image.has_alpha else None,
    )


def execute_once(
    provider: ImageProvider, request: GenerationRequest, out_dir: Path, *, attempt: int = 1
) -> GenerationResult:
    """Single generation attempt: gate -> generate -> atomic commit. No retry, no QA (M2)."""
    check_request_allowed(provider, request)
    result = provider.generate(request)
    outputs = []
    for idx, img in enumerate(result.images, start=1):
        name = f"{request.task_id}/attempt-{attempt:02d}/native-{idx:02d}.{img.format.lower()}"
        outputs.append(commit_image(img, out_dir, name))
    return GenerationResult(
        task_id=request.task_id,
        status=TaskStatus.QA_PENDING,
        attempt=attempt,
        outputs=tuple(outputs),
        provider=result.provider,
        native_size=result.native_size,
        qa_summary={"is_mock": result.is_mock, "model": result.model, "seed": result.seed},
    )
