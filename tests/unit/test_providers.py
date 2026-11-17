"""Provider contract, request gating (G4, T11) and capability registry (T10)."""

from __future__ import annotations

from typing import Any

import pytest

from ip_asset_production.models import GenerationRequest, ProviderCapabilities
from ip_asset_production.providers import (
    ApprovalRequiredError,
    CapabilityError,
    CapabilityRegistry,
    EgressBlockedError,
    ImageProvider,
    MockProvider,
    ProviderResult,
    ProviderTimeoutError,
    check_request_allowed,
    choose_native_size,
)
from ip_asset_production.providers.base import DataEgress
from ip_asset_production.providers.mock import DEFAULT_MOCK_CAPABILITIES


def make_request(**overrides: Any) -> GenerationRequest:
    base: dict[str, Any] = {
        "task_id": "task-001",
        "template_id": "BASE_VIEW",
        "character_id": "char-fox",
        "character_version": "v1",
        "compiled_prompt": "an original orange fox mascot, front view, full body",
        "output_spec": {"width_px": 1024, "height_px": 1024, "format": "PNG", "alpha_required": False},
        "approval_status": "approved",
    }
    base.update(overrides)
    return GenerationRequest.model_validate(base)


def ref(ref_id: str, scope: str = "private_local") -> dict[str, Any]:
    return {"ref_id": ref_id, "uri": f"workspace/private/{ref_id}.png", "role": "identity", "permission_scope": scope}


