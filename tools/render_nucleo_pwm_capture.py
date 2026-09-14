#!/usr/bin/env python3
"""Plot recorded digital samples, without synthesis or hardware access."""
import argparse
from bisect import bisect_left, bisect_right
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from nucleo_logic_capture import CHANNEL_MAP
from saleae_pwm_analyze import load_csv, transitions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    times, values = load_csv(args.csv, list(CHANNEL_MAP))
    high_edges = transitions(times, values[0])
    low_edges = transitions(times, values[1])
    reference = high_edges[len(high_edges) // 2]["time"]
    switch = next(e["time"] for e in high_edges if e["time"] >= reference and e["to"] == 0)
    partner = next(e["time"] for e in low_edges if e["time"] > switch and e["to"] == 1)
    fig, (overview, detail) = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [2, 1]}, layout="constrained")

    def draw(ax, start, end, channels):
        first = max(0, bisect_right(times, start) - 1)
        last = min(len(times), bisect_left(times, end) + 1)
        x = [(t - start) * 1e6 for t in times[first:last]]
        for index, ch in enumerate(channels):
            level = (len(channels) - index - 1) * 1.5
            ax.step(x, [level + v * 0.8 for v in values[ch][first:last]], where="post", lw=1.3, color="black")
        ax.set_yticks([(len(channels) - i - 1) * 1.5 + 0.4 for i in range(len(channels))],
                      [f"CH{ch}  {CHANNEL_MAP[ch]['signal']} / {CHANNEL_MAP[ch]['gpio']}" for ch in channels])
        ax.set_xlim(0, (end - start) * 1e6)
        ax.set_ylim(-0.3, len(channels) * 1.5)
        ax.set_xlabel("Time from left edge (us)")
        ax.grid(axis="x", color="0.85", linewidth=0.5)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)

    draw(overview, reference, reference + 3 / 16000, list(CHANNEL_MAP))
    overview.set_title("Recorded Nucleo outputs: 3 carrier periods", loc="left", fontsize=13)
    start = switch - 3e-6
    draw(detail, start, switch + 5e-6, [0, 1])
    detail.axvspan((switch - start) * 1e6, (partner - start) * 1e6, color="0.90", zorder=0)
    detail.set_title(f"U pair, both outputs LOW: {(partner - switch) * 1e6:.3f} us", loc="left", fontsize=13)
    fig.suptitle("Isolated logic test only | Saleae 24 MHz | IPM disconnected", fontsize=14)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    plt.close(fig)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
