"""Check Uno RPC/loop ownership and execute the actual RAII lock on host threads."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def ownership_checks(source):
    signatures = ("static bool rpc_cmd(String cmd) {",
                  "static String rpc_get() {",
                  "void loop() {\n#if USE_ROUTER_BRIDGE")
    guarded = {}
    for signature in signatures:
        begin = source.find(signature)
        guarded[signature] = begin >= 0 and (
            "ScopedControlLock<ControlMutex> owner(g_control_owner);"
            in source[begin:begin + 400].split("#endif", 1)[0])
    return {
        "all_shared_state_entrypoints_guarded": all(guarded.values()),
        "same_kernel_mutex": "k_mutex_lock(&g_control_mutex, K_FOREVER)" in source,
        "priority_inheriting_mutex_not_IRQ_mask": "static struct k_mutex g_control_mutex{};" in source,
        "no_kernel_iterable_section": "K_MUTEX_DEFINE(g_control_mutex)" not in source,
        "initialized_before_router": (
            "if (k_mutex_init(&g_control_mutex) != 0) k_panic();\n    delay(6000);\n    Bridge.begin"
            in source),
        "failed_lock_panics": "if (k_mutex_lock(&g_control_mutex, K_FOREVER) != 0) k_panic();" in source,
        "release_before_yield": (
            "  owner.release();\n#endif\n#if defined(ARDUINO_ARCH_ZEPHYR)\n  k_yield();"
            in source),
    }


PROGRAM = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <thread>
#include <type_traits>
#include <vector>
#include "scoped_control_lock.h"
struct Mutex {
 std::recursive_mutex native;
 void lock() { native.lock(); }
 void unlock() { native.unlock(); }
};
using Guard = ScopedControlLock<Mutex>;
static_assert(!std::is_copy_constructible<Guard>::value, "guard cannot be copied");
static_assert(!std::is_copy_assignable<Guard>::value, "guard cannot be assigned");
unsigned assertions;
void check(bool ok, const char *name) {
 ++assertions;
 if (!ok) { std::fprintf(stderr, "FAIL %s\n", name); std::exit(1); }
}
bool other_thread_can_lock(Mutex &mutex) {
 bool acquired = false;
 std::thread worker([&]() {
  acquired = mutex.native.try_lock();
  if (acquired) mutex.native.unlock();
 });
 worker.join();
 return acquired;
}
int main() {
 Mutex mutex;
 {
  Guard outer(mutex);
  check(!other_thread_can_lock(mutex), "other thread excluded during owned transaction");
  {
   Guard inner(mutex);
   check(!other_thread_can_lock(mutex), "nested RPC snapshot owns same recursive mutex");
  }
  check(!other_thread_can_lock(mutex), "inner destruction does not release outer owner");
  outer.release();
  check(other_thread_can_lock(mutex), "explicit release allows another thread before yield");
  outer.release();
 }
 check(other_thread_can_lock(mutex), "double release and destructor do not over-unlock");
 auto early_return = [&]() { Guard owner(mutex); return; };
 early_return();
 check(other_thread_can_lock(mutex), "early return releases owner");
 try { Guard owner(mutex); throw 1; } catch (int) {}
 check(other_thread_can_lock(mutex), "exception releases owner in host test");
 std::vector<unsigned char> wire;
 std::mutex byte_mutex;
 std::atomic<unsigned> ready{0};
 auto sender = [&](unsigned char id) {
  ++ready;
  while (ready != 2) std::this_thread::yield();
  for (unsigned packet = 0; packet < 1000; ++packet) {
   Guard owner(mutex);
   for (unsigned byte = 0; byte < 32; ++byte) {
    { std::lock_guard<std::mutex> byte_owner(byte_mutex); wire.push_back(id); }
    std::this_thread::yield();
   }
  }
 };
 std::thread loop(sender, 0xAA), rpc(sender, 0x55);
 loop.join(); rpc.join();
 check(wire.size() == 64000, "all simulated frame bytes retained");
 for (unsigned offset = 0; offset < wire.size(); offset += 32) {
  check(std::all_of(wire.begin()+offset, wire.begin()+offset+32,
                   [&](unsigned char b) { return b == wire[offset]; }),
        "concurrent loop and callback cannot splice frames with shared ownership");
 }
 std::printf("{\"pass\":true,\"assertions\":%u,\"frames\":2000}\n", assertions);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    source_path = root / "UNOQ_MOTOR/UNOQ_MOTOR.ino"
    header = root / "UNOQ_MOTOR/scoped_control_lock.h"
    source = source_path.read_text(encoding="utf-8-sig")
    report = {"pass": False, "scope": "real RAII header on host mutex; source placement checks",
              "hardware_commands": 0, "powered_CRC_cause_proven": False,
              "sources": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (source_path, header)}}
    try:
        checks = ownership_checks(source)
        report["placement_checks"] = checks
        if not all(checks.values()):
            raise RuntimeError("missing transaction ownership")
        removed = source.replace("  ScopedControlLock<ControlMutex> owner(g_control_owner);", "", 1)
        report["removed_callback_guard_detected"] = not all(ownership_checks(removed).values())
        compiler = shutil.which("g++")
        if not compiler:
            raise RuntimeError("g++ required")
        (out / "host_test.cpp").write_text(PROGRAM, encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            unit, exe = Path(folder) / "test.cpp", Path(folder) / "test.exe"
            unit.write_text(PROGRAM, encoding="utf-8")
            build = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                    "-pthread", "-I", str(header.parent), str(unit), "-o", str(exe)],
                                   capture_output=True, text=True, timeout=60)
            (out / "compile.log").write_text(build.stdout + build.stderr, encoding="utf-8")
            if build.returncode:
                raise RuntimeError("host build failed")
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
            (out / "run.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            if run.returncode:
                raise RuntimeError(run.stderr.strip())
            report.update(json.loads(run.stdout))
            report["pass"] = report["pass"] and report["removed_callback_guard_detected"]
    except Exception as exc:
        report["pass"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
