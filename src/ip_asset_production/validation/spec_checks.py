"""Static consistency checks across SPEC, catalogs, prompts, styles, schemas and test cases.

Every check returns a list of problems; an empty list means the check passed. The checks
encode M0 acceptance ("41+14+10 records complete, every item has a prompt") plus the
cross-file invariants that keep the SPEC and machine-readable data from drifting apart.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..data import RepoData
from ..paths import UnsafePathError, safe_join
from ..schemas import SchemaRegistry

CATEGORY_IDS = [f"A{i:02d}" for i in range(1, 14)]
NEW_IDS = [f"NEW-{i:02d}" for i in range(1, 15)]
APP_IDS = [f"APP-{i:02d}" for i in range(1, 11)]
STYLE_IDS = [f"STYLE-{i:03d}" for i in range(1, 49)]
GROUP_IDS = [f"G{i:02d}" for i in range(1, 9)]
STYLES_PER_GROUP = 6
LEGACY_IDS = (
    [f"foundation-{i:02d}" for i in range(1, 9)]
    + [f"complete-{i:02d}" for i in range(1, 10)]
    + [f"detail-{i:02d}" for i in range(1, 25)]
)
LEGACY_VARIANTS = {"clean", "annotated"}
ACCEPTANCE_IDS = [f"T{i:02d}" for i in range(1, 30)]

# v1.2 previews cover the three core prototypes; FANTASY_PROTO is deferred (ADR-013).
CORE_PREVIEW_SUBJECTS = {
    "anime_human": "human",
    "animal": "animal",
    "anthropomorphic_object": "object",
}
SUBJECT_COLUMNS = ["anime_human", "animal", "anthropomorphic_object", "fantasy_creature"]
STYLE_SCALAR_DIMENSIONS = ("medium", "tradition", "proportions", "material", "linework", "detail")
PREVIEW_SIZE = (1024, 1024)

STYLE_TABLE_ROW = re.compile(
    r"^\| (STYLE-\d{3}) \| ([^|]+?) \| ([^|]+?) \|"
    r"\s*(✓|—)\s*\|\s*(✓|—)\s*\|\s*(✓|—)\s*\|\s*(✓|—)\s*\| ([^|]+?) \|\s*$",
    re.M,
)
GROUP_HEADING = re.compile(r"^### (G0\d)｜")
TEXT_BLOCK_AFTER_HEADING = re.compile(r"^### (?P<id>[A-Z][A-Z0-9_-]+)[^\n]*\n+```text\n(?P<body>.*?)\n```", re.M | re.S)


@dataclass
class CheckResult:
    name: str
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class Report:
    results: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def problems(self) -> list[str]:
        return [f"[{r.name}] {p}" for r in self.results for p in r.problems]


def _dupes(values: list[Any]) -> list[Any]:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def _expect_sequence(label: str, actual: list[str], expected: list[str]) -> list[str]:
    if actual == expected:
        return []
    problems = []
    if d := _dupes(actual):
        problems.append(f"{label}: duplicate ids {d}")
    if missing := [x for x in expected if x not in actual]:
        problems.append(f"{label}: missing ids {missing}")
    if extra := [x for x in actual if x not in expected]:
        problems.append(f"{label}: unexpected ids {extra}")
    if not problems:
        problems.append(f"{label}: ids out of order")
    return problems


def _text_blocks(markdown: str) -> dict[str, str]:
    """Map ``### ID ...`` headings to the first ```text block that follows them."""
    return {m.group("id"): m.group("body").strip() for m in TEXT_BLOCK_AFTER_HEADING.finditer(markdown)}


def _expand_legacy_refs(line: str) -> list[str]:
    """Expand mapping notation such as ``detail-13/14/21..24`` into explicit ids."""
    ids: list[str] = []
    for prefix, body in re.findall(r"`([a-z]+)-([0-9./]+)`", line):
        for part in body.split("/"):
            if ".." in part:
                lo, hi = part.split("..")
                ids.extend(f"{prefix}-{i:02d}" for i in range(int(lo), int(hi) + 1))
            elif part:
                ids.append(f"{prefix}-{int(part):02d}")
    return ids


# --------------------------------------------------------------------------- schemas


