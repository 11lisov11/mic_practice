"""USB-only stock-firmware checks. Never attach motors during this diagnostic."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from load_bench.red_board import DEFAULT_IDENTITY,RedBoard,enumerate_boards,passive_probe
from load_bench.runner import dump


def output_test():
    r=dict(kind="stock_usb_only_outputs",completed=False,steps=[],firmware_changed=False,
           motion_commands_sent=0,electrical_output_measured=False)
    with RedBoard(write_enabled=True) as board:
        r["identity"]=board.identity;r["initial"]=board.status()
        try:
            r["initialized"]=board.initialize_io()
            for mask in (1,2,4,8):
                r["steps"].append(dict(request=mask,status=board.outputs(mask)))
                time.sleep(.12)
                r["steps"].append(dict(request=0,status=board.outputs(0)))
            r["completed"]=True
        except BaseException as exc:r["error"]=repr(exc)
        finally:
            try:r["cleanup"]=board.stop_io()
            except BaseException as exc:r["completed"]=False;r["cleanup_error"]=repr(exc)
            r["hid_trace"]=board.trace
    return r


def crash_child():
    # Parent invokes this only for the user's separate, USB-only board.
    board=RedBoard(write_enabled=True)
    board.initialize_io()
    status=board.outputs(1)
    print(json.dumps(dict(kind="ready_before_abrupt_exit",pid=os.getpid(),status=status,
                         hid_trace=board.trace)),flush=True)
    os._exit(71)  # Intentionally bypass close/finally: emulate a host-process crash.


def host_loss_test(seconds=5.):
    r=dict(kind="stock_usb_only_host_process_loss",completed=False,firmware_changed=False,
           motion_commands_sent=0,electrical_output_measured=False,observation_s=seconds,
           usb_power_retained=True,samples=[],expected_child_exit=71)
    child=None
    try:
        child=subprocess.Popen([sys.executable,"-X","utf8",str(Path(__file__).resolve()),
            "_crash_child","--bare-usb-confirmed"],cwd=str(ROOT),stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,encoding="utf-8",creationflags=0x08000000)
        output,error=child.communicate(timeout=10)
        r["child_exit"]=child.returncode;r["child_stderr"]=error
        if child.returncode!=71:raise RuntimeError("Child did not reach verified output ON: "+error)
        r["child"]=json.loads(output)
        with RedBoard() as observer:
            r["identity"]=observer.identity;started=time.monotonic()
            while time.monotonic()-started<seconds:
                status=observer.status();status["since_observation_start_s"]=time.monotonic()-started
                r["samples"].append(status)
            r["observer_trace"]=observer.trace
        off=[x for x in r["samples"] if x["outputs"]==0]
        r["output_autooff_observed"]=bool(off)
        r["first_observed_off_s"]=off[0]["since_observation_start_s"] if off else None
        r["retained_on_for_at_least_s"]=max((x["since_observation_start_s"] for x in r["samples"] if x["outputs"]==1),default=0.)
        r["host_watchdog_qualified"]=False  # electrical timing is still unmeasured
        r["completed"]=True
    except BaseException as exc:r["error"]=repr(exc)
    finally:
        if child is not None and child.poll() is None:
            child.kill();child.communicate(timeout=3)  # only this task's own subprocess
        try:
            with RedBoard(write_enabled=True) as cleanup:
                cleanup.status();r["cleanup"]=cleanup.stop_io();r["cleanup_trace"]=cleanup.trace
        except BaseException as exc:r["completed"]=False;r["cleanup_error"]=repr(exc)
    return r


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("inventory","probe","outputs","host-loss","_crash_child"))
    parser.add_argument("--bare-usb-confirmed",action="store_true")
    parser.add_argument("--seconds",type=float,default=5.)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    if args.mode not in ("inventory","probe") and not args.bare_usb_confirmed:
        parser.error("Only run with the red board disconnected from ALL external circuits; --bare-usb-confirmed is required")
    if not 3<=args.seconds<=15:parser.error("Host-loss observation must be 3..15 seconds")
    if args.mode=="_crash_child":crash_child();return
    if args.mode=="inventory":result=dict(boards=enumerate_boards(),output_reports_sent=0)
    elif args.mode=="probe":result=passive_probe()
    elif args.mode=="outputs":result=output_test()
    else:result=host_loss_test(args.seconds)
    if args.out:dump(args.out,result)
    summary={k:v for k,v in result.items() if k not in ("steps","samples","hid_trace","observer_trace","cleanup_trace","child")}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if result.get("completed") is False:raise SystemExit(2)


if __name__=="__main__":main()
