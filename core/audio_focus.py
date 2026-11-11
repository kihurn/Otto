"""Temporary per-session audio caps. Keep endpoint volume and mute untouched."""
from contextlib import contextmanager
import os
import threading
import time
from uuid import uuid4


class WindowsSessions:
    def snapshot(self):
        from comtypes import COMError
        from pycaw.pycaw import AudioSession, AudioUtilities, IAudioSessionControl2
        default = AudioUtilities.GetSpeakers().id
        sessions = {}
        for device in AudioUtilities.GetAllDevices(0, 1):
            try:
                iterator = device.AudioSessionManager.GetSessionEnumerator()
                for index in range(iterator.GetCount()):
                    control = iterator.GetSession(index).QueryInterface(IAudioSessionControl2)
                    session = AudioSession(control)
                    if session.ProcessId in (0, os.getpid()):
                        continue
                    key = device.id + '|' + session.InstanceIdentifier
                    sessions[key] = (device.id, session.SimpleAudioVolume)
            except (OSError, AttributeError, COMError):
                if device.id == default:
                    raise
                continue
        return default, sessions


class SessionCaps:
    def __init__(self, provider, cap, journal):
        self.provider = provider
        self.cap = cap
        self.journal = journal
        self.owned = {}
        self.relinquished = set()

    def save(self):
        from core.config import save_json
        save_json(self.journal, self.owned)

    def recover(self):
        from core.config import load_json
        previous = load_json(self.journal, {})
        if isinstance(previous, dict):
            self.owned = {key: record for key, record in previous.items()
                          if isinstance(record, dict) and set(record) == {'original', 'applied'}
                          and all(type(value) in (float, int) and 0 <= value <= 1 for value in record.values())}
        self.update(False)

    def update(self, active):
        endpoint, sessions = self.provider.snapshot()
        for key, record in list(self.owned.items()):
            if key not in sessions:
                continue  # A disconnected session can return with the same identity.
            device, volume = sessions[key]
            now = volume.GetMasterVolume()
            if abs(now - record['applied']) > .001:
                self.relinquished.add(key)
            elif active and device == endpoint:
                continue
            else:
                volume.SetMasterVolume(record['original'], None)
                if abs(volume.GetMasterVolume() - record['original']) > .001:
                    continue
            del self.owned[key]
            self.save()
        if not active:
            self.relinquished.clear()
            return
        for key, (device, volume) in sessions.items():
            if device != endpoint or key in self.owned or key in self.relinquished or volume.GetMute():
                continue
            original = volume.GetMasterVolume()
            if original > self.cap:
                self.owned[key] = {'original': original, 'applied': self.cap}
                self.save()  # Persist the receipt before the mutation.
                volume.SetMasterVolume(self.cap, None)


class AudioFocus:
    """Only the worker touches COM. Hotkey callbacks update a lease and return."""
    def __init__(self, enabled, cap=.2, idle_seconds=30, warn=lambda msg: None):
        self.lock = threading.Lock()
        self.leases = {}
        self.wake = threading.Event()
        self.closed = False
        self.idle_seconds = idle_seconds
        self.thread = None
        if enabled and os.name == 'nt':
            from core.config import DATA
            caps = SessionCaps(WindowsSessions(), cap, DATA / 'audio-duck-recovery.json')
            self.thread = threading.Thread(target=self._worker, args=(caps, warn), daemon=True)
            self.thread.start()

    def acquire(self, key, seconds=None):
        if self.thread is None:
            return
        with self.lock:
            self.leases[key] = time.monotonic() + (seconds or self.idle_seconds)
        self.wake.set()

    def release(self, key):
        with self.lock:
            self.leases.pop(key, None)
        self.wake.set()

    @contextmanager
    def hold(self, seconds=60):
        key = uuid4().hex
        self.acquire(key, seconds)
        try:
            yield
        finally:
            self.release(key)

    def close(self):
        self.closed = True
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=3)

    def _worker(self, caps, warn):
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception as error:
            warn(f'Audio ducking unavailable ({type(error).__name__}).')
            return
        ownership = None
        locked = False
        try:
            import msvcrt
            ownership = caps.journal.with_suffix('.lock').open('a+b')
            if ownership.tell() == 0:
                ownership.write(b'0')
                ownership.flush()
            ownership.seek(0)
            msvcrt.locking(ownership.fileno(), msvcrt.LK_NBLCK, 1)
            locked = True
            caps.recover()
            while not self.closed:
                with self.lock:
                    now = time.monotonic()
                    self.leases = {key:end for key,end in self.leases.items() if end > now}
                    active = bool(self.leases)
                if active or caps.owned:
                    caps.update(active)
                self.wake.wait(.4)
                self.wake.clear()
        except Exception as error:
            warn(f'Audio ducking stopped ({type(error).__name__}).')
        finally:
            try:
                if caps.owned:
                    caps.update(False)
            except Exception:
                pass  # The next startup can restore an unchanged session from the journal.
            if ownership:
                if locked:
                    ownership.seek(0)
                    msvcrt.locking(ownership.fileno(), msvcrt.LK_UNLCK, 1)
                ownership.close()
            comtypes.CoUninitialize()
