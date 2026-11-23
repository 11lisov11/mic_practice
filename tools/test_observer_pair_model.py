"""Same independent flux/inverter plant and actual two-channel ADC for both variants."""
import json,subprocess
from test_foc_estimate_publish_fix import native_source
from test_observer_current_window import compile_case
import prepare_observer_pair_noise as p


def main():
 out=p.OUT/'verification'
 template=p.read(p.ROOT/'artifacts/live_bench_20261117/remaining_nis_offline_r1/independent_inverter.cpp')
 pre=template.split('#define MIC_NATIVE_BUILD',1)[0]
 tail=template[template.index('#undef ma_observe'):]
 begin=tail.index(' float amp=');end=tail.index(' int rc=ma_native_fast(reference);',begin)
 tail=tail[:begin]+r'''
 float amp=(float)(ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN));
 unsigned pair=timer.CCR1>=timer.CCR2&&timer.CCR1>=timer.CCR3?2:timer.CCR2>=timer.CCR3?1:0;
 unsigned first=pair==2?1:0,second=pair==0?1:2,third=3-first-second;
 double sensed_phases[3]={a,-.5*a+.8660254037844386*b,-.5*a-.8660254037844386*b};
 sample={};sample.zero=1;sample.valid=frames>0;sample.cycles=cycle.CYCCNT-4000;sample.sequence=++frames;
 double gain=scenario==18?.9:scenario==19?1.1:1.;
 int n0=0,n1=0;
 if(scenario==4){n0=(int)(frames%3)-1;n1=(int)((frames+1)%3)-1;}
 if(scenario==5){n0=(int)(((frames*1103515245U+12345U)>>16)%33)-16;n1=(int)(((frames*1664525U+1013904223U)>>16)%33)-16;}
 if(scenario==16)n0+=8;
 sample.counts[first]=(int16_t)(lround(sensed_phases[first]*gain/amp)+n0);
 sample.counts[second]=(int16_t)(lround(sensed_phases[second]*gain/amp)+n1);
 sample.counts[third]=-sample.counts[first]-sample.counts[second];
 if(scenario==17){sample.counts[0]=150;sample.counts[1]=-75;sample.counts[2]=-75;}
 sample.arr=timer.ARR;sample.bus_v=fake_bus;
 sample.ccr[0]=timer.CCR1;sample.ccr[1]=timer.CCR2;sample.ccr[2]=timer.CCR3;
#ifdef PAIR_NOISE_CANDIDATE
 sample.pair=(uint8_t)pair;
#endif
 float reference=(float)fmin(5.,5.*(next_irq-origin)/170000000.);
''' +tail[end:]
 results={}
 cases=[(0,'nominal'),(1,'Rs_plus20pct'),(2,'Rr_plus20pct'),(3,'Lm_minus5pct'),(4,'ADC_1count'),(5,'ADC_16counts'),
        (8,'device_drop_0_5V'),(9,'device_drop_1V'),(10,'device_drop_1_5V'),(11,'device_drop_2V'),
        (12,'deadtime_plus0_25us'),(13,'deadtime_plus0_50us'),(14,'deadtime_minus0_25us'),
        (15,'device_Ron_1ohm'),(16,'channel_offset_8counts'),(17,'raw_overcurrent'),
        (18,'current_gain_minus10pct'),(19,'current_gain_plus10pct')]
 for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
  extra='';this_tail=tail
  if label=='candidate':
   extra='#define PAIR_NOISE_CANDIDATE 1\n'
   extra_pre='''
static int host_observe_noise(ma_observer*,const ma_motor*,float,float,float,float,float,const ma_noise*);
#define ma_observe_noise host_observe_noise
'''
   prefix=pre+extra_pre
   this_tail='#undef ma_observe_noise\n'+this_tail
   this_tail=this_tail.replace('static void host_publication_irq(){', '''
static int host_observe_noise(ma_observer*o,const ma_motor*m,float a,float b,float va,float vb,float dt,const ma_noise*n){
 assert(!observing);observing=true;int rc=ma_observe_noise(o,m,a,b,va,vb,dt,n);++observer_calls;
 advance(sim_now+wall_cycles);observing=false;return rc;
}
static void host_publication_irq(){''')
  else:prefix=pre
  exe=compile_case(out,'pair_plant_'+label,extra+prefix+native_source(folder)+'\n'+this_tail,folder)
  results[label]=[]
  for scenario,name in cases:
   r=subprocess.run([str(exe),'95737','17000',str(scenario),str(out/(label+'_'+name+'.bin'))],capture_output=True,text=True,check=True)
   results[label].append(dict(case=name,**json.loads(r.stdout)))
  r=subprocess.run([str(exe),'357000','0','0',str(out/(label+'_stale.bin'))],capture_output=True,text=True,check=True)
  results[label].append(dict(case='observer_2_1ms',**json.loads(r.stdout)))
 c=results['candidate'];assert c[0]['completed_5s'] and c[0]['native_valid_fraction_after1s']>.99
 assert c[15]['fault']==2 and not c[15]['completed_5s']
 assert c[-1]['fault']==3 and not c[-1]['completed_5s']
 report=dict(passed=True,hardware_commands=0,results=results,actual_ADC_two_selected_channels=True,
  raw_trip_A=1.35,estimate_age_limit_ms=2,Q_unchanged=True,phase_R_floor_A2=.0004,
  thresholds_unchanged=True,target_timing_measured=False,wall_cycles_assumed=95737,
  qualification='independent synthetic plant scenarios only; not a replay of physical full history')
 (out/'pair_model_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 for b,c in zip(results['baseline'],results['candidate']):
  print(b['case'],'NIS',round(b['peak_NIS'],2),'->',round(c['peak_NIS'],2),
        'valid',round(b['native_valid_fraction_after1s'],3),'->',round(c['native_valid_fraction_after1s'],3),
        'fault',b['fault'],'->',c['fault'])


if __name__=='__main__':main()
