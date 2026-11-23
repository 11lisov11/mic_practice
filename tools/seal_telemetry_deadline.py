"""Seal1603/1604 without hardware access; retain OFF qualification requirement."""
import inspect,json,re,subprocess
import prepare_telemetry_deadline as p
import seal_observer_input_epoch as generic
from build_multi_native import BIN
from test_foc_update_latency_fix import function


def main():
    tests=json.loads(p.read(p.OUT/'verification/report.json'))
    model=json.loads(p.read(p.OUT/'model_verification/model_report.json'))
    capture=json.loads(p.read(p.OUT/'verification/NIS_capture_regression.json'))
    assert tests['passed'] and model['passed'] and model['baseline_candidate_model_trajectories_identical']
    assert capture['raw1024_wire_roundtrip'] and capture['release_decoder_CRC_and_cause_verified']
    changed=[];unchanged=[]
    for rel in json.loads(p.read(p.BASE/'source_hashes.json')):
        old=p.read(p.BASE/rel).replace('2026111601',str(p.NEW[0])).replace('2026111602',str(p.NEW[1]))
        new=p.read(p.OUT/rel)
        (unchanged if old==new else changed).append(rel)
    assert changed==['nucleo/Src/main.c'],changed
    a=p.read(p.BASE/'nucleo/Src/main.c');b=p.read(p.OUT/'nucleo/Src/main.c')
    for name in ('uno_send_reply','uno_link_poll','mic_send_current_page','mic_send_research_page',
        'uno_tx_submit','uno_tx_watchdog','uno_tx_tc_isr'):
        old=function(a,name).replace('2026111601',str(p.NEW[0])).replace('2026111602',str(p.NEW[1]))
        assert old==function(b,name),name
    # Every actual change to the native main TU is inside the OFF-only helper.
    a=a.replace('2026111601',str(p.NEW[0])).replace('2026111602',str(p.NEW[1]))
    assert a.replace(function(a,'mic_send_bulk_page'),function(b,'mic_send_bulk_page'))==b
    arm={}
    for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        elf=folder/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        asm=subprocess.check_output([str(BIN/'arm-none-eabi-objdump.exe'),'-d',str(elf)],text=True)
        p.write(p.OUT/f'verification/ARM_{label}.txt',asm);scopes={}
        for name in ('ma_native_fast','ma_native_profile_tick'):
            m=re.search(r'^\w+ <'+re.escape(name)+r'>:\n(.*?)(?=^\w+ <|\Z)',asm,re.M|re.S);assert m,name
            scopes[name]=re.findall(r'\bbl(?:\.w)?\s+[^<\n]+<([^>]+)>',m[1])
        arm[label]=scopes
    assert arm['baseline']==arm['candidate']
    arm.update(passed=True,changed_source_files=changed,unchanged_source_files=len(unchanged),
        native_FAST_call_scope_identical=True,OFF_profile_body_unchanged=True,
        RUN_control_reply_and_UART_watchdog_bodies_unchanged=True,
        receiver_and_HMI_freshness_unchanged=True,ADC_and_NIS_capture_unchanged=True,
        target_timing_measured=False)
    p.write(p.OUT/'verification/ARM_scope.json',json.dumps(arm,indent=2)+'\n')
    source=inspect.getsource(generic.main).replace('_observer_input.hex','_telemetry_deadline.hex').replace('_observer_trace.elf-zsk.bin','_telemetry_deadline.elf-zsk.bin')
    scope=dict(generic.__dict__,p=p);exec(compile(source,__file__,'exec'),scope);scope['main']()
    m=json.loads(p.read(p.OUT/'manifest.json'))
    m.update(verification_reports={rel:p.sha(p.OUT/rel) for rel in (
        'verification/report.json','verification/ARM_scope.json','verification/NIS_capture_regression.json',
        'model_verification/model_report.json','nucleo_build_report.json',
        'build/uno/unoq_mcsdk_scalar.build-manifest.json')},
        qualified=False,OFF_CPU_qualified=False,FOC_start_ready=False,
        previous_measured_OFF_cycles=3618,previous_measurement_is_candidate_measurement=False,
        target_timing_requalification_required=True,hardware_commands=0,installed=False)
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,pair=list(p.NEW),installed=False,
        preserved_files_verified=m['preserved_files_verified'],RAM_unallocated=m['RAM_unallocated'])))


if __name__=='__main__':main()
