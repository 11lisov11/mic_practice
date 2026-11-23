"""Stage the HMI completion fix for the installed AIR56 LSO pair."""
from hashlib import sha256
import json

from prepare_air56_lso_trip_capture import OUT as BASE, ROOT, replace

OUT = ROOT / 'artifacts/live_bench_20261123/air56_lso_hmi_bounded_stop_r1'


def patch_server(source):
    start = source.index('class HvArmState:')
    end = source.index('\nclass ', start + 1)
    arm = source[start:end]
    arm = replace(arm, '        self._calibration_provider = calibration_provider',
                  '        self._bounded_run = None\n        self._calibration_provider = calibration_provider')
    arm = replace(arm, '''    def mark_started(self) -> None:
        with self._lock:
            if self._expires_at > _now_ts():
                self._started = True
''', '''    def mark_started(self, bounded_run=None) -> None:
        with self._lock:
            if self._expires_at > _now_ts():
                self._started = True
                self._bounded_run = bounded_run if not self._manual_session else None

    def finish_bounded_run(self, status: dict) -> bool:
        with self._lock:
            if not self._started or self._manual_session or self._bounded_run is None:
                return False
            before_id, start_ms, pair, limit_s = self._bounded_run
            sd = status.get("mc_sd_live") or {}
            if ((status.get("fw_build"), status.get("mc_fw_build")) != pair
                or status.get("run_start_ms") != start_ms
                or not 0 <= _as_int(status, "mc_age_ms", 999999) < 300
                or _as_int(status, "precharge", 1) != 0
                or _as_int(status, "bp_ext", 0x08) & 0x08
                or not isinstance(sd, dict) or sd.get("level") != "HIGH"
                or sd.get("break_irq_enabled") is not True
                or sd.get("config_ok") is not True
                or not bounded_run_complete(status, {"run_id": before_id}, limit_s)):
                return False
            self._expires_at = 0.0
            self._started = False
            self._bounded_run = None
            return True
''')
    source = source[:start] + arm + source[end:]
    source = replace(source, '''                if run_ok and running:
                    self.hv_arm.mark_started()''', '''                if run_ok and running:
                    bounded_run = None
                    before_id = initial_status.get("run_id")
                    start_ms = candidate.get("run_start_ms")
                    pair = (candidate.get("fw_build"), candidate.get("mc_fw_build"))
                    if (not self._manual_start_requested and self.hv_arm.cfg.trial_gate is None
                        and effective_limit is not None and type(before_id) is int
                        and type(start_ms) is int and candidate.get("run_reason") == 0
                        and pair == (initial_status.get("fw_build"), initial_status.get("mc_fw_build"))
                        and candidate.get("run_id") == ((before_id + 1) & 0xffffffff)
                        and candidate.get("run_limit_ms") == round(effective_limit * 1000)):
                        bounded_run = (before_id, start_ms, pair, effective_limit)
                    self.hv_arm.mark_started(bounded_run)''')
    return replace(source, '''                    if not live_ok:
                        gate=self.hv_arm.cfg.trial_gate''', '''                    if live_ok and status is not None and self.hv_arm.finish_bounded_run(status):
                        self.logs.add(f"WIFI_BOUNDED_COMPLETE run_id={status['run_id']} outputs off")
                        self._runtime_bad_monitor.reset()
                        continue
                    if not live_ok:
                        gate=self.hv_arm.cfg.trial_gate''')


def main():
    source = BASE / 'web_hmi/server.py'
    data = source.read_bytes()
    verified = json.loads((BASE / 'verification.json').read_text(encoding='utf8'))
    assert sha256(data).hexdigest() == verified['web_hmi_sha256']
    result = patch_server(data.decode().replace('\r\n', '\n')).encode()
    compile(result, str(OUT / 'server.py'), 'exec')
    OUT.mkdir(exist_ok=True)
    (OUT / 'server.py').write_bytes(result)
    print(OUT)


if __name__ == '__main__':
    main()
