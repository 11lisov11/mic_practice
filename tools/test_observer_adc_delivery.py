"""Replay real page senders, capture/transport/decoder and saved NIS; no devices."""
import ast,json,math,subprocess
import prepare_observer_adc_delivery as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def scheduler(out):
    prefix=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
enum{UV3_FRAME=43,UNO_TX_TAG_DIAG=0,HAL_OK=0};
static const unsigned MIC_NUCLEO_FW_BUILD_ID=2026111602;
static struct {unsigned head,tail,hard_error;} mic_uart_tx;
static struct {bool command_enabled;} uno_link;
static bool mic_last_control_reply_safe_off=true,MOE;
static void* TIM1;
static bool LL_TIM_IsEnabledAllOutputs(void*){return MOE;}
static double now_us,next_done;
static unsigned delivered[10],page_mask[2][64],first_complete[2],full_errors;
static uint8_t queue[4][43];
static void drain(){while(mic_uart_tx.head!=mic_uart_tx.tail&&next_done<=now_us){
 auto*p=queue[mic_uart_tx.tail&3];unsigned type=p[2];++delivered[type];
 if(type==2||type==4){unsigned row=type==2?0:1;page_mask[row][p[5]]=1;
  unsigned n=0;for(unsigned i=0;i<(row?35:62);++i)n+=page_mask[row][i];
  if(n==(row?35U:62U)&&!first_complete[row])first_complete[row]=(unsigned)now_us;}
 ++mic_uart_tx.tail;next_done+=430000000.0/115200;}}
static int uno_tx_submit(const uint8_t*p,unsigned){
 if(mic_uart_tx.head-mic_uart_tx.tail>=4){++full_errors;return 1;}
 bool empty=mic_uart_tx.head==mic_uart_tx.tail;
 memcpy(queue[mic_uart_tx.head&3],p,43);++mic_uart_tx.head;
 if(empty)next_done=now_us+430000000.0/115200;
 return 0;}
static int ma_observer_trace_packet(uint8_t*p,unsigned,unsigned page){memset(p,0,43);p[2]=2;p[5]=page;return 1;}
static int mic_current_peak_packet(uint8_t*p,unsigned page,unsigned){memset(p,0,43);p[2]=4;p[5]=page;return 1;}
static unsigned last[10];
static void other(unsigned id,unsigned now,unsigned period,bool loose=false){
 if(MOE||uno_link.command_enabled||mic_uart_tx.hard_error||now-last[id]<period)return;
 if(!loose&&mic_uart_tx.head-mic_uart_tx.tail>1)return;
 uint8_t p[43]={};p[2]=id;if(uno_tx_submit(p,0)==HAL_OK)last[id]=now;}
static void mic_send_repeat_meta(unsigned now){other(0,now,500);}
static void mic_send_boot_page(unsigned now){other(1,now,500);}
static void mic_send_break_page(unsigned now){other(3,now,200,true);}
static void mic_send_noise_page(unsigned now){other(5,now,20);}
static void mic_send_identification(unsigned now){other(6,now,250);}
static void control(unsigned now){
 uint8_t p[43]={};p[2]=7;assert(!uno_tx_submit(p,0));
 if(now-last[8]>=100&&mic_uart_tx.head-mic_uart_tx.tail<=1){
  p[2]=8;assert(!uno_tx_submit(p,0));assert(!uno_tx_submit(p,0));last[8]=now;}
 if(now-last[9]>=200&&mic_uart_tx.head-mic_uart_tx.tail<=1){p[2]=9;assert(!uno_tx_submit(p,0));last[9]=now;}
}
'''
    outputs={}
    for label,folder in [('legacy',p.BASE),('candidate',p.OUT)]:
        src=p.read(folder/'nucleo/Src/main.c')
        functions='\n'.join(function(src,n) for n in ('mic_send_observer_page','mic_send_peak_page'))
        if label=='candidate':functions+='\n'+function(src,'mic_send_bulk_page')
        legacy='mic_send_repeat_meta(ms);mic_send_boot_page(ms);mic_send_observer_page(ms);mic_send_break_page(ms);mic_send_peak_page(ms);mic_send_noise_page(ms);mic_send_identification(ms);'
        tail=r'''
