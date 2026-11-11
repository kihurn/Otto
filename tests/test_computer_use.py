import time
import pytest
from core.computer_use import validate, execute
from core.tasks import Evidence, Task, Step
from core.action_runtime import current, ActionInterrupted
from core.brain import NoBrainAvailable
from core.computer_use import model_failure


@pytest.mark.parametrize('proposal', [None, {},
    {'version':1,'snapshot_id':'old','action':'done','target':{}},
    {'version':1,'snapshot_id':'s','action':'shell','target':{}},
    {'version':1,'snapshot_id':'s','action':'enter','target':{}},
    {'version':1,'snapshot_id':'s','action':'click','target':{'x':float('nan'),'y':.5}},
    {'version':1,'snapshot_id':'s','action':'click','target':{'x':2,'y':.5}},
    {'version':1,'snapshot_id':'s','action':'type_query','target':{'text':'invented'}},
])
def test_invalid_proposals(proposal):
    with pytest.raises(ValueError):
        validate(proposal, {'id':'s'})


class Provider:
    def __init__(self):
        self.effects = []
        self.matches = False
        self.freshness = True
    def verify(self, goal):
        return Evidence('fake_observer', observed={'matches':True}) if self.matches else None
    def observe(self):
        return {'id':str(len(self.effects)),'image':'fake_image'}
    def fresh(self, snapshot, point):
        return self.freshness
    def act(self, action, target, snapshot, goal):
        self.effects.append((action,snapshot['id']))
    def success_text(self, goal):
        return 'Observed complete.'


def test_observe_after_each_action(monkeypatch):
    monkeypatch.setattr(time,'sleep',lambda t: None)
    provider = Provider()
    def propose(snapshot, goal, deadline):
        if len(provider.effects) == 1:
            provider.matches = True
        return {'version':1,'snapshot_id':snapshot['id'],'action':'click','target':{'x':.5,'y':.5}}
    outcome = execute(provider, propose, {}, time.monotonic()+45)
    assert outcome.ok and provider.effects == [('click','0')]


def test_model_done_cannot_claim_success():
    provider = Provider()
    result = execute(provider, lambda s,*a: {'version':1,'snapshot_id':s['id'],'action':'done','target':{}}, {}, time.monotonic()+45)
    assert not result.ok and not provider.effects


def test_changed_window_does_not_click():
    provider = Provider(); provider.freshness = False
    result = execute(provider, lambda s,*a: {'version':1,'snapshot_id':s['id'],'action':'click','target':{'x':.5,'y':.5}}, {}, time.monotonic()+45)
    assert not result.ok and not provider.effects


def test_cancel_during_inference_does_not_click():
    provider = Provider()
    task = Task('x',[Step('s','visual_task',{})])
    def propose(s,*a):
        task.cancel.set()
        return {'version':1,'snapshot_id':s['id'],'action':'click','target':{'x':.5,'y':.5}}
    token = current.set((task,1,time.monotonic()+45))
    try:
        with pytest.raises(ActionInterrupted):
            execute(provider, propose, {}, time.monotonic()+45)
        assert not provider.effects
    finally:
        current.reset(token)


def test_six_action_budget(monkeypatch):
    monkeypatch.setattr(time,'sleep',lambda t: None)
    provider = Provider()
    result = execute(provider, lambda s,*a: {'version':1,'snapshot_id':s['id'],'action':'scroll_down','target':{}}, {}, time.monotonic()+45)
    assert not result.ok and len(provider.effects) == 6


@pytest.mark.parametrize('reasons,code', [
    (['qwen: timeout'], 'model_timeout'),
    (["qwen: reply wasn't valid JSON"], 'model_invalid_json'),
    (['qwen: unreachable'], 'model_unavailable'),
])
def test_model_failures_have_distinct_diagnostics(reasons, code):
    assert model_failure(NoBrainAvailable(reasons))[0] == code


def test_first_image_budget_stays_within_task_deadline():
    provider = Provider()
    budgets = []
    end = time.monotonic() + 12
    def propose(snapshot, goal, deadline):
        budgets.append(deadline)
        return {'version':1,'snapshot_id':snapshot['id'],'action':'stop','target':{}}
    execute(provider, propose, {}, end)
    assert budgets == [end-3]
