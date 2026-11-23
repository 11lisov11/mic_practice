"""Compile actual native adapter and ARM objects; never contact the bench."""
import json,shutil,subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from audit_nis_1716_saved_step import ROOT,BASE,CAP,OUT,sha
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case


def main():
    overlay=OUT/'overlay';out=OUT/'verification_final'
    fixture=(BASE/'verification/window_adapter.cpp').read_text(encoding='utf-8')
    pre=fixture[:fixture.index('#define MIC_NATIVE_BUILD')]
    pre=pre.replace('static void mic_current_request_observer_capture(){}',
        '''static uint32_t request_first,request_end,request_step;static unsigned request_calls;
static void mic_current_request_observer_capture(uint32_t first,uint32_t end,uint32_t step){
 request_first=first;request_end=end;request_step=step;++request_calls;
}''')
    tail=fixture[fixture.index('static void NVIC_SetPendingIRQ(int irq){'):]
    saved=json.loads((CAP/'observer_trace_decoded.json').read_text(encoding='utf-8'))
    d=saved['first_nis_replay'];row=saved['first_loss'];tofloat=lambda x:repr(float(x))+'f'
    previous=(row['observation_cycles']-round(d['inputs']['dt_s']*170000000))&0xffffffff
    setup=f'''
 // Exact saved prior/input, but deliberately retain an earlier FLUX-only loss.
 // The first-NIS replay must still request ITS raw source exactly once.
 timer.BDTR=1;fake_bus=319;selected=MA_FOC;qualification=FE_ESTIMATED;
 profile_ready=1;running=1;run_fault=0;fe_complete=1;fe_fault=0;id_profile_attempted=1;
 cycle.CYCCNT={row['observer_adc_cycles']+10000}U;telemetry_seq=0;
 memset(&observer,0,sizeof(observer));
 const float px[6]={{{','.join(map(tofloat,d['prior_state']))}}};
 const float pp[36]={{{','.join(tofloat(v) for r in d['prior_covariance'] for v in r)}}};
 memcpy(observer.x,px,sizeof(px));memcpy(observer.p,pp,sizeof(pp));
 observer.steps={d['prior_steps']}U;observer.rejected={d['prior_rejected']}U;
 ma_estimate_reset({previous}U);observer_center_cycles={previous}U;
 bin_current={{}};bin_current.valid=bin_current.zero=1;bin_current.cycles={row['observer_adc_cycles']}U;
 bin_cycles=bin_current.cycles;bin_current.sequence=42;bin_control_sequence=42;bin_control_adc_cycles=bin_cycles;
 bin_va={tofloat(d['inputs']['va_V'])};bin_vb={tofloat(d['inputs']['vb_V'])};
 bin_window={{}};bin_window.first={row['window_first_cycles']}U;bin_window.center={row['observation_cycles']}U;
 bin_window.end=bin_cycles;bin_window.previous_center={previous}U;bin_window.count=16;bin_window.pair_counts=16U<<5;
 bin_window.ia={tofloat(d['inputs']['ia_A'])};bin_window.ib={tofloat(d['inputs']['ib_A'])};
 bin_window.va=bin_window.tail_va=bin_va;bin_window.vb=bin_window.tail_vb=bin_vb;
 memset(&observer_trace,0,sizeof(observer_trace));observer_trace.seen_valid=1;
 observer_trace.blob.header.first_loss_present=1;observer_trace.blob.header.first_loss_step=500;
 observer_trace.blob.first_loss.reasons=OD_FLUX;
 request_calls=0;inject_torn=false;ma_native_service();
 assert(!run_fault&&observer_trace.replay_latched&&observer.steps==503);
 assert(fabsf(observer.nis-25.66879654f)<.0002f);++checks;
 assert(request_calls==1&&request_first==bin_window.first&&request_end==bin_window.end&&request_step==503);++checks;
 assert(observer_trace.blob.header.first_loss_step==500&&observer_trace.blob.first_loss.reasons==OD_FLUX);++checks;
 ma_native_service();assert(request_calls==1);++checks;
'''
    tail=tail.replace(' printf(',setup+'\n printf(',1)
    native=native_source(overlay).replace('sample=bin_current;ow_bin window=bin_window;',
        'sample=bin_current;ow_bin window=bin_window;if(inject_torn){++telemetry_seq;inject_torn=false;}')
    exe=compile_case(out,'exact_native_adapter',pre+native+'\n'+tail,overlay)
    r=subprocess.run([str(exe)],capture_output=True,text=True)
    (out/'exact_native_adapter_run.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
    result=json.loads(r.stdout)
    # Real ARM compilation of both modified translation units, same target and
    # include tree. No image flashing/linker RAM assumption is inferred here.
    plugins=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins')
    tool=next(plugins.glob('com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin/arm-none-eabi-gcc.exe'))
    common=['-mcpu=cortex-m4','-std=gnu11','-g3','-DDEBUG','-DARM_MATH_CM4','-DUSE_HAL_DRIVER','-DSTM32G431xx','-c',
        '-Ofast','-ffunction-sections','-fdata-sections','-Wall','-fstack-usage','--specs=nano.specs',
        '-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-mthumb']
    includes=['Drivers/STM32G4xx_HAL_Driver/Inc','Drivers/STM32G4xx_HAL_Driver/Inc/Legacy',
        'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Inc','MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/Any/Inc',
        'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/G4xx/Inc','Drivers/CMSIS/Device/ST/STM32G4xx/Include',
        'Drivers/CMSIS/Include','Drivers/CMSIS/DSP/Include']
    compiled={}
    for label,folder in [('baseline',BASE),('candidate',overlay)]:
        for name in ('current_shunt','multi_native'):
            obj=out/(label+'_'+name+'.o')
            cmd=[str(tool),str(folder/'nucleo/Src'/(name+'.c')),*common,'-I'+str(folder/'nucleo/Inc')]
            cmd+=['-I'+str(BASE/'nucleo'/i) for i in includes]+['-o',str(obj)]
            r=subprocess.run(cmd,capture_output=True,text=True)
            (out/(label+'_'+name+'_ARM_build.log')).write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
            compiled[label+'_'+name]=str(obj)
    def section(file,name):
        with Path(file).open('rb') as f:return ELFFile(f).get_section_by_name(name).data()
    same={name:section(compiled['baseline_multi_native'],'.text.'+name)==section(compiled['candidate_multi_native'],'.text.'+name)
        for name in ('ma_native_fast','mic_observer_step','mic_observer_noise')}
    assert all(same.values()),same
    report=dict(passed=True,hardware_commands=0,host_adapter=result,ARM_translation_units_compiled=4,
        ARM_fast_and_observer_sections_byte_identical=same,actual_target_cycles_measured=False,
        new_NIS_source_hook_tested_despite_earlier_non_NIS_loss=True,
        diagnostic_first_NIS_mean_and_state_unchanged=True,firmware_images_linked=False)
    (out/'native_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
