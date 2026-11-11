"""Compile a compound request once. Generated sentences are never routed again."""
import re
from core import details, planner
from core.audio_context import is_followup
from core.music_goals import compile_music
from core.search_goals import new_tab, web_query
from hands.registry import InvalidPlan


def clauses(text):
    outside = list(text)
    for match in re.finditer(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\x27[^\x27\n]*\x27(?!\w)', text):
        outside[match.start():match.end()] = 'X' * len(match[0])
    pattern = r'\s*(?:,?\s*\b(?:and then|then|after that|afterwards|and also)\b|;|,?\s*\band\b(?=\s+(?:open|close|search|play|set|turn|write|find|type|pause|google|check)\b))\s*'
    spans = list(re.finditer(pattern, ''.join(outside), re.I))
    result, start = [], 0
    for span in spans:
        result.append(text[start:span.start()].strip(' ,'))
        start = span.end()
    result.append(text[start:].strip(' ,'))
    return result


def compile_request(text, apps, brain):
    parts = clauses(text)
    if not 2 <= len(parts) <= 4 or any(not p for p in parts):
        return planner.Plan([], 'none', error='Please give me between two and four complete tasks.')
    # "click view then click status in notepad": the app named at the end applies to every part.
    tail = re.search(r'\s+(?:in|on)\s+([\w .]+?)\s*[.!?]*$', parts[-1])
    acts = r'(?:click|press|tap|hit|tick|untick|check|uncheck|turn on|turn off|type)\b'
    if tail and apps is not None and apps.match_exact(' '.join(tail[1].lower().split())) and re.match(acts, details._t(parts[-1])):
        parts = [p if not re.match(acts, details._t(p)) or re.search(r'\s(?:in|on)\s+[\w .]+$', details._t(p))
                 else f'{p} in {tail[1]}' for p in parts[:-1]] + [parts[-1]]
    steps = []
    typing_into = None   # the app opened by the previous part, if any
    volume_seen = False  # an earlier part was about the volume
    for index, part in enumerate(parts):
        intent = None
        if volume_seen and is_followup(details._t(part)):
            # "set volume to 70, then lower it by 32": "it" is the volume from the earlier part.
            part = re.sub(r'\bit\b', 'the volume', details._t(part))
        if new_tab(part):
            # A web search opens its own new tab, so "open a new tab and search X" is just the search.
            if index + 1 < len(parts) and web_query(parts[index + 1]):
                continue
            intent = details.Intent('web', 'open_site', {'site': 'new tab'})
        if intent is None:
            intent = compile_music(part)
        if intent is None:
            query = web_query(part)
            if query:
                intent = details.Intent('web', 'web_search', {'query': query})
        if intent is None:
            for area in ('media', 'timer', 'apps', 'notes', 'files'):
                candidate = details.by_rules(area, part, apps)
                if candidate and area == 'apps' and candidate.action in {'open', 'close', 'switch_to'}:
                    # Do not expand a model/fuzzy app guess into a compound's side effect.
                    requested = re.sub(r'^(?:open|launch|start|close|quit|switch to)\s+', '', details._t(part))
                    if not apps.match_exact(requested):
                        candidate = None
                if candidate and not candidate.check_app:
                    intent = candidate
                    break
        if intent is None:
            return planner.brain_plan(text, None, brain)  # Named steps for original request, not prose.
        try:
            built = planner.builtin_steps(intent)
            if not built:
                return planner.brain_plan(text, None, brain)
            # "open Word and write hello" means type it into Word, not make a separate Notepad note.
            if (typing_into and any(s['do'] == 'new_note' for s in built)
                    and not re.search(r'\bnote', part, re.I)):
                words = next(s['with'].get('text', '') for s in built if s['do'] == 'new_note')
                if not words:
                    return planner.Plan([], 'none', error=f'What should I type in {typing_into}? Nothing was run.')
                built = [planner._step('type_in_app', app=typing_into, text=words)]
            opened = [s['with'].get('app', '') for s in built if s['do'] in {'open_app', 'switch_to'}]
            typing_into = opened[-1] if opened and 'notepad' not in opened[-1].casefold() else None
            volume_seen = volume_seen or any(s['do'] in {'set_volume', 'change_volume', 'get_volume'} for s in built)
            steps.extend(built)
        except (InvalidPlan, TypeError, ValueError):
            return planner.Plan([], 'none', error='One of those tasks has invalid arguments; nothing was run.')
    try:
        steps = planner.validate_steps(steps)
    except InvalidPlan as error:
        return planner.Plan([], 'none', error=f'Nothing was run: {error}')
    return planner.Plan(steps, 'compiled')
