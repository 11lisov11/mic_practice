"""Pure read-only snapshot decoding; embedded into the prepared HMI server."""
import struct as _break_struct

_BREAK_FIELDS = (
    "magic", "schema", "bytes", "tick_ms", "tim_sr", "tim_dier", "tim_bdtr",
    "tim_cnt", "tim_arr", "tim_ccr1", "tim_ccr2", "tim_ccr3", "gpioa_idr",
    "context_valid", "context_tick_ms", "reference_speed_unit", "motor_state",
    "current_faults", "occurred_faults", "vbus_v", "temperature_deci_c",
    "command_sequence", "start_window")


def break_wire_status(kv):
    records = []
    for kind in (0, 1):
        item = {"kind": "first_since_boot" if kind == 0 else "first_start_window",
                "available": False, "captured": False}
        try:
            text = kv.get(f"mc_break{kind}_hex", "")
            age = int(kv.get(f"mc_break{kind}_age_ms", "-1"))
            peer_age = int(kv.get("bp_age_ms", "999999"))
            peer = int(kv.get("bp_fw_build", "0"))
            if not text or text == "-":
                item["reason"] = "not_received"
            elif len(text) != 184 or any(c not in "0123456789abcdefABCDEF" for c in text):
                item["reason"] = "invalid_hex"
            elif peer not in (2026101102, 2026101204) or not 0 <= peer_age < 300 or not 0 <= age <= 5000:
                item["reason"] = "stale_or_wrong_peer"
            else:
                data = bytes.fromhex(text)
                raw = dict(zip(_BREAK_FIELDS, _break_struct.unpack("<23I", data)))
                item["age_ms"] = age
                if not any(data):
                    item.update(available=True, reason="no_recorded_break")
                elif (raw["magic"] != 0x314B5242 or raw["schema"] != 2 or raw["bytes"] != 92
                      or raw["context_valid"] not in (0, 1) or raw["start_window"] not in (0, 1)
                      or not raw["tim_sr"] & 0x180 or (kind == 1 and raw["start_window"] != 1)):
                    item["reason"] = "invalid_record"
                else:
                    for field in ("reference_speed_unit", "temperature_deci_c"):
                        if raw[field] & (1 << 31):
                            raw[field] -= 1 << 32
                    context = None
                    if raw["context_valid"]:
                        context = {k: raw[k] for k in _BREAK_FIELDS[14:22]}
                        context["age_at_irq_ms"] = (raw["tick_ms"] - raw["context_tick_ms"]) & 0xFFFFFFFF
                        context["reference_electrical_hz"] = raw["reference_speed_unit"] / 10.0
                        context["temperature_c"] = raw["temperature_deci_c"] / 10.0
                    item.update(available=True, captured=True, reason="recorded", raw=raw,
                        event={"bif": bool(raw["tim_sr"] & 0x80), "b2if": bool(raw["tim_sr"] & 0x100),
                               "pa6_high_at_irq": bool(raw["gpioa_idr"] & 0x40),
                               "bke_at_irq": bool(raw["tim_bdtr"] & 0x1000),
                               "moe_at_irq": bool(raw["tim_bdtr"] & 0x8000),
                               "during_start_request_window": bool(raw["start_window"])},
                        cached_context=context)
        except (ValueError, TypeError, OverflowError):
            item["reason"] = "invalid_metadata"
        records.append(item)
    return {"mc_break_snapshots": records,
            "mc_break_transport": "passive_off_only_v1",
            "mc_break_limitations": ["Not live telemetry: delivery occurs only with outputs off",
                "Reference frequency is not measured rotor speed; context is cached",
                "PA6 is sampled at IRQ, not the electrical edge; pulse duration is unknown",
                "J4 voltage and qualified phase current are not measured",
                "Cannot uniquely identify overcurrent, undervoltage, or interference"]}
