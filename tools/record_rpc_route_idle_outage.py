"""Record new idle outage without overwriting the successful earlier route test."""
import json
import prepare_rpc_route_recovery as p

def main():
    out=p.OUT/'idle_timeout_diagnosis_r1'
    report=json.loads(p.read(out/'report.json'))
    native=json.loads(p.read(out/'native/report.json'))
    ram=out/'Uno_RAM_nonatomic.bin';assert ram.stat().st_size==786432
    assert native['passed'] and all(not row['moe'] for row in native['rows'])
    history=json.loads(p.read(p.OUT/'preserved_all_hashes.json'))
    for rel,h in history.items():assert p.sha(p.ROOT/rel)==h,rel
    report.update(current_RPC_usable=False,FOC_start_ready=False,Uno_RAM_bytes=ram.stat().st_size,
        Uno_RAM_SHA256=p.sha(ram),Uno_RAM_snapshot_atomic=False,Uno_after_dump_core_state='running',
        openocd_dump_reset_commands=0,openocd_dump_halt_commands=0,openocd_dump_flash_writes=0,
        Nucleo_passive_state=native,old_capture_files_verified=len(history),
        timing_of_RPC_loss='After earlier successful OFF qualification and before this user-requested FOC preparation; no new PWM run',
        operator_next='Keep both boards on PC,15V ON,J1 OFF. No motor run or CLEAR until RPC is restored.',
        conclusion='Lost route recovery was verified earlier, but it does not cure every RPC failure. New direct GET timeout reproduced while idle; original cause unresolved.')
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    m=json.loads(p.read(p.OUT/'manifest.json'));m.update(current_RPC_usable=False,FOC_start_ready=False,
        latest_idle_outage='idle_timeout_diagnosis_r1/report.json')
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(RAM_saved=True,native_PWM_OFF=True,old_capture_files_verified=len(history),START=0,CLEAR=0,RESET=0)))

if __name__=='__main__':main()
