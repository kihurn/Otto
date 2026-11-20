import pytest

from core import planner, recipes
from core.details import Intent
from hands.registry import InvalidPlan, load_all
from core.tasks import Task, TaskStatus








@pytest.mark.parametrize('query', ['the first result', 'the second song', 'it'])
def test_unbound_result(query):
    load_all()
    with pytest.raises(InvalidPlan):
        planner.validate_steps([{'do': 'play_music', 'with': {'query': query}}])


@pytest.mark.parametrize('value', [True, '40', float('nan')])
def test_raw_numeric_rejected(value):
    load_all()
    assert planner.make_plan(Intent('timer', 'set_timer', {'seconds': value}), '', None).error


def test_literal_content_and_recipe_boundary():
    load_all()
    planner.validate_steps([{'do': 'new_note', 'with': {'text': '{title}'}}])
    assert recipes.fill([{'with': {'text': '{text}'}}], {'text': '{title}'})[0]['with']['text'] == '{title}'
    with pytest.raises(InvalidPlan):
        recipes.fill([{'with': {'text': '{query}'}}], {})


def test_terminal_task_cannot_restart():
    t = Task('x', [])
    t.transition(TaskStatus.RUNNING)
    t.transition(TaskStatus.CANCELLED)
    with pytest.raises(ValueError):
        t.transition(TaskStatus.RUNNING)
