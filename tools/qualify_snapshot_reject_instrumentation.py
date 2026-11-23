"""Exercise actual byte parser and compare all assembler decisions to r4."""
import argparse,json,re,subprocess
from pathlib import Path
from ipm_break_wifi_selftest import WIRE_TESTS,load_module
from uart_v3_uno_peer_selftest import PREAMBLE,TESTS
from uno_reply_restart_selftest import function
from prepare_pwm_filter_pair import sha
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4'

def qualify(package,out):
    out.mkdir(parents=True,exist_ok=False);folder=package/'production/UNOQ_MOTOR'
    source=(folder/'UNOQ_MOTOR.ino').read_text()
    a=source.index('static bool nucleo_check_reply(');b=source.index('  const bool clear_ack',a)
    integrity=source[a:b]+'  return true;\n}\n'
    extra='''
#include "break_wire.h"
static bw_receiver g_break_wire;
uint8_t g_rx_rejected[UV3_FRAME];
uint32_t g_rx_rejected_ms=0,g_rx_poll_ms=0,g_rx_poll_gap_max_ms=0;
bool g_bp_mcsdk_telemetry=true,g_pwm_enabled=false;
uint8_t g_bp_status=1;
uint32_t g_bp_fw_build=BW_NUCLEO_BUILD,g_bp_last_rsp_ms=100;
'''
    control=TESTS.replace('int main()','int control_tests()').replace('cases,tests);\n}', 'cases,tests);\n return 0;\n}',1)
    observation='''
void observation_tests(){
 flush_partial();bw_reset(&g_break_wire);g_bp_status=0x63;g_pwm_enabled=true;g_bp_last_rsp_ms=65;
 uint8_t empty[BW_BYTES]={};Reply p{};bw_packet(p.data(),empty,0,0);
 const auto last=g_nucleo_last_rx_ms;g_nucleo_waiting_rsp=true;
 feed(p);
 check(g_break_wire.bad_pages==1 && g_break_wire.first_reject.valid,"first reject retained");
 const auto first=g_break_wire.first_reject;
 check(first.reason==BW_REJECT_NOT_FRESH_OFF && first.now_ms==100 && first.rsp_age_ms==35 &&
   first.bp_status==0x63 && first.pwm_enabled==1 && !first.fresh_off,"caller captures actual off-transition context");
 check(!memcmp(first.packet,p.data(),UV3_FRAME) && uv3_crc_ok(first.packet),"complete CRC-valid raw page retained");
 check(g_nucleo_last_rx_ms==last && g_nucleo_waiting_rsp,"reject cannot acknowledge control");
 p[15]^=1;const auto old_crc=g_nucleo_rx_bad_integrity;feed(p);
 check(g_nucleo_rx_bad_integrity==old_crc+1 && g_break_wire.bad_pages==2,"later corruption still counted");
 check(!memcmp(&first,&g_break_wire.first_reject,sizeof(first)),"later reject cannot overwrite first");
 bw_reset(&g_break_wire);check(!g_break_wire.first_reject.valid && g_break_wire.bad_pages==0,"peer reset clears diagnostic as before");
 std::printf("{\\"mc_break_reject_valid\\":\\"1\\",\\"mc_break_reject_code\\":\\"5\\",\\"mc_break_reject_packet_hex\\":\\"");
 for(unsigned i=0;i<UV3_FRAME;++i)std::printf("%02x",first.packet[i]);
 std::puts("\\"}");
}
'''
    program='#include <cstring>\n'+PREAMBLE+extra+integrity+function(source,'nucleo_uart_poll')+control+WIRE_TESTS+observation
    program+='\nint main(){control_tests();wire_tests();observation_tests();return 0;}\n'
    def run(name,code):
        unit=out/(name+'.cpp');unit.write_text(code);exe=unit.with_suffix('.exe')
        build=subprocess.run(['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror','-I',str(folder),str(unit),'-o',str(exe)],capture_output=True,text=True)
        (out/(name+'_build.log')).write_text(build.stdout+build.stderr);build.check_returncode()
        result=subprocess.run([str(exe)],capture_output=True,text=True)
        (out/(name+'_run.log')).write_text(result.stdout+result.stderr);result.check_returncode();return result.stdout
    parser=run('actual_parser',program)
    def bare(path):return '\n'.join(line for line in path.read_text().splitlines() if not line.startswith('#'))
    comparison='#include <cstdint>\n#include <cstring>\n#include <cassert>\n#include <cstdio>\n#include "uart_v3_transport.h"\n#define BW_NUCLEO_BUILD 2026101408UL\n'
    comparison+='namespace old {\n'+bare(BASE/'production/UNOQ_MOTOR/break_wire.h')+'\n}\n'
    comparison+='namespace candidate {\n'+bare(folder/'break_wire.h')+'\n}\n'
    comparison+='''
unsigned comparisons=0;
void same(old::bw_receiver &a,candidate::bw_receiver &b,const uint8_t *p,uint32_t peer,bool off,uint32_t now){
 auto x=old::bw_receive(&a,p,peer,off,now),y=candidate::bw_receive(&b,p,peer,off,now);
 assert(x==y && a.good_pages==b.good_pages && a.bad_pages==b.bad_pages);
 assert(!memcmp(a.stage,b.stage,sizeof(a.stage)) && !memcmp(a.data,b.data,sizeof(a.data)) &&
  !memcmp(a.complete,b.complete,sizeof(a.complete)) && !memcmp(a.received_ms,b.received_ms,sizeof(a.received_ms)));
 ++comparisons;
}
int main(){
 uint8_t r[old::BW_BYTES]={},p[UV3_FRAME];
 for(unsigned pos=0;pos<UV3_FRAME;++pos)for(unsigned bit=0;bit<8;++bit)for(unsigned seal=0;seal<2;++seal)
  for(unsigned context=0;context<4;++context){
   old::bw_receiver a{};candidate::bw_receiver b{};old::bw_packet(p,r,0,0);p[pos]^=uint8_t(1U<<bit);if(seal)uv3_seal(p);
   same(a,b,p,context&1 ? 0 : BW_NUCLEO_BUILD,context&2,100);
  }
 old::bw_put32(r,0x314b5242);old::bw_put32(r+4,2);old::bw_put32(r+8,old::BW_BYTES);old::bw_put32(r+16,0x80);old::bw_put32(r+88,1);
 for(unsigned mutation=0;mutation<100;++mutation){
  old::bw_receiver a{};candidate::bw_receiver b{};
  for(unsigned cycle=0;cycle<30;++cycle){
   old::bw_packet(p,r,cycle%2,cycle%4);
   if(mutation%3==1 && cycle%5==0){p[(mutation+cycle)%UV3_FRAME]^=1;uv3_seal(p);}
   same(a,b,p,BW_NUCLEO_BUILD,cycle%7!=0,(cycle*201U)+UINT32_MAX-2000U);
  }
 }
 std::printf("{\\"same_decisions\\":%u}\\n",comparisons);
}
'''
    differential=run('legacy_comparison',comparison)
    m=load_module(package/'production/web_hmi/server.py');checks=0
    actual_packet=json.loads(parser.splitlines()[-1])
    assert m.break_reject_status(actual_packet)['mc_break_reject_record_valid']==1
    checks+=1
    for code,label in {1:'FRAME_CRC',2:'HEADER',3:'PAGE_LAYOUT',4:'PEER_BUILD',5:'NOT_FRESH_OFF',6:'RESERVED',7:'PADDING',8:'DUPLICATE',9:'RECORD_CRC',10:'RECORD_ABI',11:'WINDOW_KIND'}.items():
        kv={'mc_break_reject_valid':'1','mc_break_reject_code':str(code),'mc_break_reject_packet_hex':actual_packet['mc_break_reject_packet_hex']}
        data=m.break_reject_status(kv);assert data['mc_break_reject_record_valid']==1 and data['mc_break_reject_reason']==label;checks+=1
    for change in ({'mc_break_reject_code':'99'},{'mc_break_reject_valid':'2'},{'mc_break_reject_pwm':'2'},
                   {'mc_break_reject_packet_hex':'ab'}, {'mc_break_reject_packet_hex':'gg'*43},{'mc_break_reject_ms':'-1'},
                   {'mc_break_reject_ms':'oops'},{'mc_break_reject_fresh_off':'2'}):
        assert m.break_reject_status(dict(kv,**change))['mc_break_reject_record_valid']==0;checks+=1
    assert m.break_reject_status({})['mc_break_reject_record_valid']==0;checks+=1
    report=dict(pass_=True,hardware_commands=0,actual_parser=[json.loads(x) for x in parser.splitlines()[:2]],
       actual_receiver_packet_hmi_decode_pass=True,actual_frame_hex_chars=len(actual_packet['mc_break_reject_packet_hex']),
       legacy_comparison=json.loads(differential),hmi_metadata_checks=checks,control_and_assembler_decisions_unchanged=True,
       first_rejection_not_overwritten=True,actual_parser_source_sha256=sha(folder/'UNOQ_MOTOR.ino'),header_sha256=sha(folder/'break_wire.h'),
       hmi_sha256=sha(package/'production/web_hmi/server.py'))
    report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True,type=Path);p.add_argument('--outdir',required=True,type=Path)
    a=p.parse_args();qualify(a.package.resolve(),a.outdir.resolve())
