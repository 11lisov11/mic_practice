"""Exact linked memory, old-stack corruption replay, actual OFF page scheduler."""
import json,subprocess,shutil
from elftools.elf.elffile import ELFFile
import prepare_boot_stack_integrity as p
from test_foc_update_latency_fix import function

def main():
 out=p.OUT/'verification/stack_and_pages_r2';out.mkdir(parents=True,exist_ok=False)
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 with elf.open('rb') as f:
  e=ELFFile(f);sy={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
  value=lambda n:int(sy[n]['st_value'])
  limit,top,retained=value('__StackLimit'),value('_estack'),value('mic_boot_retained')
  assert top-limit==4096 and value('_Min_Heap_Size')==512
  assert retained+32<=value('_end') and value('_end')+512<=limit
  assert int(sy['MCPAsyncBuffUARTA_A']['st_size'])==int(sy['MCPAsyncBuffUARTA_B']['st_size'])==518
  old_sp=0x200078c0;old_record=0x200078ec
  assert old_sp<old_record and old_sp>limit+32 and retained+32<limit
  # Captured real ADC write stays above the new stack floor and cannot touch boot.
  assert old_record>=limit and not retained<=old_record<retained+32
  layout=dict(stack_limit=limit,stack_top=top,retained=retained,heap_end=value('_end')+512,
   preserved_heap_reserve=512,stack_reserve=4096,old_captured_SP=old_sp,
   old_ADC_write=old_record,old_corruption_reproduced=True,new_record_outside_captured_stack=True)
  p.write(out/'layout.json',json.dumps(layout,indent=2)+'\n')
 # Machine code BEFORE link: addresses shift, but no observer/fast instructions or relocations change.
 before=p.BASE/'nucleo/STM32CubeIDE/Debug/Application/User/multi_native.o'
 after=p.OUT/'nucleo/STM32CubeIDE/Debug/Application/User/multi_native.o'
 same=[]
 with before.open('rb') as b,after.open('rb') as a:
  old,new=ELFFile(b),ELFFile(a)
  for name in ('.text.ma_native_fast','.text.mic_observer_step','.text.mic_observer_noise'):
   assert old.get_section_by_name(name).data()==new.get_section_by_name(name).data(),name;same.append(name)
 for name in ('motor_control.h','foc_experiment.h','current_adc_deadline.h','current_adc_window_plan.h','uart_v3_transport.h','local_stop.h','first_break_snapshot.h','observer_start_history.h'):
  assert p.sha(p.BASE/'nucleo/Inc'/name)==p.sha(p.OUT/'nucleo/Inc'/name),name
 source=p.read(p.OUT/'nucleo/Src/main.c');baseline=p.read(p.BASE/'nucleo/Src/main.c')
 for name in ('mic_send_bulk_page','mic_send_boot_page','mic_send_repeat_meta'):
  assert function(source,name)==function(baseline,name),name
 code=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include "boot_wire.h"
#include "repeat_state.h"
static const uint32_t MIC_NUCLEO_FW_BUILD_ID=2026111810U;
enum {HAL_OK=0,UNO_TX_TAG_DIAG=0};
struct{uint32_t head,tail,hard_error;}mic_uart_tx;
struct{bool command_enabled;}uno_link;
static bool MOE,mic_last_control_reply_safe_off,records;static void*TIM1;
static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static rp_state mic_repeat_state;
static struct{uint32_t magic;}mic_after_clear_break;
enum{MIC_BREAK_MAGIC=0x1234};static bool mic_repeat_wave_ready;
static mb_record boot;static mb_receiver received;static uint32_t now,origin;
static uint8_t last_repeat[43],queue[4][43];static uint32_t repeat_seen;
static double us,done_at,boot_last=-1,repeat_last=-1,max_boot,max_repeat;
static unsigned full_errors,boot_count,repeat_count,control_count,max_pending;
static void mic_boot_packet(uint8_t*p,uint32_t tick){mb_packet(p,&boot,tick);}
static int uno_tx_submit(const uint8_t*p,uint8_t){
 unsigned pending=mic_uart_tx.head-mic_uart_tx.tail;
 if(pending>=4){++full_errors;return 1;}
 memcpy(queue[mic_uart_tx.head&3],p,43);++mic_uart_tx.head;
 if(++pending>max_pending)max_pending=pending;
 if(pending==1)done_at=us+430e6/921600.;return 0;
}
static void drain(){while(mic_uart_tx.tail!=mic_uart_tx.head&&done_at<=us){
 auto*p=queue[mic_uart_tx.tail&3];uint32_t tick=origin+(uint32_t)(done_at/1000);
 if(p[2]==MB_WIRE){assert(mb_receive(&received,p,MIC_NUCLEO_FW_BUILD_ID,true,tick));
  if(boot_last>=0&&done_at-boot_last>max_boot)max_boot=done_at-boot_last;boot_last=done_at;++boot_count;}
 if(p[2]==RPM_VERSION){assert(rpm_valid(p,MIC_NUCLEO_FW_BUILD_ID,true));memcpy(last_repeat,p,43);repeat_seen=tick;
  if(repeat_last>=0&&done_at-repeat_last>max_repeat)max_repeat=done_at-repeat_last;repeat_last=done_at;++repeat_count;}
 if(p[2]==0x80){mic_last_control_reply_safe_off=true;++control_count;}
 ++mic_uart_tx.tail;done_at+=430e6/921600.;}}
static void generic(uint32_t tick,unsigned type,uint32_t period,unsigned index,bool enabled=true,unsigned count=1){
 static uint32_t last[9];if(!enabled||MOE||mic_uart_tx.hard_error||(uint32_t)(tick-last[index])<period||mic_uart_tx.head-mic_uart_tx.tail>1)return;
 uint8_t p[43]={};p[2]=(uint8_t)type;for(unsigned i=0;i<count;++i)assert(uno_tx_submit(p,0)==HAL_OK);last[index]=tick;
}
static void mic_send_current_page(uint32_t n){generic(n,0xd2,200,0);}
static void mic_send_research_page(uint32_t n){generic(n,0xe4,100,1,true,2);}
static void mic_send_observer_page(uint32_t n){generic(n,0xea,20,2,records);}
static void mic_send_break_page(uint32_t n){generic(n,0xd1,200,3);}
static void mic_send_peak_page(uint32_t n){generic(n,0xd8,100,4,records);}
static void mic_send_noise_page(uint32_t n){generic(n,0xe7,20,5,records);}
static void mic_send_identification(uint32_t n){generic(n,0xe5,records?20:250,6);}
static void mic_send_clear_page(uint32_t n){generic(n,0xee,500,7,records);}
'''
 for name in ('mic_send_repeat_meta','mic_send_boot_page','mic_send_bulk_page'):code+='\n'+function(source,name)
 code+=r'''
int main(int argc,char**argv){
 assert(argc==4);records=atoi(argv[1])!=0;origin=(uint32_t)strtoul(argv[2],0,0);unsigned delay=atoi(argv[3]);
 boot={MB_MAGIC,MIC_NUCLEO_FW_BUILD_ID,1,0x14000000,0,MB_CURRENT_CLEARED,0,0};boot.crc=mb_crc(&boot);
 // Exact symptom: valid first page then an ADC-stack overwrite. TTL is NOT relaxed.
 uint8_t packet[43];mb_packet(packet,&boot,520);mb_receiver bad={};assert(mb_receive(&bad,packet,MIC_NUCLEO_FW_BUILD_ID,true,520));
 mb_record corrupted=boot;corrupted.magic=0x432e;mb_packet(packet,&corrupted,1020);
 assert(!mb_receive(&bad,packet,MIC_NUCLEO_FW_BUILD_ID,true,1020));assert(!mb_fresh(&bad,MIC_NUCLEO_FW_BUILD_ID,true,2500));
 uint32_t command_ms=origin;
 for(us=0;us<30e6;us+=delay){
  now=origin+(uint32_t)(us/1000);drain();
  if((uint32_t)(now-command_ms)>=50){uint8_t p[43]={};p[2]=0x80;assert(uno_tx_submit(p,2)==HAL_OK);command_ms=now;}
  mic_send_bulk_page(now);
  if(us>3e6){assert(mb_fresh(&received,MIC_NUCLEO_FW_BUILD_ID,true,now));assert((uint32_t)(now-repeat_seen)<1500);
   assert(rpm_u32(last_repeat+34)==mb_u32(received.packet+30));}
 }
 assert(boot_count>30&&repeat_count>30&&control_count>500&&!full_errors&&max_pending<=4);
 assert(max_boot<1500000&&max_repeat<1500000);
 unsigned b=boot_count,r=repeat_count;MOE=true;for(unsigned i=0;i<2000;++i){us+=1000;now=origin+(uint32_t)(us/1000);drain();mic_send_bulk_page(now);}
 assert(boot_count<=b+1&&repeat_count<=r+1);assert(!mb_fresh(&received,MIC_NUCLEO_FW_BUILD_ID,true,now));
 printf("{\"passed\":true,\"boot_pages\":%u,\"repeat_pages\":%u,\"max_boot_gap_us\":%.1f,\"max_repeat_gap_us\":%.1f,\"queue_full\":%u,\"TTL_unchanged\":true,\"old_corruption_negative_control\":true}\n",b,r,max_boot,max_repeat,full_errors);
}
'''
 cpp=out/'actual_pages.cpp';p.write(cpp,code);exe=cpp.with_suffix('.exe')
 x=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I',str(p.OUT/'nucleo/Inc'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'build.log',x.stdout+x.stderr);x.check_returncode();results=[]
 for records in (0,1):
  for origin in ('0','0xfffff000'):
   for delay in (100,1900):
    x=subprocess.run([str(exe),str(records),origin,str(delay)],capture_output=True,text=True);p.write(out/f'case_{records}_{origin}_{delay}.log',x.stdout+x.stderr);x.check_returncode();results.append(json.loads(x.stdout))
 p.write(out/'report.json',json.dumps(dict(passed=True,hardware_commands=0,layout=layout,ARM_object_sections_unchanged=same,
  page_sender_and_scheduler_actual=True,other_record_payloads_and_DMA_timing_simulated=True,cases=results,limits=[4000,2]),indent=2)+'\n')
 print(json.dumps(dict(passed=True,cases=len(results),layout=layout)))

if __name__=='__main__':main()
