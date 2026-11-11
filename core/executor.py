"""First verified task path: Spotify music. Other domains remain conservative."""
import time
from copy import deepcopy

from core.tasks import Task, Step, TaskStatus, Outcome, OutcomeStatus, Evidence
from hands.registry import ACTIONS, Result


def observe_playback(sp, target):
    state = sp._call('GET', '/me/player') or {}
    item = state.get('item') or {}
    device = state.get('device') or {}
    context = state.get('context') or {}
    identities = {item.get('uri'), (item.get('linked_from') or {}).get('uri')}
    matching = (bool(identities.intersection(target['uris'])) if target['kind'] == 'liked' else
                target['uri'] in identities if target['kind'] == 'track' else
                context.get('uri') == target['uri'])
    observed = {'uri': item.get('uri'), 'device_id': device.get('id'),
                'playing': state.get('is_playing'), 'context_uri': context.get('uri')}
    ok = matching and device.get('id') == target['device_id'] and state.get('is_playing') is True
    return ok, Evidence('spotify.player', target=deepcopy(target),
                        expected={'playing': True}, observed=observed)


def verify(sp, task, target, end):
    evidence = []
    while not task.cancel.is_set() and time.monotonic() < end:
        try:
            ok, observation = observe_playback(sp, target)
            evidence.append(observation)
            if ok and not task.cancel.is_set() and time.monotonic() < end:
                return Outcome(OutcomeStatus.VERIFIED, f"Playing {target['description']}.",
                               {'playback_target': target}, evidence, side_effect_possible=True)
        except Exception:
            pass
        task.cancel.wait(min(0.5, max(0, end - time.monotonic())))
    status = OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN
    return Outcome(status, "Cancelled." if task.cancel.is_set() else
                   "I couldn't confirm the requested music is playing on Spotify.",
                   {'playback_target': target}, evidence, side_effect_possible=True)


def music_step(step, task, end, progress):
    from core.config import load_settings
    if load_settings().get('spotify', {}).get('playback_backend', 'api') == 'desktop':
        from hands.spotify_desktop import play
        return play(step, task, end, progress)
    from connectors import spotify as sp
    from hands.media import _launch_spotify, _spotify
    if not _spotify():
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'Connect Spotify first with otto spotify.')
    if task.cancel.is_set():
        return Outcome(OutcomeStatus.CANCELLED, 'Cancelled.')
    progress('Searching Spotify.')
    uris = None
    if step.action == 'play_liked':
        saved = sp._call('GET', '/me/tracks', {'limit': 50}) or {}
        uris = [(entry.get('track') or {}).get('uri') for entry in saved.get('items', []) if entry]
        uris = [uri for uri in uris if uri]
        if not uris:
            return Outcome(OutcomeStatus.NEEDS_INPUT, 'No playable Liked Songs were returned.')
        kind, uri, description = 'liked', uris[0], 'a selection from your Liked Songs'
    else:
        found = sp.best_match(**step.args)
        if not found:
            return Outcome(OutcomeStatus.NEEDS_INPUT, 'I could not confidently match that music. Tell me the title and artist.')
        kind, uri, item = found
        description = sp.describe(kind, item)
    progress('Opening Spotify and connecting to its player.')
    if task.cancel.is_set() or time.monotonic() >= end:
        return Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                       'Stopped before connecting to the player.')
    # Discovery can retain a closed/inactive player; ensure the desktop app is opened too.
    _launch_spotify()
    dev = sp.ensure_device(_launch_spotify)
    if not dev:
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'I could not identify this PC’s Spotify player. Open Spotify or set spotify.device_name.')
    target = {'kind': kind, 'uri': uri, 'device_id': dev['id'], 'description': description}
    if uris:
        target['uris'] = uris
    if task.cancel.is_set() or time.monotonic() >= end:
        return Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                       'Stopped before playback was sent.')
    progress('Starting playback and checking the song.')
    from core.action_runtime import check
    check()
    dispatch_error = None
    try:
        if uris:
            sp._call('PUT', '/me/player/play', {'device_id': dev['id']}, {'uris': uris})
        else:
            sp.play(uri, kind, dev['id'])
    except Exception as error:
        # A failed response after dispatch does not prove the command failed. Never retry blindly.
        dispatch_error = {'error_class': type(error).__name__, 'http_status': getattr(error, 'status', None)}
    outcome = verify(sp, task, target, min(end, time.monotonic() + 6))
    outcome.data['dispatch'] = dispatch_error or {'accepted': True}
    if outcome.status == OutcomeStatus.UNCERTAIN:
        if dispatch_error:
            outcome.say += f" Playback request error: {dispatch_error['error_class']} (status {dispatch_error['http_status']})."
        elif outcome.evidence and all(not e.observed.get('uri') for e in outcome.evidence):
            outcome.say = 'Spotify accepted the command but reports no current playback. Try playing one song manually in Spotify, then ask me again.'
    from core import log
    log.write({'type': 'spotify_playback_check', 'task_id': task.id, 'dispatch': outcome.data['dispatch'],
               'target': target, 'last_observed': outcome.evidence[-1].observed if outcome.evidence else None,
               'outcome_status': outcome.status.value})
    return outcome


