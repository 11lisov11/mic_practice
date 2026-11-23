import ast,json,hashlib,subprocess,shutil,unittest
from pathlib import Path
import prepare_standstill_commissioning as p
from audit_production_pwm_filters import function

class Commissioning(unittest.TestCase):
 def test_actual_native_driver_capture_and_uart(self):
  # Reuse only the established fake peripheral surface. Compile the actual NEW
  # C driver and actual protocol parsers; no Python implementation of its logic.
  tree=ast.parse(p.read(p.ROOT/'tools/test_multi_algorithm.py'))
  method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='test_native_adapter_and_wire_actual_c')
  assign=next(n for n in method.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='pre' for t in n.targets))
  pre=ast.literal_eval(assign.value)+r'''
#include "identify_core.h"
#include "identify_wire.h"
static int PWM_ParamsM1,off_calls;
static void PWM_SwitchOffPWM(int*){timer.BDTR=0;++off_calls;}
'''
  src='\n'.join(line for line in p.read(p.OUT/'nucleo/Src/multi_native.c').splitlines() if not line.startswith(('#include','#pragma')))
  checks=r'''
static void config(uint8_t*p,unsigned op,unsigned index,uint32_t value){
 memset(p,0,UV3_FRAME);p[4]=8;p[6]=(uint8_t)op;p[7]=(uint8_t)index;memcpy(p+8,&value,4);p[12]=1;p[13]=0xA6;
}
int main(){
 uint8_t pkt[UV3_FRAME];xp_receiver caps={};ma_native_diag(pkt,2026102932);
 assert(xp_receive(&caps,pkt,2026102932,true,0)&&caps.caps==15&&caps.qualification==0);
 mi_config cfg={77,MI_DC,0,0,.1f,12.23f,3000,1,{0,0,0},.025f,{0,0},0};
 auto stage=[&](){for(unsigned i=0;i<15;i++){uint32_t raw;memcpy(&raw,(uint8_t*)&cfg+4*i,4);config(pkt,4,i,raw);assert(ma_native_config(pkt));}};
 stage();config(pkt,5,0,123);assert(!ma_native_config(pkt));
 uint32_t cfg_crc=uv3_crc32c((uint8_t*)&cfg,sizeof(cfg));config(pkt,5,0,cfg_crc);assert(ma_native_config(pkt));
 config(pkt,3,4,0);assert(ma_native_config(pkt));assert(!profile_ready&&qualification==0);
 assert(ma_native_request(4));assert(!ma_native_prepare());sample.zero=1;assert(ma_native_prepare());
 ma_id_status(pkt,2026102932);id_meta meta={};assert(id_receive_status(&meta,pkt,2026102932,true,10));
 assert(meta.config_crc==cfg_crc&&id_execution_allowed(&meta,11,cfg_crc,false,5000));
 assert(!id_execution_allowed(&meta,11,0,false,5000));assert(!id_execution_allowed(&meta,11,cfg_crc,true,5000));
 assert(!id_execution_allowed(&meta,11,cfg_crc,false,3000));assert(!id_execution_allowed(&meta,1510,cfg_crc,false,5000));
 timer.BDTR=1;ma_native_service();assert(!running); // main cannot consume the first-IRQ priming transition
 sample.valid=0;assert(ma_native_fast(5)==MC_NO_ERROR&&running&&!id_state.active);
 sample.valid=1;sample.bus_v=320;sample.arr=5312;sample.epoch=1;sample.cycles=cycle.CYCCNT-100;
 for(unsigned i=0;i<3;i++)sample.ccr[i]=2656;
 assert(ma_native_fast(5)==MC_NO_ERROR);assert(id_state.active&&!off_calls);
 config(pkt,4,0,99);assert(!ma_native_config(pkt));
 // Completion calls only the same public MCSDK switch-OFF primitive as V/f.
 cycle.CYCCNT=id_state.start+SystemCoreClock*3U+1000;sample.cycles=cycle.CYCCNT-100;sample.epoch++;
 assert(ma_native_fast(5)==MC_NO_ERROR&&off_calls==1&&!timer.BDTR);
 assert(ma_native_complete());ma_native_service();assert(id_state.ready&&!id_state.active);
 id_blob blob={};for(int page=MI_PAGES-1;page>=0;page--){
  assert(ma_id_page(pkt,2026102932,(unsigned)page));
  assert(id_receive_page(&blob,pkt,2026102932,true));
 }
 assert(blob.complete&&memcmp(blob.bytes,id_state.bytes,MI_BYTES)==0);
 assert(!id_receive_page(&blob,pkt,2026102922,true));
 pkt[20]^=1;assert(!id_receive_page(&blob,pkt,2026102932,true));
 assert(ma_id_page(pkt,2026102932,MI_PAGES-1));pkt[37]=1;uv3_seal(pkt);assert(!id_receive_page(&blob,pkt,2026102932,true));
 uint32_t saved_crc=id_state.crc;config(pkt,6,0,saved_crc^1);assert(!ma_native_config(pkt)&&id_state.ready);
 config(pkt,6,0,saved_crc);assert(ma_native_config(pkt)&&!id_state.ready&&!id_configured);
 assert(!ma_native_request(2)); // identification does NOT qualify FOC
 stage();config(pkt,5,0,cfg_crc);assert(!ma_native_config(pkt)); // old run identity cannot be replayed
 assert(!profile_ready&&qualification==0);
}
'''
  out=p.OUT/'verification';out.mkdir(exist_ok=True);unit=out/'native.cpp';p.write(unit,pre+src+checks);exe=unit.with_suffix('.exe')
  b=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
    '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True)
  p.write(out/'native_compile.log',b.stdout+b.stderr);b.check_returncode();subprocess.run([str(exe)],check=True)
 def test_existing_protections_and_adcs_preserved(self):
  for rel in ['Inc/drive_parameters.h','Inc/power_stage_parameters.h','Inc/current_core.h','Inc/current_adc_window_plan.h',
    'Inc/current_adc_deadline.h','Src/stm32g4xx_hal_msp.c','Src/stm32g4xx_mc_it.c']:
   self.assertEqual((p.OUT/'nucleo'/rel).read_bytes(),(p.BASE/'nucleo'/rel).read_bytes(),rel)
  a=p.read(p.BASE/'nucleo/Src/main.c');b=p.read(p.OUT/'nucleo/Src/main.c')
  for name in ('MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_rearm_break_irq','uno_latch_fault','uno_clear_frame_is_safe','uno_update_softstart_state','uno_link_poll'):
   self.assertEqual(function(a,name).replace('2026102922','2026102932'),function(b,name),name)
  a=p.read(p.BASE/'nucleo/Src/current_shunt.c');b=p.read(p.OUT/'nucleo/Src/current_shunt.c')
  self.assertEqual(function(a,'mic_current_adc_irq').replace('ma_publish_current(cycles0,epoch0,eligible,a,b);',
    'ma_publish_current(cycles0,epoch0,eligible,a,b,current_ccr,bus);'),function(b,'mic_current_adc_irq'))
  core=p.read(p.OUT/'nucleo/Inc/identify_core.h')
  for forbidden in ('EnableAllOutputs','MC_StartMotor','AcknowledgeFault','->BDTR','->CCER','->CCR1'):
   self.assertNotIn(forbidden,core)
 def test_missing_current_response_is_rejected_at_one_hz_and_dc(self):
  out=p.OUT/'verification';out.mkdir(exist_ok=True);unit=out/'no_response.cpp'
  p.write(unit,r'''
#include "identify_core.h"
#include <cassert>
int main(){
 ma_geometry g={5312,5184,771,112,240,229};ma_output output;
 for(unsigned kind=MI_DC;kind<=MI_AC;kind++){
  mi_state state={};mi_config cfg={88,kind,kind==MI_AC?1.f:0.f,0,.1f,12.23f,8000,1,{0,0,0},.025f,{0,0},0};
  cfg.calibration_crc=mi_cal_crc(&cfg);assert(mi_begin(&state,&cfg,0));
  int result=MI_OK;unsigned n=0;
  for(;n<70000&&result==MI_OK;n++){
   mi_sample sample={};sample.valid=1;sample.bus=320;sample.arr=5312;sample.epoch=n;
   sample.cycles=n*10624;for(unsigned i=0;i<3;i++)sample.ccr[i]=2656;
   result=mi_step(&state,&g,&sample,sample.cycles,170000000,&output);
  }
  assert(result==MI_NO_RESPONSE&&!state.active&&!output.valid);
  assert(n<(kind==MI_DC?22000U:50000U));
 }
}
''')
  exe=unit.with_suffix('.exe');subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
   '-I',str(p.OUT/'nucleo/Inc'),str(unit),'-o',str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
 def test_powered_starts_still_require_all_original_hmi_checks(self):
  def methods(path):
   source=p.read(path).replace('''                if run_ok and identification_point_complete(candidate,initial_status):
                    self.hv_arm.disarm()
                    return True,"Native identification completed before HTTP response",candidate
''','')
   t=ast.parse(source);c=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
   return {n.name:ast.dump(n,include_attributes=False) for n in c.body if isinstance(n,ast.FunctionDef)}
  a=methods(p.BASE/'web_hmi/server.py');b=methods(p.OUT/'web_hmi/server.py')
  for name in ('start_sequence','_start_without_precharge','stop_sequence','operator_heartbeat_fresh'):
   self.assertEqual(a[name].replace('2026102921','2026102931').replace('2026102922','2026102932'),b[name],name)
 def test_late_http_success_requires_native_stopped_capture_and_fault_free_matching_run(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('id_hmi_completion',p.ROOT/'tools/motor_commissioning/hmi_completion.py')
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  initial=dict(algorithm_selected=4,id_config_crc=123,id_run_id=77,run_id=1,id_duration_ms=3000)
  status=dict(initial,fw_build=2026102931,mc_fw_build=2026102932,state='SAFE',pwm=0,bp_status=0,
    mc_age_ms=30,id_valid=1,estop=0,mc_fault_current_mask=0,mc_fault_occurred_mask=0,
    mc_transport_fault=0,id_fault=0,id_flags=13,id_result_crc=444,run_id=2,run_elapsed_ms=3300)
  self.assertTrue(m.identification_point_complete(status,initial))
  for change in ({'pwm':1},{'mc_fault_current_mask':4},{'mc_transport_fault':7},{'id_fault':2},{'run_id':1},
    {'id_config_crc':124},{'run_elapsed_ms':1},{'mc_age_ms':301},{'id_flags':1},{'id_result_crc':0}):
   self.assertFalse(m.identification_point_complete(dict(status,**change),initial),change)
 def test_actual_http_capture_route_is_readonly_and_rejects_running_or_changed_record(self):
  import importlib.util,threading
  from types import SimpleNamespace
  spec=importlib.util.spec_from_file_location('commissioning_capture_route',p.OUT/'web_hmi/server.py')
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  status=dict(pwm=0,state='SAFE',id_complete=1,id_result_crc=123,id_run_id=77,id_view_page=0,id_page_hex='00'*128)
  calls=[];replies=[]
  app=SimpleNamespace(control_lock=threading.RLock(),rpc=SimpleNamespace(
   get=lambda:(True,dict(status),None),cmd=lambda cmd:(calls.append(cmd) or True,None)))
  fake=SimpleNamespace(path='/api/identification?page=0',server=SimpleNamespace(app=app),
   _require_control_access=lambda **kw:True,_send_json=lambda data,code=200:replies.append((data,code)))
  for patch in ({'pwm':1},{'state':'VF_RUN'},{'id_complete':0}):
   old=dict(status);status.update(patch);m.Handler.do_GET(fake)
   self.assertEqual(replies[-1][1],409);self.assertFalse(calls);status.clear();status.update(old)
  m.Handler.do_GET(fake)
  self.assertEqual(calls,['IDENT PAGE 0']);self.assertEqual(replies[-1][0]['hex'],'00'*128)
  calls.clear();count=[0]
  def changed():
   count[0]+=1;return True,dict(status,id_result_crc=123 if count[0]==1 else 124),None
  app.rpc.get=changed;m.Handler.do_GET(fake)
  self.assertEqual(replies[-1][1],409);self.assertEqual(calls,['IDENT PAGE 0'])
if __name__=='__main__':unittest.main()
