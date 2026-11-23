"""Prepare an isolated first-break RAM recorder; no hardware access or flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from prepare_mcsdk_logic_bench import replace_once

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6/nucleo"
HEADER = ROOT / "research/ipm_break/first_break_snapshot.h"
BUILD_ID = 2026101101


def source_hashes(folder):
    return {str(p.relative_to(folder)).replace("\\", "/"):
            hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()
            and not any(part in ("Debug", "Release", ".settings") for part in p.relative_to(folder).parts)}


def patched_main(text):
    text = replace_once(text, '#include "uart_v3_transport.h"',
        '#include "uart_v3_transport.h"\n#include "first_break_snapshot.h"\n'
        'volatile mic_break_snapshot_t mic_first_break;\n'
        'volatile mic_break_snapshot_t mic_first_start_break;\n'
        'volatile uint32_t mic_break_start_window;\n'
        'volatile uint32_t mic_break_irq_count;\n'
        'volatile mic_break_context_t mic_break_context[2];\n'
        'volatile uint32_t mic_break_context_index;\n'
        'volatile uint32_t mic_break_context_valid;')
    text = replace_once(text, "#define MIC_NUCLEO_FW_BUILD_ID 2026101006UL",
                        f"#define MIC_NUCLEO_FW_BUILD_ID {BUILD_ID}UL")
    text = replace_once(text, '  (void)MC_StopMotor1();',
                        '  (void)MC_StopMotor1();\n  mic_break_start_window = 0U;')
    text = replace_once(text, '    if (start_state == IDLE && !MC_StartMotor1()) start_failed = true;',
        '    if (start_state == IDLE) {\n'
        '      mic_break_start_window = 1U;\n'
        '      if (!MC_StartMotor1()) {\n'
        '        mic_break_start_window = 0U;\n'
        '        start_failed = true;\n'
        '      }\n'
        '    }')
    return replace_once(text, '  /* ACK clears the masks before the scheduler leaves FAULT_OVER. */',
        '  /* Cached context is explicitly not an IRQ-time sensor sample. */\n'
        '  const mic_break_context_t break_context = {\n'
        '      now_ms, MC_GetMecSpeedReferenceMotor1(), (uint32_t)motor_state,\n'
        '      mcsdk_faults, MC_GetOccurredFaultsMotor1(), vbus_v, temp_deci_c,\n'
        '      uno_link.last_seq};\n'
        '  mic_break_publish_context(&break_context);\n\n'
        '  /* ACK clears the masks before the scheduler leaves FAULT_OVER. */')


def patched_irq(text):
    text = replace_once(text, '#include "mcp_config.h"',
                        '#include "mcp_config.h"\n#include "first_break_snapshot.h"')
    return replace_once(text, '  /* BIF cannot clear while the break level is active.',
        '  mic_break_capture_first(HAL_GetTick());\n'
        '  /* BIF cannot clear while the break level is active.')


def prepare(out):
    before = source_hashes(REFERENCE)
    out.mkdir(parents=True, exist_ok=False)
    project = out / "nucleo"
    shutil.copytree(REFERENCE, project, ignore=shutil.ignore_patterns("Debug", "Release"))
    for name, patch in (("Src/main.c", patched_main), ("Src/stm32g4xx_mc_it.c", patched_irq)):
        path = project / name
        path.write_text(patch(path.read_text(encoding="utf-8-sig")), encoding="utf-8")
    shutil.copy2(HEADER, project / "Inc/first_break_snapshot.h")
    if source_hashes(REFERENCE) != before:
        raise RuntimeError("Frozen reference changed during preparation")
    after = source_hashes(project)
    changes = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    expected = ["Inc/first_break_snapshot.h", "Src/main.c", "Src/stm32g4xx_mc_it.c"]
    if changes != expected:
        raise RuntimeError(f"Unexpected candidate changes: {changes}")
    manifest = dict(schema="mic_ai.ipm_first_break_candidate.v1", prepared=True,
        firmware_build_id=BUILD_ID, baseline_build_id=2026101006,
        changed_files=changes, reference_sha256=before,
        candidate_sha256=after, hardware_commands=0, installed=False,
        hv_release_approved=False, uart_packet_layout_changed=False,
        protection_configuration_changed=False,
        diagnostic_transport="RAM dump after mains/J4 off; not Wi-Fi telemetry",
        retention="first break since reboot + first break in a START request window; STOP/CLEAR do not erase records",
        identity_policy="Unknown diagnostic build is intentionally not allowed by current powered-trial gate")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", required=True, type=Path)
    args = parser.parse_args()
    manifest = prepare(args.outdir.resolve())
    print(json.dumps({k: manifest[k] for k in ("prepared", "firmware_build_id", "changed_files", "installed")}))


if __name__ == "__main__":
    main()
