#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    project = repo / "nucleo_g431_uart_bridge_pio"
    compiler = shutil.which("g++")
    if not compiler:
        raise RuntimeError("g++ not found; install a host C++ compiler")

    with tempfile.TemporaryDirectory(prefix="nucleo_bridge_selftest_") as temp_dir:
        executable = Path(temp_dir) / "nucleo_bridge_selftest.exe"
        compile_cmd = [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{project / 'include'}",
            str(project / "src" / "proto.cpp"),
            str(project / "src" / "bridge_controller.cpp"),
            str(project / "test" / "bridge_controller_test.cpp"),
            "-o",
            str(executable),
        ]
        subprocess.run(compile_cmd, check=True)
        result = subprocess.run([str(executable)], check=True, text=True, capture_output=True)
        print(result.stdout.strip())

        pwm_executable = Path(temp_dir) / "nucleo_pwm_math_selftest.exe"
        pwm_compile_cmd = [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{project / 'include'}",
            str(project / "src" / "motor_bench_policy.cpp"),
            str(project / "src" / "motor_pwm_math.cpp"),
            str(project / "test" / "pwm_math_test.cpp"),
            "-o",
            str(pwm_executable),
        ]
        subprocess.run(pwm_compile_cmd, check=True)
        pwm_result = subprocess.run(
            [str(pwm_executable)], check=True, text=True, capture_output=True
        )
        print(pwm_result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
