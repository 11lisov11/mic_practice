"""Reproduce a local STOP followed by a valid RUN heartbeat; no hardware I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def function(text, name):
    match = re.search(r"(?:__weak\s+)?void\s+" + name + r"\s*\([^;]*?\)\s*\{", text)
    if not match:
        raise ValueError("Missing function: " + name)
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[match.start():end].replace("__weak", "")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    main_source = (args.project / "Src/main.c").read_text()
    tasks_source = (args.project / "Src/mc_tasks.c").read_text()
    callback = function(tasks_source, "UI_HandleStartStopButton_cb")
    start = "    if (start_state == IDLE) {"
    end = "\n  }\n  HAL_NVIC_EnableIRQ(USART1_IRQn);"
    if main_source.count(start) != 1 or main_source.count(end) != 1:
        raise ValueError("Unexpected RUN command publication layout")
    publication = main_source[main_source.index(start):main_source.index(end)]
    program = r'''
#include <cstdio>
enum { IDLE, RUN, STOPPING };
int state = RUN;
unsigned starts = 0;
unsigned mic_break_start_window = 0;
int MC_GetSTMStateMotor1() { return state; }
bool MC_StopMotor1() { state = STOPPING; return true; }
bool MC_StartMotor1() { ++starts; state = RUN; return true; }
''' + callback + r'''
int main() {
 UI_HandleStartStopButton_cb();
 if (state != STOPPING) return 2;
 // Model completion of the MCSDK stop procedure. No electromechanical model.
 state = IDLE;
 const int start_state = MC_GetSTMStateMotor1();
 bool start_failed = false;
''' + publication + r'''
 std::printf("restart=%u failed=%u\n", starts, unsigned(start_failed));
 return starts == 1 && !start_failed ? 0 : 3;
}
'''
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ required")
    args.outdir.mkdir(parents=True, exist_ok=False)
    unit = args.outdir.resolve() / "button_restart.cpp"
    executable = unit.with_suffix(".exe")
    unit.write_text(program)
    subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(unit), "-o", str(executable)], check=True, capture_output=True, text=True)
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
    report = {
        "schema": "mic_ai.local_button_restart_audit.v1",
        "reproduction_pass": True,
        "button_stop_restart_path_reproduced": True,
        "installed_firmware_safe_local_stop_proven": False,
        "hardware_commands": 0,
        "firmware_modified": False,
        "stdout": result.stdout.strip(),
        "source_sha256": {
            name: hashlib.sha256((args.project / name).read_bytes()).hexdigest()
            for name in ("Src/main.c", "Src/mc_tasks.c")
        },
        "assumptions": ["Valid ENABLE heartbeat passes preceding transport and semantic guards",
                        "No active MCSDK fault; stop procedure reaches IDLE"],
        "limitations": ["Extracted callback and START branch with mocked MCSDK APIs",
                        "No IRQ timing, physical PWM or powered button test",
                        "Does not establish that the user encountered this path"],
    }
    (args.outdir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
