"""Production normal-packet generation/senders -> UART FIFO -> Uno -> HMI, PC only."""
import ast,json,subprocess
import prepare_telemetry_deadline as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


PRE=r'''
#include <cassert>
#include <cstdio>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include "uart_v3_transport.h"
#include "current_wire.h"
#define __DMB() ((void)0)
#include "current_snapshot.h"
using std::isfinite;
#define ADC_REFERENCE_VOLTAGE 3.3
#define RSHUNT .04
#define AMPLIFICATION_GAIN 2.1
enum{HAL_OK=0,UNO_TX_TAG_DIAG=0};
static const unsigned MIC_NUCLEO_FW_BUILD_ID=2026111604;
static cm_core state;static volatile unsigned state_sequence;static unsigned packets;
static double now_us,next_done;static uint32_t origin_ms;
static uint32_t HAL_GetTick(){return origin_ms+(uint32_t)(now_us/1000);}
static struct{uint32_t head,tail,hard_error;} mic_uart_tx;
static struct{bool command_enabled;} uno_link;
static bool MOE,mic_last_control_reply_safe_off=false,records;
static void*TIM1;static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static uint8_t queue[4][43];static double queued_at[4];
static ct_receiver receiver;
static uint32_t full_errors,controls,bulk_count,max_pending;
static double max_control_us,last_control_us=-1e9;
static double last_normal[3]={-1,-1,-1},max_gap[3];
static unsigned mask[2][62],first_complete[2];
static FILE*csv;
static void drain(){while(mic_uart_tx.head!=mic_uart_tx.tail&&next_done<=now_us){
 auto*frame=queue[mic_uart_tx.tail&3];unsigned type=frame[2];
 if(type==0x80){++controls;double age=now_us-queued_at[mic_uart_tx.tail&3];if(age>max_control_us)max_control_us=age;last_control_us=now_us;mic_last_control_reply_safe_off=true;}
 if(type==CT_SUMMARY||type==CT_DETAIL||type==CT_QUALITY){
  assert(ct_receive(&receiver,frame,MIC_NUCLEO_FW_BUILD_ID,now_us-last_control_us<300000,HAL_GetTick()));
  unsigned slot=type==CT_SUMMARY?0:type==CT_DETAIL?1:2;
  if(last_normal[slot]>=0){double gap=now_us-last_normal[slot];if(gap>max_gap[slot])max_gap[slot]=gap;}
  last_normal[slot]=now_us;
 }
 if(type==0xea||type==0xd8){unsigned row=type==0xea?0:1;mask[row][frame[5]]=1;unsigned n=0;
  for(unsigned i=0;i<(row?35U:62U);++i)n+=mask[row][i];
  if(n==(row?35U:62U)&&!first_complete[row])first_complete[row]=(unsigned)now_us;}
 ++mic_uart_tx.tail;next_done+=430000000.0/115200;
}}
static int uno_tx_submit(const uint8_t*frame,uint8_t){
 unsigned pending=mic_uart_tx.head-mic_uart_tx.tail;
 if(pending>=4){++full_errors;return 1;}
 bool empty=pending==0;memcpy(queue[mic_uart_tx.head&3],frame,43);queued_at[mic_uart_tx.head&3]=now_us;
 ++mic_uart_tx.head;if(++pending>max_pending)max_pending=pending;
 if(empty)next_done=now_us+430000000.0/115200;
 return 0;}
static void mark(uint8_t*p,unsigned kind){memset(p,0,43);p[0]=0x55;p[1]=0xaa;p[2]=(uint8_t)kind;p[38]=1;uv3_seal(p);}
static void ma_native_service(){}
static void ma_native_diag(uint8_t*p,unsigned){mark(p,0xe4);}
static void ma_timing_diag(uint8_t*p,unsigned,unsigned){mark(p,0xe8);}
static int mic_zero_packet(uint8_t*p,unsigned){mark(p,0xd9);return 1;}
static int ma_observer_trace_packet(uint8_t*p,unsigned,unsigned page){mark(p,0xea);p[5]=page;return records;}
static int mic_current_peak_packet(uint8_t*p,unsigned page,unsigned){mark(p,0xd8);p[5]=page;return records;}
static int mic_current_noise_packet(uint8_t*p,unsigned page,unsigned){mark(p,0xdb);p[5]=page;return 1;}
static void ma_id_status(uint8_t*p,unsigned){mark(p,0xe5);}
static int ma_id_page(uint8_t*p,unsigned,unsigned page){mark(p,0xe6);p[5]=page;return records;}
static unsigned other_last[3];
static void other(unsigned index,unsigned now,unsigned period,unsigned type,bool loose=false){
 if(MOE||uno_link.command_enabled||!mic_last_control_reply_safe_off||mic_uart_tx.hard_error||
  (uint32_t)(now-other_last[index])<period||(!loose&&mic_uart_tx.head-mic_uart_tx.tail>1))return;
 uint8_t f[43];mark(f,type);if(!uno_tx_submit(f,0)){other_last[index]=now;++bulk_count;}}
static void mic_send_repeat_meta(unsigned now){other(0,now,500,0xec);}
static void mic_send_boot_page(unsigned now){other(1,now,500,0xe9);}
static void mic_send_break_page(unsigned now){other(2,now,200,0xd1,true);}
static void hex(FILE*f,const uint8_t*p){for(unsigned i=0;i<43;++i)fprintf(f,"%02x",p[i]);}
static void export_row(){
 if(!csv||now_us<2000000)return;
 unsigned now=HAL_GetTick();
 fprintf(csv,"{\"t_us\":%u,\"ages\":[%u,%u,%u],\"packets\":[\"",(unsigned)now_us,
  receiver.has_summary?(uint32_t)(now-receiver.summary_ms):999999,
  receiver.has_detail?(uint32_t)(now-receiver.detail_ms):999999,
  receiver.has_quality?(uint32_t)(now-receiver.quality_ms):999999);
 hex(csv,receiver.summary);fputs("\",\"",csv);hex(csv,receiver.detail);fputs("\",\"",csv);hex(csv,receiver.quality);fputs("\"]}\n",csv);
}
'''

