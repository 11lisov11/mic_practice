"""Record the authorized current-trip trial; actual C kernel replay, GET only."""
import hashlib,json,math,subprocess,shutil,urllib.request
import prepare_foc_update_latency_fix as p
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def main():
 out=p.OUT/'powered_FOC_CPU_IRQ_20261030_r2';assert not (out/'analysis.json').exists()
 report=json.loads(p.read(out/'report.json'));s=report['after'];timing=s['foc_runtime'];fault=timing['first_fault']
 adc=json.loads(p.read(out/'ADC_peak_decoded.json'))
 assert report['start_commands']==report['clear_commands']==1 and not report['passed']
 assert report['runtime_record_received'] and report['ADC_record_received']
 assert s['state']=='SAFE' and s['pwm']==0 and fault['reason_code']==7 and fault['algorithm_fault']==2
 row=next(x for x in adc['samples'] if x['cycles']==fault['adc_cycles'])
 assert row['accepted_by_monitor'] and row['timer_cnt_at_update']==120
 assert not any(row[k] for k in ('three_leg_window_rejected','queue_overflow_observed','publish_deadline_missed','pending_epoch_mismatch','injected_queue_not_empty'))
 # Use the identical counts->SI operation and actual released ma_control.
 src=p.read(p.OUT/'nucleo/Src/multi_native.c')
 import re
 m=re.search(r'static inline float ma_amps\([^\n]+',src)
 if not m:m=re.search(r'static float ma_amps\([^\n]+',src)
 assert m,'actual ma_amps definition required'
 from test_foc_update_latency_fix import function
 scale_function=function(src,'ma_amps')
 cpp='''#include <cstdio>
#include "foc_experiment.h"
#include "parameters_conversion.h"
'''+scale_function+'''
int main(){
 const ma_motor model=FE_ESTIMATED_MOTOR;
 const float ia=ma_amps(-91),ib=(ma_amps(-91)+2.f*ma_amps(140))*.5773502692f;
 ma_controller c={};ma_output out={};float x[6]={};
 ma_geometry g={5312,5184,771,112,240,229};
 int rc=ma_control(&c,&model,x,&g,MA_FOC,ia,ib,.2f,325.f,1.f/16000,1,&out);
 printf("%d %.9g %.9g %.9g %.9g\\n",rc,ia,ib,hypotf(ia,ib),model.trip_current);
 return rc==MA_CURRENT?0:1;
}
'''
 # parameters_conversion pulls MCU-specific headers: extract only the three
 # exact conversion constants from the sealed application's parameters instead.
 inc=p.OUT/'nucleo/Inc'
 definitions=[]
 for name in ('ADC_REFERENCE_VOLTAGE','RSHUNT','AMPLIFICATION_GAIN'):
  found=[]
  for f in inc.glob('*.h'):
   matches=re.findall(r'^\s*#define\s+'+name+r'\s+([^\n]+)',p.read(f),re.M)
   found.extend(matches)
  assert found and all(v==found[0] for v in found),name
  definitions.append('#define '+name+' '+found[0])
 cpp=cpp.replace('#include "parameters_conversion.h"','\n'.join(definitions))
 file=out/'current_trip_replay.cpp';p.write(file,cpp);exe=file.with_suffix('.exe')
 build=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-I',str(inc),str(file),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'current_trip_replay_build.log',build.stdout+build.stderr);build.check_returncode()
 played=subprocess.run([str(exe)],capture_output=True,text=True,check=True);p.write(out/'current_trip_replay.log',played.stdout)
 rc,ia,ib,norm,threshold=map(float,played.stdout.split());assert rc==2 and norm>threshold
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}));token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
 for name,path in (('observed_after_analysis','/api/status'),('SD_after_decoded','/api/bkin-trace'),('SD_after_snapshots','/api/break-snapshot')):
  req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
  with op.open(req,timeout=8) as response:obj=json.load(response)
  assert obj['ok'];p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
 now=json.loads(p.read(out/'observed_after_analysis.json'))['data'];assert now['state']=='SAFE' and now['pwm']==0
 saved={}
 for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
  saved.update(json.loads(p.read(p.OUT/rel)))
 for rel,h in saved.items():assert sha(p.ROOT/rel)==h,rel
 pre=p.OUT/'powered_FOC_CPU_IRQ_20261030_r1'
 for rel,h in json.loads(p.read(pre/'saved_files_sha256.json')).items():assert sha(pre/rel)==h
 result=dict(completed_5s=False,pair=list(p.NEW),START=1,CLEAR=1,repeat_START=0,flash=0,RESET=0,
  outputs_off=True,physical_rotation_verified=False,trial_session_ms=s['run_elapsed_ms'],
  ADC_frames=adc['total_samples'],ADC_time_s_at16kHz=adc['total_samples']/16000,
  ADC_record_bytes=(out/'ADC_peak.bin').stat().st_size,ADC_record_sha256=sha(out/'ADC_peak.bin'),
  exact_reason='FT_CONTROL / MA_CURRENT',reason_code=7,algorithm_fault=2,
  MCSDK_mask=s['mc_fault_current_mask'],MCSDK_duration_mask_not_proof_of_timing_overrun=True,
  fast_max_cycles=s['algorithm_fast_cycles'],fast_limit_cycles=5312,
  fault_path_cycles=round(fault['fast_elapsed_us']*170),first_fault=fault,CPU_IRQ=timing,
  current_trip_reproduced_actual_C=True,nominal_i_alpha_A=ia,nominal_i_beta_A=ib,
  nominal_vector_magnitude_A=norm,current_trip_A=threshold,
  raw_fault_row=row,real_current_or_measurement_spike_not_resolved=True,
  current_scale_physically_qualified=False,ADC_guard2048_unchanged=True,
  full5s_UPDATE_fix_not_yet_qualified=True,
  update_at_fault_cnt=120,old_update_fault_not_seen_before_current_stop=True,
  old_files_preserved=len(saved),new_SD_Break_observed=False,
  next_step='Analyze single accepted current spike and ADC regular/injected interaction from saved data. No new START/CLEAR/flash without a concrete verified change.')
 p.write(out/'analysis.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 p.write(out/'saved_files_sha256.json',json.dumps({f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
 manifest=json.loads(p.read(p.OUT/'manifest.json'));manifest.update(powered_trial_attempted=True,powered_5s_completed=False,
  powered_reason='MA_CURRENT',powered_first_fault_reason=7,powered_observer_steps=130,
  start_commands=1,clear_commands=1,powered_trial_report='powered_FOC_CPU_IRQ_20261030_r2/analysis.json')
 p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
 f=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(f);idx=old.index('## 2026-10-30:')
 note=('## 2026-10-30:3003/3004одинCLEAR/START;раннийMA_CURRENT,ШИМOFF\n\n'
  'Poweredr1START0/CLEAR0:при325ВсохранилсяMC_UNDER_VOLT4. Пользовательявно\n'
  'разрешилодинCLEARиодинпускприготовыхзащитах. Poweredr2CLEAR1/START1,\n'
  'послеCLEARзащитыготовы;5секНЕпройдены. SAFE/PWM0/run_id1,сеанс188мс,\n'
  '2098ADCкадров~0,131с,полный1024байт/35страницполучен,наблюдатель130шагов.\n'
  'Причинаfirstreason7FT_CONTROL/algorithm2MA_CURRENT,НЕMA_STALE. MCSDKмаска1\n'
  'здесьизобщегокодавозвратаMC_DURATION,НЕдоказательстводедлайна. Fastmax4798<5312,\n'
  'faultpath2655тактов. ADCage32,159мкс,estimate999,912мкс,sampleflags7,\n'
  'причинныйADCsequence2097,cycles4161026805,UPDATECNT120<2048,окно/очередь/epochOK.\n'
  f'CountsU/V/W=-91/140/-49,номинальныйвектор{norm:.6f}А>порога{threshold:.6f}А,\n'
  'реальныйCрегуляторвоспроизвёлMA_CURRENT. ЭтоНЕдоказательствореальноготока:\n'
  'масштабнеквалифицирован,одиночныйскачокАЦПещёнужноразобрать. ADC1ISR111\n'
  'против107передним:естьфлагEOCрегулярнойгруппы,причиннаясвязьНЕдоказана.\n'
  'CPU_IRQlastwall509,241/IRQ391,071/CPUupper118,171мкс;maxwall625,788,\n'
  'maxIRQ495,335,maxCPU209,6(разныемаксимумынескладывать),metererrors0.\n'
  'SDHIGH/BIE/config_ok,новогоBreakнет,UART/hardware/transport/RPC0.1007старых\n'
  'файловсохранены+poweredr1. 2048итоковый1,35А/защитыпрежние.\n'
  'ПолноеустранениепозднегоUPDATEна5секНЕподтверждено:этотпусккороче.\n'
  'Питаниепользовательнеменял:J1ON/15ВON/повербанки/PCиSaleaeOFF.\n'
  'РазрешённыеCLEARиSTARTизрасходованы;повторов/сбросов/прошивкинебыло.\n'
  'Далееанализтоковогоскачка/совместнойработыregular-injectedADCпоимеющейсязаписи.\n'
  'Отчёт:foc_update_latency_fix_r1/powered_FOC_CPU_IRQ_20261030_r2/analysis.json.\n\n')
 p.write(f,old[:idx]+note+old[idx:])
 print(json.dumps(dict(completed_5s=False,START=1,CLEAR=1,outputs_off=True,
  reason='MA_CURRENT',actual_C_replay=True,nominal_vector_A=norm,threshold_A=threshold,
  update_CNT=120,fast_max_cycles=4798,old_files_preserved=len(saved))))
if __name__=='__main__':main()
