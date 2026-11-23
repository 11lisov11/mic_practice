"""Reproduce the encoded-on/physical-off transition with the actual emitter."""
import argparse,json,re,subprocess
from pathlib import Path
from ipm_break_wifi_selftest import emitter_program
from uno_reply_restart_selftest import function
from prepare_pwm_filter_pair import sha

def qualify(package,out):
    out.mkdir(parents=True,exist_ok=False)
    folder=package/'fixture/UNOQ_MOTOR';source=(package/'fixture/nucleo/Src/main.c').read_text()
    base=emitter_program();start=base.index('static void mic_send_break_page(');end=base.index('\nint main()',start)
    program=base[:start]+function(source,'mic_send_break_page')+base[end:]
    program=program.replace('uint32_t mic_break_diag_tx_errors;', 'uint32_t mic_break_diag_tx_errors;\nbool mic_last_control_reply_safe_off=true;')
    statement=re.search(r'  mic_last_control_reply_safe_off = .*?;',source)[0]
    program=program.replace('int main() {','void published(int tx_status,uint8_t status){\n'+statement+'\n}\nint main() {')
    anchor=' std::printf("{\\"pass\\":true,'
    addition='''
 // The encoded reply says ON, but the timer is now physically OFF.
 // A page must wait for a successful OFF reply published to the UART peer.
 transmit_status=HAL_OK;timer.BDTR&=~(1U<<15);mc_state=0;
 const auto sent_before=sent.size();
 published(HAL_OK,0x6d);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before);++count;
 published(HAL_OK,0x0d);now+=200;mic_send_break_page(now);
 assert(mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
 published(1,0x0d);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
 published(HAL_OK,0x03);now+=200;mic_send_break_page(now);
 assert(!mic_last_control_reply_safe_off && sent.size()==sent_before+1);++count;
'''
    assert anchor in program;program=program.replace(anchor,addition+anchor)
    unit=out/'actual_emitter.cpp';unit.write_text(program);exe=unit.with_suffix('.exe')
    def execute(label,code):
        target=out/(label+'.cpp');target.write_text(code)
        build=subprocess.run(['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror','-I',str(folder),'-I',str(Path(__file__).resolve().parents[1]/'research/ipm_break'),str(target),'-o',str(exe)],capture_output=True,text=True)
        (out/(label+'_build.log')).write_text(build.stdout+build.stderr);build.check_returncode()
        r=subprocess.run([str(exe)],capture_output=True,text=True);(out/(label+'_run.log')).write_text(r.stdout+r.stderr);return r
    result=execute('candidate',program);result.check_returncode()
    mutant=execute('missing_publish_gate',program.replace('!mic_last_control_reply_safe_off || ',''))
    assert mutant.returncode!=0,'Missing publication gate was not detected'
    report=json.loads(result.stdout);report.update(hardware_commands=0,mutation_detected=True,
      mcu_source_sha256=sha(package/'fixture/nucleo/Src/main.c'),acceptance_gate_unchanged=True,
      scope='Actual Nucleo emitter and publication predicate; register/UART mocks reproduce observed stop ordering')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True,type=Path);p.add_argument('--outdir',required=True,type=Path)
    a=p.parse_args();qualify(a.package.resolve(),a.outdir.resolve())
