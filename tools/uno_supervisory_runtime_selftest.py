"""Execute production RUNLIMIT setter with host stubs; test active zero-stop wiring."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    source=(root/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
    setter=re.search(r'static void set_run_limit\(float seconds\) \{.*?\n\}',source,re.S).group()
    zero_begin=source.index('  // Auto-stop if target frequency is zero')
    zero_block=source[zero_begin:source.index('  if (g_start_req)',zero_begin)]
    program='''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "mcsdk_supervisory.h"
bool g_pwm_enabled=false;
const bool START_REQUIRE_RUN_LIMIT=true;
const bool NUCLEO_MCSDK_ACIM_BACKEND=true;
bool g_duty_mode=false,g_diag_pwm=false,g_stop_requested=false;
float g_freq_cmd=0;
uint32_t g_run_limit_ms=0,g_run_deadline_ms=0,now=0;
unsigned stops=0,cases=0;
uint32_t millis() { return now; }
float clampf(float x,float lo,float hi) { return x<lo?lo:(x>hi?hi:x); }
void request_normal_stop() { ++stops; g_pwm_enabled=false; }
void check(bool ok) { ++cases; if(!ok) { std::fprintf(stderr,"failed case %u\\n",cases); std::exit(1); } }
''' + setter + '\nvoid zero_stop_tick() {\n' + zero_block + '\n}\n' + '''
int main() {
 now=1000; g_pwm_enabled=true; g_run_deadline_ms=16000;
 set_run_limit(3); check(g_run_deadline_ms==4000);
 now=2000; set_run_limit(3); check(g_run_deadline_ms==4000);
 set_run_limit(600); check(g_run_deadline_ms==4000);
 set_run_limit(0); check(!g_pwm_enabled && stops==1 && g_run_deadline_ms==0);
 set_run_limit(15); check(g_run_limit_ms==15000 && g_run_deadline_ms==0);
 for(uint32_t n : {0U,1U,0xffff0000U,0xffffff00U}) {
  uint32_t previous=n+15000;
  check(unoq_bounded_run_deadline(n,3000,previous,true)==n+3000);
  check(unoq_bounded_run_deadline(n,30000,previous,true)==previous);
 }
 check(unoq_bounded_run_deadline(0xffffff00U,256,0,true)!=0);
 check(unoq_mcsdk_zero_stop(true,0));
 check(unoq_mcsdk_zero_stop(true,.05f));
 check(!unoq_mcsdk_zero_stop(true,.1f));
 check(!unoq_mcsdk_zero_stop(false,0));
 g_pwm_enabled=true; g_freq_cmd=0; unsigned old_stops=stops;
 zero_stop_tick(); check(!g_pwm_enabled && stops==old_stops+1 && !g_stop_requested);
 g_pwm_enabled=true; g_freq_cmd=10;
 zero_stop_tick(); check(g_pwm_enabled && stops==old_stops+1);
 std::printf("%u",cases);
}
'''
    program='#include <initializer_list>\n'+program
    compiler=shutil.which('g++')
    if not compiler: raise RuntimeError('g++ required')
    with tempfile.TemporaryDirectory() as tmp:
        unit,exe=Path(tmp)/'test.cpp',Path(tmp)/'test.exe'
        unit.write_text(program,encoding='utf-8')
        subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',
                        '-I',str(root/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],text=True,capture_output=True)
        if run.returncode:
            (out/'failure.txt').write_text(run.stderr,encoding='utf-8')
            raise RuntimeError('production runtime regression: '+run.stderr.strip())
    assert re.search(r'if \(unoq_mcsdk_zero_stop\(NUCLEO_MCSDK_ACIM_BACKEND, g_freq_cmd\)\) \{\s*request_normal_stop\(\);\s*return;',source)
    assert 'g_io_test_mode || unoq_mcsdk_zero_stop(true, g_freq_cmd)' in source
    assert 'unoq_bounded_run_deadline(millis(), g_run_limit_ms, 0U,' in source
    report={'pass':True,'cases':int(run.stdout),'scope':'offline actual RUNLIMIT setter and zero-stop call sites; no physical PWM'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
