"""Character profiles and immutable approved versions (SPEC §3, §2.3 G2/G3, T02/T17/T22/T28).

A ``CharacterVersion`` is validated against ``schemas/character-profile.schema.json`` on every
write. Drafts and pending candidates may be rewritten; once a version is ``approved`` its file
is frozen — any change (identity anchors, style, palette, topology...) produces a new version
that records ``parent_version``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ContractModel, IPType, ReferenceImage
from .paths import safe_join
from .schemas import SchemaRegistry

CreationMode = Literal["REFERENCE_DIRECT", "REFERENCE_TRANSFORM", "ORIGINAL_CREATE"]
ApprovalStatus = Literal["draft", "pending", "approved", "archived"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VERSION_RE = re.compile(r"^v(\d+)$")
IDENTITY_ROLES = frozenset({"identity", "face", "silhouette"})
# Fields whose change means "a different approved look" (SPEC §3.1, §4A.5).
IDENTITY_FIELDS = (
    "ip_type",
    "body_topology",
    "identity_anchors",
    "style_profile",
    "style_id",
    "palette",
    "anatomy",
    "canonical_image_sha256",
    "reference_manifest",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class CharacterError(ValueError):
    """Invalid character data or a forbidden transition."""


class ImmutableVersionError(CharacterError):
    """Attempt to overwrite an approved character version (create a new version instead)."""


class ExportConsent(ContractModel):
    provider: str
    data_categories: tuple[str, ...]
    purpose: str
    approved: bool
    approved_at: str | None = None


class CharacterVersion(ContractModel):
    character_id: str
    version: str
    approval_status: ApprovalStatus
    creation_mode: CreationMode
    ip_type: IPType
    body_topology: str = Field(min_length=1)
    style_profile: dict[str, Any]
    identity_anchors: tuple[str, ...]
    reference_manifest: tuple[ReferenceImage, ...]
    rights_acknowledgement: bool
    display_name: str | None = None
    allowed_variations: tuple[str, ...] = ()
    canonical_image_uri: str | None = None
    canonical_image_sha256: str | None = None
    palette: dict[str, str] = Field(default_factory=dict)
    keep_features: tuple[str, ...] = ()
    change_features: tuple[str, ...] = ()
    approved_at: str | None = None
    style_id: str | None = Field(default=None, pattern=r"^STYLE-\d{3}$")
    style_preview_refs: tuple[str, ...] = ()
    parent_version: str | None = None
    created_at: str | None = None
    anatomy: dict[str, Any] | None = None
    export_consent: ExportConsent | None = None

    @model_validator(mode="after")
    def _rules(self) -> CharacterVersion:
        if not ID_RE.match(self.character_id):
            raise ValueError("character_id must be lower-case kebab/snake (a-z0-9_-, max 64)")
        if not VERSION_RE.match(self.version):
            raise ValueError("version must look like v1, v2, ...")
        if "medium" not in self.style_profile:
            raise ValueError("style_profile.medium is required")
        if self.creation_mode != "ORIGINAL_CREATE" and not self.reference_manifest:
            raise ValueError(f"{self.creation_mode} requires at least one reference image")
        return self

    # -- gate checks --------------------------------------------------------------------------
    @property
    def is_digital_human(self) -> bool:
        return self.ip_type == "digital_human"

    @property
    def style_confirmed(self) -> bool:
        return bool(self.style_profile.get("style_confirmed"))

    @property
    def has_identity_reference(self) -> bool:
        return any(r.role in IDENTITY_ROLES for r in self.reference_manifest)

    def approval_problems(self) -> list[str]:
        """Everything that blocks G3 approval of this version (empty list = approvable)."""
        problems = []
        if not self.is_digital_human and not self.style_confirmed:
            problems.append("G2: 非数字人角色的 style_profile 尚未确认 (style_profile.style_confirmed=false)")
        if not self.is_digital_human and not self.style_id and not self.style_profile.get("custom_style"):
            problems.append("G2: 需要选择 STYLE-XXX 或记录 custom_style")
        if self.creation_mode == "REFERENCE_TRANSFORM" and (not self.keep_features or not self.change_features):
            problems.append("REFERENCE_TRANSFORM 必须记录 keep_features[] 与 change_features[]")
        if self.has_identity_reference and not self.rights_acknowledgement:
            problems.append("参考图包含身份/肖像：需要用户确认肖像与使用权限 (rights_acknowledgement)")
        if not self.identity_anchors:
            problems.append("identity_anchors 不能为空")
        if not self.canonical_image_uri or not self.canonical_image_sha256:
            problems.append("G3: 需要一张已生成并验证的定妆图 (canonical_image_uri / sha256)")
        return problems

    def identity_differs(self, other: CharacterVersion) -> list[str]:
        a, b = self.to_contract(), other.to_contract()
        return [f for f in IDENTITY_FIELDS if a.get(f) != b.get(f)]


def next_version(version: str) -> str:
    m = VERSION_RE.match(version)
    if not m:
        raise CharacterError(f"bad version {version!r}")
    return f"v{int(m.group(1)) + 1}"


class CharacterStore:
    """File-backed store under ``<root>/characters/<character_id>/<version>.json``.

    ``root`` should be a private workspace directory (default ``workspace/private``), which is
    git-ignored: reference URIs and canonical images are user data (SPEC §3.2, §11).
    """

    def __init__(
        self, root: Path, schemas: SchemaRegistry | None = None, *, clock: Callable[[], str] = utc_now
    ) -> None:
        self.root = Path(root)
        self.schemas = schemas or SchemaRegistry()
        self.clock = clock

    def _path(self, character_id: str, version: str) -> Path:
        if not ID_RE.match(character_id) or not VERSION_RE.match(version):
            raise CharacterError(f"invalid id/version {character_id!r}/{version!r}")
        return safe_join(self.root, f"characters/{character_id}/{version}.json")

    def _write(self, cv: CharacterVersion) -> Path:
        payload = cv.to_contract()
        self.schemas.validate("character_profile", payload)
        path = self._path(cv.character_id, cv.version)
        if path.exists() and self.load(cv.character_id, cv.version).approval_status == "approved":
            raise ImmutableVersionError(
                f"{cv.character_id}/{cv.version} is approved and immutable; create {next_version(cv.version)}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        if cv.approval_status == "approved":
            path.chmod(0o444)
        return path

    def load(self, character_id: str, version: str) -> CharacterVersion:
        path = self._path(character_id, version)
        if not path.is_file():
            raise CharacterError(f"no such character version {character_id}/{version}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.schemas.validate("character_profile", payload)
        return CharacterVersion.model_validate(payload)

    def versions(self, character_id: str) -> list[str]:
        d = safe_join(self.root, f"characters/{character_id}")
        if not d.is_dir():
            return []
        found = [p.stem for p in d.glob("v*.json") if VERSION_RE.match(p.stem)]
        return sorted(found, key=lambda v: int(v[1:]))

    def latest(self, character_id: str, *, approved_only: bool = False) -> CharacterVersion | None:
        for v in reversed(self.versions(character_id)):
            cv = self.load(character_id, v)
            if not approved_only or cv.approval_status == "approved":
                return cv
        return None

    # -- SPEC §9.2 upsert_character_version ------------------------------------------------------
    def save_candidate(self, draft: CharacterVersion) -> CharacterVersion:
        """Store a draft/pending candidate. Approved versions are never touched."""
        if draft.approval_status in ("approved", "archived"):
            raise CharacterError("use approve() to approve a candidate")
        cv = draft if draft.created_at else draft.model_copy(update={"created_at": self.clock()})
        self._write(cv)
        return cv

    def approve(self, character_id: str, version: str, *, approved_by_user: bool) -> CharacterVersion:
        """G3: freeze a pending candidate after explicit user approval."""
        if not approved_by_user:
            raise CharacterError("G3 requires explicit user approval")
        cv = self.load(character_id, version)
        if cv.approval_status == "approved":
            return cv
        problems = cv.approval_problems()
        if problems:
            raise CharacterError("cannot approve: " + "; ".join(problems))
        approved = cv.model_copy(update={"approval_status": "approved", "approved_at": self.clock()})
        self._write(approved)
        return approved

    def derive(self, base: CharacterVersion, **changes: Any) -> CharacterVersion:
        """New pending version from ``base`` (T17: changed anchors never overwrite history)."""
        latest = self.versions(base.character_id)
        new_version = next_version(latest[-1] if latest else base.version)
        payload = base.to_contract()
        payload.update(_jsonable(changes))
        payload.update(
            version=new_version,
            approval_status="pending",
            approved_at=None,
            parent_version=base.version,
            created_at=self.clock(),
        )
        look_changed = any(
            k in changes for k in ("identity_anchors", "style_profile", "style_id", "palette", "body_topology")
        )
        if look_changed and "canonical_image_sha256" not in changes:
            # A new look needs a new canonical image before it can be approved.
            payload["canonical_image_uri"] = None
            payload["canonical_image_sha256"] = None
        cv = CharacterVersion.model_validate(payload)
        self._write(cv)
        return cv

    def upsert_character_version(self, draft: CharacterVersion, approval: bool = False) -> CharacterVersion:
        """Save ``draft``; if it targets an approved version, branch to a new version instead."""
        path = self._path(draft.character_id, draft.version)
        if path.exists():
            existing = self.load(draft.character_id, draft.version)
            if existing.approval_status == "approved":
                if not existing.identity_differs(draft) and existing.to_contract() == draft.to_contract():
                    return existing
                changes = {k: v for k, v in draft.to_contract().items() if existing.to_contract().get(k) != v}
                for k in ("version", "approval_status", "approved_at", "created_at", "parent_version"):
                    changes.pop(k, None)
                derived = self.derive(existing, **changes)
                return (
                    self.approve(derived.character_id, derived.version, approved_by_user=True) if approval else derived
                )
        saved = self.save_candidate(draft.model_copy(update={"approval_status": "pending"}))
        return self.approve(saved.character_id, saved.version, approved_by_user=True) if approval else saved


def _jsonable(changes: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in changes.items():
        if isinstance(v, ContractModel):
            out[k] = v.to_contract()
        elif isinstance(v, tuple | list):
            out[k] = [i.to_contract() if isinstance(i, ContractModel) else i for i in v]
        else:
            out[k] = v
    return out
