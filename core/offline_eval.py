"""Seeded practice and repeatable reports using the real planner and simulated effects."""
import random
import re
import time
from uuid import uuid4

from core import compiler, details, planner, safety
from core.config import DATA, load_json, save_json
from core.tasks import Evidence, Outcome, OutcomeStatus, Step, Task
from core.training import digest
from core import learning
from hands.registry import InvalidPlan, load_all

SCENARIO_VERSION = 1


def step(action, **args):
    return {'do':action, 'with':args}


def scenarios(count, seed):
    randomizer = random.Random(seed)
    for index in range(count):
        level = randomizer.randint(10, 80)
        seconds = randomizer.randint(10, 120)
        volume = step('set_volume', level=level)
        timer = step('set_timer', seconds=seconds, label='')
        kind = index % 5
        if kind == 0:
            text, expected, outcome = f'Set the volume to {level}', [volume], 'verified'
        elif kind == 1:
            text, expected, outcome = f'Set a timer for {seconds} seconds', [timer], 'verified'
        elif kind in {2, 3}:
            text = f'Set the volume to {level}, then set a timer for {seconds} seconds'
            expected, outcome = [volume, timer], 'verified' if kind == 2 else 'failed'
        else:
            text, expected, outcome = f'Set the volume to {level}, then set the volume to 101', [], 'invalid_plan'
        yield {'id':index+1, 'text':text, 'expected_steps':expected, 'expected_outcome':outcome}


def evaluate(case):
    text = case['text']
    started = time.perf_counter()
    if len(compiler.clauses(text)) > 1:
        plan = compiler.compile_request(text, None, None)
    else:
        intent = details._media(text) or details.by_rules('timer', text, None)
        plan = planner.Plan(planner.builtin_steps(intent) or [], 'builtin') if intent else planner.Plan([], 'none')
    effects = []
    actual_steps = []
    try:
        if plan.error:
            raise InvalidPlan(plan.error)
        actual_steps = planner.validate_steps(plan.steps)
    except InvalidPlan:
        actual = 'invalid_plan'
    else:
        task = Task(text, [Step(item.get('id',f's{i}'), item['do'], item.get('with',{}))
                           for i,item in enumerate(actual_steps)], mode='evaluation')
        def simulated(action):
            effects.append(step(action.action, **action.args))
            if case['expected_outcome'] == 'failed':
                return Outcome(OutcomeStatus.FAILED, 'Injected first-step failure.')
            return Outcome(OutcomeStatus.VERIFIED, 'Simulation observed expected effect.',
                           evidence=[Evidence('simulation', observed={'action':action.action})])
        result = safety.run_plan(actual_steps, task=task, evaluation_backend=simulated)
        actual = result.data.get('outcome_status', result.data.get('error_code'))
    expected_effects = case['expected_steps'][:1] if case['expected_outcome'] == 'failed' else case['expected_steps']
    passed = (actual == case['expected_outcome'] and actual_steps == case['expected_steps'] and effects == expected_effects)
    return {'id':case['id'], 'passed':passed, 'outcome':actual, 'steps':actual_steps,
            'simulated_effects':effects, 'ms':round((time.perf_counter()-started)*1000, 2)}


def run(count, seed, baseline_id=None, root=None):
    if not 1 <= count <= 1000:
        raise ValueError('Task count must be between 1 and 1000.')
    load_all()
    root = root or DATA/'training'
    cases = list(scenarios(count, seed))
    fingerprint = digest(cases)
    previous = None
    if baseline_id is not None:
        if not re.fullmatch(r'[0-9a-f]{32}', baseline_id):
            raise ValueError('Invalid baseline run ID.')
        baseline = load_json(root/baseline_id/'metrics.json', {})
        if baseline.get('state') != 'complete' or baseline.get('scenario_hash') != fingerprint:
            raise ValueError('Baseline must be a completed run with the same scenario set.')
        previous = baseline
    identity = uuid4().hex
    directory = root/identity
    directory.mkdir(parents=True)
    manifest = {'id':identity,'state':'running','version':SCENARIO_VERSION,'seed':seed,'scenario_hash':fingerprint}
    save_json(directory/'manifest.json', manifest)
    save_json(directory/'scenarios.json', cases)
    try:
        results = [evaluate(case) for case in cases]
        regressions = [row['id'] for row,old in zip(results,previous['results']) if old['passed'] and not row['passed']] if previous else []
        passed = sum(row['passed'] for row in results)
        metrics = dict(manifest, state='complete', passed=passed, total=count, results=results,
                       baseline_passed=previous['passed'] if previous else None, regressions=regressions)
        save_json(directory/'metrics.json', metrics)
        # Review-only paraphrases use a separate template family from the evaluation set.
        candidates = [{'text':f'Please adjust my sound level to {level} percent','area':'media',
                       'action':'set_volume','source':'offline_template','status':'pending_review'}
                      for level in (17, 34, 51, 68, 85)]
        held_out = learning.test_texts()
        candidates = [row for row in candidates if learning.norm(row['text']) not in held_out]
        save_json(directory/'candidate_examples.json', candidates)
        baseline_text = f"{previous['passed']}/{count}" if previous else 'Unavailable (first run)'
        (directory/'REPORT.md').write_text(
            f'# Offline evaluation {identity}\n\nSimulated tasks: {passed}/{count}\n\nBaseline: {baseline_text}\n\n'
            f'Regressions: {regressions or "none"}\n\nNo live desktop actions or model promotion.\n', encoding='utf-8')
        manifest['state'] = 'complete'
        return directory, metrics
    except BaseException:
        manifest['state'] = 'interrupted'
        raise
    finally:
        save_json(directory/'manifest.json', manifest)
