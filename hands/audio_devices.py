"""Windows media output discovery and verified changes, with session-local undo."""
import re
import time
from core.action_runtime import check
from core.tasks import Evidence, Outcome, OutcomeStatus
from hands.registry import action, READ, UNDOABLE

MEDIA_ROLES = (0, 1)
_receipt = None


class WindowsAudioOutputs:
    def inventory(self):
        from pycaw.pycaw import AudioUtilities
        return {device.id: device.FriendlyName for device in AudioUtilities.GetAllDevices(0, 1)}

    def defaults(self):
        from pycaw.pycaw import AudioUtilities
        enumerator = AudioUtilities.GetDeviceEnumerator()
        return {role: enumerator.GetDefaultAudioEndpoint(0, role).GetId() for role in MEDIA_ROLES}

    def set(self, endpoint, role):
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import ERole
        check()
        AudioUtilities.SetDefaultDevice(endpoint, [ERole(role)])


def observed(say, data, expected=None):
    return Outcome(OutcomeStatus.VERIFIED, say, data,
                   [Evidence('windows.audio_outputs', expected=expected or {}, observed=data)])


@action('list_audio_outputs', READ, {}, lambda: 'list audio outputs')
def list_outputs():
    outputs = WindowsAudioOutputs().inventory()
    return observed('Available outputs are ' + ', '.join(outputs.values()) + '.' if outputs else
                    'Windows reports no active audio outputs.', {'outputs': outputs})


@action('get_audio_output', READ, {}, lambda: 'read the default audio output')
def get_output():
    provider = WindowsAudioOutputs()
    defaults = provider.defaults()
    name = provider.inventory().get(defaults[1], 'an output no longer listed as active')
    return observed(f'Default media output is {name}.', {'defaults': defaults})


def change(provider, expected_before, requested):
    if provider.defaults() != expected_before or not set(requested.values()) <= set(provider.inventory()):
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'Audio outputs changed. Please select the output again.')
    failed = False
    for role, endpoint in requested.items():
        if expected_before[role] == endpoint:
            continue
        check()
        try:
            provider.set(endpoint, role)
        except (OSError, AttributeError):
            failed = True
            break
    actual = provider.defaults()
    if actual != requested or failed:
        return Outcome(OutcomeStatus.UNCERTAIN, 'Windows did not confirm the complete output change.',
                       {'defaults': actual}, [Evidence('windows.audio_outputs', expected=requested, observed=actual)],
                       side_effect_possible=True)
    return observed('Audio output changed.', {'defaults': actual}, requested)


def select_output(provider, endpoint):
    global _receipt
    outputs = provider.inventory()
    if endpoint not in outputs:
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'That audio output is no longer available.')
    before = provider.defaults()
    wanted = dict.fromkeys(MEDIA_ROLES, endpoint)
    result = change(provider, before, wanted)
    if result.ok:
        result.say = (f'{outputs[endpoint]} was already the output, so nothing changed.' if before == wanted
                      else f'Default media output is {outputs[endpoint]}.')
        if before != wanted:
            _receipt = (time.monotonic() + 120, before, wanted)
    else:
        _receipt = None
    return result


@action('set_audio_output', UNDOABLE, {'device': 'audio output name'}, lambda device: f'set audio output to {device}')
def set_output(device):
    provider = WindowsAudioOutputs()
    outputs = provider.inventory()
    name = device.strip().casefold()
    matches = {key: label for key, label in outputs.items() if label.casefold() == name}
    if not matches:
        pattern = re.compile(r'(?<!\w)' + re.escape(name) + r'(?!\w)')
        matches = {key: label for key, label in outputs.items() if pattern.search(label.casefold())}
    if len(matches) != 1:
        if not matches:
            return Outcome(OutcomeStatus.NEEDS_INPUT, f'I found no active output called {device}. Ask me to list audio outputs.')
        candidates = list(matches.items())[:8]
        options = ', '.join(f'{index}. {label}' for index, (_, label) in enumerate(candidates, 1))
        return Outcome(OutcomeStatus.NEEDS_INPUT, f'Which output? {options}', {'audio_candidates': candidates})
    return select_output(provider, next(iter(matches)))


@action('swap_audio_output', UNDOABLE, {}, lambda: 'switch to the other audio output')
def swap_output():
    """"Swap my audio output": the output that is NOT playing now (with more than two, ask which)."""
    provider = WindowsAudioOutputs()
    outputs = provider.inventory()
    current = provider.defaults().get(1)
    others = [(key, label) for key, label in outputs.items() if key != current]
    if not others:
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'There is only one audio output, so there is nothing to swap to.')
    if len(others) > 1:
        candidates = others[:8]
        options = ', '.join(f'{index}. {label}' for index, (_, label) in enumerate(candidates, 1))
        return Outcome(OutcomeStatus.NEEDS_INPUT, f'Swap to which output? {options}', {'audio_candidates': candidates})
    return select_output(provider, others[0][0])


@action('set_audio_output_id', UNDOABLE, {'device': 'selected audio endpoint ID'}, lambda device: 'set the selected audio output')
def set_output_id(device):
    return select_output(WindowsAudioOutputs(), device)


@action('undo_audio_output', UNDOABLE, {}, lambda: 'restore the previous audio output')
def undo_output():
    global _receipt
    receipt, _receipt = _receipt, None
    if not receipt or receipt[0] < time.monotonic():
        return Outcome(OutcomeStatus.NEEDS_INPUT, 'There is no recent output change to undo.')
    _, previous, selected = receipt
    result = change(WindowsAudioOutputs(), selected, previous)
    if result.ok:
        result.say = 'Restored the previous media output.'
    return result
