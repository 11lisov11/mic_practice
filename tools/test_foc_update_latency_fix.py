"""Exercise interrupted snapshots, actual packet encoding and recorded gates."""
import json,subprocess,shutil,re
import prepare_foc_update_latency_fix as p
import test_foc_runtime_fix as common
def function(text,name):
 match=re.search(r'^\w[^\n;]*\b'+name+r'\([^;]*?\)\s*\{',text,re.M)
 assert match,name
 depth=0
 for i in range(text.index('{',match.start()),len(text)):
  if text[i]=='{':depth+=1
  elif text[i]=='}':
   depth-=1
   if not depth:return text[match.start():i+1]
 raise AssertionError(name)

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
 source=p.read(p.OUT/'nucleo/Src/current_shunt.c')
 code=r'''
#include <cassert>
#include <cstdio>
#include <math.h>
#include "current_core.h"
#include "uart_v3_transport.h"
static cm_core state;static volatile uint32_t state_sequence;
static unsigned packets,copies;static int split_at=-1,interrupts_left;
static void interrupted_copy(cm_core*dst,const cm_core*src){
 ++copies;
 if(interrupts_left&&split_at>=0){
  unsigned char*d=(unsigned char*)dst;const unsigned char*s=(const unsigned char*)src;
  memcpy(d,s,split_at);
  ++state_sequence;memset(&state,0x5a,sizeof(state));++state_sequence;
  memcpy(d+split_at,s+split_at,sizeof(state)-split_at);--interrupts_left;
 }else *dst=*src;
}
#define CM_SNAPSHOT_COPY(d,s) interrupted_copy(d,s)
#define CM_SNAPSHOT_BARRIER() __asm__ volatile("":::"memory")
#include "current_snapshot.h"
#include "current_adc_deadline.h"
static unsigned HAL_GetTick(){return 1000;}
#define ADC_REFERENCE_VOLTAGE 3.3f
#define RSHUNT .04f
#define AMPLIFICATION_GAIN 2.1f
'''
 for name in ('ma_u','put16','put32','mic_current_packet'):code+='\n'+function(source,name)
 old=p.read(p.BASE/'nucleo/Src/current_shunt.c')
 reference=function(old,'mic_current_packet').replace('mic_current_packet(','reference_packet(').replace(
  'uint32_t key=__get_PRIMASK();__disable_irq();copy=state;__set_PRIMASK(key);','copy=state;')
 code+='\n'+reference
 code+=r'''
int main(){
 assert(sizeof(state)==296);cm_core copy;
 for(unsigned pos=0;pos<=sizeof(state);++pos){
  memset(&state,0xa5,sizeof(state));state_sequence=0;copies=0;
  split_at=(int)pos;interrupts_left=1;
  assert(cm_snapshot_read(&copy,&state,&state_sequence));
  assert(copies==2&&memcmp(&copy,&state,sizeof(state))==0);
 }
 split_at=100;interrupts_left=100;state_sequence=0;copies=0;
 assert(!cm_snapshot_read(&copy,&state,&state_sequence)&&copies==3);
 state_sequence=1;copies=0;assert(!cm_snapshot_read(&copy,&state,&state_sequence)&&copies==0);
 state_sequence=0xfffffffeU;interrupts_left=1;copies=0;
 assert(cm_snapshot_read(&copy,&state,&state_sequence)&&state_sequence==0&&copies==2);
 uint8_t packet[UV3_FRAME],reference[UV3_FRAME];memset(packet,0xa5,sizeof(packet));
 state_sequence=1;assert(!mic_current_packet(packet,0,1));
 for(auto b:packet)assert(b==0xa5);
 state_sequence=0;split_at=-1;interrupts_left=0;
 cm_init(&state);state.zero_ready=1;state.published.n=32;
 state.published.square[0]=33;state.published.square[1]=67;state.published.square[2]=21;
 for(unsigned i=0;i<4;++i){state.raw[i]=2048+i;state.offset[i]=2060+i;}
 for(unsigned detail=0;detail<3;++detail){
  packets=0;reference_packet(reference,detail,2026103004);
  packets=0;assert(mic_current_packet(packet,detail,2026103004));
  assert(memcmp(packet,reference,sizeof(packet))==0);
 }
 assert(!mic_adc_bottom_update(5312,2226,0));
 assert(mic_adc_bottom_update(5312,137,0));
 puts("snapshot interleavings297, bounded retries, odd writer, wrap, packet equivalence OK");
}
'''
 common.compile_run(out,'snapshot_and_packets',code)
 # Actual sender must not enqueue an invalid/uninitialized packet or advance slot.
 sender=function(p.read(p.OUT/'nucleo/Src/main.c'),'mic_send_current_page')
 pre=r'''
#include <cassert>
#include <cstdint>
enum{UV3_FRAME=43,HAL_OK=0,UNO_TX_TAG_DIAG=1,MIC_NUCLEO_FW_BUILD_ID=2026103004};
static struct{unsigned head,tail,hard_error;}mic_uart_tx;
static int success,calls,tx;
static int mic_zero_packet(uint8_t*,unsigned){return 0;}
static int mic_current_packet(uint8_t*,uint8_t,unsigned){++calls;return success;}
static int uno_tx_submit(uint8_t*,unsigned){++tx;return 0;}
'''
 common.compile_run(out,'sender_skips_busy',pre+sender+'''
int main(){mic_send_current_page(201);assert(calls==1&&tx==0);
success=1;mic_send_current_page(202);assert(calls==2&&tx==1);
mic_send_current_page(203);assert(calls==2&&tx==1);}
''')
 # Replay every recorded row with the unchanged actual guard; bad row MUST fail.
 capture=json.loads(p.read(p.BASE/'powered_FOC_CPU_IRQ_20261030_r2/ADC_peak_decoded.json'))
 replay=p.read(p.BASE/'powered_FOC_CPU_IRQ_20261030_r2/ADC_timing_replay.cpp')
 output=common.compile_run(out,'recorded_ADC_replay',replay)
 rows=[list(map(int,line.split(','))) for line in output.splitlines()]
 assert len(rows)==12 and rows[10]==[10,0,1,1]
 assert all(row[1:]==[1,1,1] for row in rows[:10])
 # Apart from writer publication markers, acquisition logic stays identical.
 before=function(old,'mic_current_adc_irq');after=function(source,'mic_current_adc_irq')
 assert after.replace('''  if(captured_pair<3){
    ++state_sequence;__DMB();
    cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);
    __DMB();++state_sequence;
  }''','''  if(captured_pair<3)cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);''')==before
 for rel in ('motor_control.h','current_adc_deadline.h','current_adc_window_plan.h','current_core.h','foc_experiment.h','local_stop.h'):
  assert (p.OUT/'nucleo/Inc'/rel).read_bytes()==(p.BASE/'nucleo/Inc'/rel).read_bytes(),rel
 assert 'MIC_ADC_PUBLISH_MARGIN_TICKS=2048U' in p.read(p.OUT/'nucleo/Inc/current_adc_deadline.h')
 p.write(out/'selftest.json',json.dumps(dict(passed=True,hardware_commands=0,
  snapshot_interleave_positions=297,bounded_three_attempts=True,odd_and_wrap_checked=True,
  busy_packet_not_sent=True,all_three_packet_encodings_equivalent=True,
  recorded_ADC_rows=12,original_bad_frame_still_rejected=True,ADC_guard_2048_unchanged=True,
  ADC_feedback_logic_unchanged=True,physical_5s_completion_not_proven=True),indent=2)+'\n')
 print('Snapshot, sender, recorded ADC replay passed; no hardware access')

if __name__=='__main__':main()