TAIL=r'''
static void control(unsigned now){uint8_t frame[43];mark(frame,0x80);assert(!uno_tx_submit(frame,0));
 ma_native_service();mic_send_research_page(now);ma_native_service();mic_send_current_page(now);ma_native_service();}
int main(int argc,char**argv){
 assert(argc==7);unsigned cadence=atoi(argv[1]),phase=atoi(argv[2]),stride=atoi(argv[3]);records=atoi(argv[4]);origin_ms=strtoul(argv[5],nullptr,0);
 csv=fopen(argv[6],"wb");assert(csv);cm_init(&state);state.zero_ready=1;state.zero_stable=3;state.zero_attempts=3;
 for(unsigned i=0;i<4;++i){state.offset[i]=state.raw[i]=2065+i;state.zero_low[i]=2050+i;state.zero_high[i]=2080+i;state.count[i]=256;}
 state.published.n=3200;state.published.start_ms=0;state.published.end_ms=200;state.published.flags=CM_FROZEN;
 for(unsigned i=0;i<3;++i){state.published.square[i]=(uint64_t)3200*(80+i)*(80+i);state.published.peak[i]=85+i;}
 unsigned next_control=phase,next_export=0;
 for(unsigned us=0;us<70000000;us+=stride){now_us=us;drain();unsigned now=HAL_GetTick();
  if(us>=next_control){control(now);next_control+=cadence;}
  mic_send_bulk_page(now);
  if(us>=next_export){export_row();next_export+=20000;}
 }
 fclose(csv);
 unsigned gap[3];for(unsigned i=0;i<3;++i)gap[i]=(unsigned)max_gap[i];
 printf("{\"summary_gap_us\":%u,\"detail_gap_us\":%u,\"quality_gap_us\":%u,\"receiver_good\":%u,\"receiver_bad\":%u,\"control_replies\":%u,\"max_control_latency_us\":%.1f,\"queue_full\":%u,\"max_pending\":%u,\"observer_complete_us\":%u,\"ADC_complete_us\":%u}\n",
  gap[0],gap[1],gap[2],receiver.good,receiver.bad,controls,max_control_us,full_errors,max_pending,first_complete[0],first_complete[1]);
 CHECK
 // An OFF scheduler must not start sending anything during RUN or on an
 // unacknowledged/offline link; no bypass through the new normal priority.
 for(unsigned gate=0;gate<4;++gate){MOE=gate==0;uno_link.command_enabled=gate==1;
  mic_last_control_reply_safe_off=gate!=2;mic_uart_tx.hard_error=gate==3;
  unsigned before=mic_uart_tx.head;mic_send_bulk_page(HAL_GetTick()+10000);assert(mic_uart_tx.head==before);}
}
'''


def compile_variants(out):
    common.p=p
    current=p.read(p.OUT/'nucleo/Src/current_shunt.c')
    producers='\n'.join(function(current,n) for n in ('ma_u','put16','put32','mic_current_packet'))
    result={}
    for label,folder in [('baseline',p.BASE),('candidate',p.OUT)]:
        src=p.read(folder/'nucleo/Src/main.c')
        senders='\n'.join(function(src,n) for n in ('mic_send_research_page','mic_send_current_page',
            'mic_send_observer_page','mic_send_peak_page','mic_send_noise_page','mic_send_identification','mic_send_bulk_page'))
        checks='' if label=='baseline' else '''assert(gap[0]<750000&&gap[1]<1500000&&gap[2]<1500000);
 assert(!full_errors&&!receiver.bad&&max_control_us<50000);
 if(records)assert(first_complete[0]&&first_complete[1]&&first_complete[0]<20000000&&first_complete[1]<20000000);'''
        code=PRE+producers+'\n'+senders+TAIL.replace('CHECK',checks)
        cpp=out/(label+'.cpp');p.write(cpp,code)
        # Build without executing: argv/CSV belongs to each explicit scenario.
        import shutil
        cmd=[shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
             '-Wno-unused-function','-Wno-misleading-indentation','-Wno-missing-field-initializers',
             '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(cpp),'-o',str(cpp.with_suffix('.exe'))]
        proc=subprocess.run(cmd,capture_output=True,text=True);p.write(out/(label+'_build.log'),proc.stdout+proc.stderr);proc.check_returncode()
        result[label]=cpp.with_suffix('.exe')
    return result


def hmi_function():
    src=p.read(p.OUT/'web_hmi/server.py');tree=ast.parse(src)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('current_crc32c','with_shunt_currents')]
    ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'release_HMI','exec'),ns)
    return ns['with_shunt_currents']


