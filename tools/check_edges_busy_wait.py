import json,subprocess,shutil
import prepare_no_switch_diag as p
import prepare_full_edges_busy_wait as prep
TEST=r'''
#include "nucleo_encoder.c"
#include <cassert>
#include <cstdio>
static uint32_t us;
static void step(){us+=10;test_tick=us/1000;test_dwt.CYCCNT=us*170;mic_encoder_poll();}
int main(){
 test_rcc.CR=RCC_CR_HSIRDY;test_gpio.IDR=0x1d0;test_i2c.ISR.value=1;
 test_gpio.MODER=0xa5a0000a;mock_external_sda=true;mock_release_on=4;
 mic_encoder_init();assert(enc.configured);
 while(us<300000)step();
 #if FIXED_WAIT
 assert(enc.errors==1&&enc.primary_busy==1);
 #else
 assert(enc.errors==15&&enc.primary_busy==15);
 #endif
 assert(enc.reads==0&&!enc.bus_ok&&!enc.angle_ok&&!enc.speed_ok&&enc.cause==EC_BUSY);
 assert(!bus_clear.attempted&&!mock_gpio_writes&&!(I2C1->CR1&1)&&!I2C1->CR2);
 assert(fault_ready==1&&release_probe[0].complete);
 const unsigned before=enc.errors;uint32_t frozen[40];memcpy(frozen,fault_record[0],sizeof(frozen));sr_probe probe=release_probe[0];
 mic_encoder_allow_bus_clear(true);
 while(!bus_clear.result && us<310000)step();
 assert(bus_clear.result==BC_CLEARED&&bus_clear.pulses==9&&!bus_clear.active);
 assert(enc.errors==before&&!memcmp(frozen,fault_record[0],sizeof(frozen))&&!memcmp(&probe,&release_probe[0],sizeof(probe)));
 while(enc.state!=1&&us<350000)step();
 assert(enc.state==1);
 I2C1->CR2&=~I2C_CR2_START;I2C1->ISR.value=EC_TXIS|EC_BUSYF;step();assert(enc.state==2);
 I2C1->ISR.value=EC_TC|EC_BUSYF;step();assert(enc.state==3);I2C1->CR2&=~I2C_CR2_START;
 for(unsigned b: {0x20U,7U,99U}){I2C1->RXDR=b;I2C1->ISR.value=EC_RXNE|EC_BUSYF;step();}
 I2C1->ISR.value=EC_STOPF;step();assert(enc.reads==1&&enc.bus_ok&&enc.angle_ok&&enc.raw==1891);
 assert(enc.errors==before&&!memcmp(frozen,fault_record[0],sizeof(frozen)));
 printf("{\"passed\":true,\"fixed_wait\":%u,\"BUSY_before_gate\":%u,\"recovery_pulses\":9,\"first_snapshot_preserved\":true,\"healthy_read_after\":true,\"hardware_calls\":0}\n",FIXED_WAIT,before);
}
'''
def main():
 c=prep.OUT;v=c/'verification';mock=v/'driver_mock';mock.mkdir(exist_ok=True)
 base=p.ROOT/'artifacts/live_bench_20261027/i2c_persistent_pe_r1/verification/mock'
 for f in base.iterdir():shutil.copy2(f,mock/f.name)
 code='#include <initializer_list>\n'+TEST;p.write(v/'startup_gate_replay.cpp',code)
 flags=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers']
 def run(tag,src,project,defs=(),args=()):
  exe=v/(tag+'.exe');q=subprocess.run(flags+list(defs)+['-I',str(mock),'-I',str(project/'nucleo/Inc'),'-I',str(project/'nucleo/Src'),str(src),'-o',str(exe)],capture_output=True,text=True,timeout=60)
  p.write(v/(tag+'_compile.log'),q.stdout+q.stderr);assert not q.returncode,q.stderr
  q=subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=60);p.write(v/(tag+'.log'),q.stdout+q.stderr);assert not q.returncode,q.stderr
  return json.loads(q.stdout)
 results={}
 for fixed,root in [(0,prep.OLD),(1,c)]:results['fixed' if fixed else 'old']=run('gate_'+str(fixed),v/'startup_gate_replay.cpp',root,['-DFIXED_WAIT='+str(fixed)])
 for mode in ('normal','lost_pe','missing_hook'):
  results['platform_'+mode]=run('platform_'+mode,p.ROOT/'tools/i2c_persistent_pe/platform_test.cpp',c,args=[mode])
 for mode in ('0','1','2'):
  results['bus_'+mode]=run('bus_'+mode,p.ROOT/'tools/sda_idle_bus_clear/driver_test.cpp',c,args=[mode])
 # Re-run the actual complete fixture/safety/math adapter for this image.
 import check_full_mcsdk_edges as check
 check.prep=prep;check.main()
 report=json.loads(p.read(v/'native_tests.json'));report['startup_gate_replay']=results
 report['startup_transfer_core_unchanged']=p.sha(c/'nucleo/Inc/encoder_core.h')==p.sha(prep.OLD/'nucleo/Inc/encoder_core.h')
 assert report['startup_transfer_core_unchanged'];p.write(v/'native_tests.json',json.dumps(report,indent=2)+'\n')
 print(json.dumps(results))
if __name__=='__main__':main()
