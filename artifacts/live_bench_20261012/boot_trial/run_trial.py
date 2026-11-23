"""Pinned existing trial runner adapted to exactly 1108/1102, 5 Hz / 3 s."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))


def load_runner(name='boot_trial_runner'):
    source=ROOT/'tools/wifi_uart_v3_trial.py'
    regression=json.loads((Path(__file__).parent/'regression_r2/report.json').read_text())
    expected=regression['source_sha256']['tools/wifi_uart_v3_trial.py']
    if not regression['pass'] or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Trial runner changed after regression')
    text=source.read_text()
    for before,after in (
        ('PAIR = (2026101007, 2026101006)','PAIR = (2026101108, 2026101102)'),
        ('SENDER_PAIR = (2026101008, 2026101006)','SENDER_PAIR = (2026101108, 2026101102)'),
        ('0 < float(s["freq_cmd"]) <= 10','0 < float(s["freq_cmd"]) <= 5'),
    ):
        if text.count(before)!=1:
            raise RuntimeError('Unexpected trial template')
        text=text.replace(before,after)
    ns={'__name__':name,'__file__':str(source)}
    exec(compile(text,str(source),'exec'),ns)
    return ns


if __name__=='__main__':
    # Preparation is done separately with the source/measurement audit. Avoid
    # reusing the template's older zero-only preparation path at 9-V aux bias.
    if len(sys.argv)<2 or sys.argv[1] not in ('observe','run','cancel'):
        raise SystemExit('Use observe, run or cancel; run requires explicit operator-ready confirmation')
    raise SystemExit(load_runner()['main']())
