import time

from runtime_python import ensure_modules_or_reexec

ensure_modules_or_reexec(["saleae"], "MIC_PRACTICE_LA_PROBE_REEXEC")
import saleae.automation as sa

def main() -> int:
    mgr = sa.Manager.connect(port=10430, connect_timeout_seconds=2)
    info = mgr.get_app_info()
    print("app", info, flush=True)

    devices = []
    for _ in range(30):
        devices = mgr.get_devices()
        if devices:
            break
        time.sleep(0.1)

    print("devices", devices, flush=True)
    mgr.close()

    if not devices:
        print("ERROR: Logic2 is running, but no analyzer device is connected/visible.", flush=True)
        print("FIX: Open Logic2 and confirm a device is listed (not Demo). Replug USB or restart Logic2.", flush=True)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
