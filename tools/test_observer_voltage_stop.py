"""Production send-policy/observer/recorder regressions. No boards or network."""
import json,importlib.util,sys
import prepare_observer_voltage_stop as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function
from test_foc_observer_schedule_fix import stripped_header


def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 pre=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include "superseded_reply.h"
static uint32_t clock_us=100000,g_bp_last_rsp_ms=100,g_nucleo_last_tx_ms=100;
static uint32_t g_nucleo_last_send_us=100000,g_nucleo_last_send_ms=100;
static const uint32_t BP_REPLY_TIMEOUT_MS=500,NUCLEO_RUN_REPLY_GUARD_US=8000,
 NUCLEO_SCALAR_MIN_SEND_US=50000,NUCLEO_RUN_MIN_SEND_US=50000,NUCLEO_HEARTBEAT_MS=50;
static const bool USE_EXTERNAL_PWM=true,NUCLEO_MCSDK_ACIM_BACKEND=true,USE_NUCLEO_UART_FALLBACK=true;
static bool g_estop_latched=false,g_io_test_mode=false,g_diag_pwm=false,g_duty_mode=false,g_clear_fault_req=false,
 g_pwm_enabled=true,g_nucleo_waiting_rsp=true,g_nucleo_waiting_clear=false;
static unsigned g_bp_fault_code=0,g_bp_status=0,g_mode=0,g_state=1;
enum{MODE_VF=0,STATE_VF_RUN=1,BP_STATUS_FAULT=8,BP_STATUS_TIMEOUT=16};
static uint8_t g_nucleo_waiting_seq=1,seq=1;
static SupersededReplies g_nucleo_superseded;
static unsigned writes;
static uint32_t millis(){return clock_us/1000;}static uint32_t micros(){return clock_us;}
static void nucleo_uart_poll(){}
'''
 tail=r'''
static void reset(){clock_us=100000;g_bp_last_rsp_ms=g_nucleo_last_tx_ms=g_nucleo_last_send_ms=100;
 g_nucleo_last_send_us=100000;g_nucleo_superseded={};g_nucleo_waiting_rsp=true;g_nucleo_waiting_seq=1;seq=1;writes=0;}
