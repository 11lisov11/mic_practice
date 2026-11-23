"""Test actual working Nucleo handlers, corruption recovery and power loss offline."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from production_mcsdk_link_dynamic_selftest import PREAMBLE, CASES, generate
from prepare_uart_recovery_pair import ROOT, BASE, transport
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha, write
from local_stop_fixture_selftest import body
from ipm_break_wifi_selftest import load_module

EXTRA = r'''
bool local_stop = false;
volatile unsigned mic_local_stop_latched, mic_break_start_window;
bool mic_last_control_reply_safe_off;
bool mic_local_stop_blocked() { return local_stop; }
bool mic_local_stop_clear() { if(local_stop) return false; return true; }
struct mic_break_context_t { uint32_t tick; int16_t ref; uint32_t state;
  uint16_t current, occurred, bus; int16_t temp; uint8_t seq; };
void mic_break_publish_context(const mic_break_context_t *) {}
uint8_t mock_read_rdr() { uart_registers.ISR &= ~UART_FLAG_RXNE; return (uint8_t)uart_registers.RDR; }
'''

TESTS = r'''
void check(bool v,const char *name) { ++tests;if(!v){std::fprintf(stderr,"FAIL %s\n",name);std::exit(1);} }
using Frame = std::array<uint8_t,UV3_FRAME>;
Frame packet(unsigned seq,uint8_t flags=0,uint8_t mode=0,unsigned hz=0) {
 Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=UV3_VERSION;f[3]=flags;f[4]=mode;f[5]=(uint8_t)seq;
 for(unsigned i=0;i<4;++i) { f[6+i]=(uint8_t)(hz>>(8*i)); }
 uv3_seal(f.data());return f;
}
void feed(Frame f,int ne=-1) {
 peer_expect(f[5],f[3]==8);
 for(unsigned i=0;i<f.size();++i) {
  uart_registers.ISR=UART_FLAG_RXNE|((int)i==ne ? UART_FLAG_NE : 0);
  uart_registers.RDR=f[i];USART1_IRQHandler();
 }
 uno_link_poll();
}
void reset(bool warm=true,unsigned seq=1,uint32_t tick=100) {
 now_ms=tick;bus_v=310;mc_fault=mc_occurred=0;motor_state=IDLE;
 test_timer={};local_stop=false;mic_local_stop_latched=0;mic_break_start_window=0;
 start_succeeds=tx_succeeds=true;starts=stops=ramps=0;ramp_target=0;
 uno_link_init();uno_link.softstart_ready=true;
 if(warm)for(unsigned i=0;i<3;++i){now_ms+=50;feed(packet(seq+i));}
}
void running() {reset();now_ms+=50;feed(packet(4,1,3,5000));check(motor_state==RUN,"start");}
void run() {
 // Per-byte flags travel through the ACTUAL ISR and ring, not directly to the parser.
 for(unsigned pos=0;pos<UV3_FRAME;++pos) {
  reset();now_ms+=50;feed(packet(4,1,3,5000),(int)pos);
  check(starts==1 && !uno_link.fault_latched && uno_transport.accepted_noise_frames==1,"intact NE START at every byte");
  check(uno_link.bad_count==0,"accepted NE never presented as fatal bad frame");
  check(peer::g_bp_ne_accepted==1 && peer::g_bp_fault_code==0,"Uno receives intact NE START reply");
 }
 running();for(unsigned seq=5;seq<=7;++seq){now_ms+=50;feed(packet(seq,1,3,5000));}
 now_ms+=50;feed(packet(8,1,3,6000),6);
 check(!uno_link.fault_latched && ramp_target==RPM_2_SPEED_UNIT(360),"intact NE frequency change");
 running();auto last=uno_transport.last_valid_ms;
 uno_consume_sample(0x42,UV3_NE);
 check(!uno_link.fault_latched && uno_transport.last_valid_ms==last,"stray NE does not refresh watchdog");
 now_ms+=50;feed(packet(5,1,3,5000));check(!uno_link.fault_latched,"next fresh command after stray NE");
 // Finite exhaustive sweep of all single-bit edits in payload and CRC.
 for(unsigned pos=0;pos<UV3_FRAME;++pos)for(unsigned bit=0;bit<8;++bit) {
  running();Frame bad=packet(5,1,3,6000);bad[pos]^=(uint8_t)(1U<<bit);
  const auto before_ramps=ramps;const auto deadline=uno_transport.last_valid_ms;
  now_ms+=50;feed(bad);
  check(!uno_link.fault_latched && ramps==before_ramps && uno_transport.last_valid_ms==deadline,"corruption cannot apply a command or feed watchdog");
  check(uno_transport.dropped_frames==1 && uno_link.bad_count==0,"discard has separate visible counter");
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one observed loss permits bounded fresh sequence gap");
  check(peer::g_bp_recovered_drops==1 && peer::g_bp_bad_cnt==0,"Uno decodes recovery counter separately from fatal errors");
 }
 running();now_ms+=50;Frame bad=packet(5,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(4,1,3,5000));check(uno_link.fault_latched,"loss never permits duplicate/replay");
 running();now_ms+=50;bad=packet(5,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(7,1,3,6000));check(uno_link.fault_latched,"one loss cannot permit a two-frame gap");
 running();now_ms+=50;feed(packet(6,1,3,6000));check(uno_link.fault_latched,"unobserved sequence gap is rejected");
 // Sliding window is shared by accepted noise and discarded packets.
 running();for(unsigned seq=5;seq<=7;++seq){now_ms+=50;bad=packet(seq,1,3,6000);bad[8]^=1;feed(bad);}
 check(uno_link.fault_latched && motor_state==IDLE,"third damaged packet in 1s latches off");
 now_ms+=50;feed(packet(8,1,3,5000));check(starts==1 && uno_link.fault_latched,"clean ENABLE cannot restart a latched failure");
 running();last=uno_transport.last_valid_ms;now_ms=last+300;
 uno_link_poll();check(!uno_link.fault_latched,"watchdog at 300ms");
 ++now_ms;uno_link_poll();check(uno_link.fault_latched && motor_state==IDLE,"watchdog at 301ms");
 for(unsigned flags:{UV3_PE,UV3_FE,UV3_ORE}) {
  running();uno_consume_sample(0,flags);
  check(uno_link.fault_latched && motor_state==IDLE,"hard UART errors still immediate");
 }
 running();uart_registers.ISR=UART_FLAG_NE;USART1_IRQHandler();uno_link_poll();
 check(uno_link.fault_latched,"NE with no associated RX byte remains hard failure");
 running();local_stop=true;uno_link_poll();check(uno_link.fault_latched && motor_state==IDLE,"local stop wins over transport recovery");
 // Actual MCSDK/bus branches keep UART alive after losing high voltage.
 running();mc_fault=mc_occurred=4;motor_state=FAULT_NOW;bus_v=10;uno_link_poll();
 auto before=uno_link.good_count;now_ms+=50;feed(packet(5));
 check(uno_link.good_count==before+1 && uv3_crc_ok(reply.data()),"STOP reply continues after loss of power");
 check(uno_link.first_current_faults==4 && uno_link.first_uart_errors==0 && reply[9]!=0,"undervoltage visible separately from UART");
 check(peer::g_mc_diagnostics.valid && peer::g_mc_diagnostics.current_faults==4 && peer::g_mc_diagnostics.uart_errors==0 && peer::g_bp_vdc==10,"Uno receives real undervoltage diagnostic reply");
 check(uno_transport.fault==UV3_WAIT && !uno_link.command_enabled,"power loss does not invent transport failure");
 mc_fault=0;motor_state=FAULT_OVER;bus_v=310;now_ms+=4000;feed(packet(6,1,3,5000));
 check(starts==1 && uno_link.fault_latched,"power restoration never silently restarts");
 for(unsigned pos=0;pos<UV3_FRAME;++pos) {
  running();now_ms+=50;auto damaged=packet(5,1,3,6000);
  for(unsigned i=0;i<UV3_FRAME;++i)if(i!=pos)uno_consume_sample(damaged[i],0);
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one deleted byte resynchronizes next command");
  running();now_ms+=50;damaged=packet(5,1,3,6000);
  for(unsigned i=0;i<UV3_FRAME;++i){if(i==pos)uno_consume_sample(0x42,0);uno_consume_sample(damaged[i],0);}
  now_ms+=50;feed(packet(6,1,3,6000));
  check(!uno_link.fault_latched && uno_link.last_seq==6,"one inserted byte resynchronizes next command");
 }
 // Partial packets never feed either watchdog; next clean packet may recover.
 running();auto f=packet(5,1,3,5000);for(unsigned i=0;i<12;++i)uno_consume_sample(f[i],0);
 last=uno_transport.last_valid_ms;now_ms+=16;uno_link_poll();
 check(!uno_link.fault_latched && uno_transport.last_valid_ms==last,"partial packet expires without feeding watchdog");
 now_ms+=34;feed(packet(6,1,3,5000));check(!uno_link.fault_latched,"clean recovery after partial deadline");
 // Noise on CLEAR may never acknowledge a physical/transport fault.
 running();uno_latch_fault_reason(UNO_FAULT_ESTOP,UNO_DIAG_ESTOP);
 now_ms+=50;feed(packet(5,8,0,0),6);check(uno_link.fault_latched,"noisy CLEAR cannot release latch");
 now_ms+=50;feed(packet(6,8,0,0));check(!uno_link.fault_latched && !uno_link.command_enabled,"clean explicit CLEAR releases without START");
 // Timer wrap and sequence wrap retain the same recovery semantics.
 reset(true,252,UINT32_MAX-300);now_ms+=50;feed(packet(255,1,3,5000));
 now_ms+=50;bad=packet(0,1,3,6000);bad[8]^=1;feed(bad);
 now_ms+=50;feed(packet(1,1,3,6000));check(!uno_link.fault_latched,"loss across sequence/time wrap");
 std::printf("{\"pass\":true,\"assertions\":%u,\"single_bit_corruptions\":%u,\"ne_byte_positions\":%u,\"hardware_commands\":0}\n",tests,UV3_FRAME*8,UV3_FRAME);
}
int main(){run();}
'''

def peer_program(folder):
    source=(folder/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    functions=body(source,'nucleo_check_reply')+'\n'+body(source,'nucleo_uart_poll')
    declarations=[]
    for name in sorted(set(re.findall(r'\bg_\w+',functions))):
        match=re.search(r'(?m)^static[^\n;]*\b'+name+r'\b[^\n]*;',source)
        assert match,name
        declarations.append(match.group(0))
    constants=[]
    for name in sorted(set(re.findall(r'\b[A-Z][A-Z_0-9]+\b',functions))):
        match=re.search(r'(?m)^static const[^\n;]*\b'+name+r'\b[^\n]*;',source)
        if match:
            constants.append(match.group(0).replace('NUCLEO_MCSDK_ACIM_BACKEND = false','NUCLEO_MCSDK_ACIM_BACKEND = true'))
    return r'''
#include <deque>
#include "nucleo_fault_diagnostics.h"
#include "link_timing.h"
#include "break_wire.h"
#include "superseded_reply.h"
#include "uno_q_control.h"
namespace peer {
struct SerialStub { std::deque<uint8_t> bytes;
 int available(){return (int)bytes.size();} int read(){auto b=bytes.front();bytes.pop_front();return b;} } NUCLEO_SERIAL;
unsigned irq_lock(){return 0;} void irq_unlock(unsigned){}
uint32_t millis(){return ::now_ms;} uint32_t micros(){return ::now_ms*1000U;}
void enc_speed_update(uint16_t,bool,uint32_t){}
float bp_vdc_from_raw(uint16_t){return 0;} float bp_temp_voltage_from_raw(uint16_t){return 0;}
bool bp_temp_c_from_raw(uint16_t,float*){return false;} float bp_phase_voltage_from_raw(uint16_t){return 0;}
'''+'\n'.join(dict.fromkeys(constants+declarations))+'\n'+functions+r'''
}
void peer_expect(uint8_t seq,bool clear){peer::g_nucleo_waiting_seq=seq;peer::g_nucleo_waiting_rsp=true;peer::g_nucleo_waiting_clear=clear;}
void peer_receive(const uint8_t *data,unsigned size){
 for(unsigned i=0;i<size;++i) { peer::NUCLEO_SERIAL.bytes.push_back(data[i]); }
 peer::nucleo_uart_poll();
}
'''

def build_program(folder):
    source=(folder/'nucleo/Src/main.c').read_text()
    start=source.index('enum {',source.index('/* USER CODE BEGIN 0 */'))
    end=source.index('static void MX_USART1_UART_Init(void) {',start)
    block=source[start:end]
    match=re.search(r'static void mic_send_break_page\([^;]*?\)\s*\{',block)
    a,b=match.start(),match.end();depth=1
    while depth:
        depth+=(block[b]=='{')-(block[b]=='}');b+=1
    block=block[:a]+'static void mic_send_break_page(uint32_t) {}'+block[b:]
    block=block.replace('(uint8_t)huart1.Instance->RDR','mock_read_rdr()')
    baseline,_=generate(ROOT)
    macros=baseline[len(PREAMBLE):baseline.index('enum {')]
    mocks=PREAMBLE.replace('std::array<uint8_t, 32> reply;','std::array<uint8_t, UV3_FRAME> reply;')
    mocks=mocks.replace('std::memcpy(reply.data(), data, size); return tx_succeeds ? HAL_OK : 1;',
                        'std::memcpy(reply.data(), data, size); if(tx_succeeds) peer_receive(data,size); return tx_succeeds ? HAL_OK : 1;')
    manual_include='#include "manual_scalar_control.h"\n' if (folder/'nucleo/Inc/manual_scalar_control.h').exists() else ''
    if 'MC_HasRampCompletedMotor1()' in block:
        mocks += '\nbool MC_HasRampCompletedMotor1() { return true; }\n'
    return '#include "uart_v3_transport.h"\n'+manual_include+'void peer_receive(const uint8_t *,unsigned);\n'+mocks+peer_program(folder)+EXTRA+macros+block+TESTS

def main(folder,out):
    out.mkdir(parents=True,exist_ok=False)
    mf=json.loads((folder/'manifest.json').read_text())
    assert source_hashes(folder/'nucleo')==mf['nucleo_source_sha256']
    expected=transport((BASE/'nucleo/Inc/uart_v3_transport.h').read_text())
    advisory=mf.get('intact_ne_is_advisory',False)
    if advisory:
        from prepare_uart_advisory_ne_pair import advisory_policy
        expected=advisory_policy(expected)
    assert (folder/'nucleo/Inc/uart_v3_transport.h').read_text()==expected
    program=build_program(folder)
    if advisory:
        burst=r'''
 // CRC-correct single-NE packets must not spend damaged-packet recovery budget.
 running();
 for(unsigned seq=5;seq<=44;++seq){
  now_ms+=50;feed(packet(seq,1,3,5000),6);
  check(!uno_link.fault_latched && motor_state==RUN,"verified NE burst keeps validated command link alive");
 }
 check(uno_transport.accepted_noise_frames==40 && uno_transport.noise_used==0 && uno_transport.dropped_frames==0,
       "verified NE metadata remains visible and distinct from discarded data");
 now_ms+=50;auto corrupt=packet(45,1,3,6000);corrupt[8]^=1;feed(corrupt);
 check(!uno_link.fault_latched && uno_transport.dropped_frames==1,"true corruption retains its separate budget after NE burst");
 now_ms+=50;feed(packet(46,1,3,6000),10);
 check(!uno_link.fault_latched && uno_link.last_seq==46,"verified NE can recover an observed lost packet");
 auto committed=uno_transport.last_valid_ms;
 for(unsigned i=0;i<5;++i){now_ms=committed+50*(i+1);uno_consume_sample(0x42,UV3_NE);}
 now_ms=committed+301;uno_link_poll();
 check(uno_link.fault_latched && motor_state==IDLE,"unframed noise never becomes a verified command heartbeat");
'''
        program=program.replace(' // Per-byte flags travel',burst+'\n // Per-byte flags travel')
    unit=out/'actual_nucleo_control.cpp';unit.write_text(program)
    exe=unit.with_suffix('.exe')
    args=['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror','-I',str(folder/'nucleo/Inc'),'-I',str(folder/'UNOQ_MOTOR')]
    result=subprocess.run(args+[str(unit),'-o',str(exe)],capture_output=True,text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr);result.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True)
    (out/'run.log').write_text(run.stdout+run.stderr);run.check_returncode()
    report=json.loads(run.stdout)
    report.update(scope='Actual Nucleo ISR/ring/command handler/reply -> actual Uno full UART parser and decoder; HAL/MCSDK/BKIN acquisition mocked',
      hardware_validated=False,source_sha256=sha(folder/'nucleo/Src/main.c'),
      header_sha256=sha(folder/'nucleo/Inc/uart_v3_transport.h'),power_loss_reply_test=True,
      uno_source_sha256=sha(folder/'UNOQ_MOTOR/UNOQ_MOTOR.ino'))
    mod=load_module(folder/'web_hmi/server.py')
    data=mod.RpcBridge._parse_status_string('state=SAFE mode=VF pwm=0 fw_build=2026101413 mc_fw_build=2026101412 bp_recovered_drops=1 bp_bad=0 bp_bad_cnt=0 bp_transport_fault=0')
    assert data['mc_recovered_drops']==1 and data['mc_bad_cnt']==0
    report['hmi_recovery_counter_decode']=True
    calibration=ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/vbus_recalibration_preparation/original_vbus_calibration.json'
    baseline=ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/working_bus_on_1791997952551152700/first_status.json'
    status=json.loads(baseline.read_text())
    status.update(fw_build=mf['pair'][0],bp_fw_build=mf['pair'][1],mc_fw_build=mf['pair'][1],
      state='SAFE',state_code=0,pwm=0,estop=0,bp_fault=0,bp_status=1,bp_softstart_ready=1,
      bp_bad=0,bp_bad_cnt=0,bp_bad_integrity=0,bp_bad_sequence=0,bp_transport_fault=0,
      bp_age_ms=20,bp_rsp_age_ms=20,mc_age_ms=20,mc_rsp_age_ms=20,
      bp_vbus_age_ms=20,bp_temp_age_ms=20,vdc=319.,bp_vdc=319.,bp_vbus_raw=3190,
      bp_recovered_drops=1,bp_ne_observed=1,bp_ne_accepted=1,bp_ne_flags=4,freq_cmd=5.,freq=0.,link=True)
    for key,value in list(status.items()):
        if key.startswith('bp_'):status['mc_'+key[3:]]=value
    status=mod.with_motor_controller_aliases(status)
    points=mod.VbusCalibrationStore(str(calibration))
    assert points.is_valid(status)
    cfg=mod.HvArmConfig(enabled=True,min_vdc=250,max_vdc=360)
    assert mod.hv_arm_precheck(status,cfg,points.is_valid(status))[0]
    assert not mod.hv_arm_precheck(dict(status,fw_build=2026101411),cfg,True)[0]
    monitor=mod.HvRuntimeBadFrameMonitor()
    assert monitor.observe(status)[0]
    assert monitor.observe(dict(status,mc_recovered_drops=2,bp_recovered_drops=2))[0]
    report['new_pair_arm_and_separate_recovery_counter']=True
    # Negative controls prove that the new scenarios detect broken guards.
    original_header=(folder/'nucleo/Inc/uart_v3_transport.h').read_text()
    mutations={
      'CRC_removed':('return stored == uv3_crc32c(frame, UV3_PAYLOAD);','(void)stored; return true;'),
      'drop_refreshes_watchdog':('rx->last_drop_reason = reason;','rx->last_drop_reason = reason; rx->last_valid_ms = now_ms;'),
      'budget_three':('UV3_NE_BUDGET = 2,','UV3_NE_BUDGET = 3,'),
      'sequence_guard_removed':('advance == 0 || advance > (uint8_t)(rx->recoverable_losses + 1U)','advance == 255'),
    }
    outcomes=[]
    for name,(before,after) in mutations.items():
        assert original_header.count(before)==1,name
        target=out/name;target.mkdir();(target/'uart_v3_transport.h').write_text(original_header.replace(before,after))
        mutant=target/'actual_control.cpp';mutant.write_text(program);binary=mutant.with_suffix('.exe')
        built=subprocess.run(args+[str(mutant),'-o',str(binary)],capture_output=True,text=True)
        (target/'compile.log').write_text(built.stdout+built.stderr);built.check_returncode()
        broken=subprocess.run([str(binary)],capture_output=True,text=True)
        (target/'run.log').write_text(broken.stdout+broken.stderr)
        assert broken.returncode!=0 and 'FAIL ' in broken.stderr,name
        outcomes.append(dict(name=name,detected=True,failure=broken.stderr.strip()))
    report['mutations']=outcomes
    if advisory:
        target=out/'old_shared_NE_budget';target.mkdir()
        (target/'uart_v3_transport.h').write_text((ROOT/'artifacts/live_bench_20261014/uart_recovery_working_pair_r1/nucleo/Inc/uart_v3_transport.h').read_text())
        mutant=target/'actual_control.cpp';mutant.write_text(program);binary=mutant.with_suffix('.exe')
        built=subprocess.run(args+[str(mutant),'-o',str(binary)],capture_output=True,text=True)
        (target/'compile.log').write_text(built.stdout+built.stderr);built.check_returncode()
        broken=subprocess.run([str(binary)],capture_output=True,text=True)
        (target/'run.log').write_text(broken.stdout+broken.stderr)
        assert broken.returncode!=0 and 'FAIL verified NE burst' in broken.stderr
        report['old_shared_NE_budget_regression_detected']=True
        report['intact_ne_metadata_not_counted_as_damaged_packet']=True
    assert source_hashes(folder/'nucleo')==mf['nucleo_source_sha256']
    assert source_hashes(folder/'UNOQ_MOTOR')==mf['uno_source_sha256']
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();main(a.candidate.resolve(),a.outdir.resolve())
