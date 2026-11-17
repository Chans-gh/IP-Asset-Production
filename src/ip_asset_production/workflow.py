"""Approval-gate state machine G1-G6 with save/reload (SPEC §2.3; T03, T19, T22).

::

    intake --G1--> style_selection --G2--> candidate --G3--> planning --G4--> production
       (digital humans skip G2)                                              |  ^
                                                                    G5 pause v  | resume
                                                                           paused
    production --G6--> delivered

``restyle()`` returns to ``style_selection`` and clears G2..G4: a different style is a new
character version / style branch (SPEC §4A.5), never an in-place edit.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .character import CharacterStore, CharacterVersion, utc_now
from .intent import CreationIntent
from .paths import safe_join
from .planner import PlanResult, approve_plan
from .styles import StyleLibrary

STATES = ("intake", "style_selection", "candidate", "planning", "production", "paused", "delivered")
GATES = ("G1", "G2", "G3", "G4", "G5", "G6")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class GateError(RuntimeError):
    """A transition was attempted without its approval gate."""


@dataclass
class GateRecord:
    passed: bool = False
    at: str | None = None
    note: str | None = None


@dataclass
class Session:
    project_id: str
    state: str = "intake"
    mode: str | None = None
    ip_type: str | None = None
    body_topology: str | None = None
    use_cases: list[str] = field(default_factory=list)
    style_id: str | None = None
    style_source: str | None = None
    character_id: str | None = None
    character_version: str | None = None
    plan: dict[str, Any] | None = None
    paused_reason: str | None = None
    gates: dict[str, GateRecord] = field(default_factory=lambda: {g: GateRecord() for g in GATES})
    history: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not PROJECT_RE.match(self.project_id):
            raise ValueError("project_id must be lower-case a-z0-9_- (max 64)")

    # -- helpers -------------------------------------------------------------------------------
    def _require(self, *states: str) -> None:
        if self.state not in states:
            raise GateError(f"action not allowed in state {self.state!r} (expected {states})")

    def _pass(self, gate: str, note: str | None = None) -> None:
        self.gates[gate] = GateRecord(True, utc_now(), note)
        self.history.append({"at": utc_now(), "event": f"{gate} passed", "note": note or ""})

    def _move(self, state: str) -> None:
        self.history.append({"at": utc_now(), "event": f"{self.state} -> {state}", "note": ""})
        self.state = state

    @property
    def needs_style(self) -> bool:
        return self.ip_type != "digital_human"

    # -- G1 ------------------------------------------------------------------------------------
    def confirm_intent(
        self,
        intent: CreationIntent,
        *,
        answered_question: bool = False,
        ip_type: str | None = None,
        body_topology: str | None = None,
    ) -> None:
        self._require("intake")
        resolved_type = ip_type or intent.ip_type
        if resolved_type is None:
            raise GateError("G1: ip_type is unknown — ask the user")
        if (intent.question or intent.conflicts) and not answered_question:
            raise GateError(f"G1: open question: {intent.question}")
        self.mode = intent.mode
        self.ip_type = resolved_type
        self.body_topology = body_topology or intent.body_topology
        self.use_cases = list(intent.use_cases)
        self._pass("G1", f"{self.mode}/{self.ip_type}/{self.body_topology}")
        self._move("style_selection" if self.needs_style else "candidate")

    # -- G2 ------------------------------------------------------------------------------------
    def confirm_style(self, style_id: str, styles: StyleLibrary, *, source: str = "user_selected") -> dict[str, Any]:
        """Bind a confirmed STYLE-XXX; returns the style_profile to store on the candidate."""
        self._require("style_selection")
        if not self.needs_style:
            raise GateError("digital humans do not use the anime style branch")
        style = styles.resolve(style_id)
        if self.ip_type and style["style_id"] not in {s["style_id"] for s in styles.candidates(self.ip_type)}:
            raise GateError(f"{style_id} does not support {self.ip_type}")
        self.style_id = style["style_id"]
        self.style_source = source
        self._pass("G2", f"{self.style_id} ({source})")
        self._move("candidate")
        return styles.style_profile(self.style_id, confirmed=True)

    def restyle(self) -> None:
        """Change style after G2: back to style selection, new candidate/version required."""
        self._require("candidate", "planning", "production")
        for g in ("G2", "G3", "G4"):
            self.gates[g] = GateRecord()
        self.plan = None
        self.character_version = None
        self.style_id = None
        self._move("style_selection")

    # -- G3 ------------------------------------------------------------------------------------
    def record_candidate(self, cv: CharacterVersion) -> None:
        self._require("candidate")
        if self.needs_style and cv.style_id != self.style_id:
            raise GateError(f"candidate style {cv.style_id} != confirmed style {self.style_id}")
        if cv.approval_status not in ("draft", "pending"):
            raise GateError("a candidate must be draft/pending")
        self.character_id = cv.character_id
        self.character_version = cv.version

    def approve_character(self, store: CharacterStore, *, approved_by_user: bool) -> CharacterVersion:
        self._require("candidate")
        if not (self.character_id and self.character_version):
            raise GateError("G3: no candidate recorded")
        cv = store.approve(self.character_id, self.character_version, approved_by_user=approved_by_user)
        self._pass("G3", f"{cv.character_id}/{cv.version}")
        self._move("planning")
        return cv

    # -- G4 ------------------------------------------------------------------------------------
    def approve_plan(self, result: PlanResult, *, approved_by_user: bool) -> dict[str, Any]:
        self._require("planning")
        if result.plan["character_version"] != self.character_version:
            raise GateError("plan was made for a different character version")
        plan = approve_plan(result, approved_by_user=approved_by_user)
        self.plan = plan
        self._pass("G4", f"{len(result.execution_order)} tasks, {result.estimates.get('generation_calls')} calls")
        self._move("production")
        return plan

    # -- G5 / G6 -------------------------------------------------------------------------------
    def pause(self, reason: str) -> None:
        """G5: identity drift, unclear egress permission or cost anomaly stops production."""
        self._require("production")
        self.paused_reason = reason
        self.gates["G5"] = GateRecord(False, utc_now(), reason)
        self._move("paused")

    def resume(self, *, resolved_by_user: bool) -> None:
        self._require("paused")
        if not resolved_by_user:
            raise GateError("G5: the pause reason must be resolved by the user")
        self._pass("G5", f"resolved: {self.paused_reason}")
        self.paused_reason = None
        self._move("production")

    def delivery_check(self, *, all_hard_checks_passed: bool, partial_report: str | None = None) -> None:
        """G6: specs/completeness verified; partial success is allowed only when reported."""
        self._require("production")
        if not all_hard_checks_passed and not partial_report:
            raise GateError("G6: failed hard checks must be reported as partial delivery")
        self._pass("G6", partial_report or "all hard checks passed")
        self._move("delivered")

    # -- persistence ---------------------------------------------------------------------------
    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Session:
        data = dict(data)
        gates = {g: GateRecord(**v) for g, v in data.pop("gates", {}).items()}
        s = cls(**data)
        s.gates.update(gates)
        if s.state not in STATES:
            raise ValueError(f"unknown state {s.state!r}")
        return s


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, project_id: str) -> Path:
        if not PROJECT_RE.match(project_id):
            raise ValueError("bad project id")
        return safe_join(self.root, f"sessions/{project_id}.json")

    def save(self, session: Session) -> Path:
        p = self.path(session.project_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=p.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(session.to_json(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return p

    def load(self, project_id: str) -> Session:
        return Session.from_json(json.loads(self.path(project_id).read_text(encoding="utf-8")))
