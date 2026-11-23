"""Per-trial cumulative RPC baseline. Pure status validation; no device access."""
import math
import time


class RpcCounterGuard:
    KEYS = ('rpc_response_timeouts', 'rpc_send_timeouts')

    def __init__(self, decode_boot, *, clock=time.monotonic):
        self.decode_boot = decode_boot
        self.clock = clock
        self.baseline = None
        self.identity = None
        self.started = None
        self.last_time = None
        self.last_tick = None
        self.last_good = None
        self.last_rx = None
        self.progress_at = None
        self.samples = 0
        self.progressed = False
        self.ready = False
        self.failure = None

    @staticmethod
    def u32(value):
        if type(value) is not int or not 0 <= value <= 0xffffffff:
            raise ValueError('Missing or invalid uint32 telemetry')
        return value

    def fail(self, reason):
        if self.failure is None:
            self.failure = reason
        self.ready = False
        return False

    def observe(self, status):
        """Latch any fault; never rebaseline within the same trial."""
        if self.failure is not None:
            return False
        try:
            now = self.clock()
            if not math.isfinite(now) or self.last_time is not None and now < self.last_time:
                raise ValueError('Host monotonic clock invalid')
            age = status.get('mc_age_ms')
            if type(age) not in (int, float) or not 0 <= age < 300:
                raise ValueError('Native link stale or unreadable')
            counters = {key: self.u32(status.get(key)) for key in self.KEYS}
            # Boot pages are OFF-only and expire after1500ms during a valid RUN.
            # First binding requires a fresh page. Later compare its CRC-checked
            # immutable identity; mc_age/good-frame progress stay live throughout.
            boot = self.decode_boot(status, require_fresh=self.baseline is None)
            identity = (boot['Linux_boot_id'], tuple(boot['identity']))
            tick = self.u32(boot['native_tick_ms'])
            good = self.u32(status.get('mc_good_cnt'))
            # Native wire count is uint16 and saturates at65535. The Uno's
            # independent uint32 counter advances only on accepted native RSPs.
            # Missing/stalled/decreasing live progress still fails closed.
            live_rx = self.u32(status.get('uno_rx_count'))
            if self.baseline is None:
                if status.get('state') != 'SAFE' or status.get('pwm') != 0:
                    raise ValueError('RPC baseline requires outputs OFF')
                self.baseline = counters
                self.identity = identity
                self.started = self.progress_at = now
            else:
                if counters != self.baseline:
                    raise ValueError('RPC counter changed: new timeout, reset or wrap')
                if identity != self.identity:
                    raise ValueError('Boot identity changed')
                if ((tick - self.last_tick) & 0xffffffff) >= 0x80000000:
                    raise ValueError('Native uptime decreased')
                delta = (good - self.last_good) & 0xffffffff
                if delta >= 0x80000000:
                    raise ValueError('Native good-frame counter decreased')
                rx_delta=(live_rx-self.last_rx)&0xffffffff
                if rx_delta>=0x80000000:
                    raise ValueError('Uno native-reply counter decreased')
                if rx_delta:
                    self.progressed = True
                    self.progress_at = now
                elif now - self.progress_at >= .300:
                    raise ValueError('Native frames stopped advancing')
            self.last_time, self.last_tick, self.last_good = now, tick, good
            self.last_rx=live_rx
            self.samples += 1
            self.ready = self.samples >= 3 and self.progressed and now - self.started >= 2.0
            return True
        except (AssertionError, ValueError, TypeError, KeyError, OverflowError) as error:
            return self.fail(str(error) or type(error).__name__)

    def check(self, status):
        return self.observe(status) and self.ready

    def snapshot(self):
        return dict(baseline=self.baseline, boot_identity=self.identity,
                    samples=self.samples, ready=self.ready, failure=self.failure,
                    quiet_window_seconds=None if self.started is None else self.last_time-self.started,
                    policy='Stable historical counters allowed; any change latches failure; no rebaseline')
