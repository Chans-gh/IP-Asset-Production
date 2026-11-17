"""QA: deterministic hard checks + recorded soft review (SPEC §8.3, §4A.6, §9.2 ``validate_assets``).

``quality_result = {status: passed|failed|needs_review, checks[], failure_codes[], reviewer, approved_at}``

Hard checks are measured from files. Soft checks (identity, topology, style, naturalness) are
never auto-passed: without a reviewer verdict they are ``not_reviewed`` and the overall status is
``needs_review`` (unless the caller explicitly accepts unreviewed soft checks for internal
mock/regression runs, which are then labelled as such).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from .character import utc_now
from .models import OutputSpec
from .postprocess import alpha_checks, within_safe_margin
from .print_layout import PrintSpec, inspect_print_pdf
from .providers.mock import MOCK_PNG_MARKER_KEY
from .typography import TextRecord
from .workspace import DeliveryError, inspect_image

CheckStatus = Literal["pass", "fail", "needs_review", "not_reviewed", "skipped"]
SOFT_CHECKS = ("identity_consistency", "topology_correct", "style_consistency", "no_artifacts_or_garbled_text")

SoftReviewer = Callable[[Path, Mapping[str, Any]], Mapping[str, tuple[str, str]]]
"""Returns ``{check_id: (pass|fail|needs_review, evidence)}`` for the soft checks it judged."""


@dataclass
class Check:
    id: str
    status: CheckStatus
    detail: str = ""
    hard: bool = True

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status, "detail": self.detail, "kind": "hard" if self.hard else "soft"}


@dataclass
class QualityResult:
    status: Literal["passed", "failed", "needs_review"]
    checks: list[Check] = field(default_factory=list)
    failure_codes: list[str] = field(default_factory=list)
    reviewer: str | None = None
    approved_at: str | None = None

    @property
    def hard_passed(self) -> bool:
        return all(c.status in ("pass", "skipped") for c in self.checks if c.hard)

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": [c.to_json() for c in self.checks],
            "failure_codes": self.failure_codes,
            "reviewer": self.reviewer,
            "approved_at": self.approved_at,
        }


def check_image_file(
    path: Path,
    spec: OutputSpec,
    *,
    expect_real: bool = True,
    safe_margin_pct: float | None = None,
) -> list[Check]:
    checks: list[Check] = []
    if not path.is_file():
        return [Check("file_exists", "fail", f"missing {path.name}")]
    checks.append(Check("file_exists", "pass", path.name))
    try:
        facts = inspect_image(path)
    except DeliveryError as exc:
        return [*checks, Check("decodable", "fail", str(exc))]
    checks.append(Check("decodable", "pass", f"{facts.format} {facts.mode}"))
    dims_ok = (facts.width_px, facts.height_px) == (spec.width_px, spec.height_px)
    checks.append(
        Check(
            "dimensions",
            "pass" if dims_ok else "fail",
            f"{facts.width_px}x{facts.height_px} vs {spec.width_px}x{spec.height_px}",
        )
    )
    fmt_ok = facts.format.upper() == spec.format.upper()
    checks.append(Check("format", "pass" if fmt_ok else "fail", f"{facts.format} vs {spec.format}"))
    with Image.open(path) as im:
        im.load()
        marker = im.info.get(MOCK_PNG_MARKER_KEY)
        if spec.alpha_required:
            a = alpha_checks(im.convert("RGBA") if im.mode in ("LA", "PA", "P") else im)
            checks.append(Check("alpha_verified", "pass" if a.get("ok") else "fail", str(a)))
        if safe_margin_pct:
            ok, detail = within_safe_margin(im, safe_margin_pct)
            checks.append(Check("safe_margin", "pass" if ok else "fail", detail))
    if expect_real:
        checks.append(
            Check("not_mock", "fail" if marker == "true" else "pass", "mock marker present" if marker else "")
        )
    return checks


def check_text(records: Sequence[TextRecord], approved: Sequence[str]) -> Check:
    drawn = [r.text for r in records]
    ok = list(drawn) == list(approved)
    return Check("layout_text_exact", "pass" if ok else "fail", f"drawn={drawn} approved={list(approved)}")


def check_print_pdf(path: Path, spec: PrintSpec) -> list[Check]:
    try:
        facts = inspect_print_pdf(path)
    except (OSError, ValueError) as exc:
        return [Check("print_pdf_valid", "fail", str(exc))]
    trim_ok = facts.trim_mm == (float(spec.trim_mm[0]), float(spec.trim_mm[1]))
    bleed_ok = abs(facts.bleed_mm - spec.bleed_mm) < 0.05
    px_ok = facts.image_px == spec.canvas_px
    return [
        Check("print_pdf_valid", "pass", f"media {facts.media_mm} mm"),
        Check("print_trim", "pass" if trim_ok else "fail", f"{facts.trim_mm} vs {spec.trim_mm}"),
        Check("print_bleed", "pass" if bleed_ok else "fail", f"{facts.bleed_mm} vs {spec.bleed_mm} mm"),
        Check(
            "print_pixels",
            "pass" if px_ok else "fail",
            f"{facts.image_px} vs {spec.canvas_px} @ {facts.effective_ppi} ppi",
        ),
    ]


def finalize(
    checks: list[Check],
    *,
    soft: Mapping[str, tuple[str, str]] | None = None,
    reviewer: str | None = None,
    allow_unreviewed_soft: bool = False,
    soft_checks: Sequence[str] = SOFT_CHECKS,
) -> QualityResult:
    all_checks = list(checks)
    soft = soft or {}
    for sid in soft_checks:
        if sid in soft:
            st, ev = soft[sid]
            status: CheckStatus = st if st in ("pass", "fail", "needs_review") else "needs_review"  # type: ignore[assignment]
            all_checks.append(Check(sid, status, ev, hard=False))
        else:
            all_checks.append(Check(sid, "not_reviewed", "no reviewer verdict", hard=False))
    failures = [c.id for c in all_checks if c.status == "fail"]
    if failures:
        status_out: Literal["passed", "failed", "needs_review"] = "failed"
    elif any(c.status in ("needs_review",) for c in all_checks) or (
        not allow_unreviewed_soft and any(c.status == "not_reviewed" for c in all_checks)
    ):
        status_out = "needs_review"
    else:
        status_out = "passed"
    return QualityResult(
        status=status_out,
        checks=all_checks,
        failure_codes=[f"FAIL_{f.upper()}" for f in failures],
        reviewer=reviewer,
        approved_at=utc_now() if status_out == "passed" else None,
    )


def validate_image(
    path: Path,
    spec: OutputSpec,
    *,
    expect_real: bool = True,
    safe_margin_pct: float | None = None,
    reviewer: SoftReviewer | None = None,
    reviewer_name: str | None = None,
    context: Mapping[str, Any] | None = None,
    allow_unreviewed_soft: bool = False,
) -> QualityResult:
    """SPEC §9.2 ``validate_assets`` for one file."""
    checks = check_image_file(path, spec, expect_real=expect_real, safe_margin_pct=safe_margin_pct)
    soft = None
    if reviewer is not None and all(c.status == "pass" for c in checks):
        soft = reviewer(path, context or {})
    return finalize(checks, soft=soft, reviewer=reviewer_name, allow_unreviewed_soft=allow_unreviewed_soft)
