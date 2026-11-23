import ast,hashlib,importlib.util,json,shutil,subprocess,tempfile,unittest
from pathlib import Path
from prepare_multi_algorithm import ROOT,BASE,OUT,NEW,read,write
from audit_production_pwm_filters import function

class Multi(unittest.TestCase):
    def test_native_adapter_and_wire_actual_c(self):
        pre=r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include "multi_native.h"
#include "motor_control.h"
#include "uart_v3_transport.h"
#include "research_wire.h"
#include "multi_command.h"
struct Timer{uint32_t ARR=5312,CCR1=100,CCR2=200,CCR3=300,BDTR=0;};
static Timer timer;static Timer*TIM1=&timer;
struct Cycle{uint32_t CYCCNT=1000;};static Cycle cycle;static Cycle*DWT=&cycle;
static uint32_t SystemCoreClock=170000000;
static int motor_state=0;enum{IDLE=0,MC_NO_ERROR=0,MC_SW_ERROR=128,MC_DURATION=1};
static int MC_GetSTMStateMotor1(){return motor_state;}
static int LL_TIM_IsEnabledAllOutputs(Timer*t){return t->BDTR!=0;}
struct Bus{int _Super;};static Bus BusVoltageSensor_M1;
static uint16_t VBS_GetAvBusVoltage_V(int*){return 320;}
static void __DMB(){}
#define TW_AFTER 484
#define TNOISE 255
#define DEADTIME_NS 1350
#define ADV_TIM_CLK_MHz 170
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f
static ma_current_sample sample={};
static int sample_coherent=1;
int mic_current_fast(ma_current_sample*out){*out=sample;return sample_coherent;}
'''
        body='\n'.join(line for line in read(OUT/'nucleo/Src/multi_native.c').splitlines()
                       if not line.startswith(('#include','#pragma')))
        checks=r'''
