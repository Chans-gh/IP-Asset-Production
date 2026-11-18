"""Template registry and structural applicability (SPEC §5.1, §5.2).

``catalogs/templates.json`` holds one record per generatable template: the schema-conformant
``template`` object (``schemas/asset-template.schema.json``) plus ``rules`` describing which
capability tags must be present (``skip_if_missing``) or trigger an adapted prompt
(``adapt_if_missing``). Capability tags come from the body topology and can be overridden per
character via ``anatomy.capability_tags`` / ``anatomy.absent_parts``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from .data import RepoData

Applicability = Literal["applicable", "adapt", "skip"]

# Human-readable explanations for missing tags (used in skip/adapt rationales).
TAG_EXPLANATION_ZH = {
    "has_limbs": "角色没有四肢",
    "has_hands": "角色没有手",
    "has_feet": "角色没有脚/腿",
    "has_paws": "角色没有爪",
    "wearable": "角色没有可穿戴/可附着部位",
    "visible_mouth": "角色没有可见的发声结构（嘴/喙）",
    "can_hold": "角色无法持握物体",
    "separable_parts": "角色不可分件",
    "non_human": "该模板只用于非人形/物种结构",
    "multi_character": "该任务需要第二个已批准角色",
    "has_face": "角色没有可识别的面部",
}


class CatalogError(ValueError):
    """Unknown template / use case or inconsistent catalog data."""


@dataclass(frozen=True)
class Template:
    template_id: str
    kind: Literal["foundation", "application"]
    category: str
    title: str
    prompt_id: str
    default_priority: str
    applicable_ip_types: tuple[str, ...]
    dependencies: tuple[str, ...]
    outputs: tuple[Mapping[str, Any], ...]
    use_cases: tuple[str, ...]
    variants: tuple[str, ...]
    qa_rules: tuple[str, ...]
    version: str
    skip_if_missing: tuple[str, ...] = ()
    adapt_if_missing: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Template:
        t = record["template"]
        rules = record.get("rules", {})
        return cls(
            template_id=t["template_id"],
            kind=t["kind"],
            category=t["category"],
            title=t["title"],
            prompt_id=t["prompt_id"],
            default_priority=t["default_priority"],
            applicable_ip_types=tuple(t["applicable_ip_types"]),
            dependencies=tuple(t["dependencies"]),
            outputs=tuple(t["outputs"]),
            use_cases=tuple(t["use_cases"]),
            variants=tuple(t.get("variants", ())),
            qa_rules=tuple(t.get("qa_rules", ())),
            version=t["version"],
            skip_if_missing=tuple(rules.get("skip_if_missing", ())),
            adapt_if_missing=tuple(rules.get("adapt_if_missing", ())),
            raw=t,
        )

    @property
    def primary_output(self) -> Mapping[str, Any]:
        return self.outputs[0]


@dataclass(frozen=True)
class SupportDecision:
    template_id: str
    applicability: Applicability
    rationale: str
    missing_tags: tuple[str, ...] = ()


class TemplateRegistry:
    def __init__(self, data: RepoData | None = None) -> None:
        self.data = data or RepoData()
        doc = self.data.templates
        self._templates = {t.template_id: t for t in (Template.from_record(r) for r in doc["templates"])}
        self.topology_tags: dict[str, tuple[str, ...]] = {k: tuple(v) for k, v in doc["topology_tags"].items()}
        self.use_cases: dict[str, dict[str, Any]] = doc["use_cases"]
        self.default_recommendation: tuple[str, ...] = tuple(doc["default_recommendation"])
        legacy = self.data.legacy_mapping["records"]
        self._legacy = {r["legacy_id"]: r for r in legacy}

    def __contains__(self, template_id: object) -> bool:
        return template_id in self._templates

    def __iter__(self) -> Iterator[Template]:
        return iter(self._templates.values())

    def ids(self) -> list[str]:
        return list(self._templates)

    def get(self, template_id: str) -> Template:
        try:
            return self._templates[template_id]
        except KeyError:
            raise CatalogError(f"unknown template_id {template_id!r}") from None

    def legacy(self, legacy_id: str) -> tuple[Template, str]:
        """Resolve one of the 41 legacy records to its template family and output variant."""
        try:
            rec = self._legacy[legacy_id]
        except KeyError:
            raise CatalogError(f"unknown legacy_id {legacy_id!r}") from None
        return self.get(rec["prompt_family"]), rec["variant"]

    def templates_for_use_case(self, use_case: str) -> tuple[str, ...]:
        try:
            return tuple(self.use_cases[use_case]["templates"])
        except KeyError:
            raise CatalogError(f"unknown use case {use_case!r}; known: {sorted(self.use_cases)}") from None

    # -- structural adaptation -------------------------------------------------------------
    def capability_tags(
        self, body_topology: str, anatomy: Mapping[str, Any] | None = None, *, extra: Iterable[str] = ()
    ) -> frozenset[str]:
        if body_topology not in self.topology_tags:
            raise CatalogError(f"unknown body_topology {body_topology!r}; known: {sorted(self.topology_tags)}")
        tags = set(self.topology_tags[body_topology])
        if anatomy:
            tags |= set(anatomy.get("capability_tags", ()))
            tags -= set(anatomy.get("absent_parts", ()))
        tags |= set(extra)
        return frozenset(tags)

    def supports(self, template_id: str, ip_type: str, tags: frozenset[str]) -> SupportDecision:
        """SPEC §5.2 ``supports(ip_type, body_topology, capability_tags)``."""
        t = self.get(template_id)
        if ip_type not in t.applicable_ip_types:
            return SupportDecision(template_id, "skip", f"{t.title} 不适用于 {ip_type}")
        missing = tuple(tag for tag in t.skip_if_missing if tag not in tags)
        if missing:
            why = "；".join(TAG_EXPLANATION_ZH.get(m, m) for m in missing)
            return SupportDecision(template_id, "skip", f"SKIPPED_NOT_APPLICABLE：{why}", missing)
        adapt = tuple(tag for tag in t.adapt_if_missing if tag not in tags)
        if adapt:
            why = "；".join(TAG_EXPLANATION_ZH.get(m, m) for m in adapt)
            return SupportDecision(template_id, "adapt", f"按角色自身结构适配：{why}", adapt)
        return SupportDecision(template_id, "applicable", "适用")
