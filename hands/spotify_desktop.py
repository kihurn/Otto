"""Bounded Spotify desktop playback, without Spotify Web API calls."""
import re
import time
import unicodedata

from core.tasks import Outcome, OutcomeStatus, Evidence


def normalized(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+', text.casefold())).replace('the weekend', 'the weeknd')


def matches(label, query, artist=''):
    label = ' ' + normalized(label) + ' '
    return (' ' + normalized(query) + ' ' in label and
            (not artist or ' ' + normalized(artist) + ' ' in label))


def play_candidates(dialog, query, artist):
    candidates = []
    for ctrl in dialog.descendants(control_type='Button'):
        name = (ctrl.window_text() or '').strip()
        if not ctrl.is_visible() or not ctrl.is_enabled():
            continue
        if name.casefold().startswith('play ') and matches(name, query, artist):
            candidates.append(ctrl)
        elif name.casefold() == 'play' or name.casefold().startswith('play '):
            # Spotify's icon may be labelled only Play; bind it to a small song card.
            parent = ctrl.parent()
            for _ in range(3):
                if parent is None:
                    break
                bounds = parent.rectangle()
                if bounds.width() > 1600 or bounds.height() > 320:
                    break
                texts = [(c.window_text() or '') for kind in ('Text', 'Hyperlink')
                         for c in parent.descendants(control_type=kind)]
                text = ' '.join(texts)
                if len(texts) <= 12 and len(text) <= 600 and matches(text, query, artist):
                    candidates.append(ctrl)
                    break
                if len(texts) > 12:
                    break  # Never bind a player-wide Play button using the whole page.
                parent = parent.parent()
    return candidates


def play(step, task, end, progress):
    from core.action_runtime import check, ActionInterrupted
    from hands import apps, media, win
    from pywinauto import Application
    if step.action != 'play_music' or step.args.get('kind', 'auto') not in {'auto', 'track'}:
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'Desktop playback currently needs a song title and artist.')
    query, artist = step.args['query'], step.args.get('artist', '')
    progress('Opening Spotify and searching for the song.')
    check()
    opened = apps.open_app('Spotify')
    if not opened.ok:
        return Outcome(OutcomeStatus.UNCERTAIN, 'I could not open Spotify.')
    if task.cancel.is_set():
        return Outcome(OutcomeStatus.CANCELLED, 'Cancelled.')
    searched = apps.search_in_app('Spotify', f'{query} {artist}'.strip())
    if not searched.ok:
        return Outcome(OutcomeStatus.UNCERTAIN, searched.say)
    # Wait for a uniquely named, visible Play control. No blind global play toggle.
    chosen = None
    search_end = min(end, time.monotonic() + 10)
    while not task.cancel.is_set() and time.monotonic() < search_end:
        window = win.find_window('Spotify')
        if window:
            try:
                dlg = Application(backend='uia').connect(handle=window['hwnd']).window(handle=window['hwnd'])
                candidates = play_candidates(dlg, query, artist)
                if len(candidates) == 1:
                    chosen = candidates[0]
                    break
                if len(candidates) > 1:
                    return Outcome(OutcomeStatus.NEEDS_INPUT, 'More than one matching Play button is visible; please choose the song in Spotify.')
            except Exception:
                pass
        task.cancel.wait(0.5)
    if task.cancel.is_set():
        return Outcome(OutcomeStatus.CANCELLED, 'Cancelled.')
    if chosen is None:
        from core.recovery import recover
        recovered = bool(window and recover(window['hwnd'], 'activate_spotify_track', query, artist))
        if not recovered:
            return Outcome(OutcomeStatus.UNCERTAIN, 'Spotify search opened, but I could not identify a safe matching Play control. Please focus the song manually.')
    else:
        recovered = False
    if time.monotonic() >= end:
        return Outcome(OutcomeStatus.UNCERTAIN, 'The task timed out before play was pressed.')
    if not window or win.foreground() != window['hwnd']:
        return Outcome(OutcomeStatus.UNCERTAIN, 'Spotify lost focus; I have not pressed play.')
    progress('Starting the selected song and checking playback.')
    check()
    try:
        if not recovered:
            chosen.invoke()
    except ActionInterrupted:
        raise
    except Exception:
        return Outcome(OutcomeStatus.UNCERTAIN, 'The Play control did not respond; please check Spotify.', side_effect_possible=True)
    observations = []
    verify_end = min(end, time.monotonic() + 6)
    while not task.cancel.is_set() and time.monotonic() < verify_end:
        for session in media.sessions() or []:
            if 'spotify' not in session.get('app', '').casefold():
                continue
            evidence = Evidence('windows.spotify_session', target={'query': query, 'artist': artist},
                                expected={'playing': True}, observed=dict(session))
            observations.append(evidence)
            if (session.get('status') == media.PLAYING and matches(session.get('title', ''), query)
                    and (not artist or normalized(artist) == normalized(session.get('artist', '')))
                    and not task.cancel.is_set()):
                target = {'backend': 'desktop', 'query': query, 'artist': artist}
                return Outcome(OutcomeStatus.VERIFIED, f'Playing {query}' + (f' by {artist}.' if artist else '.'),
                               {'playback_target': target}, observations, side_effect_possible=True)
        task.cancel.wait(0.5)
    return Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                   'Cancelled.' if task.cancel.is_set() else 'I pressed the matching Play control, but could not verify the requested song.',
                   evidence=observations, side_effect_possible=True)