static void config(uint8_t*p,unsigned op,unsigned index,uint32_t value){
 memset(p,0,UV3_FRAME);p[4]=8;p[6]=(uint8_t)op;p[7]=(uint8_t)index;
 memcpy(p+8,&value,4);p[12]=1;p[13]=0xA6;
}
int main(){
 assert(fabs(ma_amps(100)-.959358f)<.00001f);
 for(unsigned a=0;a<4;a++)assert(ma_wire_mode(a)==(a==1?3:a==2?6:a==3?7:0));
 for(unsigned mask=0;mask<32;mask++){
   assert(bool(ma_config_allowed(mask&1,mask&2,mask&4,mask&8,mask&16))==((mask&15)==0&&bool(mask&16)));
   assert(bool(ma_config_cancel(mask&1,mask&2,mask&4,mask&8,mask&16))==((mask&15)!=0||!(mask&16)));
 }
 uint8_t command[UV3_FRAME];memset(command,0xFF,sizeof(command));command[2]=3;command[5]=29;
 ma_config_encode(command,1,4,0x12345678);assert(command[2]==3&&command[3]==0&&command[4]==8&&command[5]==29);
 for(unsigned i=14;i<39;i++)assert(!command[i]);
 uint8_t p[UV3_FRAME];ma_native_diag(p,2026102922U);xp_receiver rx={};
 assert(xp_receive(&rx,p,2026102922U,true,10));assert(rx.caps==7&&rx.selected==1&&!rx.profile_ready);
 assert(!xp_fresh(&rx,true,2510));assert(!xp_receive(&rx,p,2026102912U,true,12));
 for(unsigned i=0;i<UV3_FRAME;i++){p[i]^=1;assert(!xp_receive(&rx,p,2026102922U,true,12));p[i]^=1;}
 config(p,3,2,0);assert(ma_native_config(p));assert(ma_native_selected()==2);
 assert(!ma_native_request(2));assert(ma_native_fast(5)==MC_SW_ERROR&&timer.CCR1==100);
 config(p,1,13,0);assert(!ma_native_config(p));
 ma_motor m={12.23f,10,.9f,.9f,.84f,.0003f,.00015f,1,.35f,1.1f,1.35f,400,12};
 for(unsigned i=0;i<13;i++){uint32_t v;memcpy(&v,(uint8_t*)&m+4*i,4);config(p,1,i,v);assert(ma_native_config(p));}
 config(p,2,0,123);assert(!ma_native_config(p));
 config(p,2,0,uv3_crc32c((uint8_t*)&m,sizeof(m)));assert(ma_native_config(p));assert(!ma_native_request(2));
 // Qualification=7 here is a HOST FIXTURE assertion, not hardware evidence.
 for(unsigned i=0;i<13;i++){uint32_t v;memcpy(&v,(uint8_t*)&m+4*i,4);config(p,1,i,v);assert(ma_native_config(p));}
 config(p,2,7,uv3_crc32c((uint8_t*)&m,sizeof(m)));assert(ma_native_config(p));
 assert(ma_native_request(2));assert(ma_native_prepare());
 timer.BDTR=1;sample.zero=1;sample.valid=0;sample.cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR&&timer.CCR1==timer.ARR/2);
 assert(!ma_native_request(3));config(p,3,3,0);assert(!ma_native_config(p));
 sample.valid=1;sample.counts[0]=20;sample.counts[1]=-10;cycle.CYCCNT+=10625;sample.cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR);
 estimate_seq|=1;sample_coherent=0;cycle.CYCCNT+=10625;
 assert(ma_native_fast(5)==MC_NO_ERROR); // preempted writers never cause a spin or false fault
 estimate_seq++;sample_coherent=1;
 const auto ccr=timer.CCR1;
 cycle.CYCCNT+=1700000;assert(ma_native_fast(5)!=MC_NO_ERROR&&timer.CCR1==ccr);
 assert(first_fault==MA_STALE);timer.BDTR=0;ma_native_service();assert(ma_native_prepare());
 assert(first_fault==MA_STALE&&run_fault==0); // retain first failure across reset of controller state
 motor_state=1;assert(!ma_native_prepare());motor_state=IDLE;
 ma_native_diag(p,2026102922U);assert(xp_receive(&rx,p,2026102922U,true,50));
 assert(rx.profile_crc==uv3_crc32c((uint8_t*)&m,sizeof(m)));
}
'''
        dest=OUT/'host_tests';dest.mkdir(exist_ok=True)
        source=dest/'native_fixture.cpp';write(source,pre+body+checks);exe=source.with_suffix('.exe')
        subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                        '-I',str(OUT/'nucleo/Inc'),'-I',str(OUT/'UNOQ_MOTOR'),str(source),'-o',str(exe)],check=True,capture_output=True)
        subprocess.run([str(exe)],check=True)

    def test_actual_c_on_independent_plant(self):
        dest=OUT/'model';dest.mkdir(exist_ok=True);exe=dest/'test.exe'
        subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
          '-I',str(OUT/'nucleo/Inc'),str(ROOT/'tools/multi_algorithm/model_test.cpp'),'-o',str(exe)],check=True,capture_output=True)
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        write(dest/'report.json',json.dumps(dict(passed=result.returncode==0,scenarios=rows,
          plant='independent double-precision flux-state RK4, averaged inverter with nominal deadtime',
          controller='actual float C from target header',model_parameters='SIMULATION PRIORS, not motor identification',
          hardware_evidence=False,switching_ring_and_common_mode_not_modelled=True),indent=2))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(len(rows),8)

    def test_original_protections_and_adc_geometry_preserved(self):
        for rel in ['Inc/current_adc_window_plan.h','Inc/current_adc_deadline.h','Inc/current_core.h',
          'Inc/drive_parameters.h','Inc/power_stage_parameters.h','Src/stm32g4xx_mc_it.c','Src/stm32g4xx_hal_msp.c']:
            self.assertEqual((BASE/'nucleo'/rel).read_bytes(),(OUT/'nucleo'/rel).read_bytes(),rel)
        old=read(BASE/'nucleo/Src/main.c');new=read(OUT/'nucleo/Src/main.c')
        for name in ['MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_clear_frame_is_safe','uno_latch_fault',
                     'uno_stop_motor','uno_rearm_break_irq','uno_update_softstart_state','mic_local_stop_blocked','uno_link_poll']:
            self.assertEqual(function(old,name).replace('2026102912','2026102922'),function(new,name),name)
        old=read(BASE/'nucleo/Src/current_shunt.c');new=read(OUT/'nucleo/Src/current_shunt.c')
        added='  ma_publish_current(cycles0,epoch0,eligible,a,b);\n'
        self.assertEqual(function(old,'mic_current_adc_irq'),function(new,'mic_current_adc_irq').replace(added,''))
        old=read(BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino');new=read(OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
        self.assertEqual(function(old,'control_step'),function(new,'control_step'))
        native=read(OUT/'nucleo/Src/multi_native.c')
        for forbidden in ['EnableAllOutputs','DisableIT_BRK','->BDTR=','->CCER=','MC_StartMotor','MC_AcknowledgeFault']:
            self.assertNotIn(forbidden,native)
        self.assertLess(native.index('if(fault||elapsed>'),native.index('TIM1->CCR1=out.ccr'))

    def test_hmi_algorithm_gate_and_existing_start_guards(self):
        def load(path):
            spec=importlib.util.spec_from_file_location('multi_hmi_test',path)
            m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
        m=load(OUT/'web_hmi/server.py')
        d=dict(fw_build=NEW[0],mc_fw_build=NEW[1],research_native_valid=1,research_native_caps=7,
               algorithm_selected=2,algorithm_qualification=0)
        q=m.with_research_suite(d)
        self.assertEqual(q['research_actuator_algorithm'],'FOC_FIXED')
        self.assertEqual([r['id'] for r in q['research_algorithms'] if r['hardware_ready']],['VF_FIXED'])
        d['algorithm_qualification']=7
        self.assertEqual(len([r for r in m.research_catalog(d) if r['hardware_ready']]),3)
        def methods(p):
            tree=ast.parse(read(p));cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
        a=methods(BASE/'web_hmi/server.py');b=methods(OUT/'web_hmi/server.py')
        for name in ['start_sequence','stop_sequence','_start_without_precharge','operator_heartbeat_fresh']:
            self.assertEqual(a[name].replace('2026102911','2026102921').replace('2026102912','2026102922'),b[name],name)

    def test_actual_http_algorithm_route_never_starts_and_rejects_running_stale_wrong_peer(self):
        from types import SimpleNamespace
        import threading
        spec=importlib.util.spec_from_file_location('multi_route_test',OUT/'web_hmi/server.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        status=dict(fw_build=NEW[0],mc_fw_build=NEW[1],research_native_caps=7,research_native_valid=1,
                    pwm=0,state='SAFE',mc_age_ms=20)
        calls=[];responses=[]
        app=SimpleNamespace(control_lock=threading.RLock(),logs=SimpleNamespace(add=lambda line:None),
             rpc=SimpleNamespace(get=lambda:(True,status,None),cmd=lambda cmd:(calls.append(cmd) or True,None)))
        fake=SimpleNamespace(path='/api/algorithm',server=SimpleNamespace(app=app),_require_control_access=lambda:True,
             _read_json=lambda:{'algorithm':2},_send_json=lambda data,code:responses.append((data,code)))
        for patch in ({'pwm':1},{'state':'FOC_RUN'},{'mc_age_ms':301},{'research_native_caps':1},{'fw_build':2026102911}):
            original=dict(status);status.update(patch);m.Handler.do_POST(fake)
            self.assertEqual(responses[-1][1],409);self.assertFalse(calls);status.clear();status.update(original)
        m.Handler.do_POST(fake);self.assertEqual(calls,['SET ALGORITHM FOC']);self.assertEqual(responses[-1][1],200)

if __name__=='__main__':unittest.main()
