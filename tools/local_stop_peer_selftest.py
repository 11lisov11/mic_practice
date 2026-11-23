"""Verify the exact diagnostic and snapshot peer headers of the prepared pair."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from prepare_ipm_break_wifi import source_hashes
from prepare_unoq_local_stop_peer import BASE, PEER, sketch, diagnostics, wire

PROGRAM=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include "nucleo_fault_diagnostics.h"
#include "break_wire.h"
int main() {
 unsigned checks=0;
 auto check=[&](bool v){++checks;assert(v);};
 uint8_t reply[UV3_FRAME]={}; reply[11]=0x94;reply[13]=10;
 reply[15]=4;reply[27]=4;
 auto d=decode_nucleo_fault_diagnostics(reply,true,2026101203);
 check(d.valid && d.reason==4 && d.current_faults==4 && d.occurred_faults==4);
 check(!decode_nucleo_fault_diagnostics(reply,true,2026101204).valid);
 check(!decode_nucleo_fault_diagnostics(reply,false,2026101203).valid);
 reply[11]=0x9f;check(!decode_nucleo_fault_diagnostics(reply,true,2026101203).valid);
 reply[11]=0x98;d=decode_nucleo_fault_diagnostics(reply,true,2026101203);
 check(d.valid && d.reason==8);
 uint8_t record[BW_BYTES]={},packet[UV3_FRAME];bw_receiver rx{};
 check(BW_NUCLEO_BUILD==2026101203);
 for(unsigned p=0;p<BW_PAGES;++p) {
   bw_packet(packet,record,0,p);
   check(bw_u32(packet+6)==2026101203);
   check(bw_receive(&rx,packet,2026101203,true,p));
 }
 check(rx.complete[0] && rx.good_pages==4 && rx.bad_pages==0);
 check(!bw_receive(&rx,packet,2026101102,true,10));
 check(!bw_receive(&rx,packet,2026101203,false,10));
 std::printf("checks=%u\n",checks);
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uno',type=Path,required=True);p.add_argument('--nucleo',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True);a=p.parse_args()
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    uno=a.uno/'UNOQ_MOTOR';m=json.loads((a.uno/'manifest.json').read_text())
    assert source_hashes(uno)==m['source_sha256'] and source_hashes(BASE)==m['baseline_sha256']
    for name,fn in (('UNOQ_MOTOR.ino',sketch),('nucleo_fault_diagnostics.h',diagnostics),('break_wire.h',wire)):
        assert (uno/name).read_text()==fn((BASE/name).read_text())
    assert (uno/'break_wire.h').read_bytes()==(a.nucleo/'nucleo/Inc/break_wire.h').read_bytes()
    compiler=shutil.which('g++');assert compiler
    program=PROGRAM.replace('2026101204','__FUTURE__').replace('2026101203',str(PEER)).replace('__FUTURE__',str(PEER+1))
    cpp=out/'peer.cpp';cpp.write_text(program);exe=cpp.with_suffix('.exe')
    subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(uno),str(cpp),'-o',str(exe)],check=True,capture_output=True,text=True)
    r=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    # Negative control: the installed 1108 header rejects the new peer ID.
    old=out/'old_decoder.cpp'
    old.write_text('#include "nucleo_fault_diagnostics.h"\nint main(){uint8_t p[39]={};p[11]=0x94;return decode_nucleo_fault_diagnostics(p,true,'+str(PEER)+').valid?1:0;}\n')
    oldexe=old.with_suffix('.exe')
    subprocess.run([compiler,'-std=c++17','-I',str(BASE),str(old),'-o',str(oldexe)],check=True,capture_output=True,text=True)
    subprocess.run([str(oldexe)],check=True,capture_output=True,text=True)
    report=dict(pass_=True,checks=r.stdout.strip(),old_decoder_rejection_reproduced=True,
                source_sha256=m['source_sha256'],control_logic_unchanged=True,hardware_commands=0,
                nucleo_snapshot_header_matches=True)
    report['pass']=report.pop('pass_')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
