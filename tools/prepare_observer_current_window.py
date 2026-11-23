"""Offline candidate: coherent observer averaging, raw control/trips unchanged."""
import json,os,shutil
from prepare_standstill_commissioning import ROOT,read,write,once
from analyze_observer_nis import OUT,sha
BASE=ROOT/'artifacts/live_bench_20261116/clear_recovery_r1'
UNO=ROOT/'artifacts/live_bench_20261116/rpc_short_lock_r1'
HMI=ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1'
NEW=(2026111611,2026111612)
SOURCE=ROOT/'tools/observer_current_window'
def main():
    assert not (OUT/'preparation.json').exists(),'Never overwrite prepared firmware/evidence'
    for base in (BASE,UNO):
        for rel,h in json.loads(read(base/'source_hashes.json')).items():assert sha(base/rel)==h,rel
    for folder,base in [('nucleo',BASE),('UNOQ_MOTOR',UNO),('libraries',UNO),('web_hmi',HMI)]:
        def cp(src,dst):
            rel=os.path.relpath(src,base/folder).split(os.sep)
            if folder=='libraries' or folder=='nucleo' and rel[0] in ('Drivers','MCSDK_v6.4.2-Full'):
                if not os.path.exists(dst):os.link(src,dst)
                else:assert os.path.samefile(src,dst)
                return dst
            return shutil.copy2(src,dst)
        shutil.copytree(base/folder,OUT/folder,copy_function=cp,dirs_exist_ok=True,
            ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (OUT/folder).rglob('*'):
            if not f.is_file():continue
            s=read(f);t=s.replace('2026111605',str(NEW[0])).replace('2026111609',str(NEW[0])).replace('2026111606',str(NEW[1]))
            if t!=s:write(f,t)
    for name in ('observer_current_window.h','observer_forecast.h'):
        write(OUT/'nucleo/Inc'/name,read(SOURCE/name))
    f=OUT/'nucleo/Src/multi_native.c';s=read(f)
    s=once(s,'#include "observer_applied_voltage.h"','#include "observer_applied_voltage.h"\n#include "observer_current_window.h"\n#include "observer_forecast.h"')
    s=once(s,'static float sum_va,sum_vb;','static ow_state observer_window;\nstatic ow_bin bin_window;\nstatic uint32_t observer_center_cycles;')
    s=once(s,'static uint32_t voltage_n,start_cycles;','static uint32_t start_cycles;')
    s=s.replace('sum_va=sum_vb=0;voltage_n=0;',
        'ow_reset(&observer_window,estimate_cycles);observer_center_cycles=estimate_cycles;memset(&bin_window,0,sizeof(bin_window));')
    assert 'sum_va' in s # only obsolete accumulation below
    s=once(s,'float id,float iq,float idref,float iqref,float reference,float va,float vb,float dt,int fault,int published){',
        'float id,float iq,float idref,float iqref,float reference,float va,float vb,float dt,int fault,int published,const ow_bin*w){')
    s=once(s,' r.ia=ma_amps(s->counts[0]);r.ib=(r.ia+2.f*ma_amps(s->counts[1]))*.5773502692f;',
        ' r.ia=w->ia;r.ib=w->ib;\n r.observation_cycles=w->center;r.window_first_cycles=w->first;r.window_count=w->count;\n r.forecast_dt=(float)(w->end-w->center)/SystemCoreClock;')
    s=once(s,'  sample=bin_current;','  sample=bin_current;ow_bin window=bin_window;')
    s=once(s,'  const float dt=(float)(stamp-estimate_cycles)/SystemCoreClock;',
        '  const float dt=(float)(window.center-observer_center_cycles)/SystemCoreClock;')
    s=once(s,'  if(!sample.valid||!sample.zero||sample.cycles!=stamp)return;',
        '''  if(!sample.valid||!sample.zero||sample.cycles!=stamp||window.end!=stamp||window.count!=16U)return;
  /* A skipped completed window has lost its voltage history. Do not stretch
     the last1ms input over2ms, even when timestamp jitter falls below2ms. */
  if(window.previous_center!=observer_center_cycles){
    ma_fail_at(MA_STALE,FT_OBSERVER_DT,DWT->CYCCNT,&sample,estimate_cycles,stamp,0);return;}
''')
    s=once(s,'''  int fault=ma_observe(&observer,&model,ma_amps(sample.counts[0]),
    (ma_amps(sample.counts[0])+2.f*ma_amps(sample.counts[1]))*.5773502692f,va,vb,dt);''',
        '''  int fault=ma_observe(&observer,&model,window.ia,window.ib,va,vb,dt);
  float endpoint_estimate[6];
  if(!fault)fault=ow_forecast(&model,observer.x,window.tail_va,window.tail_vb,
    (float)(stamp-window.center)/SystemCoreClock,endpoint_estimate);''')
    s=once(s,'  int published=!fault&&ma_estimate_publish(observer.x,stamp);',
        '  int published=!fault&&ma_estimate_publish(endpoint_estimate,stamp);\n  if(!fault)observer_center_cycles=window.center;')
    s=once(s,'trace_ref,va,vb,dt,fault,published);','trace_ref,va,vb,dt,fault,published,&window);')
    s=once(s,'  if(!fault && voltage_fault)fault=voltage_fault;',
        '''  if(!fault && voltage_fault)fault=voltage_fault;
  ow_bin completed_window;int window_ready=0;
  /* Raw1.35A check above is never filtered. Include accumulator in deadline. */
  if(!fault){window_ready=ow_push(&observer_window,sample.cycles,SystemCoreClock*3U/16000U,
    actual_ia,actual_ib,applied_a,applied_b,&completed_window);
    if(window_ready<0)fault=MA_STALE;}''')
    a=s.index('  sum_va+=applied_a;');b=s.index('  return MC_NO_ERROR;',a)
    s=s[:a]+'''  if(window_ready){
    ++telemetry_seq;__DMB();bin_window=completed_window;
    bin_va=completed_window.va;bin_vb=completed_window.vb;
    bin_current=sample;bin_cycles=sample.cycles;
    bin_id=out.id_measured;bin_iq=out.iq_measured;bin_idref=out.id_ref;bin_iqref=out.iq_ref;bin_reference=reference_hz;
    bin_control_sequence=sample.sequence;bin_control_adc_cycles=sample.cycles;
    __DMB();++telemetry_seq;
  }
'''+s[b:]
    # Measure the worst (completed-window) branch in the existing OFF64 probe.
    s=once(s,'static volatile float fe_applied_a,fe_applied_b;',
        'static volatile float fe_applied_a,fe_applied_b;\nstatic ow_state fe_window_seed;')
    s=once(s,' fe_elapsed=DWT->CYCCNT-begin;',
        ''' ow_state window_probe=fe_window_seed;ow_bin window_result={0};
 const int wrc=ow_push(&window_probe,16U*10624U,31875U,
   fe_test_ia,fe_test_ib,av,bv,&window_result);
 if(wrc!=1&&!fe_rc)fe_rc=MA_STALE;
 fe_applied_a=window_result.va;fe_applied_b=window_result.vb;
 fe_elapsed=DWT->CYCCNT-begin;''')
    s=once(s,' __DMB();fe_pending=1;',
        '''  ow_reset(&fe_window_seed,0);ow_bin discard;
  for(unsigned n=1;n<16U;++n)(void)ow_push(&fe_window_seed,n*10624U,31875U,
    fe_test_ia,fe_test_ib,0,0,&discard);
  __DMB();fe_pending=1;''')
    s=once(s,'   uint32_t cycles=DWT->CYCCNT-begin;',
        '''   float probe_forecast[6]={0};
   if(!rc)rc=ow_forecast(&model,fe_test_observer.x,fe_test_out.va,fe_test_out.vb,.0005f,probe_forecast);
   fe_applied_a=probe_forecast[0];
   uint32_t cycles=DWT->CYCCNT-begin;''')
    s=s.replace('p[2]=OD_WIRE;p[3]=2;', 'p[2]=OD_WIRE;p[3]=3;').replace('OD_PAGES-1U?2U:', 'OD_PAGES-1U?28U:')
    assert 'sum_va' not in s and 'voltage_n' not in s
    write(f,s)
    f=OUT/'nucleo/Inc/observer_trace_core.h';s=read(f)
    s=s.replace('OD_CAPACITY=12,OD_STRIDE=455,OD_BYTES=1832','OD_CAPACITY=11,OD_STRIDE=500,OD_BYTES=1888')
    s=once(s,' uint32_t active_ccr[3],bus_arr;',
        ' uint32_t active_ccr[3],bus_arr;\n uint32_t observation_cycles,window_first_cycles,window_count;float forecast_dt;')
    s=s.replace('od_sample_136','od_sample_152').replace('sizeof(od_sample)==136','sizeof(od_sample)==152').replace('od_blob_1832','od_blob_1888').replace('h->schema=2','h->schema=3');write(f,s)
    for folder in ('nucleo/Inc','UNOQ_MOTOR'):
        f=OUT/folder/'observer_trace_wire.h';s=read(f)
        s=s.replace('OD_WIRE_BYTES=1832','OD_WIRE_BYTES=1888').replace('OD_PAGES=62','OD_PAGES=63').replace('OD_PAGES-1U?2U:', 'OD_PAGES-1U?28U:')
        s=s.replace('p[3]!=2','p[3]!=3').replace('data+4)!=2U','data+4)!=3U');write(f,s)
    f=OUT/'nucleo/Src/main.c';s=read(f);s=once(s,'page=(page+1U)%62U','page=(page+1U)%63U');write(f,s)
    write(OUT/'preparation.json',json.dumps(dict(pair=NEW,installed=False,hardware_commands=0,
        observer_noise_Q_R_unchanged=True,all_protection_limits_unchanged=True,
        physical_root_cause_fully_proven=False,target_timing_requalification_required=True),indent=2))
    print('Prepared OFFLINE source candidate',NEW)
if __name__=='__main__':main()
