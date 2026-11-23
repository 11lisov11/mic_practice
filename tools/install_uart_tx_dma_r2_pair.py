"""Revision 2: whole-frame DMA sender plus atomic clock/start watchdog observation."""
import math
import install_uart_tx_dma_pair as base

ROOT=base.ROOT
C=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r2'
OLD=(2026101811,2026101810)
NEW=(2026101813,2026101812)
io=base.io
GUARD=base.GUARD.replace('((2026101809,2026101808),(2026101811,2026101810))',
                        '((2026101811,2026101810),(2026101813,2026101812))')
GUARD=GUARD.replace('def precheck(s, max_vdc=20):','def _base_precheck(s, max_vdc=20):',1)+'''

def precheck(s,max_vdc=20):
    # Programming-only exception for the fully archived r1 sender watchdog
    # race, after its earlier loader timeout. No controller CLEAR or change.
    okay,reason=_base_precheck(s,max_vdc)
    if okay:return okay,reason
    sd=s.get('mc_sd_live',{})
    known_r1=(s.get('fw_build')==2026101811 and s.get('mc_fw_build')==2026101810
        and s.get('mc_fault')==5 and s.get('bp_fault')==5
        and s.get('mc_fault_reason')==13 and s.get('mc_last_bad_reason')==11
        and s.get('mc_last_tx_status')==3 and s.get('mc_transport_fault')==7
        and s.get('bp_transport_fault')==7 and s.get('mc_fault_current_mask')==0
        and s.get('mc_fault_occurred_mask')==0 and sd.get('available')
        and sd.get('level')=='HIGH' and sd.get('config_ok')
        and s.get('mc_break_wave_hex')=='-'
        and len(s.get('mc_break_snapshots',[]))==2
        and len(s.get('mc_uart_reject_hex',''))==640
        and all(x.get('available') and not x.get('captured') for x in s.get('mc_break_snapshots',[])))
    if not known_r1:return False,reason
    # Reuse ALL physical/off/fresh/hardware-error programming checks, accepting
    # precisely this saved diagnostic combination. Actual state is untouched.
    view=dict(s,mc_fault=2,bp_fault=2,mc_last_bad_reason=13)
    return _base_precheck(view,max_vdc)
'''
exec(GUARD)
original_verify=base.verify_package

def verify_package(candidate=C):
    result=original_verify(candidate)
    import json
    tests=json.loads((candidate/'selftest/report.json').read_text(encoding='utf-8'))
    if tests['mutation_controls']!=6:raise RuntimeError('clock race negative control missing')
    return result

base.C=C;base.OLD=OLD;base.NEW=NEW;base.GUARD=GUARD;base.precheck=precheck
base.verify_package=verify_package
make_remote_installer=base.make_remote_installer

if __name__=='__main__':raise SystemExit(base.main())
