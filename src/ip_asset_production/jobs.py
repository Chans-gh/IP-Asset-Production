"""Task execution: gate -> generate -> commit native -> postprocess -> QA -> bounded retry (SPEC §9.2-9.3; T09, T13).

* ``idempotency_key`` = hash of the approved request + provider; re-running a task whose files
  still match their recorded SHA-256 reuses them without another provider call.
* ``same_prompt_retry`` at most ``max_retries`` (default 2) times, only for retryable failures
  (timeouts, provider errors, hard-QA failures). Permission/egress/capability errors never retry.
* Every task writes ``task.json`` (generation-result schema + extras). Logs never contain
  reference URIs, prompts of private users beyond the stored request, tokens or keys.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .models import GenerationRequest, GenerationResult, OutputFile, TaskStatus
from .paths import safe_join
from .postprocess import Processed, ensure_alpha, fit_subject_with_margin, fit_to_spec, load_image
from .providers.base import (
    ApprovalRequiredError,
    CapabilityError,
    EgressBlockedError,
    ImageProvider,
    ProviderError,
    check_request_allowed,
)
from .providers.mock import MOCK_PNG_MARKER_KEY
from .qa import QualityResult, SoftReviewer, validate_image
from .schemas import SchemaRegistry
from .workspace import DeliveryError, commit_image

SECRET_RE = re.compile(r"(qs-[A-Za-z0-9_-]{6,}|sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|https?://\S+)", re.I)
NON_RETRYABLE = (ApprovalRequiredError, EgressBlockedError, CapabilityError)


def sanitize(message: str) -> str:
    """Strip URLs (signed download links), API keys and bearer tokens from log text."""
    return SECRET_RE.sub("[redacted]", message)[:500]


class BudgetExceededError(RuntimeError):
    """G5: the batch would exceed the approved number of provider calls."""


@dataclass
class TaskOutcome:
    task_id: str
    status: TaskStatus
    attempts: int
    files: list[OutputFile] = field(default_factory=list)
    native_size: tuple[int, int] | None = None
    provider: str | None = None
    model: str | None = None
    is_mock: bool = False
    qa: QualityResult | None = None
    errors: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    reused: bool = False
    calls: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def delivered(self) -> bool:
        return self.status in (TaskStatus.PASSED, TaskStatus.NEEDS_REVIEW) and bool(self.files)

    def result(self) -> GenerationResult:
        return GenerationResult(
            task_id=self.task_id,
            status=self.status,
            attempt=self.attempts,
            outputs=tuple(self.files),
            provider=self.provider,
            native_size=self.native_size,
            errors=tuple(dict.fromkeys(self.errors)),
            qa_summary={
                "is_mock": self.is_mock,
                "model": self.model,
                "quality_result": self.qa.to_json() if self.qa else None,
                "steps": self.steps,
                "reused": self.reused,
                **self.extras,
            },
        )


def idempotency_key(provider: ImageProvider, request: GenerationRequest) -> str:
    payload = request.to_contract()
    payload.pop("task_id", None)
    blob = json.dumps({"provider": provider.name, "request": payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_png(img: Image.Image, path: Path, *, mock: bool) -> None:
    """Atomic PNG write; real outputs carry no metadata, mock outputs keep their marker."""
    info = PngInfo()
    if mock:
        info.add_text(MOCK_PNG_MARKER_KEY, "true")
    buf = io.BytesIO()
    img.save(buf, format="PNG", pnginfo=info, optimize=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(buf.getvalue())
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class TaskRunner:
    def __init__(
        self,
        provider: ImageProvider,
        out_root: Path,
        *,
        max_retries: int = 2,
        reviewer: SoftReviewer | None = None,
        reviewer_name: str | None = None,
        allow_unreviewed_soft: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        backoff_s: float = 2.0,
        schemas: SchemaRegistry | None = None,
    ) -> None:
        if not 0 <= max_retries <= 2:
            raise ValueError("same_prompt_retry is bounded to <= 2 (SPEC §9.3)")
        self.provider = provider
        self.out_root = Path(out_root)
        self.max_retries = max_retries
        self.reviewer = reviewer
        self.reviewer_name = reviewer_name
        self.allow_unreviewed_soft = allow_unreviewed_soft
        self.sleep = sleep
        self.backoff_s = backoff_s
        self.schemas = schemas or SchemaRegistry()

    def task_dir(self, task_id: str) -> Path:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$", task_id):
            raise ValueError(f"unsafe task_id {task_id!r}")
        return safe_join(self.out_root, task_id)

    def _reuse(self, request: GenerationRequest, key: str) -> TaskOutcome | None:
        record = self.task_dir(request.task_id) / "task.json"
        if not record.is_file():
            return None
        data = json.loads(record.read_text(encoding="utf-8"))
        if data.get("idempotency_key") != key or data["result"]["status"] not in ("passed", "needs_review"):
            return None
        files = [OutputFile.model_validate(o) for o in data["result"]["outputs"]]
        for f in files:
            p = safe_join(self.task_dir(request.task_id), f.path)
            if not p.is_file() or _sha256(p) != f.sha256:
                return None
        r = data["result"]
        qa = data["result"].get("qa_summary", {})
        return TaskOutcome(
            task_id=request.task_id,
            status=TaskStatus(r["status"]),
            attempts=r["attempt"],
            files=files,
            native_size=tuple(r["native_size"]) if r.get("native_size") else None,
            provider=r.get("provider"),
            model=qa.get("model"),
            is_mock=bool(qa.get("is_mock")),
            reused=True,
            steps=["reused passed output (idempotency key match)"],
        )

    def _postprocess(
        self,
        native: Image.Image,
        request: GenerationRequest,
        *,
        fit_mode: str,
        pixel_art: bool,
        safe_margin: float | None,
    ) -> Processed:
        spec = request.output_spec
        caps = self.provider.capabilities()
        steps: list[str] = []
        alpha_method = None
        checks: dict[str, object] = {}
        img = native
        if spec.alpha_required:
            a = ensure_alpha(native, provider_alpha_native=caps.alpha_native)
            img, alpha_method, checks = a.image, a.alpha_method, a.checks
            steps += a.steps
        if spec.alpha_required and safe_margin:
            img = fit_subject_with_margin(img, (spec.width_px, spec.height_px), safe_margin)
            steps.append(f"subject re-centred with {safe_margin:.0%} safe margin")
            upscaled = False
            p = Processed(img, steps, native.size, upscaled, alpha_method, checks)
        else:
            p = fit_to_spec(img, spec, mode="cover" if fit_mode == "cover" else "contain", pixel_art=pixel_art)
            p.steps = steps + p.steps
            p.alpha_method, p.checks = alpha_method, checks
        p.native_size = native.size
        return p

    def run(
        self,
        request: GenerationRequest,
        *,
        filename: str | None = None,
        fit_mode: Literal["contain", "cover"] = "contain",
        pixel_art: bool = False,
        safe_margin: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> TaskOutcome:
        key = idempotency_key(self.provider, request)
        reused = self._reuse(request, key)
        if reused is not None:
            return reused
        tdir = self.task_dir(request.task_id)
        outcome = TaskOutcome(
            request.task_id, TaskStatus.QUEUED, 0, provider=self.provider.name, is_mock=self.provider.is_mock
        )
        name = filename or f"{request.task_id}.png"
        attempts_allowed = 1 + self.max_retries
        for attempt in range(1, attempts_allowed + 1):
            outcome.attempts = attempt
            try:
                check_request_allowed(self.provider, request)
                outcome.status = TaskStatus.GENERATING
                outcome.calls += 1
                result = self.provider.generate(request)
            except NON_RETRYABLE as exc:
                outcome.errors.append(f"{type(exc).__name__}: {sanitize(str(exc))}")
                outcome.status = TaskStatus.FAILED
                break
            except ProviderError as exc:
                outcome.errors.append(f"attempt {attempt}: {type(exc).__name__}: {sanitize(str(exc))}")
                if attempt < attempts_allowed:
                    self.sleep(self.backoff_s * attempt)
                    continue
                outcome.status = TaskStatus.FAILED
                break
            outcome.model = result.model
            outcome.native_size = result.native_size
            if not result.images:
                outcome.errors.append(f"attempt {attempt}: provider returned no image")
                continue
            try:
                native_file = commit_image(
                    result.images[0], tdir, f"attempt-{attempt:02d}/native.{result.images[0].format.lower()}"
                )
            except DeliveryError as exc:
                outcome.errors.append(f"attempt {attempt}: invalid provider image: {sanitize(str(exc))}")
                continue
            outcome.status = TaskStatus.POSTPROCESSING
            native_img = load_image(result.images[0].data)
            processed = self._postprocess(
                native_img, request, fit_mode=fit_mode, pixel_art=pixel_art, safe_margin=safe_margin
            )
            target = safe_join(tdir, name)
            save_png(processed.image, target, mock=self.provider.is_mock)
            outcome.status = TaskStatus.QA_PENDING
            qa = validate_image(
                target,
                request.output_spec,
                expect_real=not self.provider.is_mock,
                safe_margin_pct=safe_margin,
                reviewer=self.reviewer,
                reviewer_name=self.reviewer_name,
                context=context,
                allow_unreviewed_soft=self.allow_unreviewed_soft,
            )
            outcome.qa = qa
            outcome.steps = [
                f"native {native_file.width_px}x{native_file.height_px} "
                f"({native_file.path}, sha256 {native_file.sha256[:12]})",
                *processed.steps,
            ]
            outcome.extras = {
                "native_file": native_file.path,
                "upscaled": processed.upscaled,
                "alpha_method": processed.alpha_method,
                "alpha_checks": {k: v for k, v in processed.checks.items() if k != "subject_bbox"},
            }
            if qa.hard_passed:
                facts = OutputFile(
                    path=name,
                    sha256=_sha256(target),
                    width_px=request.output_spec.width_px,
                    height_px=request.output_spec.height_px,
                    format=request.output_spec.format,
                    alpha_verified=True if request.output_spec.alpha_required else None,
                    qa_status=qa.status,
                )
                outcome.files = [facts]
                outcome.status = TaskStatus.PASSED if qa.status == "passed" else TaskStatus.NEEDS_REVIEW
                break
            outcome.errors.append(f"attempt {attempt}: hard QA failed {qa.failure_codes}")
            target.unlink(missing_ok=True)  # a failed file must never look delivered
            outcome.status = TaskStatus.FAILED
        if not outcome.files:
            outcome.status = TaskStatus.FAILED
        self._record(request, key, outcome)
        return outcome

    def _record(self, request: GenerationRequest, key: str, outcome: TaskOutcome) -> None:
        result = outcome.result().to_contract()
        self.schemas.validate("generation_result", result)
        tdir = self.task_dir(request.task_id)
        tdir.mkdir(parents=True, exist_ok=True)
        record = {
            "idempotency_key": key,
            "template_id": request.template_id,
            "character_id": request.character_id,
            "character_version": request.character_version,
            "prompt_sha256": hashlib.sha256(request.compiled_prompt.encode("utf-8")).hexdigest(),
            "output_spec": request.output_spec.to_contract(),
            "result": result,
        }
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=tdir)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, tdir / "task.json")


@dataclass
class BatchReport:
    batch_id: str
    outcomes: list[TaskOutcome]
    calls: int
    skipped: list[str] = field(default_factory=list)
    stopped_reason: str | None = None

    @property
    def passed(self) -> list[str]:
        return [o.task_id for o in self.outcomes if o.status == TaskStatus.PASSED]

    @property
    def needs_review(self) -> list[str]:
        return [o.task_id for o in self.outcomes if o.status == TaskStatus.NEEDS_REVIEW]

    @property
    def failed(self) -> list[str]:
        return [o.task_id for o in self.outcomes if o.status == TaskStatus.FAILED]

    @property
    def partial(self) -> bool:
        return bool(self.failed or self.skipped or self.stopped_reason)

    def summary(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "passed": self.passed,
            "needs_review": self.needs_review,
            "failed": self.failed,
            "skipped": self.skipped,
            "provider_calls": self.calls,
            "partial": self.partial,
            "stopped_reason": self.stopped_reason,
            "errors": {o.task_id: o.errors for o in self.outcomes if o.errors},
        }


def run_batch(
    runner: TaskRunner,
    requests: Sequence[tuple[GenerationRequest, dict[str, Any]]],
    *,
    batch_id: str,
    max_calls: int | None = None,
) -> BatchReport:
    """Run many tasks; failures do not stop the batch, a budget overrun does (G5)."""
    outcomes: list[TaskOutcome] = []
    calls = 0
    skipped: list[str] = []
    stopped = None
    for i, (req, kwargs) in enumerate(requests):
        if max_calls is not None and calls + 1 > max_calls:
            stopped = f"G5: approved call budget {max_calls} reached"
            skipped = [r.task_id for r, _ in requests[i:]]
            break
        out = runner.run(req, **kwargs)
        calls += out.calls
        outcomes.append(out)
    report = BatchReport(batch_id, outcomes, calls, skipped, stopped)
    path = safe_join(runner.out_root, f"batch-{batch_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.summary(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report
