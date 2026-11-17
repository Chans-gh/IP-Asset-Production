"""Loaders for the repository's versioned data files (catalogs, styles, prompts, tests)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from .paths import repo_root, safe_join

JsonObj = dict[str, Any]


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path: Path) -> list[JsonObj]:
    rows: list[JsonObj] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno}: expected a JSON object")
            rows.append(row)
    return rows


@dataclass
class RepoData:
    """Lazy accessor for all static data files under the repository root."""

    root: Path = field(default_factory=repo_root)

    def path(self, relative: str) -> Path:
        return safe_join(self.root, relative)

    def text(self, relative: str) -> str:
        return self.path(relative).read_text(encoding="utf-8")

    @cached_property
    def asset_catalog(self) -> JsonObj:
        data: JsonObj = load_json(self.path("catalogs/asset_catalog.json"))
        return data

    @cached_property
    def legacy_mapping(self) -> JsonObj:
        data: JsonObj = load_json(self.path("catalogs/legacy_41_mapping.json"))
        return data

    @cached_property
    def style_catalog(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/catalog.json"))
        return data

    @cached_property
    def style_taxonomy(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/taxonomy.json"))
        return data

    @cached_property
    def style_prototypes(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/prototypes.json"))
        return data

    @cached_property
    def style_compatibility(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/compatibility.json"))
        return data

    @cached_property
    def style_aliases(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/legacy_style_aliases.json"))
        return data

    @cached_property
    def preview_manifest(self) -> JsonObj:
        data: JsonObj = load_json(self.path("styles/preview_manifest.json"))
        return data

    @cached_property
    def preview_requests(self) -> list[JsonObj]:
        return load_jsonl(self.path("styles/preview_requests.jsonl"))

    @cached_property
    def acceptance_cases(self) -> JsonObj:
        data: JsonObj = load_json(self.path("tests/acceptance_cases.json"))
        return data
