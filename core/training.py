"""Stage Laya calibration separately and promote only after reviewed evaluation."""
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import json
import os
import re
from uuid import uuid4

from core import learning
from core.areas import AREA_QUESTION, AREAS
from core.config import load_json, save_json


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def artifact_digest(directory):
    fingerprint = sha256()
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.name in {'report.json', 'REPORT.md'}:
            continue
        fingerprint.update(str(path.relative_to(directory)).encode() + b'\0')
        with path.open('rb') as handle:
            for block in iter(lambda: handle.read(1 << 20), b''):
                fingerprint.update(block)
    return fingerprint.hexdigest()


def gate(baseline, candidate, threshold):
    before, after = baseline['preds'], candidate['preds']
    if len(before) < 20 or len(before) != len(after):
        return False, 'Need at least 20 checked examples scored by both calibrations.'
    if [(r['text'], r['gold']) for r in before] != [(r['text'], r['gold']) for r in after]:
        return False, 'The evaluation sets differ.'
    if any(old['right'] and not new['right'] for old, new in zip(before, after)):
        return False, 'The candidate regressed on a previously correct checked request.'
    if candidate['accuracy'] < baseline['accuracy']:
        return False, 'Candidate accuracy regressed.'
    old_acted = [row for row in before if row['prob'] >= threshold]
    new_acted = [row for row in after if row['prob'] >= threshold]
    if min(len(old_acted), len(new_acted)) < 8:
        return False, 'Need at least eight confident decisions in both evaluations.'
    old_precision = sum(row['right'] for row in old_acted) / len(old_acted)
    new_precision = sum(row['right'] for row in new_acted) / len(new_acted)
    if new_precision < max(.95, old_precision):
        return False, 'Candidate confident decisions did not meet the precision gate.'
    return True, 'Evaluation passed. Review the report before explicitly promoting.'


def dataset():
    tests = [row for row in learning.load_test() if row['area'] in AREAS]
    excluded = {learning.norm(row['text']) for row in tests}
    rows = [row for row in learning.training_rows(set(AREAS)) if row['state'] not in excluded]
    return rows, tests


def stage_candidate(router, say=print):
    import laya
    from core.router import CURRENT, META, Router, _rows_hash
    rows, tests = dataset()
    checked = [row for row in tests if row['checked'].casefold() == 'y']
    if not rows:
        raise ValueError('No training examples are available.')
    identity = uuid4().hex
    directory = CURRENT.parent / 'candidates' / identity
    directory.mkdir(parents=True)
    report = {'candidate': identity, 'state':'running', 'training_hash':_rows_hash(rows),
              'test_hash':digest(tests), 'baseline_artifact':artifact_digest(router.calibration),
              'zone_hash':digest(router.settings.get('zones', {}))}
    save_json(directory/'report.json', report)
    try:
        baseline = router.score(checked)
        say(f'  Training a separate candidate on {len(rows)} examples.')
        candidate = Router(router.settings)
        candidate.device = router.device
        candidate.agent = laya.load(vegaml=True, device=router.device)
        candidate.agent.fit(rows, questions=AREA_QUESTION)
        candidate.agent.save_calibration(str(directory))
        candidate.agent.load_calibration(str(directory))
        scores = candidate.score(checked)
        eligible, reason = gate(baseline, scores, router.bars()[0])
        meta = {'hash':_rows_hash(rows), 'n_rows':len(rows), 'device':router.device,
                'saved':datetime.now().isoformat(timespec='seconds'),
                'score':{key:scores[key] for key in ('accuracy','n','checked','per_area')}, 'bars':scores['bars']}
        save_json(directory/META, meta)
        report.update(state='complete', baseline=baseline, candidate_scores=scores,
                      eligible=eligible, reason=reason, artifact=artifact_digest(directory))
        baseline_score = f'{baseline["accuracy"]:.1%}' if checked else 'Unavailable'
        candidate_score = f'{scores["accuracy"]:.1%}' if checked else 'Unavailable'
        (directory/'REPORT.md').write_text(
            f'# Laya candidate {identity}\n\nChecked requests: {len(checked)}\n\n'
            f'Baseline: {baseline_score}\n\nCandidate: {candidate_score}\n\n{reason}\n', encoding='utf-8')
        say(f'  {reason} Report: {directory / "REPORT.md"}')
        return report
    except BaseException:
        report['state'] = 'interrupted'
        raise
    finally:
        save_json(directory/'report.json', report)


@contextmanager
def promotion_lock(path):
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield  # Closing the handle releases the lock even if promotion fails.


def promote(router, identity):
    from core.router import CURRENT, _rows_hash
    if not re.fullmatch(r'[0-9a-f]{32}', identity):
        raise ValueError('Invalid candidate ID.')
    directory = CURRENT.parent / 'candidates' / identity
    with promotion_lock(CURRENT.parent / 'promotion.lock'):
        report = load_json(directory/'report.json', {})
        if report.get('state') != 'complete' or not report.get('eligible'):
            raise ValueError('This candidate has not passed evaluation.')
        from core.router import Router
        active = Router(router.settings)
        rows, tests = dataset()
        if (report.get('training_hash') != _rows_hash(rows) or report.get('test_hash') != digest(tests)
                or report.get('baseline_artifact') != artifact_digest(active.calibration)
                or report.get('zone_hash') != digest(router.settings.get('zones', {}))
                or report.get('artifact') != artifact_digest(directory)):
            raise ValueError('The evaluation inputs or calibration changed. Train and score a fresh candidate.')
        previous = active.calibration.name if active.calibration != CURRENT else None
        save_json(CURRENT.parent / 'active.json', {'candidate':identity, 'previous':previous})
    return directory


def rollback():
    from core.router import CURRENT, META
    pointer = CURRENT.parent/'active.json'
    with promotion_lock(CURRENT.parent/'promotion.lock'):
        active = load_json(pointer, {})
        if not active.get('candidate'):
            raise ValueError('No promoted candidate to roll back.')
        previous = active.get('previous')
        target = CURRENT
        if previous is not None:
            if not isinstance(previous, str) or not re.fullmatch(r'[0-9a-f]{32}', previous):
                raise ValueError('Previous candidate ID is invalid.')
            target = CURRENT.parent/'candidates'/previous
        if not (target/META).is_file():
            raise ValueError('The previous calibration is unavailable.')
        save_json(pointer, {'candidate':previous} if previous else {})
    return target
