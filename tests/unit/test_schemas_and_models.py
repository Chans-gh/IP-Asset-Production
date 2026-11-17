"""JSON Schemas are the contract; Pydantic runtime models must agree with them."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from ip_asset_production.models import (
    GenerationRequest,
    GenerationResult,
    OutputFile,
    OutputSpec,
    ProviderCapabilities,
    ReferenceImage,
    TaskStatus,
)
from ip_asset_production.providers.mock import DEFAULT_MOCK_CAPABILITIES
from ip_asset_production.schemas import SCHEMA_FILES, SchemaRegistry, SchemaValidationError

SHA = "a" * 64


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry()


def test_all_schema_files_are_valid_and_registered(registry: SchemaRegistry) -> None:
    assert registry.check_all_schemas() == []
    assert len(SCHEMA_FILES) == 8


def test_unknown_schema_name(registry: SchemaRegistry) -> None:
    with pytest.raises(KeyError):
        registry.schema("nope")


def test_validate_raises_with_messages(registry: SchemaRegistry) -> None:
    with pytest.raises(SchemaValidationError) as exc:
        registry.validate("provider_capability", {"name": "x"})
    assert "text_to_image" in str(exc.value)


def _required(schema: dict[str, Any]) -> set[str]:
    return set(schema.get("required", []))


def _model_required(model: type[BaseModel]) -> set[str]:
    return {name for name, f in model.model_fields.items() if f.is_required()}


@pytest.mark.parametrize(
    ("model", "schema_name", "pointer"),
    [
        (GenerationRequest, "generation_request", ()),
        (OutputSpec, "generation_request", ("properties", "output_spec")),
        (ReferenceImage, "generation_request", ("properties", "references", "items")),
        (ProviderCapabilities, "provider_capability", ()),
        (GenerationResult, "generation_result", ()),
        (OutputFile, "generation_result", ("properties", "outputs", "items")),
    ],
)
def test_model_fields_match_schema(
    registry: SchemaRegistry, model: type[BaseModel], schema_name: str, pointer: tuple[str, ...]
) -> None:
    schema: dict[str, Any] = registry.schema(schema_name)
    for key in pointer:
        schema = schema[key]
    assert set(model.model_fields) == set(schema["properties"]), "property sets differ"
    # A model may be stricter (require more) but never laxer than its schema.
    assert _required(schema) <= _model_required(model) | {
        name for name, f in model.model_fields.items() if f.default is not None and not f.is_required()
    }


def _request(**overrides: Any) -> GenerationRequest:
    base: dict[str, Any] = {
        "task_id": "t-1",
        "template_id": "NEW-01",
        "character_id": "char-demo",
        "character_version": "v1",
        "compiled_prompt": "a friendly fox mascot, full body",
        "output_spec": {"width_px": 1024, "height_px": 1024, "format": "PNG", "alpha_required": True},
        "approval_status": "approved",
        "references": [{"ref_id": "r1", "uri": "workspace/private/r1.png", "role": "identity"}],
    }
    base.update(overrides)
    return GenerationRequest.model_validate(base)


def test_request_dump_validates_against_schema(registry: SchemaRegistry) -> None:
    registry.validate("generation_request", _request().to_contract())


def test_request_reference_defaults_to_private(registry: SchemaRegistry) -> None:
    assert _request().references[0].permission_scope == "private_local"


@pytest.mark.parametrize("prompt", ["fox {{IP_ID}} waving", "fox {{ style_profile }}", "{{}}"])
def test_request_rejects_unresolved_placeholders(prompt: str) -> None:
    with pytest.raises(ValidationError, match="unresolved placeholders"):
        _request(compiled_prompt=prompt)


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _request(api_key="x")


def test_capabilities_dump_validates(registry: SchemaRegistry) -> None:
    registry.validate("provider_capability", DEFAULT_MOCK_CAPABILITIES.to_contract())


def test_result_dump_validates(registry: SchemaRegistry) -> None:
    result = GenerationResult(
        task_id="t-1",
        status=TaskStatus.QA_PENDING,
        attempt=1,
        outputs=(OutputFile(path="t-1/a.png", sha256=SHA, width_px=8, height_px=8, format="PNG"),),
        provider="mock",
        native_size=(8, 8),
        qa_summary={"is_mock": True},
    )
    registry.validate("generation_result", result.to_contract())


@pytest.mark.parametrize("status", [TaskStatus.PASSED, TaskStatus.EXPORTED])
def test_success_requires_real_outputs(status: TaskStatus) -> None:
    with pytest.raises(ValidationError, match="requires at least one output"):
        GenerationResult(task_id="t", status=status, attempt=1)


def test_failed_result_without_outputs_is_allowed() -> None:
    GenerationResult(task_id="t", status=TaskStatus.FAILED, attempt=3, errors=("timeout",))


def test_output_file_requires_hex_sha() -> None:
    with pytest.raises(ValidationError):
        OutputFile(path="x.png", sha256="not-a-hash", width_px=1, height_px=1, format="PNG")
