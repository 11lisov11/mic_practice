"""1809/1810: retain diagnostic records; enlarge real stack and guard its floor."""
import json,os,shutil
from pathlib import Path
import prepare_uart_921600_rx as native
import prepare_uart_tx_contract_fix as current
ROOT=native.ROOT
BASE=native.OUT
CURRENT=current.OUT
OUT=ROOT/'artifacts/live_bench_20261118/boot_stack_integrity_r1'
NEW=(2026111809,2026111810)
read,write,sha=native.read,native.write,native.sha

GUARD=r'''#ifndef MIC_STACK_GUARD_H
#define MIC_STACK_GUARD_H
#include <stdint.h>
/* The stack floor is linker-enforced ABOVE data/noinit/unchanged512B heap.
 * Fill only unused stack before HAL/NVIC initialization. No IRQ masking in RUN.
 * First32bytes are a fail-closed canary; PC reads the rest for high-water data.
 */
extern uint32_t __StackLimit;
enum {MIC_STACK_PATTERN=0xa5a55a5aU,MIC_STACK_GUARD_WORDS=8};
volatile uint32_t mic_stack_guard_failed;
static void mic_stack_guard_init(void){
 uint32_t sp;__asm volatile("mrs %0,msp":"=r"(sp));
 volatile uint32_t *at=&__StackLimit;
 for(; (uintptr_t)at+64U<sp;++at)*at=MIC_STACK_PATTERN;
 __DMB();
}
static int mic_stack_guard_ok(void){
 volatile uint32_t *at=&__StackLimit;
 for(unsigned i=0;i<MIC_STACK_GUARD_WORDS;++i)
  if(at[i]!=MIC_STACK_PATTERN){mic_stack_guard_failed=1U;return 0;}
 return mic_stack_guard_failed==0U;
}
#endif
'''

def main():
 assert not OUT.exists()
 for folder,source in [('nucleo',BASE),('UNOQ_MOTOR',CURRENT),('web_hmi',CURRENT),('libraries',CURRENT)]:
  def copy(src,dst):
   parts=Path(src).relative_to(source/folder).parts
   if folder=='libraries' or folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(source/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','backups'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for path in (OUT/folder).rglob('*'):
   if path.is_file():
    a=read(path);b=a.replace('2026111807',str(NEW[0])).replace('2026111805',str(NEW[0])).replace('2026111806',str(NEW[1]))
    if a!=b:write(path,b)
 path=OUT/'nucleo/Inc/mcp_config.h';s=read(path)
 assert '#define MCP_TX_ASYNC_PAYLOAD_MAX_A 2048U' in s
 write(path,s.replace('#define MCP_TX_ASYNC_PAYLOAD_MAX_A 2048U',
  '/* USART2 optional scope: negotiate512B; both arrays and advertised MTU use this.\n * Release3072B for a4096B CPU stack; supervisor UART1/captures are unchanged. */\n#define MCP_TX_ASYNC_PAYLOAD_MAX_A 512U'))
 path=OUT/'nucleo/STM32CubeIDE/STM32G431RBTX_FLASH.ld';s=read(path)
 assert '_Min_Stack_Size = 0x400;' in s
 s=s.replace('_Min_Stack_Size = 0x400;','_Min_Stack_Size = 0x1000;')
 s+='\n__StackLimit = _estack - _Min_Stack_Size;\nASSERT((_end + _Min_Heap_Size) <= __StackLimit, "data/noinit/heap overlap stack floor")\nASSERT((ADDR(.noinit) + SIZEOF(.noinit)) <= __StackLimit, "retained boot overlaps stack")\n'
 write(path,s);write(OUT/'nucleo/Inc/stack_guard.h',GUARD)
 path=OUT/'nucleo/Src/main.c';s=read(path)
 s='#include "stack_guard.h"\n'+s # __DMB provided below? guard requires CMSIS first.
 s=s.replace('#include "stack_guard.h"\n','',1)
 marker='#include "main.h"';assert marker in s;s=s.replace(marker,marker+'\n#include "stack_guard.h"',1)
 s=s.replace('  UNO_DIAG_RX_BUFFER = 14U,','  UNO_DIAG_RX_BUFFER = 14U,\n  UNO_DIAG_STACK = 15U,')
 marker='  /* USER CODE BEGIN 1 */';assert s.count(marker)==1
 s=s.replace(marker,marker+'\n  mic_stack_guard_init();',1)
 marker='    ma_native_service();\n    uno_link_poll();';assert marker in s
 s=s.replace(marker,'''    if(!mic_stack_guard_ok()){
      LL_TIM_DisableAllOutputs(TIM1);
      uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_STACK);
      continue; /* Never accept CLEAR/START on a damaged stack. */
    }
'''+marker)
 write(path,s)
 path=OUT/'web_hmi/server.py';s=read(path);a='13: "LINK_TIMEOUT", 14: "RX_BUFFER_OVERFLOW",';assert a in s
 write(path,s.replace(a,a+' 15: "STACK_GUARD",'))
 preserved={}
 for base in (BASE,CURRENT,ROOT/'artifacts/live_bench_20261118/telemetry_schedule_analysis_r1'):
  for f in base.rglob('*'):
   if f.is_file() and '__pycache__' not in f.parts:preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_inputs_sha256.json',json.dumps(preserved,indent=2)+'\n')
 write(OUT/'preparation.json',json.dumps(dict(pair=NEW,START=0,CLEAR=0,ARM=0,installed=False,
  root_cause='ADC ISR stack writes retained boot record: hardware watchpoint PC08001ae6 SP200078c0 vs retained200078ec',
  stack_reserve=4096,heap_reserve=512,MCSDK_UART2_async_MTU=512,supervisor_UART_baud=921600,
  scheduler_source_unchanged=True,observer_math_unchanged=True,OFF_fast_limit_cycles=4000,estimate_age_ms=2),indent=2)+'\n')
 print('Prepared1809/1810; stack4096, heap512, capture sizes unchanged, no board IO')

if __name__=='__main__':main()