def check_schemas(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    return schemas.check_all_schemas()


# --------------------------------------------------------------------------- asset catalog


def check_asset_catalog(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    cat = data.asset_catalog
    problems: list[str] = []
    categories = [c["id"] for c in cat["categories"]]
    problems += _expect_sequence("categories", categories, CATEGORY_IDS)
    priorities = set(cat["taxonomies"]["priorities"])
    for c in cat["categories"]:
        if c["default_priority"] not in priorities:
            problems.append(f"category {c['id']}: invalid default_priority {c['default_priority']}")

    new = cat["new_asset_templates"]
    problems += _expect_sequence("new_asset_templates", [t["id"] for t in new], NEW_IDS)
    if d := _dupes([t["prompt_id"] for t in new]):
        problems.append(f"new_asset_templates: duplicate prompt_id {d}")
    for t in new:
        if t["category"] not in categories:
            problems.append(f"{t['id']}: unknown category {t['category']}")
        if t["default_priority"] not in priorities:
            problems.append(f"{t['id']}: invalid default_priority {t['default_priority']}")
        if t.get("kind") != "foundation":
            problems.append(f"{t['id']}: kind must be 'foundation'")

    apps = cat["application_kits"]
    problems += _expect_sequence("application_kits", [a["id"] for a in apps], APP_IDS)
    for a in apps:
        if a.get("kind") != "application":
            problems.append(f"{a['id']}: kind must be 'application'")
        if a["prompt_id"] != a["id"]:
            problems.append(f"{a['id']}: prompt_id {a['prompt_id']} should equal kit id")

    mapping_file = cat.get("legacy_mapping_file")
    if not mapping_file or not (data.root / "catalogs" / mapping_file).is_file():
        problems.append(f"legacy_mapping_file {mapping_file!r} not found under catalogs/")
    return problems


# --------------------------------------------------------------------------- legacy 41


def check_legacy_mapping(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    legacy = data.legacy_mapping
    records = legacy["records"]
    problems: list[str] = []
    ids = [r["legacy_id"] for r in records]
    problems += _expect_sequence("legacy records", ids, LEGACY_IDS)
    if legacy.get("source_count") != len(LEGACY_IDS) or len(records) != len(LEGACY_IDS):
        problems.append(f"expected 41 legacy records, source_count={legacy.get('source_count')} len={len(records)}")

    categories = {c["id"] for c in data.asset_catalog["categories"]}
    families = set(_text_blocks(data.text("prompts/common-and-legacy.md")))
    for r in records:
        lid = r["legacy_id"]
        if r["mapped_category"] not in categories:
            problems.append(f"{lid}: unknown category {r['mapped_category']}")
        if r["prompt_family"] not in families:
            problems.append(f"{lid}: prompt family {r['prompt_family']} has no ```text block in common-and-legacy.md")
        if r["variant"] not in LEGACY_VARIANTS:
            problems.append(f"{lid}: unknown variant {r['variant']}")
        if r.get("publish_raw_source") is not False:
            problems.append(f"{lid}: publish_raw_source must be false in the public repo")
        # SPEC/prompts: detail even = annotated, odd = clean; others are clean.
        num = int(lid.rsplit("-", 1)[1])
        expected_variant = "annotated" if lid.startswith("detail-") and num % 2 == 0 else "clean"
        if r["variant"] != expected_variant:
            problems.append(f"{lid}: variant {r['variant']} but documented rule says {expected_variant}")
    return problems


def check_legacy_prompt_coverage(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    """Each legacy id is listed under exactly its own family's ``映射：`` line in the prompts."""
    text = data.text("prompts/common-and-legacy.md")
    by_id = {r["legacy_id"]: r for r in data.legacy_mapping["records"]}
    mapped: dict[str, set[str]] = {}
    family = None
    for line in text.splitlines():
        if m := re.match(r"^### (BASE_[A-Z_]+)", line):
            family = m.group(1)
        elif line.startswith("映射：") and family:
            for lid in _expand_legacy_refs(line):
                mapped.setdefault(lid, set()).add(family)
    problems = []
    for lid in by_id:
        fams = mapped.get(lid)
        if not fams:
            problems.append(f"{lid}: not listed in any 映射 line of common-and-legacy.md")
        elif fams != {by_id[lid]["prompt_family"]}:
            problems.append(f"{lid}: prompts map it to {sorted(fams)}, catalog says {by_id[lid]['prompt_family']}")
    for lid in sorted(set(mapped) - set(by_id)):
        problems.append(f"{lid}: listed in prompts but absent from legacy_41_mapping.json")
    return problems


def check_source_audit(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    rows = re.findall(
        r"^\| `([a-z]+-\d{2})` \| (A\d\d) \| `(BASE_[A-Z_]+)` \| (\w+) \|\s*$",
        data.text("docs/SOURCE_AUDIT.md"),
        re.M,
    )
    audit = {lid: (cat, fam, var) for lid, cat, fam, var in rows}
    problems = []
    if len(rows) != len(audit):
        problems.append("SOURCE_AUDIT.md has duplicate rows")
    for r in data.legacy_mapping["records"]:
        want = (r["mapped_category"], r["prompt_family"], r["variant"])
        got = audit.get(r["legacy_id"])
        if got != want:
            problems.append(f"{r['legacy_id']}: SOURCE_AUDIT.md has {got}, mapping has {want}")
    for lid in sorted(set(audit) - {r["legacy_id"] for r in data.legacy_mapping["records"]}):
        problems.append(f"{lid}: in SOURCE_AUDIT.md but not in mapping")
    return problems


# --------------------------------------------------------------------------- prompts


def check_prompt_coverage(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    problems: list[str] = []
    common_text = data.text("prompts/common-and-legacy.md")
    common = _text_blocks(common_text)
    for name in ("COMMON-LOCK", "COMMON-OUTPUT"):
        if not re.search(rf"^## PROMPT: {name}\n+```text\n.+?\n```", common_text, re.M | re.S):
            problems.append(f"common-and-legacy.md: missing '## PROMPT: {name}' text block")
    for fam in sorted({r["prompt_family"] for r in data.legacy_mapping["records"]}):
        if not common.get(fam):
            problems.append(f"common-and-legacy.md: family {fam} has no prompt text")

    new_blocks = _text_blocks(data.text("prompts/new-assets.md"))
    for tid in NEW_IDS:
        if not new_blocks.get(tid):
            problems.append(f"new-assets.md: {tid} has no ```text prompt block")
    for extra in sorted(k for k in new_blocks if k.startswith("NEW-") and k not in NEW_IDS):
        problems.append(f"new-assets.md: orphan prompt {extra} not in asset_catalog.json")

    app_blocks = _text_blocks(data.text("prompts/application-kits.md"))
    for aid in APP_IDS:
        if not app_blocks.get(aid):
            problems.append(f"application-kits.md: {aid} has no ```text prompt block")
    for extra in sorted(k for k in app_blocks if k.startswith("APP-") and k not in APP_IDS):
        problems.append(f"application-kits.md: orphan prompt {extra} not in asset_catalog.json")

    # Files the skill core prompt points at must exist.
    core = data.text("prompts/skill-core.md")
    for ref in re.findall(r"`((?:\.\./)?[\w./-]+\.(?:md|json))`", core):
        target = (data.root / "prompts" / ref).resolve()
        if not target.is_file():
            problems.append(f"skill-core.md references missing file {ref}")
    return problems


# --------------------------------------------------------------------------- styles


def check_style_catalog(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    cat = data.style_catalog
    problems = [f"schema: {e}" for e in schemas.errors("style_catalog", cat)]
    styles = cat["styles"]
    problems += _expect_sequence("style groups", [g["group_id"] for g in cat["groups"]], GROUP_IDS)
    problems += _expect_sequence("styles", [s["style_id"] for s in styles], STYLE_IDS)
    if cat["total_styles"] != len(styles):
        problems.append(f"total_styles={cat['total_styles']} but {len(styles)} entries")
    per_group = Counter(s["group_id"] for s in styles)
    for gid in GROUP_IDS:
        if per_group.get(gid, 0) != STYLES_PER_GROUP:
            problems.append(f"group {gid} has {per_group.get(gid, 0)} styles, expected {STYLES_PER_GROUP}")
    for label, key in (("display_name_zh", "display_name_zh"), ("prompt_fragment_en", "prompt_fragment_en")):
        if d := _dupes([s[key] for s in styles]):
            problems.append(f"duplicate {label}: {d}")

    dims = data.style_taxonomy["dimensions"]
    subjects = set(data.style_taxonomy["subject_types"])
    for s in styles:
        sid = s["style_id"]
        for key in STYLE_SCALAR_DIMENSIONS:
            if s[key] not in dims[key]:
                problems.append(f"{sid}: {key}={s[key]!r} not in taxonomy")
        if bad := sorted(set(s["mood"]) - set(dims["mood"])):
            problems.append(f"{sid}: mood values {bad} not in taxonomy")
        if bad := sorted(set(s["supported_subjects"]) - subjects):
            problems.append(f"{sid}: supported_subjects {bad} not in taxonomy subject_types")
        if s["preview_prototype_preference"] not in s["supported_subjects"]:
            problems.append(f"{sid}: preview_prototype_preference not among supported_subjects")
        if s["preview_prototype_preference"] not in CORE_PREVIEW_SUBJECTS:
            problems.append(f"{sid}: preview_prototype_preference must be a core v1.2 preview prototype")
        if not set(s["supported_subjects"]) & set(CORE_PREVIEW_SUBJECTS):
            problems.append(f"{sid}: supports no core preview prototype, so it can never get a v1 preview")
    return problems


def _style_table(markdown: str) -> dict[str, dict[str, Any]]:
    group = None
    rows: dict[str, dict[str, Any]] = {}
    for line in markdown.splitlines():
        if m := GROUP_HEADING.match(line):
            group = m.group(1)
            continue
        if m := STYLE_TABLE_ROW.match(line):
            sid = m.group(1)
            rows[sid] = {
                "group_id": group,
                "display_name_zh": m.group(2).strip(),
                "description_zh": m.group(3).strip(),
                "supported_subjects": sorted(SUBJECT_COLUMNS[i] for i in range(4) if m.group(4 + i) == "✓"),
                "prompt_fragment_en": m.group(8).strip(),
            }
    return rows


def _compare_style_table(doc_name: str, markdown: str, data: RepoData) -> list[str]:
    table = _style_table(markdown)
    problems = []
    if sorted(table) != STYLE_IDS:
        problems.append(f"{doc_name}: style table has {len(table)} rows; missing {sorted(set(STYLE_IDS) - set(table))}")
    for s in data.style_catalog["styles"]:
        row = table.get(s["style_id"])
        if row is None:
            continue
        for key, doc_value in row.items():
            cat_value = sorted(s[key]) if key == "supported_subjects" else s[key]
            if doc_value != cat_value:
                problems.append(f"{doc_name}: {s['style_id']}.{key} differs (doc={doc_value!r}, catalog={cat_value!r})")
    return problems


def check_spec_style_table(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    return _compare_style_table("docs/SPEC.md", data.text("docs/SPEC.md"), data) + _compare_style_table(
        "docs/STYLE_LIBRARY_AND_PREVIEWS.md", data.text("docs/STYLE_LIBRARY_AND_PREVIEWS.md"), data
    )


def check_style_support_files(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    problems: list[str] = []
    tax = data.style_taxonomy
    protos = data.style_prototypes["prototypes"]
    if sorted(protos) != sorted(tax["subject_types"]):
        problems.append(f"prototypes {sorted(protos)} != taxonomy subject_types {sorted(tax['subject_types'])}")
    if d := _dupes([p["id"] for p in protos.values()]):
        problems.append(f"duplicate prototype ids {d}")
    for key, p in protos.items():
        if not p.get("subject_en") or not p.get("subject_zh"):
            problems.append(f"prototype {key}: subject_en/subject_zh required")

    dims = tax["dimensions"]
    constraints = data.style_compatibility["constraints"]
    if d := _dupes([c["id"] for c in constraints]):
        problems.append(f"compatibility: duplicate constraint ids {d}")
    for c in constraints:
        for dim, value in c["applies_to"].items():
            if dim not in dims:
                problems.append(f"compatibility {c['id']}: unknown dimension {dim}")
            elif value not in dims[dim]:
                problems.append(f"compatibility {c['id']}: {dim}={value!r} not in taxonomy")

    aliases = data.style_aliases["aliases"]
    for old, new in aliases.items():
        if new not in STYLE_IDS:
            problems.append(f"alias {old} -> {new}: target is not a stable style id")
        if old in STYLE_IDS:
            problems.append(f"alias {old} collides with a stable style id")
    return problems


def _planned_previews(data: RepoData) -> dict[str, tuple[str, str]]:
    """preview_id -> (style_id, subject_type) implied by the catalog's applicability."""
    protos = data.style_prototypes["prototypes"]
    out: dict[str, tuple[str, str]] = {}
    for s in data.style_catalog["styles"]:
        for subject in CORE_PREVIEW_SUBJECTS:
            if subject in s["supported_subjects"]:
                out[f"{s['style_id']}-{protos[subject]['id']}"] = (s["style_id"], subject)
    return out


def check_preview_manifest(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    manifest = data.preview_manifest
    problems = [f"schema: {e}" for e in schemas.errors("style_preview_manifest", manifest)]
    items = manifest["items"]
    if manifest["total_planned"] != len(items):
        problems.append(f"total_planned={manifest['total_planned']} but {len(items)} items")
    if d := _dupes([i["preview_id"] for i in items]):
        problems.append(f"duplicate preview_id {d}")

    planned = _planned_previews(data)
    got = {i["preview_id"] for i in items}
    if missing := sorted(set(planned) - got):
        problems.append(f"applicable style×prototype pairs missing from manifest: {missing}")
    if extra := sorted(got - set(planned)):
        problems.append(f"manifest previews for unsupported/unknown style×prototype pairs: {extra}")
    if uncovered := sorted(set(STYLE_IDS) - {i["style_id"] for i in items}):
        problems.append(f"styles with no planned preview: {uncovered}")

    # SPEC §12 M1A states the planned request count explicitly.
    m = re.search(r"(\d+) 计划预览请求", data.text("docs/SPEC.md"))
    if m and int(m.group(1)) != len(items):
        problems.append(f"SPEC states {m.group(1)} planned preview requests, manifest has {len(items)}")

    styles = {s["style_id"]: s for s in data.style_catalog["styles"]}
    protos = data.style_prototypes["prototypes"]
    for item in items:
        pid = item["preview_id"]
        if pid not in planned:
            continue
        style_id, subject = planned[pid]
        style = styles[style_id]
        if (item["style_id"], item["subject_type"], item["prototype_id"]) != (style_id, subject, protos[subject]["id"]):
            problems.append(f"{pid}: style/subject/prototype fields inconsistent with preview_id")
        expected_file = f"styles/previews/{CORE_PREVIEW_SUBJECTS[subject]}/{pid}.png"
        if item["expected_file"] != expected_file:
            problems.append(f"{pid}: expected_file {item['expected_file']} != {expected_file}")
        prompt = item["prompt"]
        for label, fragment in (
            ("prototype subject_en", protos[subject]["subject_en"]),
            ("style prompt_fragment_en", style["prompt_fragment_en"]),
            ("style negative_prompt_en", style["negative_prompt_en"]),
        ):
            if fragment not in prompt:
                problems.append(f"{pid}: prompt does not contain the {label}")
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != item["prompt_sha256"]:
            problems.append(f"{pid}: prompt_sha256 mismatch")
        spec = item["output_spec"]
        if (spec.get("width_px"), spec.get("height_px"), spec.get("format")) != (*PREVIEW_SIZE, "PNG"):
            problems.append(f"{pid}: preview output_spec must be 1024x1024 PNG")
        problems += _preview_status_problems(data, item)
    return problems


def _preview_status_problems(data: RepoData, item: dict[str, Any]) -> list[str]:
    """A planned preview is never a real image; an approved one must be real, non-mock and reviewed."""
    pid, status, actual = item["preview_id"], item["status"], item["actual_file"]
    problems = []
    if status == "planned" and actual is not None:
        problems.append(f"{pid}: status planned but actual_file is set")
    if status in ("generated", "review", "approved") and not actual:
        problems.append(f"{pid}: status {status} requires actual_file")
    if status == "approved":
        if (item.get("provider") or "").lower() == "mock":
            problems.append(f"{pid}: mock output can never be an approved preview")
        if item.get("license_review") not in ("cleared", "approved"):
            problems.append(f"{pid}: approved preview needs license_review cleared/approved")
    if actual:
        try:
            path = safe_join(data.root / "styles" / "previews", str(actual).removeprefix("styles/previews/"))
        except UnsafePathError as exc:
            problems.append(f"{pid}: actual_file outside styles/previews: {exc}")
        else:
            if not path.is_file():
                problems.append(f"{pid}: actual_file {actual} does not exist")
    return problems


def check_preview_requests(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    rows = data.preview_requests
    items = data.preview_manifest["items"]
    if rows == items:
        return []
    problems = [f"preview_requests.jsonl ({len(rows)} rows) differs from preview_manifest.json items ({len(items)})"]
    by_id = {i["preview_id"]: i for i in items}
    for row in rows:
        pid = row.get("preview_id")
        if pid not in by_id:
            problems.append(f"{pid}: request has no manifest item")
        elif row != by_id[pid]:
            diff = sorted(k for k in set(row) | set(by_id[pid]) if row.get(k) != by_id[pid].get(k))
            problems.append(f"{pid}: request differs from manifest in {diff}")
    return problems


# --------------------------------------------------------------------------- tests & skill


def check_acceptance_cases(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    cases = data.acceptance_cases["cases"]
    problems = _expect_sequence("acceptance cases", [c["id"] for c in cases], ACCEPTANCE_IDS)
    for c in cases:
        if not c.get("title") or not c.get("expected"):
            problems.append(f"{c['id']}: title and expected are required")
    spec_ids = re.findall(r"^\| (T\d{2}) \|", data.text("docs/SPEC.md"), re.M)
    if spec_ids != ACCEPTANCE_IDS:
        problems.append(f"SPEC §13 lists {spec_ids}, expected {ACCEPTANCE_IDS[0]}..{ACCEPTANCE_IDS[-1]}")
    return problems


def check_skill_entry(data: RepoData, schemas: SchemaRegistry) -> list[str]:
    problems = []
    skill_dirs = sorted(p for p in (data.root / "skill").iterdir() if p.is_dir())
    if not skill_dirs:
        return ["no skill/<name>/SKILL.md found"]
    for d in skill_dirs:
        md = d / "SKILL.md"
        if not md.is_file():
            problems.append(f"{d.name}: missing SKILL.md")
            continue
        m = re.match(r"^---\n(.*?)\n---\n", md.read_text(encoding="utf-8"), re.S)
        if not m:
            problems.append(f"{d.name}/SKILL.md: missing YAML front matter")
            continue
        front = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
        name = front.get("name", "").strip()
        if name != d.name:
            problems.append(f"{d.name}/SKILL.md: name {name!r} must equal directory name")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            problems.append(f"{d.name}/SKILL.md: name must be kebab-case")
        if not front.get("description", "").strip():
            problems.append(f"{d.name}/SKILL.md: description required")
    return problems


CHECKS: list[tuple[str, Callable[[RepoData, SchemaRegistry], list[str]]]] = [
    ("schemas", check_schemas),
    ("asset_catalog", check_asset_catalog),
    ("legacy_mapping", check_legacy_mapping),
    ("legacy_prompt_coverage", check_legacy_prompt_coverage),
    ("source_audit", check_source_audit),
    ("prompt_coverage", check_prompt_coverage),
    ("style_catalog", check_style_catalog),
    ("spec_style_table", check_spec_style_table),
    ("style_support_files", check_style_support_files),
    ("preview_manifest", check_preview_manifest),
    ("preview_requests", check_preview_requests),
    ("acceptance_cases", check_acceptance_cases),
    ("skill_entry", check_skill_entry),
]


def run_all(data: RepoData | None = None, schemas: SchemaRegistry | None = None) -> Report:
    data = data or RepoData()
    schemas = schemas or SchemaRegistry(root=data.root)
    results = []
    for name, fn in CHECKS:
        try:
            problems = fn(data, schemas)
        except (KeyError, TypeError, ValueError, OSError) as exc:  # malformed data must fail, not crash
            problems = [f"check crashed: {type(exc).__name__}: {exc}"]
        results.append(CheckResult(name, problems))
    return Report(results)
