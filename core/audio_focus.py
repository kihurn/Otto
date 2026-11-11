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

    # Errors that mean "this one app's audio session went away or is busy", which is normal on Windows.
    # One session failing must never stop the others from being restored (review finding R5).
    @staticmethod
    def _session_errors():
        errors = [OSError, AttributeError, ValueError]
        try:
            from comtypes import COMError
            errors.append(COMError)
        except Exception:
            pass
        return tuple(errors)

    def update(self, active):
        """One round: give back volumes we no longer need to hold, then (while Otto is active) cap the rest."""
        endpoint, sessions = self.provider.snapshot()
        errors = self._session_errors()
        self.failed = set()                    # sessions that errored this round; retried next round
        for key, record in list(self.owned.items()):
            if key in sessions:                # a disconnected session can return later with the same identity
                self._settle(key, record, sessions[key], active and sessions[key][0] == endpoint, errors)
        if not active:
            self.relinquished.clear()
            return
        for key, (device, volume) in sessions.items():
            if device == endpoint and key not in self.owned and key not in self.relinquished:
                self._cap(key, volume, errors)

    def _settle(self, key, record, session, keep_capped, errors):
        """Restore one session we capped, unless it should stay capped. Errors only affect this session."""
        _, volume = session
        try:
            if abs(volume.GetMasterVolume() - record['applied']) > .001:
                self.relinquished.add(key)          # the user changed it; leave it alone
            elif keep_capped:
                return
            else:
                volume.SetMasterVolume(record['original'], None)
                if abs(volume.GetMasterVolume() - record['original']) > .001:
                    return
        except errors:
            self.failed.add(key)                    # keep the receipt; try again later
            return
        del self.owned[key]
        self.save()

    def _cap(self, key, volume, errors):
        """Turn one louder-than-the-cap session down, recording its original volume first."""
        try:
            if volume.GetMute():
                return
            original = volume.GetMasterVolume()
        except errors:
            self.failed.add(key)
            return
        if original <= self.cap:
            return
        self.owned[key] = {'original': original, 'applied': self.cap}
        self.save()  # Persist the receipt before the mutation (a journal failure stops here).
        try:
            volume.SetMasterVolume(self.cap, None)
        except errors:
            self.failed.add(key)   # unchanged volume; the next round sees it and drops the receipt


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
            misses = 0
            while not self.closed:
                with self.lock:
                    now = time.monotonic()
                    self.leases = {key:end for key,end in self.leases.items() if end > now}
                    active = bool(self.leases)
                if active or caps.owned:
                    try:
                        caps.update(active)
                        misses = 0
                    except OSError:
                        # Listing sessions failed (device change, Windows busy). Retry a few times before giving up.
                        misses += 1
                        if misses >= 10:
                            raise
                self.wake.wait(.4)
                self.wake.clear()
        except Exception as error:
            warn(f'Audio ducking stopped ({type(error).__name__}).')
        finally:
            for _ in range(3):                       # restore everything we can before exiting
                try:
                    if not caps.owned:
                        break
                    caps.update(False)
                    if not getattr(caps, 'failed', None):
                        break
                except Exception:
                    pass  # The next startup can restore an unchanged session from the journal.
                time.sleep(.2)
            if ownership:
                if locked:
                    ownership.seek(0)
                    msvcrt.locking(ownership.fileno(), msvcrt.LK_UNLCK, 1)
                ownership.close()
            comtypes.CoUninitialize()
