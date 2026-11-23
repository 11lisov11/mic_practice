"""Exercise the actual dispatcher with interleaved currents and fatal UART pages."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

PREAMBLE=r'''
#include <cstdio>
#include <cstdlib>
#include "current_wire.h"
static ct_receiver g_current;
static urw_receiver g_uart_reject;
static bool g_bp_mcsdk_telemetry=true,g_pwm_enabled=false;
static uint32_t g_bp_last_rsp_ms=1000,g_bp_fw_build=CT_PEER_BUILD,g_bp_status=0;
static uint32_t millis(){return 1010;}
static unsigned checks;
static void check(bool okay){++checks;if(!okay){fprintf(stderr,"mixed wire %u failed\n",checks);exit(1);}}
'''
CASES=r'''
int main() {
 ct_reset(&g_current);urw_reset(&g_uart_reject);
 uv3_rx input={};input.fatal_reject_valid=true;input.fatal_reject.meta[1]=UV3_BAD_CRC;
 uint8_t record[UR_BYTES];ur_serialize(record,&input,CT_PEER_BUILD);
 check(ur_record_valid(record,CT_PEER_BUILD));
 const uint32_t crc=uv3_crc32c(record,UR_BYTES);
 uint8_t p[UV3_FRAME];
 for(unsigned page=0;page<URW_PAGES;++page) {
  memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=URW_VERSION;p[3]=page;p[4]=URW_PAGES;
  ur_put32(p+6,CT_PEER_BUILD);ur_put32(p+10,crc);
  unsigned start=page*URW_CHUNK,n=UR_BYTES-start;if(n>URW_CHUNK)n=URW_CHUNK;
  memcpy(p+14,record+start,n);uv3_seal(p);dispatch(p);
  check(g_uart_reject.good_pages==page+1);check(g_uart_reject.bad_pages==0);
  memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=CT_SUMMARY;p[4]=page+1;p[38]=1;
  ur_put32(p+6,CT_PEER_BUILD);uv3_seal(p);dispatch(p);
  check(g_current.good==page+1);check(g_current.bad==0);
 }
 check(g_uart_reject.complete);check(memcmp(record,g_uart_reject.data,UR_BYTES)==0);
 memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=CT_DETAIL;p[4]=15;p[38]=1;
 ur_put32(p+6,CT_PEER_BUILD);uv3_seal(p);dispatch(p);
 check(g_current.has_detail && g_current.good==15);
 p[25]^=1;dispatch(p);check(g_current.bad==1);
 check(g_uart_reject.complete && g_uart_reject.bad_pages==0);
 printf("{\"passed\":true,\"checks\":%u,\"uart_record_pages\":14}",checks);
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--outdir',type=Path,required=True)
    args=p.parse_args();c=args.candidate.resolve();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    r=dict(passed=False,hardware_commands=0)
    try:
        source=(c/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8')
        a=source.index('      if(buf[2]==CT_SUMMARY || buf[2]==CT_DETAIL')
        b=source.index('      if (buf[2] == BKW_VERSION)',a)
        function='static void dispatch(const uint8_t *buf) {for(unsigned once=0;once<1;++once){\n'+source[a:b]+'\n}}\n'
        unit=out/'actual_mixed_dispatch.cpp';unit.write_text(PREAMBLE+function+CASES)
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'mixed.exe'
            build=[shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(c/'UNOQ_MOTOR'),str(unit),'-o',str(exe)]
            good=subprocess.run(build,capture_output=True,text=True,timeout=60)
            (out/'compile.log').write_text(good.stdout+good.stderr);assert good.returncode==0,'Mixed wire compile failed'
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            assert run.returncode==0,run.stderr;r.update(json.loads(run.stdout))
            # Reintroducing our original D3 collision must stop compilation.
            mutated=Path(folder)/'current_wire.h'
            mutated.write_text((c/'UNOQ_MOTOR/current_wire.h').read_text().replace('CT_SUMMARY=0xD5','CT_SUMMARY=0xD3'))
            negative=build.copy();negative[5:5]=['-I',folder]
            bad=subprocess.run(negative,capture_output=True,text=True,timeout=60)
            (out/'collision_negative_compile.log').write_text(bad.stdout+bad.stderr)
            assert bad.returncode!=0 and 'Current packets must have unique wire versions' in bad.stderr
            r['collision_negative_control']=True
    except Exception as exc:r.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
