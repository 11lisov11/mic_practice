#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import math
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_DEVICE = "79204341"
DEFAULT_STATUS_URL = "http://127.0.0.1:18080"
DEFAULT_CLEANUP = ["STOP", "ESTOP", "STOP"]


ANDROID_SNIPPET = r"""
import base64, json, socket, sys, time, traceback
sys.path.insert(0, '/data/local/tmp')
from router_rpc import rpc_call


def emit(obj):
    print(json.dumps(obj, separators=(',', ':')), flush=True)


payload = json.loads(base64.b64decode(sys.argv[1].encode('ascii')).decode('utf-8'))
steps = payload.get('steps', [])
cleanup = payload.get('cleanup', [])
socket_timeout_s = float(payload.get('socket_timeout_s', 1.0))
command_delay_s = float(payload.get('command_delay_s', 0.05))
cleanup_delay_s = float(payload.get('cleanup_delay_s', 0.05))

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(socket_timeout_s)
seq_box = [1]
ok = True
cleanup_ok = True


def send_cmd(cmd, phase):
    seq = seq_box[0]
    seq_box[0] += 1
    t0 = time.time()
    resp = rpc_call(sock, seq, 'cmd', [cmd])
    dt_ms = (time.time() - t0) * 1000.0
    good = isinstance(resp, list) and len(resp) >= 4 and resp[2] is None and resp[3] is True
    emit({'event': 'cmd', 'phase': phase, 'seq': seq, 'cmd': cmd, 'ok': bool(good), 'dt_ms': round(dt_ms, 1), 'resp': resp})
    return bool(good)


try:
    emit({'event': 'connect', 'path': '/var/run/arduino-router.sock'})
    sock.connect('/var/run/arduino-router.sock')
    for idx, step in enumerate(steps, 1):
        if 'sleep_s' in step:
            sleep_s = max(0.0, float(step['sleep_s']))
            emit({'event': 'sleep', 'idx': idx, 'sleep_s': sleep_s})
            time.sleep(sleep_s)
            continue
        cmd = str(step.get('cmd', '')).strip()
        if not cmd:
            emit({'event': 'skip', 'idx': idx, 'reason': 'empty_cmd'})
            continue
        if not send_cmd(cmd, 'run'):
            ok = False
            break
        time.sleep(command_delay_s)
except BaseException as exc:
    ok = False
    emit({'event': 'fatal', 'error': repr(exc), 'trace': traceback.format_exc()})
finally:
    for cmd in cleanup:
        try:
            if not send_cmd(str(cmd), 'cleanup'):
                cleanup_ok = False
        except BaseException as exc:
            cleanup_ok = False
            emit({'event': 'cleanup_error', 'cmd': str(cmd), 'error': repr(exc)})
        time.sleep(cleanup_delay_s)
    try:
        sock.close()
    except Exception:
        pass
    emit({'event': 'done', 'ok': bool(ok), 'cleanup_ok': bool(cleanup_ok)})

raise SystemExit(0 if ok and cleanup_ok else 2)
"""


@dataclass(frozen=True)
class Step:
    cmd: str | None = None
    sleep_s: float | None = None

    def to_json(self) -> dict[str, Any]:
        if self.cmd is not None:
            return {"cmd": self.cmd}
        return {"sleep_s": float(self.sleep_s or 0.0)}


