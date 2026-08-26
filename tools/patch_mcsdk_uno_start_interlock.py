#!/usr/bin/env python3
"""Restore the MIC_AI stop-only policy after MCSDK code regeneration."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_source(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8", errors="strict").replace("\r\n", "\n"), newline


def write_source(path: Path, text: str, newline: str) -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def patch_mcp(path: Path) -> bool:
    text, newline = read_source(path)
    original = text
    text, count_start = re.subn(
        r"MCPResponse\s*=\s*\(MCI_StartMotor\(pMCI\)\s*==\s*true\)\s*\?\s*MCP_CMD_OK\s*:\s*MCP_CMD_NOK\s*;",
        "/* MIC_AI safety policy: only the validated UNO Q scalar link may start the motor. */\n"
        "        MCPResponse = MCP_CMD_NOK;",
        text,
        count=1,
    )
    text, count_toggle = re.subn(
        r"MCPResponse\s*=\s*\(MCI_StartMotor\(pMCI\)\s*==\s*true\)\s*\?\s*MCP_CMD_OK\s*:\s*MCP_CMD_NOK\s*;",
        "/* Keep Motor Pilot/MCP as a monitoring and stop path, never as a start bypass. */\n"
        "          MCPResponse = MCP_CMD_NOK;",
        text,
        count=1,
    )
    if count_start + count_toggle not in (0, 2):
        raise RuntimeError(f"Unexpected number of MCP start sites patched: {count_start + count_toggle}")
    if "case START_MOTOR" not in text or "case START_STOP" not in text:
        raise RuntimeError("MCSDK MCP command cases are missing")
    if text != original:
        write_source(path, text, newline)
        return True
    return False


def patch_button(path: Path) -> bool:
    text, newline = read_source(path)
    original = text
    callback = re.search(
        r"(__weak void UI_HandleStartStopButton_cb \(void\)\s*\{\s*"
        r"/\* USER CODE BEGIN START_STOP_BTN \*/)(.*?)(/\* USER CODE END START_STOP_BTN \*/)",
        text,
        flags=re.DOTALL,
    )
    if callback is None:
        raise RuntimeError("MCSDK start/stop callback markers are missing")
    safe_body = (
        "\n  /* PC13 is deliberately stop-only; motor start requires a validated UNO Q frame. */\n"
        "  if (MC_GetSTMStateMotor1() != IDLE)\n"
        "  {\n"
        "    MC_StopMotor1();\n"
        "  }\n"
    )
    text = text[: callback.start()] + callback.group(1) + safe_body + callback.group(3) + text[callback.end() :]
    if text != original:
        write_source(path, text, newline)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    mcp = project / "Src" / "mcp.c"
    tasks = project / "Src" / "mc_tasks.c"
    for path in (mcp, tasks):
        if not path.is_file():
            raise FileNotFoundError(path)
    report = {
        "tool": "patch_mcsdk_uno_start_interlock",
        "project": str(project),
        "mcp_changed": patch_mcp(mcp),
        "button_changed": patch_button(tasks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
