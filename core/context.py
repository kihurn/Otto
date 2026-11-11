"""Small typed context: requested actions are separate from observed completion."""
from dataclasses import dataclass, field
from copy import deepcopy
import time


@dataclass
class ActionContext:
    requested: dict = field(default_factory=dict)
    observed: dict = field(default_factory=dict)
    updated_at: float = 0

    def record(self, task):
        self.requested = {'task_id': task.id, 'request': task.request,
                          'steps': [{'action': s.action, 'args': deepcopy(s.args)} for s in task.steps]}
        self.observed = {'task_id': task.id, 'status': str(task.status),
                         'steps': {key: {'status': str(value.status), 'data': deepcopy(value.data)}
                                   for key, value in task.results.items()}}
        self.updated_at = time.monotonic()

    def recent(self):
        return time.monotonic() - self.updated_at < 120
