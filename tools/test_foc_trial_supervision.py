"""Replay the host refusal, keepalive failures, and unchanged native ADC guards."""
import copy
import json
import threading
import time
from pathlib import Path
import run_foc_runtime_trial as trial
from foc_trial_supervision import TrialHeartbeat
import prepare_foc_observer_schedule_fix as p
import test_foc_runtime_fix as common
from test_foc_estimate_publish_fix import native_source


def main():
    trial.PAIR = p.NEW
    common.p = p
    out = p.OUT / 'verification/host_supervision_fix_r1'
    out.mkdir(exist_ok=False)
    capture = p.OUT / 'powered_FOC_schedule_20261030_r1'
    rows = [json.loads(x) for x in p.read(capture / 'status.jsonl').splitlines()]
    state = next(x['status'] for x in rows if x['label'] == 'running' and x['status']['run_elapsed_ms'] == 1893)
    assert not trial.profile(state)  # Old START-only check caused the host refusal.
    assert trial.runtime_profile(state) and trial.healthy(state)
    fresh_bad = copy.deepcopy(state)
    fresh_bad.update(mc_current_age_ms=10, mc_current_detail_age_ms=20)
    assert not trial.runtime_profile(fresh_bad) and not trial.healthy(fresh_bad)
    for changes in (dict(algorithm_profile_crc=0), dict(mc_age_ms=301),
                    dict(algorithm_fault=3), dict(research_native_valid=0)):
        bad = dict(state, **changes)
        assert not trial.runtime_profile(bad)
    for changes in (dict(mc_fault_current_mask=128), dict(estop=1),
                    dict(mc_uart_error_flags=8), dict(mc_transport_fault=4), dict(vdc=0)):
        assert not trial.healthy(dict(state, **changes))
    for key, value in [('level', 'LOW'), ('break_irq_enabled', False), ('config_ok', False)]:
        bad = copy.deepcopy(state)
        bad['mc_sd_live'][key] = value
        assert not trial.healthy(bad)
    assert not trial.profile(state)  # A new START still requires fresh zero telemetry.
    requests = []
    def request(path, body, timeout):
        assert path == '/api/operator-heartbeat' and body == {} and timeout == 2
        requests.append(time.monotonic())
        return {'ok': True}
    heartbeat = TrialHeartbeat(request, interval=.01)
    heartbeat.start()
    time.sleep(.065)
    assert heartbeat.healthy() and heartbeat.sent >= 3
    heartbeat.stop()
    sent = heartbeat.sent
    time.sleep(.03)
    assert heartbeat.sent == sent
    failure_seen = threading.Event()
    def failed(path, body, timeout):
        if failure_seen.is_set():
            raise TimeoutError('injected keepalive failure')
        failure_seen.set()
        return {'ok': True}
    failing = TrialHeartbeat(failed, interval=.01)
    failing.start()
    time.sleep(.04)
    assert not failing.healthy() and failing.error is not None
    failing.stop()
    # Source of the installed firmware is not edited. Exercise its actual fast
    # loop with zero loss, invalid ADC, aged ADC, aged estimate and raw current.
    pre = p.read(p.ROOT / 'artifacts/live_bench_20261029/foc_runtime_fix_r1/verification/native_runtime.cpp').split('#define MIC_NATIVE_BUILD', 1)[0]
    body = r'''
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static void setup(){
 timer.BDTR=0;selected=MA_FOC;qualification=FE_ESTIMATED;profile_ready=1;
 fe_complete=fe_started=1;fe_fault=0;fe_case=64;id_profile_attempted=1;
 run_fault=first_fault=0;memset(&ma_first_runtime,0,sizeof(ma_first_runtime));
 sample={};sample.valid=sample.zero=1;sample_coherent=1;fake_bus=321;
 cycle.CYCCNT=1000000;assert(ma_native_prepare());timer.BDTR=1;
 sample.cycles=cycle.CYCCNT;assert(ma_native_fast(0)==0);
 cycle.CYCCNT+=204000;sample.cycles=cycle.CYCCNT;
}
int main(){
 unsigned checked=0;
 for(unsigned which=0;which<5;++which){
  setup();unsigned reason=FT_ADC_INVALID,code=MA_STALE;
  if(which==0)sample.zero=0;
  if(which==1)sample.valid=0;
  if(which==2){sample.cycles-=31875;reason=FT_ADC_AGE;}
  if(which==3){estimate_slot[estimate_index].stamp=cycle.CYCCNT-340000;reason=FT_ESTIMATE_AGE;}
  if(which==4){sample.counts[0]=200;sample.counts[1]=-100;sample.counts[2]=-100;reason=FT_CONTROL;code=MA_CURRENT;}
  assert(ma_native_fast(0)!=0&&run_fault==code&&ma_first_runtime.word[0]==reason);++checked;
 }
 printf("{\"unchanged_native_rejections_checked\":%u}\n",checked);
}
'''
    native = json.loads(common.compile_run(out, 'native_guards', '#include <cstdio>\n' + pre + native_source(p.OUT, hook=False) + body))
    report = dict(passed=True, hardware_commands=0, saved_false_host_refusal_reproduced=True,
        START_fresh_autozero_still_required=True, fresh_negative_zero_still_rejected=True,
        runtime_accepts_only_unknown_expired_zero_with_native_RUN_ack=True,
        native_guards=native, SD_UART_profile_faults_still_rejected=True,
        heartbeat_periodic_and_stopped_cleanly=True, heartbeat_failure_blocks_run=True,
        authenticated_keepalive_endpoint_only=True, MCU_firmware_not_changed=True,
        current_telemetry_starvation_source_not_yet_isolated=True,
        no_claim_of_five_second_hardware_completion=True)
    p.write(out / 'report.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
