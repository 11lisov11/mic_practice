"""Host trial keepalive; never sends START, CLEAR or motor configuration."""
import threading
import time


class TrialHeartbeat:
    def __init__(self, request, interval=0.5):
        self.request = request
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.error = None
        self.sent = 0
        self.last_ok = None
        self.events = []

    def pulse(self):
        try:
            self.request('/api/operator-heartbeat', {}, timeout=2)
            self.last_ok = time.monotonic()
            self.sent += 1
            self.events.append(dict(at=self.last_ok, ok=True))
        except Exception as error:
            self.error = str(error)
            self.events.append(dict(at=time.monotonic(), ok=False, error=self.error))
            raise

    def start(self):
        self.pulse()  # Confirm one authenticated keepalive before ARM.
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.pulse()
            except Exception:
                return

    def healthy(self):
        return (self.error is None and self.last_ok is not None
                and time.monotonic() - self.last_ok < 3)

    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.5)

    def snapshot(self):
        return dict(sent=self.sent, error=self.error, events=list(self.events),
                    interval_s=self.interval, motor_commands=0)
