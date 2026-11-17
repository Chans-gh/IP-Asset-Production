"""JSON Schema registry. The files under ``schemas/`` are the authoritative contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .data import load_json
from .paths import repo_root

# Logical name -> file name. Names are used throughout code and tests.
SCHEMA_FILES: dict[str, str] = {
    "asset_plan": "asset-plan.schema.json",
    "asset_template": "asset-template.schema.json",
    "character_profile": "character-profile.schema.json",
    "generation_request": "generation-request.schema.json",
    "generation_result": "generation-result.schema.json",
    "provider_capability": "provider-capability.schema.json",
    "style_catalog": "style-catalog.schema.json",
    "style_preview_manifest": "style-preview-manifest.schema.json",
}


class SchemaValidationError(ValueError):
    def __init__(self, schema_name: str, errors: list[str]) -> None:
        self.schema_name = schema_name
        self.errors = errors
        super().__init__(f"{schema_name}: " + "; ".join(errors))


@dataclass
class SchemaRegistry:
    root: Path = field(default_factory=repo_root)
    _validators: dict[str, Draft202012Validator] = field(default_factory=dict, init=False, repr=False)

    @property
    def schema_dir(self) -> Path:
        return self.root / "schemas"

    def schema(self, name: str) -> dict[str, Any]:
        if name not in SCHEMA_FILES:
            raise KeyError(f"unknown schema {name!r}; known: {sorted(SCHEMA_FILES)}")
        data: dict[str, Any] = load_json(self.schema_dir / SCHEMA_FILES[name])
        return data

    def validator(self, name: str) -> Draft202012Validator:
        if name not in self._validators:
            schema = self.schema(name)
            Draft202012Validator.check_schema(schema)
            self._validators[name] = Draft202012Validator(schema)
        return self._validators[name]

    def errors(self, name: str, instance: Any) -> list[str]:
        """Return human-readable validation errors (empty list == valid)."""
        out = []
        for err in sorted(self.validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path)):
            loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
            out.append(f"{loc}: {err.message}")
        return out

    def validate(self, name: str, instance: Any) -> None:
        errs = self.errors(name, instance)
        if errs:
            raise SchemaValidationError(name, errs)

    def check_all_schemas(self) -> list[str]:
        """Meta-validate every schema file; also report schema files not registered."""
        problems: list[str] = []
        for name in SCHEMA_FILES:
            try:
                Draft202012Validator.check_schema(self.schema(name))
            except (SchemaError, OSError, ValueError) as exc:
                problems.append(f"{SCHEMA_FILES[name]}: {exc}")
        on_disk = {p.name for p in self.schema_dir.glob("*.schema.json")}
        for extra in sorted(on_disk - set(SCHEMA_FILES.values())):
            problems.append(f"{extra}: schema file is not registered in SCHEMA_FILES")
        return problems