int main(){
 unsigned lost=0,accepted=0;
 for(unsigned delay=9000;delay<50000;delay+=1000){
  reset();
  for(unsigned t=1000;t<=delay;t+=1000){clock_us=100000+t;attempt(0,0,0,true,false);}
  bool retired=g_nucleo_superseded.consume(1,clock_us,500000);
  if(!retired&&g_nucleo_waiting_rsp&&g_nucleo_waiting_seq==1){++accepted;g_nucleo_waiting_rsp=false;g_bp_last_rsp_ms=millis();}
  else ++lost;
  assert(writes==0); // no actual replacement before50ms
 }
 EXPECT_CASES
 reset();clock_us=150000;attempt(0,0,0,true,false);assert(writes==1&&g_nucleo_waiting_seq==2);
 assert(g_nucleo_superseded.consume(1,151000,500000)); // genuinely replaced reply stays stale
 reset();clock_us=101000;attempt(0,0,0,false,true);assert(writes==1); // immediate STOP bypasses cadence
 assert(g_nucleo_superseded.consume(1,102000,500000));
 reset();clock_us=600000;assert(!bp_fault_or_timeout(millis()));clock_us=601000;assert(bp_fault_or_timeout(millis()));
 g_bp_status=BP_STATUS_FAULT;clock_us=100001;assert(bp_fault_or_timeout(millis()));
 printf("{\"accepted_current_replies\":%u,\"discarded_current_replies\":%u,\"genuine500ms_watchdog_preserved\":true}\n",accepted,lost);
}
'''
 results={}
 for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
  s=p.read(folder/'UNOQ_MOTOR/UNOQ_MOTOR.ino');sender=function(s,'nucleo_send_pwm')
  head=sender[:sender.index('  uint8_t pkt[BP_FRAME_LEN]')]
  tx=sender[sender.rindex('    if (force && g_nucleo_waiting_rsp)' if label=='baseline' else '    if (g_nucleo_waiting_rsp)'):sender.index('    const uint32_t timing_tx_begin')]
  head=head.replace('nucleo_send_pwm(', 'attempt(')
  pos=head.index('{')+1;head=head[:pos]+'(void)d_u;(void)d_v;(void)d_w;'+head[pos:]
  code=pre+function(s,'bp_fault_or_timeout')+'\n'+head+'''
 uint8_t seq=++::seq;const bool clear_eff=g_clear_fault_req;'''+tx+'''
 ++writes;g_nucleo_last_send_us=now_us;g_nucleo_last_send_ms=now;g_nucleo_last_tx_ms=now;
}
'''+tail.replace('EXPECT_CASES','assert(accepted==0&&lost==41);' if label=='baseline' else 'assert(accepted==41&&lost==0);')
  results[label]=json.loads(common.compile_run(out,'reply_lifecycle_'+label,code))

 # Differential arithmetic: diagnostics must not retune the EKF/current loop.
 pre='''#include <cassert>\n#include <cstdio>\n#include <cmath>\n#include <cstring>\n#include <cstdint>\n#include <cfloat>\n#include "current_adc_window_plan.h"\nusing std::isfinite;using std::isnan;\n'''
 a=stripped_header(p.read(p.BASE/'nucleo/Inc/motor_control.h'));b=stripped_header(p.read(p.OUT/'nucleo/Inc/motor_control.h'))
 code=pre+'namespace old {\n'+a+'\n}\nnamespace candidate {\n'+b+'\n}\n'+r'''
int main(){
 old::ma_motor m={12.23f,11.004422f,.52809386f,.52809386f,.4944776f,.0002f,.000147906f,1,.25f,.8f,1.35f,400,12};
 candidate::ma_motor nm;memcpy(&nm,&m,sizeof(m));
 unsigned tested=0;
 for(unsigned i=0;i<20000;++i){
  old::ma_observer a;old::ma_controller ca;old::ma_reset(&a,&ca);
  candidate::ma_observer b;candidate::ma_controller cb;candidate::ma_reset(&b,&cb);
  for(unsigned j=0;j<6;++j)a.x[j]=b.x[j]=(j==4?30.f:j==5?0.f:.1f*sinf(i*.013f+j));
  float ia=.5f*cosf(i*.1f),ib=.5f*sinf(i*.1f),va=10*cosf(i*.03f),vb=10*sinf(i*.03f);
  int ra=old::ma_observe(&a,&m,ia,ib,va,vb,.001f),rb=candidate::ma_observe(&b,&nm,ia,ib,va,vb,.001f);
  assert(ra==rb&&memcmp(a.x,b.x,sizeof(a.x))==0&&memcmp(a.p,b.p,sizeof(a.p))==0&&a.nis==b.nis);
  assert(a.steps==b.steps&&a.rejected==b.rejected);
  double nis=0;for(unsigned ch=0;ch<2;++ch)nis+=double(b.innovation[ch])*b.innovation[ch]/b.innovation_variance[ch];
  assert(fabs(nis-b.nis)<1.e-5*(1+b.nis));++tested;
 }
 printf("{\"EKF_bit_exact_cases\":%u,\"NIS_decomposition_verified\":true}\n",tested);
}
'''
 numeric=json.loads(common.compile_run(out,'observer_numeric_differential',code))
 # Active compares must determine input voltage, irrespective of next preload.
 code=r'''
#include <cassert>
#include <cstdio>
#include "observer_applied_voltage.h"
#include "observer_trace_core.h"
#include "observer_trace_wire.h"
#include "stop_evidence.h"
int main(){
 ma_geometry g={5312,5184,771,112,240,229};uint16_t c[3]={2600,2800,2500};float a,b;
 assert(!ma_applied_voltage(&g,c,5312,323,.3f,-.2f,&a,&b));
 float expected_a=((2600.f-(2600.f+2800+2500)/3.f)*323/5312);
 float loss=323.f*229/(2.f*5312);
 float p[3]={loss,loss*ma_clip((-.5f*.3f+.8660254038f*-.2f)/.05f,-1,1),loss*ma_clip((-.5f*.3f-.8660254038f*-.2f)/.05f,-1,1)};
 expected_a-=(2*p[0]-p[1]-p[2])/3;
 assert(fabsf(a-expected_a)<1.e-5f);
 assert(ma_applied_voltage(&g,c,0,323,.3f,-.2f,&a,&b)==MA_BUS);
 c[1]=6000;assert(ma_applied_voltage(&g,c,5312,323,.3f,-.2f,&a,&b)==MA_WINDOW);
 StopEvidence stop;stop.capture(1,842,1,3,0,99,0,341,800,1,7,10);auto saved=stop;
 stop.capture(2,999,2,0,0,0,0,0,0,0,0,0);assert(memcmp(&stop,&saved,sizeof(stop))==0);
 od_capture cap={};od_begin(&cap,2026111406);
 for(unsigned i=1;i<=5000;++i){od_sample r={};r.steps=i;r.nis=i==600?37.f:0;r.flux_alpha=.235f;
 r.reasons=od_reasons(1,1,i,0,.235f,.25f,r.nis);r.published=1;od_push(&cap,&r);}
 assert(cap.blob.header.first_loss_step==600);od_freeze(&cap,0);
 assert(cap.blob.header.schema==2&&cap.blob.header.count==12&&sizeof(od_blob)==1832);
 cap.blob.header.crc=uv3_crc32c((uint8_t*)&cap.blob,OD_BYTES);od_receiver rx={};uint8_t f[43];
 for(unsigned n=0;n<OD_PAGES;++n){memset(f,0,43);f[0]=0x55;f[1]=0xaa;f[2]=OD_WIRE;f[3]=2;f[4]=1;
 f[5]=n;f[6]=OD_PAGES;f[7]=n==OD_PAGES-1?2:30;f[38]=1;memcpy(f+8,((uint8_t*)&cap.blob)+n*30,f[7]);uv3_seal(f);
 assert(odw_receive(&rx,f,2026111406,2026111406,true));}
 assert(rx.complete);f[3]=1;uv3_seal(f);assert(!odw_receive(&rx,f,2026111406,2026111406,true));
 puts("active voltage, immutable stop evidence, schema2 recorder/transport passed");
}
'''
 common.compile_run(out,'voltage_stop_wire',code)
 # Protection functions and ADC/Break path remain unchanged except build IDs.
 for rel in ['nucleo/Src/current_shunt.c','nucleo/Inc/current_adc_deadline.h','nucleo/Inc/current_adc_window_plan.h',
  'nucleo/Inc/foc_experiment.h','nucleo/Inc/local_stop.h','UNOQ_MOTOR/superseded_reply.h']:
  expected=p.read(p.BASE/rel).replace('2026111403',str(p.NEW[0])).replace('2026111404',str(p.NEW[1]))
  assert expected==p.read(p.OUT/rel),rel
 for fn in ['uno_rearm_break_irq','mic_repeat_break_irq','uno_handle_valid_frame']:
  assert function(p.read(p.BASE/'nucleo/Src/main.c'),fn)==function(p.read(p.OUT/'nucleo/Src/main.c'),fn)
 assert function(p.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),'bp_fault_or_timeout')==function(p.read(p.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),'bp_fault_or_timeout')
 report=dict(passed=True,reply_lifecycle=results,numeric=numeric,hardware_commands=0,
  thresholds_changed=False,watchdog_500ms_unchanged=True,actual_current_reply_not_retired_before_replacement=True)
 p.write(out/'report.json',json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