class FakeExternalProvider:
    """Stands in for a real cloud adapter; never performs network I/O."""

    def __init__(self, caps: ProviderCapabilities | None = None) -> None:
        self._caps = caps or DEFAULT_MOCK_CAPABILITIES.model_copy(update={"name": "fake-cloud"})
        self.sent: list[GenerationRequest] = []

    @property
    def name(self) -> str:
        return self._caps.name

    @property
    def data_egress(self) -> DataEgress:
        return "external"

    @property
    def is_mock(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def generate(self, request: GenerationRequest) -> ProviderResult:
        check_request_allowed(self, request)
        self.sent.append(request)
        raise AssertionError("not reached in these tests")


def test_mock_implements_protocol() -> None:
    assert isinstance(MockProvider(), ImageProvider)
    assert isinstance(FakeExternalProvider(), ImageProvider)


def test_mock_is_local_and_marked_mock() -> None:
    p = MockProvider()
    assert p.data_egress == "local" and p.is_mock


def test_mock_output_is_deterministic() -> None:
    a = MockProvider().generate(make_request())
    b = MockProvider().generate(make_request())
    assert a.images[0].data == b.images[0].data
    c = MockProvider().generate(make_request(compiled_prompt="a different prompt"))
    assert c.images[0].data != a.images[0].data


def test_mock_reports_native_not_target_size() -> None:
    # 3:4 target (SPEC full-body 1536x2048) -> nearest native 1024x1536 (2:3), never a fake 1536x2048.
    req = make_request(output_spec={"width_px": 1536, "height_px": 2048, "format": "PNG", "alpha_required": False})
    res = MockProvider().generate(req)
    assert res.native_size == (1024, 1536)
    assert (res.images[0].width_px, res.images[0].height_px) == (1024, 1536)


def test_mock_alpha_only_when_requested() -> None:
    opaque = MockProvider().generate(make_request()).images[0]
    alpha_req = make_request(output_spec={"width_px": 1024, "height_px": 1024, "format": "PNG", "alpha_required": True})
    transparent = MockProvider().generate(alpha_req).images[0]
    assert not opaque.has_alpha and transparent.has_alpha


def test_mock_without_alpha_capability_does_not_claim_alpha() -> None:
    caps = DEFAULT_MOCK_CAPABILITIES.model_copy(update={"alpha_native": False})
    alpha_req = make_request(output_spec={"width_px": 1024, "height_px": 1024, "format": "PNG", "alpha_required": True})
    assert not MockProvider(caps).generate(alpha_req).images[0].has_alpha


def test_mock_injected_timeouts_are_bounded() -> None:
    p = MockProvider(fail_first_n=2)
    for _ in range(2):
        with pytest.raises(ProviderTimeoutError):
            p.generate(make_request())
    assert p.generate(make_request()).images
    assert p.calls == 3


def test_unapproved_request_is_refused() -> None:
    with pytest.raises(ApprovalRequiredError):
        MockProvider().generate(make_request(approval_status="pending"))


def test_private_reference_blocked_for_external_provider() -> None:
    """T11: real-person/private references never leave the machine without consent."""
    ext = FakeExternalProvider()
    with pytest.raises(EgressBlockedError, match="private_local"):
        ext.generate(make_request(references=[ref("face-1")]))
    assert ext.sent == []


def test_consented_reference_allowed_for_external_provider() -> None:
    check_request_allowed(FakeExternalProvider(), make_request(references=[ref("face-1", "approved_external")]))


def test_private_reference_allowed_for_local_provider() -> None:
    check_request_allowed(MockProvider(), make_request(references=[ref("face-1")]))


def test_reference_limits_enforced() -> None:
    single = DEFAULT_MOCK_CAPABILITIES.model_copy(update={"multi_reference": False})
    with pytest.raises(CapabilityError, match="multiple references"):
        check_request_allowed(MockProvider(single), make_request(references=[ref("a"), ref("b")]))
    capped = DEFAULT_MOCK_CAPABILITIES.model_copy(update={"max_reference_count": 1})
    with pytest.raises(CapabilityError, match="max_reference_count"):
        check_request_allowed(MockProvider(capped), make_request(references=[ref("a"), ref("b")]))
    no_i2i = DEFAULT_MOCK_CAPABILITIES.model_copy(update={"image_to_image": False, "multi_reference": False})
    with pytest.raises(CapabilityError, match="reference images not supported"):
        check_request_allowed(MockProvider(no_i2i), make_request(references=[ref("a")]))


def test_choose_native_size_prefers_aspect_then_area() -> None:
    caps = DEFAULT_MOCK_CAPABILITIES.model_copy(update={"native_sizes": ((512, 512), (1024, 1024), (1536, 1024))})
    assert choose_native_size(caps, (2048, 2048)) == (1024, 1024)
    assert choose_native_size(caps, (3840, 2160)) == (1536, 1024)
    with pytest.raises(CapabilityError):
        choose_native_size(caps.model_copy(update={"native_sizes": ()}), (1, 1))


def test_registry_default_is_offline_mock_only() -> None:
    reg = CapabilityRegistry.offline_default()
    assert reg.names() == ["mock"]
    assert reg.select(make_request()).name == "mock"


def test_registry_refuses_external_provider_unless_opted_in() -> None:
    with pytest.raises(PermissionError):
        CapabilityRegistry().register(FakeExternalProvider())
    reg = CapabilityRegistry(allow_external=True)
    reg.register(FakeExternalProvider())
    assert reg.names() == ["fake-cloud"]


def test_registry_rejects_duplicates_and_non_providers() -> None:
    reg = CapabilityRegistry()
    reg.register(MockProvider())
    with pytest.raises(ValueError):
        reg.register(MockProvider())
    with pytest.raises(TypeError):
        reg.register(object())  # type: ignore[arg-type]


def test_registry_without_providers_reports_planning_only() -> None:
    """T10: no image provider -> explicit error, never a fake success."""
    with pytest.raises(CapabilityError, match="only planning/prompt export"):
        CapabilityRegistry().select(make_request())


def test_registry_skips_external_provider_for_private_refs() -> None:
    reg = CapabilityRegistry(allow_external=True)
    reg.register(FakeExternalProvider())
    reg.register(MockProvider())
    assert reg.select(make_request(references=[ref("face-1")])).name == "mock"


def test_registry_preference_is_strict() -> None:
    reg = CapabilityRegistry(allow_external=True)
    reg.register(FakeExternalProvider())
    reg.register(MockProvider())
    with pytest.raises(EgressBlockedError):
        reg.select(make_request(provider_preference="fake-cloud", references=[ref("face-1")]))
    with pytest.raises(KeyError):
        reg.select(make_request(provider_preference="missing"))


def test_registry_required_capabilities() -> None:
    reg = CapabilityRegistry.offline_default()
    with pytest.raises(CapabilityError, match="mask_inpaint"):
        reg.select(make_request(), require=["mask_inpaint"])
    with pytest.raises(ValueError, match="unknown capability"):
        reg.select(make_request(), require=["teleport"])
