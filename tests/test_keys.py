from senses.keys import ChordState


def test_chord_hold_release_and_repeat():
    calls = []
    state = ChordState(['ctrl', 'alt'], ['f9'], lambda: calls.append('down'),
                       lambda: calls.append('up'), lambda: calls.append('mute'))
    state.update('Key.ctrl_l', True)
    assert calls == []
    state.update('Key.alt_l', True)
    state.update('Key.alt_l', True)
    state.update('Key.ctrl_r', True)
    state.update('Key.ctrl_l', False)
    assert calls == ['down']
    state.update('Key.alt_l', False)
    assert calls == ['down', 'up']


def test_reverse_order_and_mute_repeat():
    calls = []
    state = ChordState(['ctrl', 'alt'], ['f9'], lambda: calls.append('down'),
                       lambda: calls.append('up'), lambda: calls.append('mute'))
    state.update('Key.alt_r', True)
    state.update('Key.ctrl_r', True)
    state.update('Key.ctrl_r', False)
    state.update('Key.f9', True)
    state.update('Key.f9', True)
    assert calls == ['down', 'up', 'mute']
