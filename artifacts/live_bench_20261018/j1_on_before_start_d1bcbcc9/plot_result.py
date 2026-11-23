"""Offline analysis only: read saved telemetry and render the captured PA6 trace."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out = Path(__file__).resolve().parent
data = json.loads((out / "decoded_wave.json").read_text(encoding="utf-8"))
raw = (out / "bkin_wave.bin").read_bytes()
levels = [(raw[32 + i // 8] >> (i % 8)) & 1 for i in range(1024)]
times = [i - 1023 for i in range(1024)]
fig, axes = plt.subplots(2, 1, figsize=(11, 5.5),
    gridspec_kw={"height_ratios": [1, 1.3]}, layout="constrained")
fig.suptitle("BKIN / PA6: событие после включения J1, до Пуска", fontsize=15)
axes[0].step(times, levels, where="post", color="#0d7680", linewidth=1.6)
axes[0].scatter([0], [0], color="#c64c27", s=35, zorder=4)
axes[0].set_xlim(-1030, 35)
axes[0].set_title("Полная запись: 1023 HIGH + 1 LOW; 1024 действительных отсчёта", fontsize=10)
axes[1].scatter(times[-9:-1], levels[-9:-1], color="#0d7680", s=38,
    label="HIGH: записанные отсчёты")
axes[1].scatter([0], [0], color="#c64c27", s=45, label="LOW: последний отсчёт")
axes[1].plot([-8, -1], [1, 1], color="#0d7680")
axes[1].axvspan(-1, 0, color="#d6ad56", alpha=.25,
    label="Переход между соседними отсчётами")
axes[1].set_xlim(-8.5, 4)
axes[1].set_title("Конец записи: длительность LOW и возврат в HIGH неизвестны", fontsize=10)
axes[1].legend(loc="upper left", bbox_to_anchor=(0, -.26), ncol=2,
    fontsize=8, frameon=False)
for ax in axes:
    ax.axvspan(0, ax.get_xlim()[1], color="#dfe3e6", alpha=.65)
    ax.set_ylim(-.2, 1.3)
    ax.set_yticks([0, 1], ["LOW", "HIGH"])
    ax.set_xlabel("Время относительно последнего DMA-отсчёта, мкс")
    ax.grid(axis="y", alpha=.22)
    ax.spines[["right", "top"]].set_visible(False)
axes[1].text(2, .54, "После границы\nне записано", ha="center", va="center",
    fontsize=9, color="#535a61")
fig.savefig(out / "bkin_wave.png", dpi=170)
plt.close(fig)

report = {
    "schema": "mic_ai.j1_before_start_result.v1",
    "client_date": "2026-10-18",
    "operator_j1_on_start_not_pressed": True,
    "motor_start_commands": 0, "fault_clear_commands": 0, "firmware_writes": 0,
    "evidence": {
        "prior_j4_only_no_recorded_break": True,
        "state": "SAFE", "pwm": 0, "arm": 0, "estop": 1,
        "vbus_v": 323, "temperature_c": 48,
        "uart_bad_crc_sequence_hardware_transport": 0,
        "bif": True, "pa6_low_at_irq": True, "moe_at_irq": False,
        "start_window": False, "cached_context_age_ms": 15, "cached_vbus_v": 10,
        "wave_valid_samples": 1024, "wave_dma_error": False,
        "pa6_high_samples": 1023, "pa6_low_samples": 1,
        "low_interval_right_censored": True,
    },
    "conclusions": [
        "A Break was recorded between the J4-only baseline and the readout after J1 was enabled, before any START or PWM activation",
        "The nonzero-ARR fix produced a full DMA record",
        "The falling transition is captured but the recovery edge and pulse width are not",
        "This event does not identify the cause of the earlier 20-25 Hz trip",
    ],
    "not_proven": [
        "SD physical source: IPM comparator, VCC undervoltage, or interference",
        "Pulse duration: one LOW sample is not a measured 1-us pulse",
        "Simultaneous J4 voltage or phase current",
    ],
    "next_measurement": "Capture the SD recovery edge and correlated driver-supply/comparator evidence; retain protection",
    "source": {
        "title": "ST UM2014 Rev3 section 4.3",
        "url": "https://www.st.com/resource/en/user_manual/um2014-1500-w-motor-control-power-board-based-on-stgib15ch60tsl-sllimm-2nd-series-ipm-stmicroelectronics.pdf",
        "note": "SD can signal comparator overcurrent or driver VCC undervoltage; fault timings are influenced by the external RC network",
    },
}
(out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8")
print(json.dumps({"plot": str(out / "bkin_wave.png"), "low_pulse_width": "not measured"}))

