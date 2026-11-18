"""Deterministic asset planner (SPEC §5.3, §9.2 ``recommend_assets``; T05, T18).

1. read character + goals (no goal -> default recommendation, never "please list assets");
2. filter applicability (``skip`` keeps its reason);
3. detect reusable passed assets by character_version + template version;
4. close ``use_case -> templates -> dependencies`` into a DAG (cycles rejected);
5. assign P0/P1/P2 (explicit targets and their dependencies are raised to P0);
6. estimate image counts / calls for the G4 confirmation;
7. emit a schema-valid ``asset-plan`` plus a topological execution order.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .catalog import CatalogError, SupportDecision, TemplateRegistry
from .character import CharacterVersion
from .schemas import SchemaRegistry

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}
# Independent images generated per template (composites are produced by postprocessing).
GENERATION_COUNTS = {
    "CANONICAL": 1,
    "BASE_VIEW": 1,  # one design sheet per group
    "BASE_DETAIL": 4,
    "BASE_EXPRESSION": 1,
    "BASE_POSE": 1,
    "BASE_STRUCTURE": 4,
    "BASE_OUTFIT": 3,
    "BASE_PROFILE": 1,
    "NEW-02": 4,
    "NEW-04": 4,
    "NEW-05": 4,
    "NEW-06": 6,
    "NEW-07": 6,
    "NEW-08": 4,
    "NEW-09": 4,
    "NEW-10": 4,
    "NEW-11": 4,
    "NEW-12": 5,
    "APP-02": 4,
    "APP-03": 4,
    "APP-04": 3,
    "APP-05": 5,
    "APP-06": 3,
    "APP-07": 2,
    "APP-08": 6,
    "APP-09": 3,
    "APP-10": 2,
}
COMPOSITES = {"NEW-01": 1, "NEW-02": 1, "NEW-04": 1, "APP-01": 1}
USE_CASE_ID = re.compile(r"^[a-z_]+$")


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class ExistingAsset:
    template_id: str
    character_id: str
    character_version: str
    template_version: str
    status: str
    sha256: str
    path: str


@dataclass
class PlanResult:
    plan: dict[str, Any]
    execution_order: list[str]
    reused: dict[str, ExistingAsset] = field(default_factory=dict)
    skipped: dict[str, SupportDecision] = field(default_factory=dict)
    estimates: dict[str, Any] = field(default_factory=dict)
    explanation_zh: list[str] = field(default_factory=list)

    @property
    def tasks(self) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = self.plan["tasks"]
        return tasks

    def task(self, template_id: str) -> dict[str, Any]:
        for t in self.tasks:
            if t["template_id"] == template_id:
                return t
        raise KeyError(template_id)


def generation_count(template_id: str, variables: Mapping[str, Any] | None = None) -> int:
    variables = variables or {}
    if template_id == "APP-01":
        return -(-int(variables.get("emoji_count", 16)) // 8)  # ADR-016: 8 busts per sheet call
    if template_id == "APP-08":
        return int(variables.get("sticker_count", GENERATION_COUNTS["APP-08"]))
    if template_id == "APP-02" and variables.get("states"):
        return len(variables["states"])
    return GENERATION_COUNTS.get(template_id, 1)


def topo_order(nodes: Iterable[str], deps: Mapping[str, Sequence[str]]) -> list[str]:
    """Deterministic Kahn ordering; raises :class:`PlanError` on cycles."""
    nodes = list(dict.fromkeys(nodes))
    indeg = {n: 0 for n in nodes}
    for n in nodes:
        for d in deps.get(n, ()):
            if d not in indeg:
                raise PlanError(f"{n} depends on {d}, which is not in the plan")
            indeg[n] += 1
    ready = sorted(n for n, k in indeg.items() if k == 0)
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in nodes:
            if n in deps.get(m, ()):
                indeg[m] -= 1
                if indeg[m] == 0:
                    ready.append(m)
                    ready.sort()
    if len(order) != len(nodes):
        cyclic = sorted(set(nodes) - set(order))
        raise PlanError(f"dependency cycle among {cyclic}")
    return order


class AssetPlanner:
    def __init__(self, registry: TemplateRegistry | None = None, schemas: SchemaRegistry | None = None) -> None:
        self.registry = registry or TemplateRegistry()
        self.schemas = schemas or SchemaRegistry(self.registry.data.root)

    def _targets(self, use_cases: Sequence[str], templates: Sequence[str]) -> tuple[list[str], dict[str, str]]:
        targets: list[str] = []
        variant_of: dict[str, str] = {}
        for uc in use_cases:
            if not USE_CASE_ID.match(uc):
                raise PlanError(f"invalid use case id {uc!r}")
            if uc == "full_set":
                targets += [t.template_id for t in self.registry if t.kind == "foundation"]
                continue
            targets += self.registry.templates_for_use_case(uc)
        for tid in templates:
            if tid in self.registry:
                targets.append(tid)
                continue
            try:
                family, variant = self.registry.legacy(tid)  # one of the 41 legacy ids
            except CatalogError:
                raise PlanError(f"unknown template or legacy id {tid!r}") from None
            targets.append(family.template_id)
            variant_of.setdefault(family.template_id, variant)
        return list(dict.fromkeys(targets)), variant_of

    def recommend_assets(
        self,
        cv: CharacterVersion,
        use_cases: Sequence[str] = (),
        *,
        templates: Sequence[str] = (),
        existing_assets: Sequence[ExistingAsset] = (),
        plan_id: str | None = None,
        variables: Mapping[str, Mapping[str, Any]] | None = None,
        extra_tags: Iterable[str] = (),
    ) -> PlanResult:
        explicit = bool(use_cases or templates)
        targets, variant_of = self._targets(use_cases, templates)
        if not explicit:
            targets = list(self.registry.default_recommendation)
        tags = self.registry.capability_tags(cv.body_topology, cv.anatomy, extra=extra_tags)

        # dependency closure (with applicability)
        decisions: dict[str, SupportDecision] = {}
        deps: dict[str, list[str]] = {}
        stack = list(reversed(targets))
        while stack:
            tid = stack.pop()
            if tid in decisions:
                continue
            decision = self.registry.supports(tid, cv.ip_type, tags)
            decisions[tid] = decision
            if decision.applicability == "skip":
                continue
            tdeps = list(self.registry.get(tid).dependencies)
            deps[tid] = tdeps
            stack.extend(reversed(tdeps))
        active = [t for t, d in decisions.items() if d.applicability != "skip"]
        for tid in active:
            missing_deps = [d for d in deps[tid] if decisions[d].applicability == "skip"]
            if missing_deps:
                deps[tid] = [d for d in deps[tid] if d not in missing_deps]
        order = topo_order(active, deps)

        # priorities
        prio = {t: self.registry.get(t).default_priority for t in active}
        if explicit:
            raised = [t for t in targets if t in prio]
            for t in raised:
                prio[t] = "P0"
            # dependencies of a raised target are at least as urgent
            for t in reversed(order):
                for d in deps[t]:
                    if PRIORITY_RANK[prio[t]] < PRIORITY_RANK[prio[d]]:
                        prio[d] = prio[t]

        # reuse (SPEC §5.3 step 3, §9.3)
        reused: dict[str, ExistingAsset] = {}
        for a in existing_assets:
            if (
                a.template_id in prio
                and a.character_id == cv.character_id
                and a.character_version == cv.version
                and a.template_version == self.registry.get(a.template_id).version
                and a.status in ("passed", "exported")
            ):
                reused[a.template_id] = a

        tasks: list[dict[str, Any]] = []
        for tid in [*order, *[t for t in decisions if t not in active]]:
            d = decisions[tid]
            t = self.registry.get(tid)
            task: dict[str, Any] = {
                "task_id": f"{cv.character_id}-{cv.version}-{tid}",
                "template_id": tid,
                "priority": prio.get(tid, t.default_priority),
                "applicability": d.applicability,
                "dependencies": [f"{cv.character_id}-{cv.version}-{x}" for x in deps.get(tid, [])],
                "rationale": d.rationale
                if tid not in reused
                else f"{d.rationale}；复用已通过 QA 的产物 {reused[tid].path}",
                "output_profile_id": f"{tid}:{t.primary_output['width_px']}x{t.primary_output['height_px']}",
            }
            if tid in variant_of:
                task["variant"] = variant_of[tid]
            elif t.variants:
                task["variant"] = t.variants[0]
            if d.applicability == "skip":
                task["skip_reason"] = d.rationale
            tasks.append(task)

        plan = {
            "plan_id": plan_id or f"plan-{cv.character_id}-{cv.version}",
            "character_id": cv.character_id,
            "character_version": cv.version,
            "user_use_cases": list(dict.fromkeys(use_cases)) or ["default_recommendation"],
            "approval_status": "pending",
            "tasks": tasks,
        }
        self.schemas.validate("asset_plan", plan)

        to_run = [t for t in order if t not in reused]
        variables = variables or {}
        per_template = {t: generation_count(t, variables.get(t)) for t in to_run}
        estimates = {
            "generation_calls": sum(per_template.values()),
            "composites": sum(COMPOSITES.get(t, 0) for t in to_run),
            "per_template": per_template,
            "reused": sorted(reused),
            "note_zh": "调用次数按每张独立图一次估计；费用以 Provider 实际申报为准，不杜撰价格。",
        }
        explanation = []
        for tid in order:
            t = self.registry.get(tid)
            role = "必做" if prio[tid] == "P0" else ("推荐" if prio[tid] == "P1" else "可选")
            explanation.append(
                f"{prio[tid]} {role}：{t.title}（{tid}）× {per_template.get(tid, 0)} 张 — {decisions[tid].rationale}"
            )
        for tid, d in decisions.items():
            if d.applicability == "skip":
                explanation.append(f"跳过：{self.registry.get(tid).title}（{tid}）— {d.rationale}")
        return PlanResult(
            plan=plan,
            execution_order=order,
            reused=reused,
            skipped={t: d for t, d in decisions.items() if d.applicability == "skip"},
            estimates=estimates,
            explanation_zh=explanation,
        )


def approve_plan(
    result: PlanResult, *, approved_by_user: bool, schemas: SchemaRegistry | None = None
) -> dict[str, Any]:
    """G4: the user confirms scope, count and cost."""
    if not approved_by_user:
        raise PlanError("G4 requires explicit user approval of the plan")
    plan = dict(result.plan)
    plan["approval_status"] = "approved"
    (schemas or SchemaRegistry()).validate("asset_plan", plan)
    result.plan = plan
    return plan
