"""Deterministic offline provider for CI and demos. Never a real deliverable.

Reference "support" here means the mock accepts reference metadata and mixes the
reference hashes into its seed; it does not read reference pixels. Every PNG it
emits carries ``ipap:mock=true`` text metadata so downstream gates can reject it.
"""

from __future__ import annotations

import hashlib
import io
import json

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

from ..models import GenerationRequest, ProviderCapabilities
from .base import (
    DataEgress,
    ProviderImage,
    ProviderResult,
    ProviderTimeoutError,
    check_request_allowed,
    choose_native_size,
)

MOCK_PNG_MARKER_KEY = "ipap:mock"

DEFAULT_MOCK_CAPABILITIES = ProviderCapabilities(
    name="mock",
    text_to_image=True,
    image_to_image=True,
    image_edit=False,
    multi_reference=True,
    mask_inpaint=False,
    seed=True,
    negative_prompt=False,
    alpha_native=True,
    native_sizes=((1024, 1024), (1024, 1536), (1536, 1024)),
    async_jobs=False,
    cost_estimate=False,
    max_images=1,
    max_reference_count=8,
)


class MockProvider:
    """Offline image provider producing deterministic placeholder PNGs.

    ``fail_first_n`` raises :class:`ProviderTimeoutError` on the first N calls, for
    exercising bounded-retry logic without a network.
    """

    def __init__(
        self,
        capabilities: ProviderCapabilities = DEFAULT_MOCK_CAPABILITIES,
        *,
        fail_first_n: int = 0,
    ) -> None:
        self._caps = capabilities
        self._fail_remaining = fail_first_n
        self.calls = 0

    @property
    def name(self) -> str:
        return self._caps.name

    @property
    def data_egress(self) -> DataEgress:
        return "local"

    @property
    def is_mock(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def generate(self, request: GenerationRequest) -> ProviderResult:
        check_request_allowed(self, request)
        self.calls += 1
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            raise ProviderTimeoutError(f"mock timeout for task {request.task_id} (injected)")

        spec = request.output_spec
        width, height = choose_native_size(self._caps, (spec.width_px, spec.height_px))
        alpha = spec.alpha_required and self._caps.alpha_native
        seed = _seed_for(request)
        data = _render_png(width, height, seed=seed, alpha=alpha, prompt=request.compiled_prompt)
        image = ProviderImage(data=data, width_px=width, height_px=height, format="PNG", has_alpha=alpha)
        return ProviderResult(
            task_id=request.task_id,
            provider=self.name,
            model="mock-deterministic-v1",
            images=(image,),
            native_size=(width, height),
            is_mock=True,
            seed=seed,
        )


def _seed_for(request: GenerationRequest) -> int:
    payload = json.dumps(
        {
            "prompt": request.compiled_prompt,
            "template": request.template_id,
            "character": [request.character_id, request.character_version],
            "refs": sorted((r.ref_id, r.sha256 or "") for r in request.references),
            "spec": request.output_spec.to_contract(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _render_png(width: int, height: int, *, seed: int, alpha: bool, prompt: str) -> bytes:
    """Draw a simple deterministic 'character' placeholder: a body blob and a head."""
    rnd = seed.to_bytes(8, "big")
    body = (rnd[0], rnd[1], rnd[2], 255)
    accent = (255 - rnd[0], 255 - rnd[1], 255 - rnd[2], 255)
    mode = "RGBA" if alpha else "RGB"
    bg = (0, 0, 0, 0) if alpha else (245, 240, 232)  # transparent or warm white
    img = Image.new(mode, (width, height), bg)
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2, height // 2
    unit = min(width, height) // 8
    head = (cx - unit, cy - 3 * unit, cx + unit, cy - unit)
    torso = (cx - int(1.4 * unit), cy - unit, cx + int(1.4 * unit), cy + 2 * unit)
    fill_body = body if alpha else body[:3]
    fill_accent = accent if alpha else accent[:3]
    draw.ellipse(torso, fill=fill_body)
    draw.ellipse(head, fill=fill_accent)

    info = PngInfo()
    info.add_text(MOCK_PNG_MARKER_KEY, "true")
    info.add_text("ipap:prompt_sha256", hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info, optimize=False)
    return buf.getvalue()
