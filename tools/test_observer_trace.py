"""Actual C recorder/wire and differential actuator tests; no hardware."""
import hashlib,importlib.util,json,sys
import prepare_observer_trace as p
import test_foc_runtime_fix as common
from test_foc_observer_schedule_fix import stripped_header
from test_foc_update_latency_fix import function


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
    code=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
int main(){
 unsigned tests=0;
 assert(sizeof(od_sample)==96&&sizeof(od_blob)==1696);++tests;
 assert(od_reasons(1,1,500,0,.2f,.25f,0)==0);++tests;
 assert(od_reasons(1,1,500,0,.125f,.25f,0)==OD_FLUX);++tests;
 assert(od_reasons(1,1,500,0,.2f,.25f,25)==OD_NIS);++tests;
 assert(od_reasons(1,1,499,0,.2f,.25f,0)==OD_WARMUP);++tests;
 assert(od_reasons(1,1,500,0,NAN,.25f,0)==(OD_FLUX|OD_NONFINITE));++tests;
 od_capture c={};od_begin(&c,2026103016U);
 for(unsigned i=1;i<=5000;++i){
   od_sample r={};r.steps=i;r.cycles=i*170000U;r.rpm=300;r.flux_alpha=.2f;
   r.nis=i>=700&&i<750?26.f:0.f;r.reasons=od_reasons(1,1,i,0,.2f,.25f,r.nis);
   r.id=.4f;r.iq=.1f;r.id_ref=.5f;r.iq_ref=.2f;r.reference_hz=5;r.dt=.001f;r.published=1;
   od_push(&c,&r);++tests;
 }
 assert(c.blob.header.first_loss_present&&c.blob.header.first_loss_step==700);
 assert(c.blob.first_loss.reasons==OD_NIS);++tests;
 od_freeze(&c,0);assert(c.blob.header.count==16&&c.blob.header.oldest==0);++tests;
 assert(c.blob.sample[0].steps==1&&c.blob.sample[15].steps==5000);++tests;
 c.blob.header.crc=uv3_crc32c((uint8_t*)&c.blob,OD_BYTES);
 od_blob saved=c.blob;od_begin(&c,2026103016U);od_push(&c,&c.latest);od_freeze(&c,3);
 assert(memcmp(&saved,&c.blob,sizeof(saved))==0);++tests;
 auto packet=[&](unsigned page,uint8_t*p){
  memset(p,0,43);p[0]=0x55;p[1]=0xaa;p[2]=OD_WIRE;p[3]=p[4]=1;p[5]=page;p[6]=OD_PAGES;
  p[7]=page==56?16:30;memcpy(p+8,((uint8_t*)&saved)+page*30,p[7]);p[38]=1;uv3_seal(p);
 };
 od_receiver rx={};uint8_t bytes[43];
 for(int i=56;i>=0;--i){packet(i,bytes);assert(odw_receive(&rx,bytes,2026103016U,2026103016U,true));++tests;}
 assert(rx.complete&&memcmp(rx.data,&saved,OD_BYTES)==0);++tests;
 packet(0,bytes);assert(!odw_receive(&rx,bytes,2026103016U,2026103016U,false));++tests;
 assert(!odw_receive(&rx,bytes,0,2026103016U,true));++tests;
 for(unsigned bit=0;bit<43*8;++bit){uint8_t damaged[43];memcpy(damaged,bytes,43);damaged[bit/8]^=1<<(bit%8);
  assert(!odw_receive(&rx,damaged,2026103016U,2026103016U,true));++tests;}
 bytes[8]^=1;uv3_seal(bytes);assert(!odw_receive(&rx,bytes,2026103016U,2026103016U,true));++tests;
 printf("{\"checks\":%u,\"trace_hex\":\"",tests);
 for(unsigned i=0;i<OD_BYTES;++i)printf("%02x",rx.data[i]);printf("\"}\n");
}
'''
    core=json.loads(common.compile_run(out,'observer_record_wire',code))
    pre='''#include <cassert>\n#include <cstdio>\n#include <cstring>\n#include <cstdint>\n#include <cmath>\n#include <cfloat>\n#include "current_adc_window_plan.h"\nusing std::isfinite;using std::isnan;\n'''
    old=stripped_header(p.read(p.BASE/'nucleo/Inc/motor_control.h'))
    new=stripped_header(p.read(p.OUT/'nucleo/Inc/motor_control.h'))
    numeric=pre+'\nnamespace old {\n'+old+'\n}\nnamespace candidate {\n'+new+'\n}\n'+r'''
static uint32_t state=0x31775;
static uint32_t next(){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
static float value(float lo,float hi){return lo+(hi-lo)*(next()>>8)*(1.f/16777216.f);}
int main(){
 old::ma_motor m={12.23f,11.004422f,.52809386f,.52809386f,.4944776f,.0002f,.000147906f,1,.25f,.8f,1.35f,400,12};
 old::ma_geometry g={5312,5184,771,112,240,229};unsigned checked=0;
 for(unsigned k=0;k<20000;++k){
  old::ma_controller a={};a.time_s=value(0,5);a.integral[0]=value(-1,1);a.integral[1]=value(-1,1);a.speed_integral=value(-.1f,.1f);
  candidate::ma_controller b;memcpy(&b,&a,sizeof(a));candidate::ma_motor nm;memcpy(&nm,&m,sizeof(m));
  candidate::ma_geometry ng;memcpy(&ng,&g,sizeof(g));
  float x[6]={value(-1,1),value(-1,1),value(.1f,.3f),value(-.2f,.2f),value(0,40),0};
  float ia=value(-1.4f,1.4f),ib=value(-1.4f,1.4f),ref=value(0,5),bus=value(290,330);
  if(k%1000==0)ia=NAN;
  old::ma_output oa;candidate::ma_output ob;
  int ra=old::ma_control(&a,&m,x,&g,2,ia,ib,ref,bus,1.f/16000,1,&oa);
  int rb=candidate::ma_control(&b,&nm,x,&ng,2,ia,ib,ref,bus,1.f/16000,1,&ob);
  assert(ra==rb&&memcmp(&a,&b,sizeof(a))==0&&memcmp(&oa,&ob,sizeof(oa))==0);++checked;
  if(!ra){float f=hypotf(x[2],x[3]);assert(ob.id_measured==x[2]/f*ia+x[3]/f*ib);}
 }
 printf("{\"bit_exact_actuator_cases\":%u}\n",checked);
}
'''
    differential=json.loads(common.compile_run(out,'observer_actuator_bit_exact',numeric))
    spec=importlib.util.spec_from_file_location('observer_hmi_test',p.OUT/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    decoded=hmi.decode_observer_trace_hex(core['trace_hex'],p.NEW[1])
    assert decoded['first_loss']['steps']==700 and decoded['first_loss']['reason_mask']==32
    assert decoded['count']==16 and decoded['samples'][0]['steps']==1 and decoded['samples'][-1]['steps']==5000
    try:hmi.decode_observer_trace_hex(core['trace_hex'],p.NEW[1]+1)
    except ValueError:pass
    else:raise AssertionError('Wrong firmware accepted')
    state=hmi.RpcBridge._parse_status_string('DATA state=SAFE mode=VF bp_fw_build=2026103016 mc_observer_trace_hex='+core['trace_hex'])
    assert state and state['mc_observer_trace_hex']==core['trace_hex']
    assert hmi.with_observer_trace(dict(mc_fw_build=p.NEW[1],mc_observer_trace_hex=core['trace_hex']))['observer_trace']['available']
    changed={'nucleo/Inc/motor_control.h','nucleo/Inc/multi_native.h','nucleo/Src/multi_native.c','nucleo/Src/main.c',
             'UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py','web_hmi/static/app.js'}
    verified=0
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (p.BASE/folder).rglob('*'):
            if not f.is_file() or '__pycache__' in f.parts:continue
            rel=f.relative_to(p.BASE).as_posix()
            if rel in changed:continue
            expected=p.read(f).replace('2026103013',str(p.NEW[0])).replace('2026103014',str(p.NEW[1])).replace('3013-boot-capture','3015-observer-trace')
            assert p.read(p.OUT/rel)==expected,rel;verified+=1
    for name in ('uno_handle_valid_frame','uno_rearm_break_irq','mic_local_stop_clear','mic_local_stop_enable_outputs'):
        assert function(p.read(p.BASE/'nucleo/Src/main.c'),name)==function(p.read(p.OUT/'nucleo/Src/main.c'),name)
    assert p.read(p.BASE/'nucleo/Inc/foc_experiment.h')==p.read(p.OUT/'nucleo/Inc/foc_experiment.h')
    for name in ('ma_observe','ma_derivative'):
        assert function(p.read(p.BASE/'nucleo/Inc/motor_control.h'),name)==function(p.read(p.OUT/'nucleo/Inc/motor_control.h'),name)
    old_native=p.read(p.BASE/'nucleo/Src/multi_native.c');new_native=p.read(p.OUT/'nucleo/Src/multi_native.c')
    assert function(old_native,'ma_native_diag')==function(new_native,'ma_native_diag')
    tap='    bin_id=out.id_measured;bin_iq=out.iq_measured;bin_idref=out.id_ref;bin_iqref=out.iq_ref;bin_reference=reference_hz;\n    bin_control_sequence=sample.sequence;bin_control_adc_cycles=sample.cycles;\n'
    assert function(new_native,'ma_native_fast').replace(tap,'')==function(old_native,'ma_native_fast')
    service=function(new_native,'ma_native_service')
    assert service.index('if(fault){ma_fail_at')<service.index('ma_observer_record(&sample')
    report=dict(passed=True,core_checks=core['checks'],differential=differential,unchanged_files=verified,
        decoded_example=decoded,hardware_commands=0,actuator_math_unchanged=True,observer_math_unchanged=True)
    p.write(out/'selftest.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,core_checks=core['checks'],differential=differential,unchanged_files=verified)))


if __name__=='__main__':main()
