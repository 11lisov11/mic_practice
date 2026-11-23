"""Save first-trial plan and verify passive state; GET only on hardware."""
import copy,hashlib,json,urllib.request
import prepare_foc_fast_budget_fix as p
import run_foc_fast_budget_trial as run

def main():
    out=p.OUT/'FOC_CPU_IRQ_trial_preparation_r1';out.mkdir(exist_ok=False)
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    assert manifest['installed'] and manifest['installation_readback_verified']
    for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
    preserved={}
    for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
        preserved.update(json.loads(p.read(p.OUT/rel)))
    for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    obj=json.load(op.open('http://192.168.1.138:8080/api/status',timeout=8))
    s=obj['data'];assert run.trial.PAIR==p.NEW
    assert run.trial.off(s) and run.trial.profile(s) and run.trial.off_timing_ready(s)
    assert s['run_id']==0 and s['vdc']<=20 and s['hmi_hv_armed']==0
    p.write(out/'USB_before_transition.json',json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    # Pure predicates: no HTTP mutation, START, CLEAR, ARM or RESET.
    valid=copy.deepcopy(s);valid['vdc']=320
    assert run.trial.healthy(valid)
    checks=[]
    for name,key,value in [('old_pair','mc_fw_build',2026102972),('stale_link','mc_age_ms',301),
        ('algorithm_fault','algorithm_fault',3),('not_zeroed','mc_current_zero_ready',0),
        ('active_Break','mc_fault_current_mask',1024),('UART_integrity','mc_bad_integrity',1),
        ('UART_hw','mc_uart_error_flags',8),('UART_transport','mc_transport_fault',1)]:
        bad=copy.deepcopy(valid);bad[key]=value;assert not run.trial.healthy(bad),name;checks.append(name)
    for key,value in [('level','LOW'),('break_irq_enabled',False),('config_ok',False)]:
        bad=copy.deepcopy(valid);bad['mc_sd_live'][key]=value
        assert not run.trial.healthy(bad),key;checks.append('SD_'+key)
    plan=dict(prepared=True,pair=list(p.NEW),start_commands=0,clear_commands=0,arm_commands=0,flash_commands=0,reset_commands=0,
        current_state='USB both boards; J1 OFF;15V ON; SAFE/PWM0',
        trial=dict(algorithm='FOC',frequency_hz=5,limit_ms=5000,host_retries=0),
        autonomous_preflight_pending=True,powered_preflight_pending=True,
        protected_refusal_predicates_checked=checks,preservation_verified=len(preserved),
        next_step='Both boards to powerbanks; PC USB and Saleae including GND disconnected;15V unchanged;J1 still OFF; no START or RESET.',
        final_step='After autonomous checks only: J1 through soft-start; fresh power/SD/protection checks; oneSTART with local5s autostop.',
        CLEAR_not_authorized=True,runner='tools/run_foc_fast_budget_trial.py',native_stop_and_Uno_local_stop_5s=True,
        limitation='OFF kernel timing is not full powered-adapter timing; this trial will measure the latter.')
    p.write(out/'plan.json',json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'preserved_records_sha256.json',json.dumps(preserved,indent=2)+'\n')
    p.write(out/'saved_files_sha256.json',json.dumps({f.name:sha(f) for f in out.iterdir() if f.is_file()},indent=2)+'\n')
    status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';text=p.read(status);idx=text.index('## 2026-10-30:')
    section='''## 2026-10-30:подготовлен одинFOC3001/3002 5Гц/5сек;ожидается перенос на повербанки

СвежийUSBстатус:3001/3002,SAFE/PWM0/run_id0,10В,FOC2/profile128CRC1354279011,
автонольготов,SDHIGH/BIE/config_ok,OFF64готово,аварий/UARTошибок0.
Пользователь запросил следующие переключения перед одним poweredFOC5Гц5сек.
run_foc_fast_budget_trial.py использует прежний проверенный runner сPAIR3001/3002;
все пороги,STOP/захват/однократныйSTART сохранены.11чистых предикатов отказа
проверены без команд на платы.854старых+54установочныхфайла проверены, сохранены.
START/CLEAR/ARM/RESET/flash0 в этом подготовительномэтапе.
Следующийфизическийшаг:обе платыUSBПК->повербанки,ПКиSaleae(включаяGND)отключены,
15ВON,J1покаOFF,Пуск/RESETненажимать. Сначалапроверитьавтономнуюзагрузку/связь,
затемпроситьвключениеJ1черезsoft-start. CLEARнеразрешён,автоматическинепосылать.
План:artifacts/live_bench_20261029/foc_fast_budget_fix_r1/FOC_CPU_IRQ_trial_preparation_r1/plan.json.

'''
    p.write(status,text[:idx]+section+text[idx:])
    print(json.dumps(dict(prepared=True,pair=list(p.NEW),preserved_files=len(preserved),guard_checks=len(checks),START=0,CLEAR=0,ARM=0)))

if __name__=='__main__':main()
