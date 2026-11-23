"""Create an offline HMI-only BKIN diagnostics correction for the installed pair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "artifacts/live_bench_20261015/manual_scalar_bkin_trace_r3/web_hmi"
OUT = ROOT / "artifacts/live_bench_20261017/bkin_hmi_diagnostic_fix_r3"
PAIR = [2026101507, 2026101506]


def replace_once(text: str, before: str, after: str, label: str) -> str:
    if text.count(before) != 1:
        raise RuntimeError(f"{label}: expected exactly one source anchor")
    return text.replace(before, after, 1)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> dict:
    if not BASE.is_dir():
        raise RuntimeError(f"Installed-pair HMI source missing: {BASE}")
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite candidate: {OUT}")
    OUT.mkdir(parents=True)
    for name in ("server.py", "static/app.js", "static/index.html", "static/style.css"):
        source, destination = BASE / name, OUT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    server_path = OUT / "server.py"
    server = server_path.read_text(encoding="utf-8-sig")
    old_event = '''                    item.update(available=True, captured=True, reason="recorded", raw=raw,
                        event={"bif": bool(raw["tim_sr"] & 0x80), "b2if": bool(raw["tim_sr"] & 0x100),
                               "pa6_high_at_irq": bool(raw["gpioa_idr"] & 0x40),
                               "bke_at_irq": bool(raw["tim_bdtr"] & 0x1000),
                               "moe_at_irq": bool(raw["tim_bdtr"] & 0x8000),
                               "during_start_request_window": bool(raw["start_window"])},
                        cached_context=context)
'''
    new_event = '''                    raw_start_window = bool(raw["start_window"])
                    context_was_running = bool(context and context["motor_state"] == 6)
                    item.update(available=True, captured=True, reason="recorded", raw=raw,
                        event={"bif": bool(raw["tim_sr"] & 0x80), "b2if": bool(raw["tim_sr"] & 0x100),
                               "pa6_high_at_irq": bool(raw["gpioa_idr"] & 0x40),
                               "bke_at_irq": bool(raw["tim_bdtr"] & 0x1000),
                               "moe_at_irq": bool(raw["tim_bdtr"] & 0x8000),
                               "during_start_request_window": raw_start_window and not context_was_running,
                               "start_window_flag_raw": raw_start_window,
                               "start_window_flag_stale_after_run": raw_start_window and context_was_running},
                        cached_context=context)
'''
    server = replace_once(server, old_event, new_event, "D1 start-window classification")
    server = replace_once(server,
        ' or not 0 <= age <= 5000:\n                item["reason"] = "stale_or_wrong_peer"',
        ' or not 0 <= age <= 0xFFFFFFFF:\n                item["reason"] = "invalid_age"',
        "retained D1 snapshot age")
    server = replace_once(server,
        '        if not 0 <= age <= 5000: return {"available": False, "reason": "stale"}\n',
        '''        if not 0 <= age <= 0xFFFFFFFF:
            return {"available": False, "reason": "invalid_age"}
        peer_age = _as_int(data, "mc_age_ms", _as_int(data, "bp_age_ms", 999999))
        if not 0 <= peer_age < 300:
            return {"available": False, "reason": "stale_peer"}
''', "retained trace freshness gate")
    old_intervals = '''        low_intervals = []
        start = None
        for i in range(valid_from, 1025):
            low = i < 1024 and samples[i] == 0
            if low and start is None: start = i
            elif not low and start is not None:
                low_intervals.append({"from_us": start - 1023, "to_us": i - 1023,
                                      "includes_capture_boundary": i == 1024})
                start = None
        return {"available": True, "reason": "recorded", "age_ms": age,
'''
    new_intervals = '''        low_intervals = []
        low_start = None
        low_count = 0
        for i in range(valid_from, 1025):
            low = i < 1024 and samples[i] == 0
            if low and low_start is None: low_start = i
            if low: low_count += 1
            elif not low and low_start is not None:
                low_intervals.append({"from_us": low_start - 1023, "to_us": i - 1023,
                                      "includes_capture_boundary": i == 1024})
                low_start = None
        snapshots = data.get("mc_break_snapshots", [])
        irq_pa6_high = None
        if isinstance(snapshots, list):
            for snapshot in snapshots:
                if (isinstance(snapshot, dict) and snapshot.get("kind") == "first_since_boot"
                        and snapshot.get("captured") is True and isinstance(snapshot.get("event"), dict)):
                    irq_pa6_high = bool(snapshot["event"].get("pa6_high_at_irq"))
                    break
        return {"available": True, "reason": "recorded", "age_ms": age,
            "retained": True, "active_level": 0, "active_polarity": "LOW",
            "active_sample_count": low_count, "active_intervals": low_intervals,
            "pa6_dma_count_verified": False,
            "sample_validity": "unverified_elapsed_time_only_no_dma_count",
            "irq_pa6_high": irq_pa6_high,
'''
    server = replace_once(server, old_intervals, new_intervals, "active-high trace decoder")
    server = replace_once(server, '                "Sub-microsecond pulse widths are below this recorder\'s resolution",',
        '                "Firmware estimates sample completeness from elapsed time and does not export DMA remaining count; sample contents are unverified",\n'
        '                "Sub-microsecond pulse widths are below this recorder\'s resolution",',
        "trace completeness limitation")
    server_path.write_text(server, encoding="utf-8", newline="\n")

    js_path = OUT / "static/app.js"
    js = js_path.read_text(encoding="utf-8-sig")
    js = replace_once(js,
        '        invalid_hex: "повреждён ответ", invalid_record: "неверный формат снимка", stale: "снимок устарел" };',
        '        invalid_hex: "повреждён ответ", invalid_record: "неверный формат снимка",\n'
        '        invalid_age: "неверный возраст снимка", stale_peer: "нет свежей связи с Nucleo" };',
        "HMI error labels")
    old_display = '''    const pulses = (trace.pa6_low_intervals || []).map((p) =>
      `${p.from_us}…${p.to_us} мкс`).join(", ");
    bkinTraceStatus.textContent = `PA6 LOW: ${pulses || "не обнаружен"}; ` +
      `${trace.valid_sample_count}/1024 отсчётов, шаг 1 мкс`;
'''
    new_display = '''    const pulses = (trace.active_intervals || []).map((p) =>
      `${p.from_us}…${p.to_us} мкс`).join(", ");
    const ageMs = Number(trace.age_ms);
    const ageText = ageMs < 1000 ? `${Math.round(ageMs)} мс` : ageMs < 60000
      ? `${(ageMs / 1000).toFixed(1)} с` : `${Math.floor(ageMs / 60000)} мин ${Math.floor(ageMs / 1000) % 60} с`;
    const irqText = trace.irq_pa6_high === null ? "нет D1-снимка" :
      trace.irq_pa6_high ? "HIGH при входе в прерывание" : "LOW при входе в прерывание";
    bkinTraceStatus.textContent = `Активный PA6 LOW: ${pulses || "не замечен в окне 1,024 мкс"}; ` +
      `${trace.valid_sample_count}/1024 отсчётов, шаг 1 мкс; ${irqText}; снимок ${ageText}. ` +
      `Отсчёты не подтверждены счётчиком DMA; длительность импульса неизвестна.`;
'''
    js = replace_once(js, old_display, new_display, "active-high retained trace display")
    js_path.write_text(js, encoding="utf-8", newline="\n")

    files = {name: sha(OUT / name) for name in
             ("server.py", "static/app.js", "static/index.html", "static/style.css")}
    manifest = {
        "schema": "mic_ai.bkin_hmi_diagnostic_fix.v1",
        "candidate": str(OUT), "installed_mcu_pair": PAIR,
        "mcu_sources_changed": False, "mcu_flash_commands": 0,
        "actuation_commands": 0, "hardware_commands": 0,
        "calibration_changed": False, "hv_release_approved": False,
        "changes": ["Show the retained trace after five seconds while requiring fresh current telemetry",
        "Decode the combined BKINP/BKP setting as active-low and show the IRQ sample beside the trace",
        "Mark legacy sample contents unverified because firmware does not export DMA progress",
        "Treat cached RUN context as runtime when the old start-window flag remained set"],
        "sha256": files,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = prepare()
    print(json.dumps({"prepared": True, "candidate": result["candidate"],
                      "mcu_flash_commands": 0, "actuation_commands": 0}))
