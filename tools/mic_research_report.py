#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def fmt(v, digits: int = 3) -> str:
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


def as_float(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        num = float(v)
        if not math.isfinite(num):
            return None
        return num
    except Exception:
        return None


def load_summary(path_text: str) -> tuple[Path, dict]:
    path = Path(path_text)
    if path.is_dir():
        path = path / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return path, data


def load_optional_summary(path_text: str) -> tuple[Path | None, dict | None]:
    if not path_text:
        return None, None
    path = Path(path_text)
    if path.is_dir():
        path = path / "summary.json"
    if not path.exists():
        return path, None
    return path, json.loads(path.read_text(encoding="utf-8-sig"))


def html_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def metric_points(data: dict, metric_key: str) -> list[tuple[float, float]]:
    by_freq = data.get("aggregate", {}).get("by_freq", {})
    points: list[tuple[float, float]] = []
    for freq, item in by_freq.items():
        x = as_float(freq)
        y = as_float(item.get(metric_key))
        if x is None or y is None:
            continue
        points.append((x, y))
    return sorted(points, key=lambda p: p[0])


def svg_plot(title: str, y_label: str, points: list[tuple[float, float]], zero_line: bool = False) -> str:
    width = 760
    height = 360
    left = 72
    right = 24
    top = 42
    bottom = 54
    plot_w = width - left - right
    plot_h = height - top - bottom

    if not points:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>'
            f'<text x="24" y="36" font-family="Arial" font-size="20">{html_escape(title)}</text>'
            f'<text x="24" y="92" font-family="Arial" font-size="14" fill="#555">No data</text>'
            "</svg>\n"
        )

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if zero_line:
        y_min = min(y_min, 0.0)
        y_max = max(y_max, 0.0)
    if abs(x_max - x_min) < 1e-9:
        x_min -= 1.0
        x_max += 1.0
    if abs(y_max - y_min) < 1e-9:
        y_min -= 1.0
        y_max += 1.0
    y_pad = (y_max - y_min) * 0.12
    y_min -= y_pad
    y_max += y_pad

    def sx(x: float) -> float:
        return left + ((x - x_min) / (x_max - x_min)) * plot_w

    def sy(y: float) -> float:
        return top + (1.0 - ((y - y_min) / (y_max - y_min))) * plot_h

    path = " ".join(("M" if i == 0 else "L") + f" {sx(x):.1f} {sy(y):.1f}" for i, (x, y) in enumerate(points))
    grid_lines: list[str] = []
    label_lines: list[str] = []
    for i in range(5):
        t = i / 4.0
        y = y_min + (y_max - y_min) * t
        py = sy(y)
        grid_lines.append(f'<line x1="{left}" y1="{py:.1f}" x2="{left + plot_w}" y2="{py:.1f}" stroke="#e5e7eb"/>')
        label_lines.append(
            f'<text x="{left - 10}" y="{py + 4:.1f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{fmt(y, 2)}</text>'
        )
    for x in xs:
        px = sx(x)
        label_lines.append(
            f'<text x="{px:.1f}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="11" fill="#555">{fmt(x, 2)}</text>'
        )
    zero = ""
    if zero_line and y_min <= 0.0 <= y_max:
        py = sy(0.0)
        zero = f'<line x1="{left}" y1="{py:.1f}" x2="{left + plot_w}" y2="{py:.1f}" stroke="#111827" stroke-dasharray="4 4"/>'
    circles = "\n".join(
        f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="4" fill="#0f766e"><title>{fmt(x, 2)} Hz: {fmt(y, 3)}</title></circle>'
        for x, y in points
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="24" y="30" font-family="Arial" font-size="20" font-weight="700" fill="#111827">{html_escape(title)}</text>
<text x="{left + plot_w / 2:.1f}" y="{height - 6}" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">Frequency, electrical Hz</text>
<text x="18" y="{top + plot_h / 2:.1f}" transform="rotate(-90 18 {top + plot_h / 2:.1f})" text-anchor="middle" font-family="Arial" font-size="12" fill="#374151">{html_escape(y_label)}</text>
{''.join(grid_lines)}
{''.join(label_lines)}
<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9ca3af"/>
<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#9ca3af"/>
{zero}
<path d="{path}" fill="none" stroke="#0f766e" stroke-width="2.5"/>
{circles}
</svg>
"""


def write_plots(summary_path: Path, data: dict, enabled: bool = True) -> list[dict]:
    if not enabled:
        return []
    specs = [
        ("mic_active_ratio.svg", "MIC Active Ratio By Frequency", "active ratio", "mic_active_ratio_mean", False),
        ("p_proxy_delta_pct.svg", "Power Proxy Delta By Frequency", "MIC vs FOC, %", "p_proxy_pct_mean", True),
        ("i_rms_delta_pct.svg", "Current RMS Delta By Frequency", "MIC vs FOC, %", "i_rms_pct_mean", True),
        ("enc_rpm_delta_pct.svg", "Encoder RPM Delta By Frequency", "MIC vs FOC, %", "enc_rpm_pct_mean", True),
    ]
    out: list[dict] = []
    for filename, title, y_label, key, zero_line in specs:
        points = metric_points(data, key)
        if not points:
            continue
        path = summary_path.with_name(filename)
        path.write_text(svg_plot(title, y_label, points, zero_line=zero_line), encoding="utf-8")
        out.append({"title": title, "path": path, "points": len(points)})
    return out


def stat_field(calibration: dict | None, key: str, field: str):
    if not calibration:
        return None
    stats = calibration.get("stats", {}) if isinstance(calibration.get("stats"), dict) else {}
    item = stats.get(key, {}) if isinstance(stats.get(key), dict) else {}
    return item.get(field)


def build_calibration_section(calibration_path: Path | None, calibration: dict | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Calibration Evidence")
    lines.append("")
    if calibration_path is None:
        lines.append("- Calibration summary: not attached. Use `--calibration-summary <path>` for final evidence reports.")
        lines.append("- Current and power-proxy conclusions are provisional without a linked calibration artifact.")
        lines.append("")
        return lines
    if calibration is None:
        lines.append(f"- Calibration summary: `{calibration_path}` could not be loaded.")
        lines.append("- Current and power-proxy conclusions are provisional until this is fixed.")
        lines.append("")
        return lines

    zero = calibration.get("zero_current_sanity", {}) if isinstance(calibration.get("zero_current_sanity"), dict) else {}
    metrics = zero.get("metrics", {}) if isinstance(zero.get("metrics"), dict) else {}
    thresholds = zero.get("thresholds", {}) if isinstance(zero.get("thresholds"), dict) else {}
    vbus_cal = calibration.get("vbus_calibration")
    temp_cal = calibration.get("temp_tso_calibration")
    lines.append(f"- Calibration summary: `{calibration_path}`")
    lines.append(f"- Calibration pass: `{calibration.get('pass', False)}`")
    lines.append(f"- Samples collected: `{calibration.get('samples_collected', 0)}`")
    lines.append(f"- Online error: `{calibration.get('online_error') or '-'}`")
    lines.append(f"- Zero-current sanity pass: `{zero.get('pass', False)}`")
    lines.append(f"- Zero-current safe samples: `{zero.get('safe_samples', 0)}/{zero.get('samples', 0)}`")
    lines.append(
        "- Zero-current metrics: "
        f"max abs phase mean `{fmt(metrics.get('max_abs_phase_mean_a'))} A`, "
        f"max abs phase peak `{fmt(metrics.get('max_abs_phase_peak_a'))} A`, "
        f"i_rms mean `{fmt(metrics.get('i_rms_mean_a'))} A`, "
        f"i_rms peak `{fmt(metrics.get('i_rms_peak_a'))} A`"
    )
    lines.append(
        "- Zero-current thresholds: "
        f"phase mean `{fmt(thresholds.get('max_zero_current_mean_a'))} A`, "
        f"phase peak `{fmt(thresholds.get('max_zero_current_peak_a'))} A`, "
        f"i_rms mean `{fmt(thresholds.get('max_zero_i_rms_mean_a'))} A`, "
        f"i_rms peak `{fmt(thresholds.get('max_zero_i_rms_peak_a'))} A`"
    )
    lines.append(
        "- Current snapshot means: "
        f"ia `{fmt(stat_field(calibration, 'ia', 'mean'))} A`, "
        f"ib `{fmt(stat_field(calibration, 'ib', 'mean'))} A`, "
        f"ic `{fmt(stat_field(calibration, 'ic', 'mean'))} A`, "
        f"i_rms `{fmt(stat_field(calibration, 'i_rms', 'mean'))} A`"
    )
    lines.append(f"- Vbus calibration constants present: `{vbus_cal is not None}`")
    lines.append(f"- Temperature calibration constants present: `{temp_cal is not None}`")
    if calibration.get("pass") is not True or zero.get("pass") is not True:
        lines.append("- Calibration is not passing; do not treat `i_rms` or `p_proxy` deltas as final scientific evidence.")
    lines.append("")
    return lines


def build_bench_context_section(data: dict) -> list[str]:
    lines: list[str] = []
    lines.append("## Bench Context")
    lines.append("")
    context = data.get("bench_context", {}) if isinstance(data.get("bench_context"), dict) else {}
    if not context:
        lines.append("- Bench context was not attached. For final evidence, pass bench fields to `mic_research_matrix.py`.")
        lines.append("")
        return lines
    preferred = [
        "operator",
        "motor_label",
        "load_note",
        "supply_note",
        "ambient_c",
        "instrumentation_note",
        "bench_note",
        "bench_config_path",
    ]
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    emitted: set[str] = set()
    for key in preferred:
        if key in context and context.get(key) not in (None, ""):
            lines.append(f"| `{key}` | {html_escape(context.get(key))} |")
            emitted.add(key)
    for key in sorted(k for k in context.keys() if k not in emitted):
        value = context.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            value_text = str(value)
        lines.append(f"| `{key}` | {html_escape(value_text)} |")
    lines.append("")
    return lines


def build_report(
    summary_path: Path,
    data: dict,
    plots: list[dict],
    calibration_path: Path | None = None,
    calibration: dict | None = None,
) -> str:
    aggregate = data.get("aggregate", {})
    rows = data.get("rows", [])
    metadata = data.get("run_metadata", {}) if isinstance(data.get("run_metadata"), dict) else {}
    git = metadata.get("git", {}) if isinstance(metadata.get("git"), dict) else {}
    lines: list[str] = []
    lines.append("# MIC Research Report")
    lines.append("")
    lines.append(f"- Source: `{summary_path}`")
    lines.append(f"- URL: `{data.get('url', '-')}`")
    lines.append(f"- Frequencies: `{data.get('freqs', '-')}`")
    lines.append(f"- Repeats: `{data.get('repeats', '-')}`")
    lines.append(f"- Duration per mode: `{data.get('duration', '-')}` s")
    lines.append(f"- Research ready: `{aggregate.get('research_ready', False)}`")
    lines.append(f"- Runs: `{aggregate.get('runs_passed', 0)}/{aggregate.get('runs_total', 0)}` passed")
    lines.append("- Backend fields: `bp_cmd_mode=2` means duty backend, `bp_cmd_mode=5` means Blue Pill measured-angle FOC.")
    lines.append("")

    lines.append("## Run Metadata")
    lines.append("")
    lines.append(f"- Timestamp UTC: `{metadata.get('timestamp_utc', '-')}`")
    lines.append(f"- Git branch: `{git.get('branch', '-')}`")
    lines.append(f"- Git commit: `{git.get('commit_short') or git.get('commit') or '-'}`")
    lines.append(f"- Git dirty: `{git.get('dirty', '-')}`")
    lines.append(f"- Command: `{' '.join(str(x) for x in metadata.get('argv', [])) or '-'}`")
    lines.append("")

    lines.extend(build_bench_context_section(data))

    lines.append("## Aggregate")
    lines.append("")
    lines.append("| Metric | Mean | Std |")
    lines.append("|---|---:|---:|")
    lines.append(
        f"| MIC active ratio | {fmt(aggregate.get('mean_mic_active_ratio'))} | {fmt(aggregate.get('std_mic_active_ratio'))} |"
    )
    lines.append(f"| p_proxy delta, % | {fmt(aggregate.get('mean_p_proxy_pct'))} | {fmt(aggregate.get('std_p_proxy_pct'))} |")
    lines.append(f"| i_rms delta, % | {fmt(aggregate.get('mean_i_rms_pct'))} | {fmt(aggregate.get('std_i_rms_pct'))} |")
    lines.append("")

    lines.extend(build_calibration_section(calibration_path, calibration))

    if plots:
        lines.append("## Plots")
        lines.append("")
        for plot in plots:
            rel = plot["path"].name
            lines.append(f"![{plot['title']}]({rel})")
            lines.append("")

    by_freq = aggregate.get("by_freq", {})
    if by_freq:
        lines.append("## By Frequency")
        lines.append("")
        lines.append("| Freq Hz | Passed | MIC active mean | p_proxy % mean | i_rms % mean | enc rpm % mean |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for freq, item in sorted(by_freq.items(), key=lambda kv: float(kv[0])):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(freq),
                        f"{item.get('runs_passed', 0)}/{item.get('runs_total', 0)}",
                        fmt(item.get("mic_active_ratio_mean")),
                        fmt(item.get("p_proxy_pct_mean")),
                        fmt(item.get("i_rms_pct_mean")),
                        fmt(item.get("enc_rpm_pct_mean")),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.append("## Runs")
    lines.append("")
    lines.append("| Freq Hz | Repeat | Pass | Backend FOC/MIC | MIC active | p_proxy % | i_rms % | enc rpm % | Summary |")
    lines.append("|---:|---:|---:|---|---:|---:|---:|---:|---|")
    for row in rows:
        summary = row.get("summary", "")
        summary_cell = f"`{summary}`" if summary else "-"
        lines.append(
            "| "
            + " | ".join(
                [
                    fmt(row.get("freq_hz"), 2),
                    str(row.get("repeat", "-")),
                    str(bool(row.get("pass"))),
                    f"{row.get('foc_bp_cmd_modes', '-')}/{row.get('mic_bp_cmd_modes', '-')}",
                    fmt(row.get("mic_active_ratio")),
                    fmt(row.get("p_proxy_pct")),
                    fmt(row.get("i_rms_pct")),
                    fmt(row.get("enc_rpm_pct")),
                    summary_cell,
                ]
            )
            + " |"
        )
    lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("- `research_ready=true` means all configured repeats passed and MIC was active above the configured threshold.")
    lines.append("- For strict measured-angle FOC research, each run should show backend command mode `5/5` and `bp_foc_backend=1` in raw summaries.")
    lines.append("- `p_proxy` is a proxy metric from telemetry, not a calibrated power analyzer measurement.")
    lines.append("- Use a passing calibration artifact with zero-current sanity before making final efficiency/current claims.")
    if git.get("dirty"):
        lines.append("- This report was generated from a dirty git worktree; commit or archive the diff before using the data as final evidence.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a Markdown report from mic_research_matrix summary.json.")
    ap.add_argument("summary", help="Path to summary.json or matrix run directory")
    ap.add_argument("--out", default="", help="Output markdown path; default: report.md next to summary.json")
    ap.add_argument("--calibration-summary", default="", help="Optional telemetry_calibration summary.json or run directory.")
    ap.add_argument("--no-plots", action="store_true", help="Do not write SVG plots next to the report.")
    args = ap.parse_args()

    summary_path, data = load_summary(args.summary)
    calibration_path, calibration = load_optional_summary(args.calibration_summary)
    out_path = Path(args.out) if args.out else summary_path.with_name("report.md")
    plots = write_plots(summary_path, data, enabled=not args.no_plots)
    out_path.write_text(build_report(summary_path, data, plots, calibration_path, calibration), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "report": str(out_path),
                "plots": [str(p["path"]) for p in plots],
                "calibration_summary": str(calibration_path) if calibration_path else "",
                "calibration_loaded": calibration is not None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