int main(int argc,char**argv){
 unsigned cadence=argc>1?(unsigned)atoi(argv[1]):50000,phase=argc>2?(unsigned)atoi(argv[2]):0;
 for(unsigned us=0;us<8000000;us+=100){now_us=us;drain();unsigned ms=us/1000;
  if((us+phase)%cadence==0){control(ms);LEGACY}
  NEW
 }
 printf("{\"observer_pages_delivered\":%u,\"ADC_pages_delivered\":%u,\"observer_complete_us\":%u,\"ADC_complete_us\":%u,\"control_replies\":%u,\"queue_full\":%u}\n",delivered[2],delivered[4],first_complete[0],first_complete[1],delivered[7],full_errors);
 CHECK
 // Gate independent of the records' readiness.
 MOE=true;auto h=mic_uart_tx.head;GATE assert(mic_uart_tx.head==h);
}
'''.replace('LEGACY',legacy if label=='legacy' else '').replace('NEW','mic_send_bulk_page(ms);' if label=='candidate' else '')
        tail=tail.replace('CHECK', 'assert(delivered[2]>0&&delivered[4]==0);' if label=='legacy' else
            'assert(first_complete[0]&&first_complete[1]&&first_complete[0]<6000000&&first_complete[1]<6000000);assert(!full_errors);')
        tail=tail.replace('GATE','mic_send_bulk_page(100000);' if label=='candidate' else 'mic_send_observer_page(100000);mic_send_peak_page(100000);')
        outputs[label]=json.loads(common.compile_run(out,'scheduler_'+label,prefix+functions+tail))
        if label=='candidate':
            extras=[]
            for cadence,phase in ((20000,0),(33000,1000),(40000,1900),(50000,17000),(100000,4300)):
                r=subprocess.run([str(out/'scheduler_candidate.exe'),str(cadence),str(phase)],capture_output=True,text=True)
                p.write(out/f'scheduler_{cadence}_{phase}.log',r.stdout+r.stderr);r.check_returncode()
                extras.append(dict(cadence_us=cadence,phase_us=phase,**json.loads(r.stdout)))
            outputs['candidate_cadence_phase_cases']=extras
    return outputs


def capture(out):
    pre=r'''
#include <cassert>
#include <cstdio>
#include "peak_core.h"
#include "peak_wire.h"
'''
    code=pre+r'''
static pc_sample sample(unsigned n){pc_sample s={};s.cycles=n*10625;s.pair=0;s.next_pair=0;s.arr=5312;s.raw[0]=2048;s.raw[1]=2048;
 for(unsigned i=0;i<4;++i)s.offset[i]=2048;return s;}
int main(){
 pc_capture c={};for(unsigned n=0;n<30;++n){auto s=sample(n);pc_push(&c,&s,n,1,1,20);}
 pc_request_observer(&c);for(unsigned n=30;n<37;++n){auto s=sample(n);pc_push(&c,&s,n,1,0,20);}
 assert(c.frozen&&c.blob.header.flags==PC_OBSERVER&&c.count==12);
 c.blob.header.firmware=2026111602;c.blob.header.crc=pc_crc((uint8_t*)&c.blob);
 auto before=c;pc_request_observer(&c);auto s=sample(100);pc_push(&c,&s,100,1,1,900);
 assert(!memcmp(&c,&before,sizeof(c)));
 FILE*f=fopen("TRACE_PATH","wb");assert(f);assert(fwrite(&c.blob,1,1024,f)==1024);fclose(f);
 pc_receiver rx={};
 for(unsigned page=0;page<35;++page){uint8_t p[43]={0x55,0xaa,0xd8,1,1,(uint8_t)page,35};
  p[7]=page==34?4:30;memcpy(p+8,((uint8_t*)&c.blob)+30*page,p[7]);p[38]=1;uv3_seal(p);
  assert(pc_receive(&rx,p,2026111602,true,100));}
 assert(rx.complete&&!memcmp(rx.data,&c.blob,1024));
 pc_capture shortc={};pc_request_observer(&shortc);
 for(unsigned n=0;n<3;++n){auto s=sample(n);pc_push(&shortc,&s,n,n<2,1,1);}
 assert(shortc.frozen&&shortc.blob.header.flags==(PC_OBSERVER|PC_SHORT));
 pc_capture threshold={};for(unsigned n=0;n<8;++n){auto s=sample(n);pc_push(&threshold,&s,n,1,1,626);}
 assert(threshold.frozen&&threshold.blob.header.flags==PC_PEAK);
 pc_capture no={};for(unsigned n=0;n<5;++n){auto s=sample(n);pc_push(&no,&s,n,n<4,1,20);}
 assert(no.frozen&&no.blob.header.flags==PC_NO_PEAK);
 puts("{\"capture_requests\":true,\"frozen_immutable\":true,\"threshold626_unchanged\":true,\"raw1024_wire_roundtrip\":true}");
}
'''.replace('TRACE_PATH',(out/'observer_loss_ADC.bin').as_posix())
    result=json.loads(common.compile_run(out,'observer_loss_ADC',code))
    source=p.read(p.OUT/'web_hmi/server.py');tree=ast.parse(source)
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('current_crc32c','decode_adc_peak_hex')]
    ns={};exec(compile(ast.Module(body=funcs,type_ignores=[]),'release_ADC_decoder','exec'),ns)
    raw=(out/'observer_loss_ADC.bin').read_bytes();d=ns['decode_adc_peak_hex'](raw.hex(),p.NEW[1])
    assert d['observer_validity_trigger'] and not d['peak_seen'] and d['sample_count']==12
    assert len([s for s in d['samples'] if s['is_trigger']])==1
    for bad in (raw[:-1],bytes([raw[0]^1])+raw[1:]):
        try:ns['decode_adc_peak_hex'](bad.hex(),p.NEW[1])
        except ValueError:pass
        else:raise AssertionError('corrupted ADC capture accepted')
    p.write(out/'observer_loss_ADC_decoded.json',json.dumps(d,indent=2)+'\n')
    result['release_decoder_CRC_and_cause_verified']=True
    return result


def main():
    common.p=p;out=p.OUT/'verification';out.mkdir(exist_ok=True)
    record=p.BASE/'powered_FOC_5Hz_r1/saved_record_analysis_r1/observer_trace_decoded.json'
    d=json.loads(p.read(record));first=d['first_loss'];parts=[e*e/s for e,s in zip(first['innovation_A'],first['innovation_variance_A2'])]
    assert first['reason_mask']==32 and first['steps']==501
    assert abs(sum(parts)-first['nis'])<1e-5
    assert parts[1]/sum(parts)>.99 and first['flux_wb']>.125
    assert first['control_sample_sequence']==first['observer_sample_sequence']
    assert first['control_adc_cycles']==first['observer_adc_cycles']==first['bin_cycles']
    expected=p.read(p.BASE/'nucleo/Inc/motor_control.h')
    assert p.read(p.OUT/'nucleo/Inc/motor_control.h')==expected
    for name in ('ma_native_fast','fe_profile_tick','fe_profile_service','ma_estimate_publish','ma_fail_at'):
        assert function(p.read(p.BASE/'nucleo/Src/multi_native.c'),name)==function(p.read(p.OUT/'nucleo/Src/multi_native.c'),name)
    scheduling=scheduler(out);captures=capture(out)
    # Execute the actual native recorder with controlled states: only the first
    # loss after valid data requests capture; it never changes NIS or validity.
    pre=r'''
