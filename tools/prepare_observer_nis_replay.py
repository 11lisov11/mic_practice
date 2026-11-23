"""Prepare schema4 one-step NIS replay without changing observer/control math."""
import json
import os
import shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
from analyze_observer_nis import sha

BASE=ROOT/'artifacts/live_bench_20261116/observer_current_window_r1'
OUT=ROOT/'artifacts/live_bench_20261117/observer_nis_replay_r1'
NEW=(2026111713,2026111714)


def main():
    assert not OUT.exists(),'Never overwrite sources or saved captures'
    for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def cp(src,dst):
            parts=Path(src).relative_to(BASE/folder).parts
            if folder=='libraries' or folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
                        ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if path.is_file():
                old=read(path);new=old.replace('2026111611',str(NEW[0])).replace('2026111612',str(NEW[1]))
                if old!=new:write(path,new)
    write(OUT/'nucleo/Inc/observer_nis_replay_core.h',read(ROOT/'tools/observer_nis_replay_core.h'))
    path=OUT/'nucleo/Inc/observer_trace_core.h';s=read(path)
    s=once(s,'#include <math.h>','#include <math.h>\n#include "observer_nis_replay_core.h"')
    s=once(s,'OD_CAPACITY=11,OD_STRIDE=500','OD_CAPACITY=8,OD_STRIDE=700')
    s=once(s,'od_sample sample[OD_CAPACITY],first_loss;','od_sample sample[OD_CAPACITY],first_loss;od_replay replay;')
    s=once(s,'uint8_t frozen,sealed,seen_valid;','uint8_t frozen,sealed,seen_valid,replay_latched;')
    s=once(s,'if(c->frozen)return; /* First completed record','if(c->frozen||c->replay_latched)return; /* First completed record')
    at=s.index('static inline void od_store(')
    s=s[:at]+'''/* Stage BEFORE ma_observe mutates x/P. The staging area is overwritten
 * until the first eligible NIS refusal, then remains immutable. This event
 * does not require a previous valid speed (unlike general first_loss).
 * No scratch capture is exposed as a real replay when no refusal occurs. */
static inline int od_replay_stage(od_capture*c,const ma_observer*o,const ma_motor*m,
 float ia,float ib,float va,float vb,float dt){
 if(c->frozen||c->replay_latched||o->steps<499U)return 0;
 od_replay*r=&c->blob.replay;
 memcpy(r->prior_x,o->x,sizeof(r->prior_x));memcpy(r->prior_p,o->p,sizeof(r->prior_p));
 r->prior_steps=o->steps;r->prior_rejected=o->rejected;r->motor=*m;
 r->input[0]=ia;r->input[1]=ib;r->input[2]=va;r->input[3]=vb;r->input[4]=dt;
 r->fpscr=od_fpscr();return 1;
}
static inline void od_replay_commit(od_capture*c,const ma_observer*o,int result,int staged){
 if(!staged||c->frozen||c->replay_latched||!(o->nis>=25.f))return;
 od_replay*r=&c->blob.replay;
 memcpy(r->post_x,o->x,sizeof(r->post_x));memcpy(r->post_p,o->p,sizeof(r->post_p));
 r->nis=o->nis;memcpy(r->predicted,o->predicted_i,sizeof(r->predicted));
 memcpy(r->innovation,o->innovation,sizeof(r->innovation));
 memcpy(r->variance,o->innovation_variance,sizeof(r->variance));
 r->post_rejected=o->rejected;r->result=(uint32_t)result;
 c->replay_latched=1;
}
''' + s[at:]
    s=once(s,'h->schema=3;','h->schema=4;')
    s=once(s,'h->flags=1U|(fault?2U:0U);','if(!c->replay_latched)memset(&c->blob.replay,0,sizeof(c->blob.replay));\n h->flags=1U|(fault?2U:0U)|(c->replay_latched?4U:0U);')
    write(path,s)
    path=OUT/'nucleo/Src/multi_native.c';s=read(path)
    s=once(s,'int fault=ma_observe(&observer,&model,window.ia,window.ib,va,vb,dt);',
           '''int replay_staged=od_replay_stage(&observer_trace,&observer,&model,window.ia,window.ib,va,vb,dt);
  int fault=ma_observe(&observer,&model,window.ia,window.ib,va,vb,dt);
  od_replay_commit(&observer_trace,&observer,fault,replay_staged);''')
    s=once(s,'p[2]=OD_WIRE;p[3]=3;','p[2]=OD_WIRE;p[3]=4;')
    # Include BOTH diagnostic copies in the stopped foreground timing probe.
    # Reuse the physical capture's RAM, but do NOT create a physical event.
    s=once(s,'''   int rc=ma_observe(&fe_test_observer,&model,fe_test_ia,fe_test_ib,
                    fe_test_out.va,fe_test_out.vb,.001f);''',
    '''   fe_test_observer.steps=499U;
   const int probe_capture=!observer_trace.blob.header.total&&!observer_trace.frozen&&!observer_trace.replay_latched;
   int probe_stage=probe_capture?od_replay_stage(&observer_trace,&fe_test_observer,&model,
      fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f):0;
   int rc=ma_observe(&fe_test_observer,&model,fe_test_ia,fe_test_ib,
                    fe_test_out.va,fe_test_out.vb,.001f);
   /* Exercise the copy's worst branch without changing actual observer NIS,
    * its result, or any qualification/protection threshold. No IRQ reads it. */
   float measured_nis=fe_test_observer.nis;fe_test_observer.nis=25.f;
   od_replay_commit(&observer_trace,&fe_test_observer,rc,probe_stage);
   fe_test_observer.nis=measured_nis;''')
    # Never touch an already captured physical replay; normal boot qualification
    # runs only before first START. Reject synthetic staging on later requalify.
    # Reset synthetic scratch only if the trace has never had physical samples.
    s=once(s,'   uint32_t cycles=DWT->CYCCNT-begin;',
               '   uint32_t cycles=DWT->CYCCNT-begin;\n   if(probe_capture){memset(&observer_trace,0,sizeof(observer_trace));}')
    write(path,s)
    for path in (OUT/'nucleo/Inc/observer_trace_wire.h',OUT/'UNOQ_MOTOR/observer_trace_wire.h'):
        s=read(path).replace('p[3]!=3','p[3]!=4').replace('odw_u32(r->data+4)!=3U','odw_u32(r->data+4)!=4U')
        write(path,s)
    path=OUT/'web_hmi/server.py';s=read(path)
    decoder=read(ROOT/'tools/observer_nis_replay_decode.py')
    # The decoder imports only standard library modules; embed it before the
    # existing decoder to keep deployed HMI independent of workspace/tools.
    s=once(s,'def decode_observer_trace_hex(value,expected):',decoder+'\n\ndef decode_observer_trace_hex(value,expected):')
    s=once(s,'(3,152,11,500,1888))','(3,152,11,500,1888),(4,152,8,700,1888))')
    s=once(s,'if not flags&1 or flags&~3 or loss','if not flags&1 or flags&~(7 if schema==4 else 3) or loss')
    s=s.replace('if schema==3','if schema>=3')
    s=once(s,'record_stride_steps=stride,samples=rows,',
               "record_stride_steps=stride,samples=rows,\n        first_nis_replay=decode_nis_replay(raw[1432:1888]) if schema==4 and flags&4 else None,")
    write(path,s)
    keep=['nucleo/Inc/motor_control.h','nucleo/Inc/foc_experiment.h',
          'nucleo/Inc/observer_current_window.h','nucleo/Inc/observer_forecast.h',
          'nucleo/Inc/observer_applied_voltage.h','nucleo/Src/current_shunt.c',
          'nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h',
          'nucleo/Inc/local_stop.h','nucleo/Inc/first_break_snapshot.h']
    for rel in keep:assert read(BASE/rel)==read(OUT/rel),rel
    write(OUT/'manifest.json',json.dumps(dict(pair=NEW,base_pair=[2026111611,2026111612],
        schema=4,record_bytes=1888,record_pages=63,history_rows=8,history_stride=700,
        replay_bytes=456,installed=False,hardware_commands=0,START=0,CLEAR=0,RESET=0,
        observer_math_unchanged=True,unchanged_modules=keep,
        protections_and_limits_unchanged=True,target_timing_qualified=False),indent=2)+'\n')
    print('Prepared offline NIS replay',NEW)


if __name__=='__main__':main()
