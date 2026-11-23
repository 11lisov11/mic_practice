"""Prepare diagnostic source overlay ONLY; no flash, bench access or motor change."""
import json,shutil
from pathlib import Path
from audit_nis_1716_saved_step import ROOT,BASE,OUT,sha


def once(s,a,b):
    assert s.count(a)==1,(a[:80],s.count(a))
    return s.replace(a,b,1)


def main():
    overlay=OUT/'overlay';overlay.mkdir(exist_ok=False)
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/folder,overlay/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc','backups'))
    path=overlay/'nucleo/Inc/peak_core.h'
    path.write_text((ROOT/'tools/observer_exact_peak_core.h').read_text(encoding='utf-8'),encoding='utf-8')
    signature='mic_current_request_observer_capture(uint32_t first,uint32_t end,uint32_t step)'
    path=overlay/'nucleo/Inc/current_shunt.h';s=path.read_text(encoding='utf-8')
    s=once(s,'mic_current_request_observer_capture(void)',signature);path.write_text(s,encoding='utf-8')
    path=overlay/'nucleo/Src/current_shunt.c';s=path.read_text(encoding='utf-8')
    s=once(s,'static volatile uint8_t peak_observer_request;\nvoid mic_current_request_observer_capture(void){peak_observer_request=1;}',
        'void '+signature+'{pc_request_observer(&peak,first,end,step);}')
    s=once(s,'    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;\n','')
    s=once(s,'  uint32_t queue_cycles=DWT->CYCCNT-cycles0;', '  uint32_t queue_cycles=DWT->CYCCNT-cycles0;\n  (void)queue_cycles; /* Schema3 reserves payload for exact source history. */')
    s=once(s,'    if(peak_observer_request){peak_observer_request=0;pc_request_observer(&peak);}\n','')
    path.write_text(s,encoding='utf-8')
    path=overlay/'nucleo/Src/multi_native.c';s=path.read_text(encoding='utf-8')
    old=''' /* First validity loss is immutable; request raw ADC around that event.
  * No diagnostic outcome changes observer/control validity or fault gates. */
 if(observer_trace.blob.header.first_loss_present&&
    observer_trace.blob.header.first_loss_step==r.steps&&(r.reasons&OD_NIS))
   mic_current_request_observer_capture();'''
    s=once(s,old,' /* Raw source capture is requested at first replay latch, above publication. */')
    s=once(s,'  od_replay_commit(&observer_trace,&observer,fault,replay_staged);',
        '''  const int replay_was_latched=observer_trace.replay_latched;
  od_replay_commit(&observer_trace,&observer,fault,replay_staged);
  if(!replay_was_latched&&observer_trace.replay_latched)
    mic_current_request_observer_capture(window.first,window.end,observer.steps);''')
    path.write_text(s,encoding='utf-8')
    path=overlay/'web_hmi/server.py';s=path.read_text(encoding='utf-8')
    helper=(ROOT/'tools/observer_exact_peak_decode.py').read_text(encoding='utf-8')
    s=once(s,'def decode_adc_peak_hex(value, expected_build=2026102510):',helper+'\n\ndef decode_adc_peak_hex(value, expected_build=2026102510):')
    s=once(s,"    if len(raw) != 1024:\n        raise ValueError('ADC trace must contain 1024 bytes')",
        "    if len(raw)==1024 and int.from_bytes(raw[4:6],'little')==3:\n        return decode_exact_adc_peak_hex(value,expected_build)\n    if len(raw) != 1024:\n        raise ValueError('ADC trace must contain 1024 bytes')")
    s=once(s,'data.update(mc_adc_peak_valid=0,mc_adc_peak=None,',
           'data.update(mc_adc_peak_source_valid=0,mc_adc_peak_valid=0,mc_adc_peak=None,')
    at="    except (ValueError,TypeError) as exc:\n        data['mc_adc_peak_status']='Ошибка записи захвата АЦП: '+str(exc)"
    s=once(s,at,"""        if trace.get('source_window_exact'):
            data.update(mc_adc_peak_source_valid=1,mc_adc_peak_status='Исходные 16 отсчётов наблюдателя сохранены')
        elif trace.get('source_window_gap'):
            data['mc_adc_peak_status']='Исходное окно недоступно; сохранена только доступная история АЦП'
"""+at)
    path.write_text(s,encoding='utf-8')
    changed=[]
    for file in overlay.rglob('*'):
        if file.is_file() and sha(file)!=sha(BASE/file.relative_to(overlay)):
            changed.append(file.relative_to(overlay).as_posix())
    assert set(changed)=={'nucleo/Inc/peak_core.h','nucleo/Inc/current_shunt.h','nucleo/Src/current_shunt.c','nucleo/Src/multi_native.c','web_hmi/server.py'},changed
    # Preserve actuator, estimator and every threshold byte-for-byte.
    a=(BASE/'nucleo/Src/multi_native.c').read_text(encoding='utf-8');b=(overlay/'nucleo/Src/multi_native.c').read_text(encoding='utf-8')
    assert a[a.index('uint16_t ma_native_fast('):]==b[b.index('uint16_t ma_native_fast('):]
    for f in ('motor_control.h','observer_pair_noise.h','foc_experiment.h','current_adc_window_plan.h','current_adc_deadline.h','local_stop.h','first_break_snapshot.h'):
        assert sha(overlay/'nucleo/Inc'/f)==sha(BASE/'nucleo/Inc'/f)
    manifest=dict(overlay_only=True,firmware_images_built=False,installed=False,hardware_commands=0,
        source_build_IDs_unchanged_NOT_a_flashable_release=True,changed=changed,
        observer_math_and_control_unchanged=True,protection_limits_unchanged=True,
        physical_NIS_fix_proven=False,target_CPU_or_RAM_qualified=False,
        purpose='Correct proven source-window capture gap; do not invent a motor/voltage correction from an underdetermined record')
    (OUT/'overlay_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))


if __name__=='__main__':main()