#include <cassert>
#include <cstdio>
#include "foc_experiment.h"
#include "multi_native.h"
#include "observer_trace_core.h"
static ma_motor model=FE_ESTIMATED_MOTOR;static ma_observer observer;
static od_capture observer_trace;static int running=1,selected=MA_FOC,run_fault;
static struct{unsigned CYCCNT;} timer;static auto DWT=&timer;static int requests;
static bool LL_TIM_IsEnabledAllOutputs(void*){return true;}static void*TIM1;
static int fe_profile_allowed(unsigned){return 1;}
static float ma_amps(int16_t c){return c*(3.3f/(4095*.04f*2.1f));}
void mic_current_request_observer_capture(){++requests;}
'''
    src=p.read(p.OUT/'nucleo/Src/multi_native.c')
    code=pre+function(src,'ma_observer_record')+r'''
static void push(unsigned step,float nis){observer.steps=step;observer.nis=nis;
 observer.x[2]=.25f;ma_current_sample s={};
 ma_observer_record(&s,1,1,1,0,0,0,0,1,0,0,.001f,0,1);}
int main(){push(499,100);assert(!requests);push(500,1);assert(!requests);
 push(501,38.9578f);assert(requests==1);auto old=observer_trace.blob.first_loss;
 for(unsigned n=502;n<550;++n)push(n,38);
 assert(requests==1&&!memcmp(&old,&observer_trace.blob.first_loss,sizeof(old)));
 assert(observer.nis==38&&observer.steps==549&&!run_fault);
 puts("{\"actual_native_recorder\":true,\"first_loss_only\":true,\"no_state_or_NIS_change\":true}");}
'''
    recorder=json.loads(common.compile_run(out,'native_observer_capture_request',code))
    from release_observer_decoder import load_decoder
    decoded=load_decoder(p.OUT)((p.BASE/'powered_FOC_5Hz_r1/saved_record_analysis_r1/observer_trace.bin').read_bytes().hex(),2026111504)
    assert decoded==d,'Matching release decoder changed the saved observer record'
    r=dict(passed=True,hardware_commands=0,scheduler=scheduling,capture=captures,native_recorder=recorder,
        saved1832_observer_decoder_regression=True,
        saved_NIS=dict(steps=501,NIS=first['nis'],components=parts,beta_fraction=parts[1]/sum(parts),
            beta_error_A=first['innovation_A'][1],input_timestamps_match=True,reason='OD_NIS',
            physical_cause_identifiable_from_sparse_record=False),
        observer_and_controller_math_byte_identical=True,thresholds_changed=False,
        fast_timed_body_unchanged=True,CPU_4000_proven_on_new_target=False,
        scheduler_scope='Two actual production page-sender functions and actual new arbiter; competing stream readiness/queue timing simulated at115200baud. Not a measured UART timeline.',
        diagnostic_request_does_not_modify_validity_or_faults=True,
        no_motor_commands=True,old_failed_records_preserved=True)
    p.write(out/'report.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))


if __name__=='__main__':main()
