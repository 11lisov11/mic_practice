"""Adapt the existing offline-only installation recipe, without contacting boards."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=(ROOT/'tools/install_observer_irq_budget.py').read_text(encoding='utf-8')
    source=source.replace('2026111501/1502','2026111503/1504')
    source=source.replace('import prepare_observer_irq_budget as p','import prepare_exact_profile_budget as p')
    source=source.replace('OLD=(2026111407,2026111408)','OLD=(2026111501,2026111502)')
    source=source.replace("assert json.loads(p.read(p.OUT/'verification/report.json'))['IRQ_priorities_and_enables_unchanged']",
        "assert json.loads(p.read(p.OUT/'verification/report.json'))['threshold_protections_identical']\n assert json.loads(p.read(p.OUT/'verification/ARM_call_scope.json'))['passed']")
    source=source.replace("assert 0<=s['mc_age_ms']<300 and s['mc_last_uart_error_flags']==0,'reply is stale or UART unhealthy'",
        "assert 0<=s['mc_age_ms']<300,'reply is stale'\n # Only offline reprogramming of the exactly recorded predecessor latch;\n # never a START exception, never a CLEAR, no new rejected frame accepted.\n if pair==OLD:\n  assert tuple(s[k] for k in ('mc_uart_error_flags','mc_last_uart_error_flags','mc_transport_fault','mc_bad_cnt'))==(2,2,4,1),'predecessor UART evidence changed'\n else:\n  assert s['mc_uart_error_flags']==s['mc_last_uart_error_flags']==0,'new UART error'")
    source=source.replace('mic_irq1502_','mic_exact1504_').replace('observer_irq_1502_','exact_profile_1504_')
    source=source.replace('_observer_irq.hex','_exact_profile_budget.hex').replace('_observer_irq.elf-zsk.bin','_exact_profile_budget.elf-zsk.bin')
    target=ROOT/'tools/install_exact_profile_budget.py'
    assert not target.exists()
    target.write_text(source,encoding='utf-8')
    compile(source,str(target),'exec')
    print('Prepared installation recipe; no hardware commands')


if __name__=='__main__':main()