def run_case(out,exe,label,args,decode):
    csv=out/(label+'.jsonl')
    proc=subprocess.run([str(exe),*[str(v) for v in args],str(csv)],capture_output=True,text=True)
    p.write(out/(label+'_run.log'),proc.stdout+proc.stderr);proc.check_returncode()
    result=json.loads(proc.stdout);bad=0;quality_missing=0;total=0;last=None
    for line in p.read(csv).splitlines():
        row=json.loads(line);age=row['ages'];hexes=row['packets']
        s=dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],mc_age_ms=0,
            mc_current_age_ms=age[0],mc_current_detail_age_ms=age[1],mc_current_quality_age_ms=age[2],
            mc_current_packet_hex=hexes[0],mc_current_detail_hex=hexes[1],mc_current_quality_hex=hexes[2])
        got=decode(s);bad+=got['mc_current_zero_ready']!=1
        quality_missing+=got['mc_current_zero_stable']!=3;total+=1;last=s
    result.update(HMI_samples=total,HMI_autonull_missing=bad,HMI_quality_missing=quality_missing)
    if label.startswith('candidate'):
        assert not bad and not quality_missing,(label,result)
        # Freshness remains real: loss of ALL normal packets must still fail.
        stale=dict(last,mc_current_age_ms=750,mc_current_detail_age_ms=1500,mc_current_quality_age_ms=1500)
        assert decode(stale)['mc_current_zero_ready']==0
        corrupt=dict(last)
        for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex'):
            raw=bytearray.fromhex(corrupt[key]);raw[15]^=1;corrupt[key]=raw.hex()
        assert decode(corrupt)['mc_current_zero_ready']==0
    return result


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    programs=compile_variants(out);decode=hmi_function();results={}
    cases=[(50000,0,100,0,0),(50000,0,100,1,0),(20000,1000,100,1,0),
        (33000,1900,250,1,0),(40000,4300,1000,1,0),(50000,17000,2000,1,0),
        (100000,4300,1000,1,0),(50000,17000,1000,1,0xfffff000)]
    results['baseline_preflight']=run_case(out,programs['baseline'],'baseline_preflight',cases[0],decode)
    results['baseline_full_bulk']=run_case(out,programs['baseline'],'baseline_full_bulk',cases[1],decode)
    assert any(results[n]['HMI_autonull_missing'] or results[n]['HMI_quality_missing'] for n in results),'Regression not reproduced'
    for i,case in enumerate(cases):
        name='candidate_'+str(i);results[name]=run_case(out,programs['candidate'],name,case,decode)
    from test_foc_update_latency_fix import function
    for name in ('ma_native_fast','fe_profile_tick','fe_profile_service','ma_estimate_publish','ma_fail_at'):
        assert function(p.read(p.BASE/'nucleo/Src/multi_native.c'),name)==function(p.read(p.OUT/'nucleo/Src/multi_native.c'),name)
    assert p.sha(p.BASE/'nucleo/Inc/motor_control.h')==p.sha(p.OUT/'nucleo/Inc/motor_control.h')
    assert p.sha(p.BASE/'nucleo/Inc/foc_experiment.h')==p.sha(p.OUT/'nucleo/Inc/foc_experiment.h')
    # The only HMI change is the release identity, never stale-data acceptance.
    a=p.read(p.BASE/'web_hmi/server.py').replace('2026111601',str(p.NEW[0])).replace('2026111602',str(p.NEW[1]))
    assert a==p.read(p.OUT/'web_hmi/server.py')
    report=dict(passed=True,hardware_commands=0,results=results,
        source_scope='Actual normal packet producer, six actual page senders and arbiter, real Uno current receiver and release HMI. Other bulk record payload readiness and115200baud TX/foreground timing simulated.',
        ordinary_receiver_freshness_750_1500_unchanged=True,no_faked_zero_ready=True,
        wrong_CRC_and_stale_negative_controls=True,observer_math_and_4000_2ms_guards_unchanged=True,
        HAL_ms_wrap_case=True,packet_sequence_wrap_tested=True,new_target_cycles_measured=False,
        RPC_scheduler_and_physical_UART_IRQ_not_emulated=True)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,baseline_missing=[results[n]['HMI_autonull_missing'] for n in ('baseline_preflight','baseline_full_bulk')],candidate_cases=len(cases),
        candidate_max_gaps_us=[max(results['candidate_'+str(i)][k] for i in range(len(cases))) for k in ('summary_gap_us','detail_gap_us','quality_gap_us')],hardware_commands=0)))


if __name__=='__main__':main()
