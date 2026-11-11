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


# Words that mean a *different recording* than the one asked for. "The Hills (Live)" is not "The Hills".
VERSION_WORDS = {'live', 'remix', 'remixed', 'mix', 'acoustic', 'instrumental', 'karaoke', 'cover', 'demo',
                 'sped', 'slowed', 'reverb', 'nightcore', 'edit', 'version', 'reprise', 'extended', 'unplugged',
                 'session', 'radio', 'mashup', 'bootleg', 'rework', 'flip', 'vip', '8d', 'clean', 'explicit'}
# Extra title parts that are still the same recording.
_SAME = re.compile(r'(?:^(?:feat|ft|featuring|with|from)\b)|(?:remaster)', re.I)


def song_title(title: str) -> str:
    """The comparable part of a playing title: drops 'feat. X', 'with X' and 'Remastered 2011', but keeps
    version words like Live, Remix or Sped Up so a different recording never counts as the right one."""
    # Split on ' - ' and on brackets; each piece is stripped afterwards (simple, linear-time patterns).
    parts = [p.strip() for p in re.split(r'[()\[\]]| - ', title or '')]
    main, extras = parts[0], [p for p in parts[1:] if p]
    kept = [e for e in extras if not _SAME.search(e.strip())]
    return normalized(' '.join([main] + kept))


def same_recording(playing_title: str, query: str) -> bool:
    """Exact match on the song (ignoring featured artists and remaster notes)."""
    return song_title(playing_title) == song_title(query)


def different_version(playing_title: str, query: str) -> bool:
    """Same song name but a version the user didn't ask for, e.g. a live recording or remix."""
    playing, wanted = song_title(playing_title), song_title(query)
    if playing == wanted or not playing.startswith(wanted + ' '):
        return False
    return bool(set(playing[len(wanted):].split()) & VERSION_WORDS)


def play_candidates(dialog, query, artist):
    candidates = []
    for ctrl in dialog.descendants(control_type='Button'):
        name = (getattr(getattr(ctrl, 'element_info', None), 'name', '') or ctrl.window_text() or '').strip()
        if not ctrl.is_visible() or not ctrl.is_enabled():
            continue
        title = normalized(query)
        label = normalized(name)
        exact_play = f'play {title}'
        if label == (f'{exact_play} by {normalized(artist)}' if artist else exact_play):
            candidates.append(ctrl)
        elif label in {'play', exact_play}:
            # Spotify's icon may be labelled only Play; bind it to a small song card.
            parent = ctrl.parent()
            for _ in range(3):
                if parent is None:
                    break
                bounds = parent.rectangle()
                if bounds.width() > 1600 or bounds.height() > 320:
                    break
                texts = [(getattr(getattr(c, 'element_info', None), 'name', '') or c.window_text() or '') for kind in ('Text', 'Hyperlink')
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
                if candidates:
                    # Spotify often lists the same song twice (the Top result card and again under Songs).
                    # Every candidate already matches the requested title and artist, so take the highest one
                    # on the page; playback is still checked against Windows afterwards.
                    chosen = candidates[0] if len(candidates) == 1 else min(
                        candidates, key=lambda c: (c.rectangle().top, c.rectangle().left))
                    break
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
            artist_ok = not artist or normalized(artist) == normalized(session.get('artist', ''))
            if (session.get('status') == media.PLAYING and artist_ok
                    and different_version(session.get('title', ''), query) and not task.cancel.is_set()):
                # Something with the right name is playing, but it's a live/remix/sped-up version.
                return Outcome(OutcomeStatus.NEEDS_INPUT,
                               f"Spotify is playing \"{session.get('title')}\", which looks like a different version. "
                               "Want me to look for the original?", evidence=observations + [evidence],
                               side_effect_possible=True)
            if (session.get('status') == media.PLAYING and same_recording(session.get('title', ''), query)
                    and artist_ok and not task.cancel.is_set()):
                target = {'backend': 'desktop', 'query': query, 'artist': artist}
                return Outcome(OutcomeStatus.VERIFIED, f'Playing {query}' + (f' by {artist}.' if artist else '.'),
                               {'playback_target': target}, observations, side_effect_possible=True)
        task.cancel.wait(0.5)
    return Outcome(OutcomeStatus.CANCELLED if task.cancel.is_set() else OutcomeStatus.UNCERTAIN,
                   'Cancelled.' if task.cancel.is_set() else 'I pressed the matching Play control, but could not verify the requested song.',
                   evidence=observations, side_effect_possible=True)
