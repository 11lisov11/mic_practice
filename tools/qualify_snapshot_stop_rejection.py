"""Show that bad_pages includes policy rejection of a CRC-valid diagnostic page."""
import argparse,json,subprocess
from pathlib import Path
from pwm_filter_hardware_session import sha

def main(package,out):
    out.mkdir(parents=True,exist_ok=False)
    header=package/'fixture/UNOQ_MOTOR/break_wire.h'
    program='''#include <cstdint>
#include <cstring>
#include <cassert>
#include <cstdio>
'''+f'#include "{header.as_posix()}"\n'+'''
int main(){
 bw_receiver rx{};uint8_t record[BW_BYTES]={},packet[UV3_FRAME];
 bw_packet(packet,record,0,0);
 assert(uv3_crc_ok(packet));
 assert(!bw_receive(&rx,packet,BW_NUCLEO_BUILD,false,100));
 assert(rx.bad_pages==1 && rx.good_pages==0 && !rx.complete[0]);
 assert(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,150));
 assert(rx.bad_pages==1 && rx.good_pages==1);
 for(unsigned page=1;page<BW_PAGES;++page){
  bw_packet(packet,record,0,page);assert(bw_receive(&rx,packet,BW_NUCLEO_BUILD,true,150+page));
 }
 assert(rx.complete[0] && rx.bad_pages==1);
 std::puts("CRC-valid page rejected while fresh-off predicate false; later accepted without changing policy");
}
'''
    unit=out/'valid_page_off_transition.cpp';unit.write_text(program)
    exe=unit.with_suffix('.exe');build=subprocess.run(['g++','-Ofast','-std=c++17',str(unit),'-o',str(exe)],capture_output=True,text=True)
    (out/'build.log').write_text(build.stdout+build.stderr);build.check_returncode()
    run=subprocess.run([str(exe)],capture_output=True,text=True);(out/'run.log').write_text(run.stdout+run.stderr);run.check_returncode()
    result=dict(pass_=True,hardware_commands=0,header_sha256=sha(header),crc_valid_page_can_increment_bad_pages=True,
       received_record_still_gated_by_fresh_off=True,firmware_modified=False,
       observed_reject_reason_proven=False,
       interpretation='Off-transition policy rejection is reproduced offline; no raw diagnostic UART page was captured during the physical run.')
    result['pass']=result.pop('pass_');(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',required=True,type=Path);p.add_argument('--outdir',required=True,type=Path)
    a=p.parse_args();main(a.package.resolve(),a.outdir.resolve())
