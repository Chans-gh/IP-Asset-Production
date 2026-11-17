"""M0 acceptance: static consistency of SPEC, catalogs, prompts, styles and test cases.

The positive test runs against the real repository; every mutation test proves the
corresponding check actually detects drift.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ip_asset_production.data import RepoData
from ip_asset_production.validation import run_all


def failing(root: Path) -> set[str]:
    return {r.name for r in run_all(RepoData(root=root)).results if not r.ok}


def test_repository_data_is_consistent(root: Path) -> None:
    report = run_all(RepoData(root=root))
    assert report.ok, "\n".join(report.problems)


def test_record_counts(root: Path) -> None:
    data = RepoData(root=root)
    assert len(data.legacy_mapping["records"]) == 41
    assert len(data.asset_catalog["new_asset_templates"]) == 14
    assert len(data.asset_catalog["application_kits"]) == 10
    assert len(data.style_catalog["styles"]) == 48
    assert len(data.preview_manifest["items"]) == 138


def test_no_preview_is_claimed_generated(root: Path) -> None:
    items = RepoData(root=root).preview_manifest["items"]
    assert all(i["status"] == "planned" and i["actual_file"] is None for i in items)


def _rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture drift: {old!r} not in {path}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _jsonl_edit(path: Path, idx: int, key: str, value: Any) -> None:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows[idx][key] = value
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_detects_missing_legacy_record(repo_copy: Path, edit_json: Any) -> None:
    edit_json(repo_copy, "catalogs/legacy_41_mapping.json", lambda d: d["records"].pop(5) and None)
    assert {"legacy_mapping", "source_audit"} <= failing(repo_copy)


def test_detects_wrong_legacy_variant(repo_copy: Path, edit_json: Any) -> None:
    def flip(d: dict[str, Any]) -> None:
        rec = next(r for r in d["records"] if r["legacy_id"] == "detail-02")
        rec["variant"] = "clean"

    edit_json(repo_copy, "catalogs/legacy_41_mapping.json", flip)
    assert {"legacy_mapping", "source_audit"} <= failing(repo_copy)


def test_detects_legacy_family_drift(repo_copy: Path, edit_json: Any) -> None:
    def move(d: dict[str, Any]) -> None:
        rec = next(r for r in d["records"] if r["legacy_id"] == "foundation-05")
        rec["prompt_family"] = "BASE_VIEW"

    edit_json(repo_copy, "catalogs/legacy_41_mapping.json", move)
    assert "legacy_prompt_coverage" in failing(repo_copy)


def test_detects_missing_new_prompt(repo_copy: Path) -> None:
    _rewrite(repo_copy / "prompts/new-assets.md", "### NEW-07", "### NEW-7X")
    assert "prompt_coverage" in failing(repo_copy)


def test_detects_missing_app_prompt(repo_copy: Path) -> None:
    _rewrite(repo_copy / "prompts/application-kits.md", "### APP-02 ", "### APP-2 ")
    assert "prompt_coverage" in failing(repo_copy)


def test_detects_duplicate_app_id(repo_copy: Path, edit_json: Any) -> None:
    def dup(d: dict[str, Any]) -> None:
        d["application_kits"][3]["id"] = "APP-01"

    edit_json(repo_copy, "catalogs/asset_catalog.json", dup)
    assert "asset_catalog" in failing(repo_copy)


def test_detects_style_catalog_vs_spec_drift(repo_copy: Path, edit_json: Any) -> None:
    def rename(d: dict[str, Any]) -> None:
        d["styles"][10]["display_name_zh"] = "改名风格"

    edit_json(repo_copy, "styles/catalog.json", rename)
    assert "spec_style_table" in failing(repo_copy)


def test_detects_applicability_drift(repo_copy: Path, edit_json: Any) -> None:
    def drop_object(d: dict[str, Any]) -> None:
        s = next(s for s in d["styles"] if s["style_id"] == "STYLE-020")
        s["supported_subjects"].remove("anthropomorphic_object")

    edit_json(repo_copy, "styles/catalog.json", drop_object)
    # SPEC table no longer matches, and the manifest now plans an unsupported preview.
    assert {"spec_style_table", "preview_manifest"} <= failing(repo_copy)


def test_detects_taxonomy_violation(repo_copy: Path, edit_json: Any) -> None:
    def bad(d: dict[str, Any]) -> None:
        d["styles"][0]["material"] = "unobtainium"

    edit_json(repo_copy, "styles/catalog.json", bad)
    assert "style_catalog" in failing(repo_copy)


def test_detects_planned_preview_with_file(repo_copy: Path, edit_json: Any) -> None:
    def fake(d: dict[str, Any]) -> None:
        d["items"][0]["actual_file"] = "styles/previews/animal/STYLE-001-ANIMAL_PROTO.png"

    edit_json(repo_copy, "styles/preview_manifest.json", fake)
    assert "preview_manifest" in failing(repo_copy)


def test_detects_approved_mock_preview(repo_copy: Path, edit_json: Any) -> None:
    target = repo_copy / "styles/previews/animal/STYLE-001-ANIMAL_PROTO.png"
    target.write_bytes(b"not really an image")

    def approve(d: dict[str, Any]) -> None:
        item = d["items"][0]
        item.update(
            status="approved", actual_file=str(target.relative_to(repo_copy)), provider="mock", license_review="cleared"
        )

    edit_json(repo_copy, "styles/preview_manifest.json", approve)
    assert "preview_manifest" in failing(repo_copy)


def test_detects_preview_path_traversal(repo_copy: Path, edit_json: Any) -> None:
    def escape(d: dict[str, Any]) -> None:
        d["items"][0].update(status="generated", actual_file="styles/previews/../../docs/SPEC.md")

    edit_json(repo_copy, "styles/preview_manifest.json", escape)
    assert "preview_manifest" in failing(repo_copy)


def test_detects_prompt_hash_mismatch(repo_copy: Path, edit_json: Any) -> None:
    def tamper(d: dict[str, Any]) -> None:
        d["items"][7]["prompt"] += " extra"

    edit_json(repo_copy, "styles/preview_manifest.json", tamper)
    assert {"preview_manifest", "preview_requests"} <= failing(repo_copy)


def test_detects_requests_jsonl_drift(repo_copy: Path) -> None:
    _jsonl_edit(repo_copy / "styles/preview_requests.jsonl", 3, "prompt", "a different prompt for this preview")
    assert failing(repo_copy) == {"preview_requests"}


def test_request_rows_may_lag_manifest_status(repo_copy: Path) -> None:
    # The JSONL is the immutable request; generation/review state lives only in the manifest.
    _jsonl_edit(repo_copy / "styles/preview_requests.jsonl", 3, "status", "generated")
    assert failing(repo_copy) == set()


def test_detects_manifest_prompt_not_compiled_from_catalog(repo_copy: Path, edit_json: Any) -> None:
    import hashlib

    def tamper(d: dict[str, Any]) -> None:
        item = d["items"][5]
        item["prompt"] = item["prompt"].replace("Apply ONLY", "Apply mostly")
        item["prompt_sha256"] = hashlib.sha256(item["prompt"].encode()).hexdigest()

    edit_json(repo_copy, "styles/preview_manifest.json", tamper)
    assert "preview_requests" in failing(repo_copy)


def test_detects_missing_manifest_item(repo_copy: Path, edit_json: Any) -> None:
    def drop(d: dict[str, Any]) -> None:
        d["items"].pop(20)
        d["total_planned"] = len(d["items"])

    edit_json(repo_copy, "styles/preview_manifest.json", drop)
    assert {"preview_manifest", "preview_requests"} <= failing(repo_copy)


def test_detects_missing_acceptance_case(repo_copy: Path, edit_json: Any) -> None:
    edit_json(repo_copy, "tests/acceptance_cases.json", lambda d: d["cases"].pop(12) and None)
    assert "acceptance_cases" in failing(repo_copy)


def test_detects_skill_name_mismatch(repo_copy: Path) -> None:
    _rewrite(repo_copy / "skill/ip-asset-production/SKILL.md", "name: ip-asset-production", "name: IP_Asset")
    assert "skill_entry" in failing(repo_copy)


def test_malformed_data_fails_instead_of_crashing(repo_copy: Path, edit_json: Any) -> None:
    edit_json(repo_copy, "catalogs/asset_catalog.json", lambda d: d.pop("categories") and None)
    assert "asset_catalog" in failing(repo_copy)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("映射：`detail-01..04`。", ["detail-01", "detail-02", "detail-03", "detail-04"]),
        ("映射：`foundation-02`、`complete-07..09`", ["foundation-02", "complete-07", "complete-08", "complete-09"]),
        ("`detail-13/14/21..22`", ["detail-13", "detail-14", "detail-21", "detail-22"]),
    ],
)
def test_legacy_ref_expansion(line: str, expected: list[str]) -> None:
    from ip_asset_production.validation.spec_checks import _expand_legacy_refs

    assert _expand_legacy_refs(line) == expected
