from types import SimpleNamespace
import pytest
from core import training, router, config
from hands import registry


def scores(count=20, wrong=()):
    preds = [{'text':str(i), 'gold':'media', 'right':i not in wrong, 'prob':.99} for i in range(count)]
    return {'preds':preds, 'accuracy':sum(row['right'] for row in preds)/count if count else 0}


def test_gate_rejects_regression_even_if_accuracy_unchanged():
    assert not training.gate(scores(wrong={1}), scores(wrong={2}), .85)[0]
    assert training.gate(scores(wrong={1}), scores(), .85)[0]


def test_unchecked_or_empty_evaluation_cannot_promote():
    assert not training.gate(scores(0), scores(0), .85)[0]


def test_promotion_checks_artifacts_and_rollback_preserves_baseline(tmp_path, monkeypatch):
    current = tmp_path/'current'
    monkeypatch.setattr(router, 'CURRENT', current)
    current.mkdir()
    config.save_json(current/router.META, {'hash':'original'})
    identity = 'a'*32
    candidate = tmp_path/'candidates'/identity
    candidate.mkdir(parents=True)
    config.save_json(candidate/router.META, {'hash':'candidate'})
    rows, tests = [], []
    monkeypatch.setattr(training, 'dataset', lambda: (rows, tests))
    good = {'accuracy': 1.0, 'preds': [{'text': str(i), 'gold': 'apps', 'prob': .99, 'right': True} for i in range(20)]}
    report = {'state':'complete', 'eligible':False, 'training_hash':router._rows_hash(rows),
              'test_hash':training.digest(tests),'baseline_artifact':training.artifact_digest(current),
              'artifact':training.artifact_digest(candidate), 'zone_hash':training.digest({}),
              'gate_version': training.GATE_VERSION, 'serving_bars': {'baseline': .85, 'candidate': .85},
              'baseline': good, 'candidate_scores': good}
    config.save_json(candidate/'report.json', report)
    instance = SimpleNamespace(settings={})
    with pytest.raises(ValueError, match='has not passed'):
        training.promote(instance, identity)
    report['eligible'] = True
    config.save_json(candidate/'report.json', report)
    assert training.promote(instance, identity) == candidate
    assert router.Router({}).calibration == candidate
    assert training.rollback() == current
    assert router.Router({}).calibration == current