def run(steps, *, dry_run=False, why='', task=None, progress=lambda message: None):
    from connectors import spotify as sp
    task = task or Task(why, [Step(s.get('id', f's{i}'), s['do'], deepcopy(s.get('with', {})))
                             for i, s in enumerate(steps)], mode='dry_run' if dry_run else 'live')
    if [(s.action, s.args) for s in task.steps] != [(s['do'], s.get('with', {})) for s in steps]:
        return Result(False, 'The task changed; please ask again.', {'error_code': 'task_mismatch'})
    dry_run = dry_run or task.mode in {'dry_run', 'evaluation'}
    task.transition(TaskStatus.RUNNING)
    end = task.deadline_at or time.monotonic() + 45
    started_at = time.monotonic()
    token = sp.deadline.set(end)
    from core.action_runtime import current, check, ActionInterrupted
    runtime_token = current.set((task, task.revision, end))
    texts = []
    combined_data = {}
    outcome = None
    try:
        for i, step in enumerate(task.steps):
            task.position = i
            # The validator permits only backwards, typed references. Resolve only verified output.
            resolved = deepcopy(step.args)
            for key, value in resolved.items():
                if isinstance(value, dict) and not dry_run:
                    producer, field = value['$ref'].split('.', 1)
                    source = task.results.get(producer)
                    if source is None or source.status != OutcomeStatus.VERIFIED:
                        raise ValueError('Reference has no verified output')
                    resolved[key] = source.data[field]
            if not dry_run:
                from core.planner import validate_steps
                validate_steps([{'do': step.action, 'with': resolved}])
                from core.safety import step_risk
                from hands.registry import ASK
                if step_risk({'do': step.action, 'with': resolved}) >= ASK and resolved != step.args:
                    raise ValueError('Resolved target needs fresh authorization')
            executing = Step(step.id, step.action, resolved, step.source)
            if task.cancel.is_set():
                outcome = Outcome(OutcomeStatus.CANCELLED, 'Cancelled.')
            elif time.monotonic() >= end:
                outcome = Outcome(OutcomeStatus.UNCERTAIN, 'The task timed out.')
            elif dry_run:
                outcome = Outcome(OutcomeStatus.SIMULATED,
                                  f'[dry run] would {ACTIONS[step.action].describe(**step.args)}.')
            elif step.action in {'play_music', 'play_liked'}:
                check()
                outcome = music_step(executing, task, end, progress)
            else:
                before_volume = None
                if step.action == 'change_volume':
                    from hands import media
                    before_volume = media.current_volume()
                if len(task.steps) > 1:
                    progress('Next, ' + ACTIONS[step.action].describe(**resolved) + '.')
                check()
                result = ACTIONS[step.action].fn(**resolved)
                outcome = result if isinstance(result, Outcome) else result.to_outcome()
                # Minimal observations for existing app/volume actions. Other domains land in D.
                if outcome.status == OutcomeStatus.DISPATCHED:
                    from hands import win, media
                    if step.action in {'open_app', 'switch_to'}:
                        window = win.find_window(step.args['app']) if win.IS_WINDOWS else None
                        if window and win.foreground() == window['hwnd']:
                            outcome = Outcome(OutcomeStatus.VERIFIED, result.say, result.data,
                                              [Evidence('windows.foreground', target=step.args,
                                                        expected={'focused': True}, observed={'hwnd': window['hwnd']})])
                    elif step.action in {'get_volume', 'set_volume', 'change_volume'}:
                        now = media.current_volume()
                        expected = resolved.get('level')
                        if step.action == 'change_volume':
                            expected = max(0, min(100, before_volume + resolved['step'])) if before_volume is not None else None
                        checkable = step.action != 'change_volume' or before_volume is not None
                        if checkable and now is not None and (expected is None or abs(now - expected) <= 1):
                            outcome = Outcome(OutcomeStatus.VERIFIED, f'Volume {now}%.', {'volume': now},
                                              [Evidence('windows.volume', expected={'level': expected}, observed={'level': now})])
                if outcome.status == OutcomeStatus.DISPATCHED:
                    outcome.say = 'That action was sent, but its result is not verified yet.'
            if (task.cancel.is_set() or time.monotonic() >= end) and outcome.status != OutcomeStatus.CANCELLED:
                outcome = Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                                  'Cancelled.' if task.cancel.is_set() else 'The task timed out.',
                                  side_effect_possible=not dry_run)
            task.results[step.id] = outcome
            combined_data.update(outcome.data)
            from core import log
            log.write({'type': 'task_step', 'task_id': task.id, 'revision': task.revision,
                       'step_id': step.id, 'action': step.action, 'outcome_status': outcome.status.value,
                       'mode': task.mode, 'evidence_count': len(outcome.evidence)})
            step.status = outcome.status.value
            texts.append(outcome.say)
            if outcome.status not in {OutcomeStatus.VERIFIED, OutcomeStatus.SIMULATED}:
                break
    except ActionInterrupted:
        outcome = Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                          'Cancelled.' if task.cancel.is_set() else 'The task changed or timed out.')
        texts.append(outcome.say)
    except KeyboardInterrupt:
        task.cancel.set()
        task.transition(TaskStatus.CANCELLED)
        raise
    except Exception:
        outcome = Outcome(OutcomeStatus.UNCERTAIN, 'I could not complete that task safely.', side_effect_possible=True)
        texts.append(outcome.say)
    finally:
        task.active_seconds += max(0, time.monotonic() - started_at)
        sp.deadline.reset(token)
        current.reset(runtime_token)
    task.transition({OutcomeStatus.VERIFIED: TaskStatus.SUCCEEDED, OutcomeStatus.SIMULATED: TaskStatus.SIMULATED,
                     OutcomeStatus.CANCELLED: TaskStatus.CANCELLED, OutcomeStatus.FAILED: TaskStatus.FAILED,
                     OutcomeStatus.NEEDS_INPUT: TaskStatus.UNCERTAIN}.get(outcome.status, TaskStatus.UNCERTAIN))
    data = dict(combined_data, outcome_status=outcome.status.value, task_id=task.id)
    return Result(outcome.ok, ' '.join(texts), data)