def http_status(base: str, timeout_s: float = 3.0) -> dict[str, Any] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base.rstrip("/") + "/api/status", timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"WARN: status precheck failed: {exc}", file=sys.stderr)
        return None
    if not payload.get("ok"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def fnum(st: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    if st is None:
        return default
    try:
        val = float(st.get(key, default))
        return val if math.isfinite(val) else default
    except Exception:
        return default


def status_line(st: dict[str, Any] | None) -> str:
    if st is None:
        return "status=unavailable"
    keys = ["state", "mode", "pwm", "estop", "bp_fault", "bp_bad", "bp_vdc", "i_rms", "enc_raw", "enc_rpm"]
    parts = []
    for key in keys:
        if key in st:
            parts.append(f"{key}={st.get(key)}")
    return " ".join(parts)


def status_int(st: dict[str, Any] | None, key: str, default: int = 0) -> int:
    try:
        return int(fnum(st, key, float(default)))
    except Exception:
        return default


def parse_step(raw: str) -> Step:
    value = raw.strip()
    lower = value.lower()
    if lower.startswith("sleep:"):
        return Step(sleep_s=max(0.0, float(value.split(":", 1)[1].strip())))
    if lower.startswith("cmd:"):
        value = value.split(":", 1)[1].strip()
    if not value:
        raise ValueError("empty step")
    return Step(cmd=value)


def clamp(x: float, lo: float, hi: float) -> float:
    return min(max(x, lo), hi)


def duty_vector(angle_rad: float, mag: float) -> tuple[float, float, float]:
    u = 0.5 + mag * math.cos(angle_rad)
    v = 0.5 + mag * math.cos(angle_rad - (2.0 * math.pi / 3.0))
    w = 0.5 + mag * math.cos(angle_rad + (2.0 * math.pi / 3.0))
    return tuple(clamp(x, 0.03, 0.97) for x in (u, v, w))


def build_duty_rotate_steps(mag: float, dwell_s: float, cycles: int, direction: str) -> list[Step]:
    angles = [0, 60, 120, 180, 240, 300]
    if direction == "ccw":
        angles = list(reversed(angles))

    steps: list[Step] = [
        Step(cmd="STOP"),
        Step(cmd="ESTOP CLEAR"),
        Step(sleep_s=0.20),
        Step(cmd="MODE DUTY"),
        Step(cmd="DUTY 0.5000 0.5000 0.5000"),
        Step(cmd="START"),
        Step(sleep_s=0.15),
    ]
    for _ in range(cycles):
        for deg in angles:
            du, dv, dw = duty_vector(math.radians(deg), mag)
            steps.append(Step(cmd=f"DUTY {du:.4f} {dv:.4f} {dw:.4f}"))
            steps.append(Step(sleep_s=dwell_s))
    return steps


def command_heads(steps: list[Step]) -> list[str]:
    heads: list[str] = []
    for step in steps:
        if step.cmd:
            heads.append(step.cmd.strip().split(maxsplit=1)[0].upper())
    return heads


def sequence_can_enable_pwm(steps: list[Step]) -> bool:
    for step in steps:
        if not step.cmd:
            continue
        cmd = step.cmd.strip().upper()
        if cmd == "START" or cmd.startswith("START "):
            return True
    return False


def sequence_duration_s(steps: list[Step], command_delay_s: float) -> float:
    total = 0.0
    for step in steps:
        if step.sleep_s is not None:
            total += max(0.0, step.sleep_s)
        elif step.cmd:
            total += command_delay_s
    return total


def build_steps(args: argparse.Namespace) -> list[Step]:
    steps: list[Step] = []
    for raw in args.step or []:
        steps.append(parse_step(raw))
    for raw in args.cmd or []:
        steps.append(Step(cmd=raw.strip()))
    if args.duty_rotate:
        steps.extend(build_duty_rotate_steps(args.mag, args.dwell_s, args.cycles, args.direction))
    if not steps:
        raise ValueError("no steps specified")
    return steps


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run a bounded command sequence through one persistent UNO Q ADB router socket."
    )
    ap.add_argument("--device", default=DEFAULT_DEVICE)
    ap.add_argument("--status-url", default=DEFAULT_STATUS_URL)
    ap.add_argument("--cmd", action="append", help="Command step. Can be repeated.")
    ap.add_argument("--step", action="append", help="Ordered step: 'cmd:START' or 'sleep:0.2'. Can be repeated.")
    ap.add_argument("--duty-rotate", action="store_true", help="Generate a bounded 6-vector DUTY rotation sequence.")
    ap.add_argument("--mag", type=float, default=0.20, help="DUTY rotation magnitude around 0.5.")
    ap.add_argument("--dwell-s", type=float, default=0.25)
    ap.add_argument("--cycles", type=int, default=1)
    ap.add_argument("--direction", choices=["cw", "ccw"], default="cw")
    ap.add_argument("--cleanup", action="append", help="Cleanup command. Default: STOP, ESTOP, STOP.")
    ap.add_argument("--no-cleanup", action="store_true", help="Disable cleanup commands. Not recommended.")
    ap.add_argument("--allow-hv", action="store_true", help="Allow enabling sequence when VBUS exceeds --max-vdc.")
    ap.add_argument("--max-vdc", type=float, default=60.0)
    ap.add_argument("--socket-timeout-s", type=float, default=1.0)
    ap.add_argument("--command-delay-s", type=float, default=0.05)
    ap.add_argument("--cleanup-delay-s", type=float, default=0.05)
    ap.add_argument("--max-bp-bad-delta", type=int, default=0)
    ap.add_argument("--post-settle-s", type=float, default=1.5, help="Poll final status for this long after cleanup.")
    ap.add_argument("--post-settle-poll-s", type=float, default=0.25)
    ap.add_argument("--hv-vdc-min", type=float, default=100.0, help="Minimum telemetry VBUS required when --allow-hv is used.")
    ap.add_argument("--skip-hv-vdc-min-check", action="store_true", help="Disable --allow-hv minimum VBUS telemetry check.")
    ap.add_argument("--timeout-s", type=float, default=0.0, help="ADB subprocess timeout. 0 = auto.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        steps = build_steps(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    cleanup = [] if args.no_cleanup else (args.cleanup if args.cleanup is not None else DEFAULT_CLEANUP)
    can_enable = sequence_can_enable_pwm(steps)
    pre = http_status(args.status_url)
    pre_bp_bad = status_int(pre, "bp_bad", 999999)
    print(f"PRE: {status_line(pre)}", flush=True)

    if pre is None and can_enable:
        print("ERROR: refusing enabling sequence because status precheck is unavailable", file=sys.stderr)
        return 3
    if pre is not None and can_enable:
        if not bool(pre.get("link", True)):
            print("ERROR: refusing enabling sequence because Blue Pill link is down", file=sys.stderr)
            return 3
        if fnum(pre, "bp_age_ms", 999999.0) > 1000.0 and fnum(pre, "bp_rsp_age_ms", 999999.0) > 1000.0:
            print("ERROR: refusing enabling sequence because Blue Pill telemetry is stale", file=sys.stderr)
            return 3
    if pre is not None and int(fnum(pre, "pwm", 0.0)) != 0 and can_enable:
        print("ERROR: refusing enabling sequence because PWM is already active", file=sys.stderr)
        return 3
    if pre is not None and can_enable:
        vdc = max(fnum(pre, "bp_vdc", 0.0), fnum(pre, "vdc", 0.0))
        if vdc > args.max_vdc and not args.allow_hv:
            print(
                f"ERROR: refusing enabling sequence at VBUS={vdc:.1f} V without --allow-hv",
                file=sys.stderr,
            )
            return 3
        if args.allow_hv and not args.skip_hv_vdc_min_check and vdc < args.hv_vdc_min:
            print(
                f"ERROR: refusing HV enabling sequence because telemetry VBUS={vdc:.1f} V is below "
                f"--hv-vdc-min={args.hv_vdc_min:.1f} V",
                file=sys.stderr,
            )
            return 3

    payload = {
        "steps": [step.to_json() for step in steps],
        "cleanup": cleanup,
        "socket_timeout_s": args.socket_timeout_s,
        "command_delay_s": args.command_delay_s,
        "cleanup_delay_s": args.cleanup_delay_s,
    }
    print(json.dumps({"steps": payload["steps"], "cleanup": cleanup}, indent=2), flush=True)
    if args.dry_run:
        return 0

    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    auto_timeout = sequence_duration_s(steps, args.command_delay_s) + len(cleanup) * args.cleanup_delay_s + 20.0
    timeout_s = args.timeout_s if args.timeout_s > 0 else max(20.0, auto_timeout)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["adb", "-s", args.device, "shell", "python3", "-", encoded],
            input=ANDROID_SNIPPET,
            text=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            timeout=timeout_s,
        )
        rc = int(proc.returncode)
    except subprocess.TimeoutExpired:
        print(f"ERROR: adb sequence subprocess timed out after {timeout_s:.1f}s", file=sys.stderr)
        rc = 124

    elapsed = time.monotonic() - started
    time.sleep(0.25)
    post = http_status(args.status_url)
    post_bp_bad = status_int(post, "bp_bad", 999999)
    bp_bad_delta = max(0, post_bp_bad - pre_bp_bad) if pre_bp_bad < 999999 and post_bp_bad < 999999 else 999999
    print(f"POST: {status_line(post)} elapsed_s={elapsed:.2f}", flush=True)
    if post is not None and int(fnum(post, "pwm", 0.0)) != 0:
        print("ERROR: final status still reports PWM active", file=sys.stderr)
        return 4

    settle_deadline = time.monotonic() + max(0.0, args.post_settle_s)
    settle_idx = 0
    while time.monotonic() < settle_deadline:
        time.sleep(max(0.05, args.post_settle_poll_s))
        sample = http_status(args.status_url)
        if sample is None:
            print(f"SETTLE {settle_idx}: status=unavailable", flush=True)
            continue
        settle_idx += 1
        sample_bp_bad = status_int(sample, "bp_bad", 999999)
        if sample_bp_bad > post_bp_bad:
            post_bp_bad = sample_bp_bad
        if int(fnum(sample, "pwm", 0.0)) != 0:
            print(f"SETTLE {settle_idx}: {status_line(sample)}", flush=True)
            print("ERROR: settled status reports PWM active", file=sys.stderr)
            return 4
        print(f"SETTLE {settle_idx}: {status_line(sample)}", flush=True)

    print(f"BP_BAD_DELTA: {bp_bad_delta}", flush=True)
    bp_bad_delta = max(0, post_bp_bad - pre_bp_bad) if pre_bp_bad < 999999 and post_bp_bad < 999999 else 999999
    print(f"BP_BAD_DELTA_SETTLED: {bp_bad_delta}", flush=True)
    if bp_bad_delta > args.max_bp_bad_delta:
        print(
            f"ERROR: bp_bad increased by {bp_bad_delta}, limit is {args.max_bp_bad_delta}",
            file=sys.stderr,
        )
        return 5
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
