"""Provider protocol, request gating and capability registry (SPEC §9.1, §3.2, §11)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from ..models import GenerationRequest, ProviderCapabilities

DataEgress = Literal["local", "external"]

# Capability flags that a caller may require when selecting a provider.
BOOLEAN_CAPABILITIES = (
    "text_to_image",
    "image_to_image",
    "image_edit",
    "multi_reference",
    "mask_inpaint",
    "seed",
    "negative_prompt",
    "alpha_native",
    "async_jobs",
    "cost_estimate",
)


class ProviderError(Exception):
    """Base class for provider failures."""


class CapabilityError(ProviderError):
    """The request needs a capability the provider does not declare."""


class EgressBlockedError(ProviderError):
    """A reference image is not cleared for transfer to an external provider (T11)."""


class ApprovalRequiredError(ProviderError):
    """The generation request has not passed its approval gate (G4)."""


class ProviderTimeoutError(ProviderError):
    """Provider did not answer in time; retryable."""


@dataclass(frozen=True)
class ProviderImage:
    """One raw image as returned by a provider, before postprocessing."""

    data: bytes
    width_px: int
    height_px: int
    format: str
    has_alpha: bool


@dataclass(frozen=True)
class ProviderResult:
    task_id: str
    provider: str
    model: str
    images: tuple[ProviderImage, ...]
    native_size: tuple[int, int]
    is_mock: bool
    seed: int | None = None


@runtime_checkable
class ImageProvider(Protocol):
    """What every provider adapter must implement.

    ``data_egress`` declares whether request data (prompts, reference images) leaves the
    machine. ``is_mock`` outputs must never be counted as real deliverables or previews.
    """

    @property
    def name(self) -> str: ...

    @property
    def data_egress(self) -> DataEgress: ...

    @property
    def is_mock(self) -> bool: ...

    def capabilities(self) -> ProviderCapabilities: ...

    def generate(self, request: GenerationRequest) -> ProviderResult: ...


def check_request_allowed(provider: ImageProvider, request: GenerationRequest) -> None:
    """Raise if ``request`` must not be sent to ``provider``. Called before every generate()."""
    if request.approval_status != "approved":
        raise ApprovalRequiredError(f"task {request.task_id}: generation request is not approved")

    if provider.data_egress == "external":
        blocked = [r.ref_id for r in request.references if r.permission_scope == "private_local"]
        if blocked:
            raise EgressBlockedError(
                f"task {request.task_id}: references {blocked} are private_local and may not be sent "
                f"to external provider {provider.name!r}; obtain transfer consent or use a local provider"
            )

    caps = provider.capabilities()
    refs = request.references
    if not refs and not caps.text_to_image:
        raise CapabilityError(f"{provider.name}: text_to_image not supported")
    if refs and not (caps.image_to_image or caps.multi_reference):
        raise CapabilityError(f"{provider.name}: reference images not supported")
    if len(refs) > 1 and not caps.multi_reference:
        raise CapabilityError(f"{provider.name}: multiple references not supported")
    if caps.max_reference_count is not None and len(refs) > caps.max_reference_count:
        raise CapabilityError(
            f"{provider.name}: {len(refs)} references exceeds max_reference_count={caps.max_reference_count}"
        )


def choose_native_size(caps: ProviderCapabilities, target: tuple[int, int]) -> tuple[int, int]:
    """Pick the native size closest in aspect ratio to ``target``; prefer larger area on ties.

    The result is what the provider will really output; reaching ``target`` is a
    postprocessing step that must be recorded, never claimed as native.
    """
    if not caps.native_sizes:
        raise CapabilityError(f"{caps.name}: no native sizes declared")
    tw, th = target
    target_ratio = tw / th

    def score(size: tuple[int, int]) -> tuple[float, int]:
        w, h = size
        return (abs(w / h - target_ratio), -(w * h))

    return min(caps.native_sizes, key=score)


class CapabilityRegistry:
    """Registry of configured providers. External (real) providers are opt-in only."""

    def __init__(self, *, allow_external: bool = False) -> None:
        self._allow_external = allow_external
        self._providers: dict[str, ImageProvider] = {}

    @classmethod
    def offline_default(cls) -> CapabilityRegistry:
        from .mock import MockProvider

        reg = cls()
        reg.register(MockProvider())
        return reg

    def register(self, provider: ImageProvider) -> None:
        if not isinstance(provider, ImageProvider):
            raise TypeError(f"{provider!r} does not implement ImageProvider")
        if provider.name in self._providers:
            raise ValueError(f"provider {provider.name!r} already registered")
        if provider.data_egress == "external" and not self._allow_external:
            raise PermissionError(
                f"provider {provider.name!r} sends data externally; construct the registry with "
                "allow_external=True after the user has configured and consented to it"
            )
        provider.capabilities()  # fail fast on an invalid capability declaration
        self._providers[provider.name] = provider

    def names(self) -> list[str]:
        return list(self._providers)

    def get(self, name: str) -> ImageProvider:
        try:
            return self._providers[name]
        except KeyError:
            raise KeyError(f"provider {name!r} not registered; available: {self.names()}") from None

    def capabilities(self, name: str) -> ProviderCapabilities:
        return self.get(name).capabilities()

    def select(self, request: GenerationRequest, *, require: Iterable[str] = ()) -> ImageProvider:
        """Return a provider that can legally and capably serve ``request``.

        ``request.provider_preference`` is honoured strictly: if the preferred provider cannot
        serve the request, the error is raised rather than silently falling back.
        """
        required = tuple(require)
        unknown = [r for r in required if r not in BOOLEAN_CAPABILITIES]
        if unknown:
            raise ValueError(f"unknown capability flags: {unknown}")

        def usable(p: ImageProvider) -> None:
            caps = p.capabilities()
            missing = [r for r in required if not getattr(caps, r)]
            if missing:
                raise CapabilityError(f"{p.name}: missing capabilities {missing}")
            check_request_allowed(p, request)

        if request.provider_preference:
            provider = self.get(request.provider_preference)
            usable(provider)
            return provider

        reasons: list[str] = []
        for provider in self._providers.values():
            try:
                usable(provider)
            except (CapabilityError, EgressBlockedError) as exc:
                reasons.append(str(exc))
                continue
            return provider
        if not self._providers:
            raise CapabilityError("no image provider configured; only planning/prompt export is available")
        raise CapabilityError("no provider can serve this request: " + " | ".join(reasons))
