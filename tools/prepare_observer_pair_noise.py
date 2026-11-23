"""Offline pair-aware measurement model; preserves all physical protection gates."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
from analyze_observer_nis import sha
BASE=ROOT/'artifacts/live_bench_20261117/observer_nis_replay_r1'
OUT=ROOT/'artifacts/live_bench_20261117/observer_pair_noise_r1'
NEW=(2026111715,2026111716)


def main():
 assert not OUT.exists()
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
    a=read(path);b=a.replace('2026111713',str(NEW[0])).replace('2026111714',str(NEW[1]))
    if a!=b:write(path,b)
 write(OUT/'nucleo/Inc/observer_pair_noise.h',read(ROOT/'tools/observer_pair_noise.h'))
 path=OUT/'nucleo/Inc/motor_control.h';s=read(path)
 s=once(s,'#include "current_adc_window_plan.h"','#include "current_adc_window_plan.h"\n#include "observer_pair_noise.h"')
 s=once(s,'int ma_observe(ma_observer*o,const ma_motor*m,float ia,float ib,',
               'int ma_observe_noise(ma_observer*o,const ma_motor*m,float ia,float ib,')
 s=once(s,'float va,float vb,float dt){\n  if(!ma_motor_valid(m)',
               'float va,float vb,float dt,const ma_noise*noise){\n  if(!noise||!isfinite(noise->aa)||!isfinite(noise->ab)||!isfinite(noise->bb)||\n     noise->aa<=0||noise->bb<=0||noise->aa*noise->bb<=noise->ab*noise->ab)return MA_INVALID;\n  if(!ma_motor_valid(m)')
 s=once(s,'  const float y[2]={ia,ib};','  const float y[2]={ia,ib};\n  const float whiten=noise->ab/noise->aa;')
 guard=read(ROOT/'tools/observer_pair_noise_guard.inc')
 s=once(s,'  o->nis=0;',guard+'  o->nis=0;')
 s=once(s,'o->steps>300&&o->nis>50','o->steps>300&&(guard_nis>50||o->nis>50)')
 s=once(s,'    const float r=.0004f,s=cov[ch][ch]+r,e=y[ch]-o->x[ch];float gain[6];',
 '''    /* Whiten correlated measurement noise before sequential updates.
     * The second row is H=[-R_ab/R_aa,1], not a fictitious beta-only sample. */
    float ph[6],gain[6];
    for(unsigned i=0;i<6;++i)ph[i]=ch?cov[i][1]-whiten*cov[i][0]:cov[i][0];
    const float r=ch?noise->bb-whiten*noise->ab:noise->aa;
    const float s=(ch?ph[1]-whiten*ph[0]:ph[0])+r;
    const float e=ch?(y[1]-whiten*y[0])-(o->x[1]-whiten*o->x[0]):y[0]-o->x[0];''')
 s=once(s,'gain[i]=cov[i][ch]/s','gain[i]=ph[i]/s')
 s=once(s,'cov[i][j]-gain[i]*cov[ch][j]-gain[j]*cov[i][ch]+gain[i]*gain[j]*s',
               'cov[i][j]-gain[i]*ph[j]-gain[j]*ph[i]+gain[i]*gain[j]*s')
 at=s.index('static inline float ma_margin(')
 s=s[:at]+'''/* Historic caller/test compatibility: same diagonal observation model.
 * Production uses ma_observe_noise with actual16-frame pair composition. */
static inline int ma_observe(ma_observer*o,const ma_motor*m,float ia,float ib,
 float va,float vb,float dt){
 const ma_noise legacy={.0004f,0,.0004f};
 return ma_observe_noise(o,m,ia,ib,va,vb,dt,&legacy);
}
'''+s[at:];write(path,s)
 path=OUT/'nucleo/Inc/multi_native.h';s=read(path)
 s=once(s,'uint16_t ccr[3],arr,bus_v;}','uint16_t ccr[3],arr,bus_v;uint8_t pair,reserved;}')
 write(path,s)
 path=OUT/'nucleo/Src/current_shunt.c';s=read(path)
 s=once(s,' out->valid=ma_fast_sample.valid;', ' out->pair=ma_fast_sample.pair;out->reserved=0;\n out->valid=ma_fast_sample.valid;')
 s=once(s,' ma_fast_sample.zero=state.zero_ready;', ' ma_fast_sample.pair=pair;ma_fast_sample.reserved=0;\n ma_fast_sample.zero=state.zero_ready;')
 write(path,s)
 path=OUT/'nucleo/Inc/observer_current_window.h';s=read(path)
 s=once(s,'uint32_t center,end,first,count,previous_center;','uint32_t center,end,first,count,previous_center,pair_counts;')
 s=once(s,'uint32_t last,previous_center,first,middle,n;','uint32_t last,previous_center,first,middle,n,pair_counts;')
 s=once(s,'int ow_push(ow_state*s','int ow_push_pair(ow_state*s')
 s=once(s,'float ia,float ib,float va,float vb,ow_bin*out){','float ia,float ib,float va,float vb,ow_bin*out,uint8_t pair){')
 s=once(s,' if(!ticks||ticks>=max_gap',' if(pair>2U||!ticks||ticks>=max_gap')
 s=once(s,' s->sum_a+=ia;s->sum_b+=ib;',' s->sum_a+=ia;s->sum_b+=ib;s->pair_counts+=1U<<(5U*pair);')
 s=once(s,' out->previous_center=s->previous_center;',' out->previous_center=s->previous_center;out->pair_counts=s->pair_counts;s->pair_counts=0;')
 s=once(s,'#endif','''/* Legacy offline fixtures have an explicitly assumed U/V pair. */
static inline int ow_push(ow_state*s,uint32_t stamp,uint32_t gap,float ia,float ib,
 float va,float vb,ow_bin*out){return ow_push_pair(s,stamp,gap,ia,ib,va,vb,out,0);}
#endif''');write(path,s)
 path=OUT/'nucleo/Inc/observer_trace_core.h';s=read(path)
 s=once(s,'r->fpscr=od_fpscr();return 1;', 'r->fpscr=od_fpscr();r->result=0;return 1;')
 s=once(s,'r->result=(uint32_t)result;', 'r->result=(r->result&0xffffff00U)|(uint32_t)result;')
 s=once(s,'h->schema=4;','h->schema=5;')
 at=s.index('static inline void od_replay_commit(')
 s=s[:at]+'''static inline int od_replay_stage_pairs(od_capture*c,const ma_observer*o,const ma_motor*m,
 float ia,float ib,float va,float vb,float dt,uint32_t pairs){
 int staged=od_replay_stage(c,o,m,ia,ib,va,vb,dt);
 if(staged)c->blob.replay.result=pairs<<8;
 return staged;
}
'''+s[at:];write(path,s)
 path=OUT/'nucleo/Src/multi_native.c';s=read(path)
 at=s.index('static ma_observer observer;')
 s=s[:at]+'''/* Stable pointer ABI for exact offline replay of actual ARM/FMA code.
 * No hardware access, no inlining/cloning to a different hidden ABI. */
__attribute__((noinline,noclone,used)) int mic_observer_noise(uint32_t counts,ma_noise*r){
 return ma_pair_noise(counts,r);
}
__attribute__((noinline,noclone,used)) int mic_observer_step(ma_observer*o,
 const ma_motor*m,const float*input,const ma_noise*noise){
 return ma_observe_noise(o,m,input[0],input[1],input[2],input[3],input[4],noise);
}
'''+s[at:]
 s=once(s,'r.window_count=w->count;', 'r.window_count=w->count|(w->pair_counts<<8);')
 s=once(s,'p[2]=OD_WIRE;p[3]=4;', 'p[2]=OD_WIRE;p[3]=5;')
 s=once(s,'''  int replay_staged=od_replay_stage(&observer_trace,&observer,&model,window.ia,window.ib,va,vb,dt);
  int fault=ma_observe(&observer,&model,window.ia,window.ib,va,vb,dt);''',
 '''  ma_noise noise;
  if(!mic_observer_noise(window.pair_counts,&noise)){
    ma_fail_at(MA_INVALID,FT_OBSERVER,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
  const float input[5]={window.ia,window.ib,va,vb,dt};
  int replay_staged=od_replay_stage_pairs(&observer_trace,&observer,&model,window.ia,window.ib,va,vb,dt,window.pair_counts);
  int fault=mic_observer_step(&observer,&model,input,&noise);''')
 s=once(s,'window_ready=ow_push(&observer_window,','window_ready=ow_push_pair(&observer_window,')
 s=once(s,'actual_ia,actual_ib,applied_a,applied_b,&completed_window);',
               'actual_ia,actual_ib,applied_a,applied_b,&completed_window,sample.pair);')
 s=once(s,'const int wrc=ow_push(&window_probe,','const int wrc=ow_push_pair(&window_probe,')
 s=once(s,'fe_test_ia,fe_test_ib,av,bv,&window_result);','fe_test_ia,fe_test_ib,av,bv,&window_result,(uint8_t)(fe_case%3U));')
 s=once(s,'(void)ow_push(&fe_window_seed,','(void)ow_push_pair(&fe_window_seed,')
 s=once(s,'fe_test_ia,fe_test_ib,0,0,&discard);','fe_test_ia,fe_test_ib,0,0,&discard,(uint8_t)(fe_case%3U));')
 s=once(s,'''   int probe_stage=probe_capture?od_replay_stage(&observer_trace,&fe_test_observer,&model,
      fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f):0;
   int rc=ma_observe(&fe_test_observer,&model,fe_test_ia,fe_test_ib,
                    fe_test_out.va,fe_test_out.vb,.001f);''',
 '''   uint32_t probe_pairs=16U<<(5U*(fe_case%3U));ma_noise noise;
   int good_noise=mic_observer_noise(probe_pairs,&noise);
   int probe_stage=probe_capture?od_replay_stage_pairs(&observer_trace,&fe_test_observer,&model,
      fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f,probe_pairs):0;
   const float input[5]={fe_test_ia,fe_test_ib,fe_test_out.va,fe_test_out.vb,.001f};
   int rc=good_noise?mic_observer_step(&fe_test_observer,&model,input,&noise):MA_INVALID;''')
 write(path,s)
 for path in (OUT/'nucleo/Inc/observer_trace_wire.h',OUT/'UNOQ_MOTOR/observer_trace_wire.h'):
  write(path,read(path).replace('p[3]!=4','p[3]!=5').replace('odw_u32(r->data+4)!=4U','odw_u32(r->data+4)!=5U'))
 # Schema5 helper reconstructs R from exact packed16-pair counts. Schema4 keeps
 # its original diagonal-noise interpretation and standalone replay support.
 path=OUT/'web_hmi/server.py';s=read(path)
 s=once(s,'def decode_nis_replay(raw):','def decode_nis_replay(raw,schema=4):')
 s=once(s,"    post=struct.unpack_from('<49f3I',raw,248)","    post=list(struct.unpack_from('<49f3I',raw,248))\n    pairs=post[51]>>8 if schema>=5 else None\n    post[51]=post[51]&255 if schema>=5 else post[51]\n    counts=[(pairs>>(5*i))&31 for i in range(3)] if pairs is not None else None\n    if counts is not None and (pairs>>15 or sum(counts)!=16):raise ValueError('NIS pair counts')")
 s=once(s,"available=True,raw_hex=raw.hex(),prior_state=", "available=True,raw_hex=raw.hex(),pair_counts=counts,prior_state=")
 s=once(s,'    return dict(available=True,raw_hex=raw.hex(),pair_counts=counts,',
 '''    R=None
    if counts is not None:
        n0,n1,n2=counts;ra=.0004*(16+n2)/16;rb=.0004*(n0-n1)/(16*math.sqrt(3));rc=.0004*(5*(n0+n1)+2*n2)/48
        R=[[ra,rb],[rb,rc]]
    return dict(available=True,raw_hex=raw.hex(),pair_counts=counts,measurement_noise_A2=R,
        innovation_kind='sequential_R_whitened' if counts is not None else 'sequential_conditional',''')
 s=once(s,'(4,152,8,700,1888))','(4,152,8,700,1888),(5,152,8,700,1888))')
 s=once(s,'7 if schema==4 else 3','7 if schema>=4 else 3')
 s=once(s,'            if num!=16',"            if schema>=5:\n                if num>>23:raise ValueError('observer sample pair reserved bits')\n                pair_counts=[(num>>(8+5*i))&31 for i in range(3)];num&=255\n                if sum(pair_counts)!=16:raise ValueError('observer sample pair counts')\n                result['pair_counts']=pair_counts\n            if num!=16")
 s=once(s,'decode_nis_replay(raw[1432:1888]) if schema==4','decode_nis_replay(raw[1432:1888],schema) if schema>=4')
 # Innovations now whiten the off-diagonal measurement correlation.
 s=once(s,"        result.update(innovation_kind='sequential_conditional',", "        result.update(innovation_kind='sequential_conditional',")
 marker='        return result\n    rows=[sample('
 addition='''        if schema>=5:
            n0,n1,n2=result['pair_counts'];raa=.0004*(16+n2)/16
            rab=.0004*(n0-n1)/(16*math.sqrt(3));rbb=.0004*(5*(n0+n1)+2*n2)/48
            w=rab/raa
            result.update(measurement_noise_A2=[[raa,rab],[rab,rbb]],innovation_kind='sequential_R_whitened',
                whitening=w,conditional_predicted_current_A=None,
                conditional_predicted_measurement_A=[ia-u[26],ib-w*ia-u[27]])
        return result
    rows=[sample('''
 s=once(s,marker,addition);write(path,s)
 write(OUT/'manifest.json',json.dumps(dict(pair=NEW,base_pair=[2026111713,2026111714],schema=5,
  built=False,installed=False,hardware_commands=0,noise_phase_floor_A2=.0004,NIS_limits=[25,50],
  physical_noise_calibrated=False,physical_NIS_fix_proven=False,
  current_trip_A=1.35,OFF_budget_cycles=4000,estimate_age_ms=2,ADC_UPDATE_ticks=2048,
  full_RUN_existing_deadline_cycles=5312,observer_math_change='pair-aware R and exact sequential whitening only',
  target_timing_qualified=False,FOC_powered_test_approved=False),indent=2)+'\n')
 print('Prepared pair-noise candidate',NEW)


if __name__=='__main__':main()
