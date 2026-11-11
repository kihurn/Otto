"""Task, step and observation records used by the execution runner."""

from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event
from time import time
from uuid import uuid4


class OutcomeStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    NEEDS_INPUT = "needs_input"
    CANCELLED = "cancelled"
    SIMULATED = "simulated"
    DISPATCHED = "dispatched"


class TaskStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CANCELLED = "cancelled"
    SIMULATED = "simulated"


@dataclass
class Evidence:
    observer: str
    target: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    observed_at: float = field(default_factory=time)


@dataclass
class Outcome:
    status: OutcomeStatus
    say: str
    data: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    error_code: str = ""
    side_effect_possible: bool = False

    def __post_init__(self):
        self.status = OutcomeStatus(self.status)
        if self.status == OutcomeStatus.VERIFIED and not self.evidence:
            raise ValueError("Verified outcomes require observation evidence.")

    @property
    def ok(self) -> bool:
        return self.status == OutcomeStatus.VERIFIED


@dataclass
class Step:
    id: str
    action: str
    args: dict = field(default_factory=dict)
    source: str = "builtin"
    status: str = "planned"


@dataclass
class Task:
    request: str
    steps: list[Step]
    id: str = field(default_factory=lambda: uuid4().hex)
    revision: int = 1
    mode: str = "live"
    status: TaskStatus = TaskStatus.PLANNED
    position: int = 0
    results: dict[str, Outcome] = field(default_factory=dict)
    cancel: Event = field(default_factory=Event, repr=False)
    active_seconds: float = 0.0
    deadline_at: float | None = None
    recoveries: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.mode not in {"live", "dry_run", "evaluation"}:
            raise ValueError("Unknown task mode.")

    def transition(self, status: TaskStatus):
        status = TaskStatus(status)
        allowed = {
            TaskStatus.PLANNED: {TaskStatus.RUNNING, TaskStatus.WAITING_INPUT, TaskStatus.CANCELLED},
            TaskStatus.RUNNING: {TaskStatus.WAITING_INPUT, TaskStatus.SUCCEEDED, TaskStatus.FAILED,
                                 TaskStatus.UNCERTAIN, TaskStatus.CANCELLED, TaskStatus.SIMULATED},
            TaskStatus.WAITING_INPUT: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
        }
        if status not in allowed.get(self.status, set()):
            raise ValueError('Invalid task transition.')
        self.status = status
