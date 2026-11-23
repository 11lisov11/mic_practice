"""Decode a saved first-break RAM dump, offline; never access the bench."""
import argparse
import json
from pathlib import Path
import struct

MAGIC = 0x314B5242
FIELDS = ("magic", "schema", "bytes", "tick_ms", "tim_sr", "tim_dier", "tim_bdtr",
          "tim_cnt", "tim_arr", "tim_ccr1", "tim_ccr2", "tim_ccr3", "gpioa_idr",
          "context_valid", "context_tick_ms", "reference_speed_unit", "motor_state",
          "current_faults", "occurred_faults", "vbus_v", "temperature_deci_c", "command_sequence", "start_window")
SIZE = len(FIELDS) * 4


def decode(data):
    if len(data) != SIZE:
        raise ValueError(f"Expected exactly {SIZE} bytes, got {len(data)}")
    values = dict(zip(FIELDS, struct.unpack("<23I", data)))
    if values["magic"] == 0 and not any(data):
        return dict(captured=False, interpretation="No recorded break since reboot (or zero-filled dump)")
    if values["magic"] != MAGIC or values["schema"] != 2 or values["bytes"] != SIZE:
        raise ValueError("Uncommitted, wrong-schema, or unrelated RAM snapshot")
    if values["context_valid"] not in (0, 1):
        raise ValueError("Invalid context flag")
    if values["start_window"] not in (0, 1):
        raise ValueError("Invalid START window flag")
    if not values["tim_sr"] & ((1 << 7) | (1 << 8)):
        raise ValueError("Committed record has neither BIF nor B2IF")
    for field in ("reference_speed_unit", "temperature_deci_c"):
        if values[field] & (1 << 31):
            values[field] -= 1 << 32
    return dict(captured=True, raw=values,
        event=dict(bif=bool(values["tim_sr"] & (1 << 7)),
            during_start_request_window=bool(values["start_window"]),
            b2if=bool(values["tim_sr"] & (1 << 8)),
            pa6_high_at_irq=bool(values["gpioa_idr"] & (1 << 6)),
            moe_at_irq=bool(values["tim_bdtr"] & (1 << 15)),
            bke_at_irq=bool(values["tim_bdtr"] & (1 << 12)),
            bie_before_handler=bool(values["tim_dier"] & (1 << 7))),
        cached_context=(dict(age_ms=(values["tick_ms"] - values["context_tick_ms"]) & 0xFFFFFFFF,
            reference_electrical_hz=values["reference_speed_unit"] / 10.0,
            reference_assumptions="This diagnostic image: SPEED_UNIT=10, pole pairs=1; not measured speed",
            motor_state=values["motor_state"], current_faults=values["current_faults"],
            occurred_faults=values["occurred_faults"], vbus_v=values["vbus_v"],
            temperature_c=values["temperature_deci_c"] / 10.0,
            command_sequence=values["command_sequence"]) if values["context_valid"] else None),
        limitations=["GPIO is read at ISR entry, not at the electrical edge; pulse duration is unknown",
            "START window includes queued startup and software STOP transition; it is not proof of RUN",
            "Hardware may clear MOE before ISR; MOE=0 is not software-stop evidence",
            "Context is a cached telemetry-time sample, not a simultaneous ADC measurement",
            "HAL tick has millisecond resolution and may lag during IRQs",
            "No measurement of the J4/15-V rail or qualified phase current is present",
            "Cannot uniquely distinguish overcurrent, driver undervoltage, or SD interference"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = decode(args.dump.read_bytes())
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"captured": report["captured"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
