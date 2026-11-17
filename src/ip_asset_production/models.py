"""Runtime Pydantic models for the provider-facing contracts.

The JSON Schemas in ``schemas/`` remain the source of truth. ``tests/unit/test_models_vs_schemas.py``
checks that every model's required fields match its schema and that dumped instances validate.
Use :meth:`ContractModel.to_contract` (not ``model_dump``) when emitting JSON for a schema.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PLACEHOLDER_RE = re.compile(r"\{\{\s*[^{}]*?\s*\}\}")

IPType = Literal[
    "digital_human", "anime_human", "cartoon_animal", "anthropomorphic_object", "fantasy_creature", "other"
]
ReferenceRole = Literal[
    "identity", "face", "silhouette", "style", "pose", "outfit", "prop", "scene", "material", "product"
]
PermissionScope = Literal["private_local", "approved_external", "demo_public"]
ImageFormat = Literal["PNG", "JPEG", "WEBP", "PDF"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def to_contract(self) -> dict[str, Any]:
        """JSON-compatible dict for schema validation; ``None`` optionals are omitted."""
        return self.model_dump(mode="json", exclude_none=True)


class ReferenceImage(ContractModel):
    ref_id: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    role: ReferenceRole
    sha256: str | None = None
    subject_id: str | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    # Default-deny: an undeclared scope is treated as private and never leaves the machine.
    permission_scope: PermissionScope = "private_local"


class OutputSpec(ContractModel):
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    format: ImageFormat
    alpha_required: bool
    color_mode: str | None = None
    ppi: float | None = None
    trim_mm: tuple[float, float] | None = None
    bleed_mm: float | None = None
    safe_margin_pct: float | None = Field(default=None, ge=0, le=0.5)


class GenerationRequest(ContractModel):
    task_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    character_id: str = Field(min_length=1)
    character_version: str = Field(min_length=1)
    compiled_prompt: str = Field(min_length=1)
    output_spec: OutputSpec
    approval_status: Literal["pending", "approved"]
    provider_preference: str | None = None
    references: tuple[ReferenceImage, ...] = ()
    variable_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("compiled_prompt")
    @classmethod
    def _no_unresolved_placeholders(cls, value: str) -> str:
        # SPEC §7.1: an unresolved {{variable}} must never be sent to a provider.
        leftover = PLACEHOLDER_RE.findall(value)
        if leftover:
            raise ValueError(f"compiled_prompt contains unresolved placeholders: {sorted(set(leftover))}")
        return value


class ProviderCapabilities(ContractModel):
    name: str = Field(min_length=1)
    text_to_image: bool
    image_to_image: bool
    image_edit: bool
    multi_reference: bool
    mask_inpaint: bool
    seed: bool
    negative_prompt: bool
    alpha_native: bool
    native_sizes: tuple[tuple[int, int], ...]
    async_jobs: bool
    cost_estimate: bool
    max_images: int | None = Field(default=None, ge=1)
    max_reference_count: int | None = Field(default=None, ge=0)

    @field_validator("native_sizes")
    @classmethod
    def _positive_sizes(cls, value: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
        for w, h in value:
            if w < 1 or h < 1:
                raise ValueError(f"native size must be positive: {(w, h)}")
        return value


class TaskStatus(StrEnum):
    """SPEC §9.2 execution states (lower-case form used by generation-result schema)."""

    PENDING = "pending"
    QUEUED = "queued"
    GENERATING = "generating"
    POSTPROCESSING = "postprocessing"
    QA_PENDING = "qa_pending"
    PASSED = "passed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    EXPORTED = "exported"


class OutputFile(ContractModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)
    format: str = Field(min_length=1)
    alpha_verified: bool | None = None
    qa_status: Literal["passed", "failed", "needs_review"] | None = None


class GenerationResult(ContractModel):
    task_id: str = Field(min_length=1)
    status: TaskStatus
    attempt: int = Field(ge=0)
    outputs: tuple[OutputFile, ...] = ()
    provider: str | None = None
    native_size: tuple[int, int] | None = None
    errors: tuple[str, ...] = ()
    qa_summary: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> GenerationResult:
        if len(set(self.errors)) != len(self.errors):
            raise ValueError("errors must be unique")
        if self.status in (TaskStatus.PASSED, TaskStatus.EXPORTED) and not self.outputs:
            # A prompt is not a generated image: success requires real files.
            raise ValueError(f"status {self.status.value} requires at least one output file")
        return self
