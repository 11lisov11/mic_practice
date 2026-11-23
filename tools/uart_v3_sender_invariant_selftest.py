"""Reproduce the ignored-magnitude incompatibility using real sender/receiver code."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from prepare_uart_v3_sender_fix import patched_sketch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--outdir",type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    snapshot=root/"artifacts/live_bench_20261010/uart_v3_candidate/firmware_r6"
    sender=(snapshot/"UNOQ_MOTOR/UNOQ_MOTOR.ino").read_text(encoding="utf-8-sig")
    receiver=(snapshot/"nucleo/Src/main.c").read_text(encoding="utf-8-sig")
    a=receiver.index("static void uno_handle_valid_frame(")
    b=receiver.index("static void uno_transport_result(",a)
    # The actual semantic handler neither reads nor applies scalar magnitude.
    assert not re.search(r"frame\[(10|11)\]|&frame\[(10|11)\]",receiver[a:b])
    fixed=patched_sketch(sender)
    assert "mcsdk_scalar ? 0U : bp_scalar_vmag_q15()" in fixed
    helper=re.search(r"static uint16_t bp_scalar_vmag_q15\(\) \{.*?\n\}",sender,re.S).group()
    def constant(name):
        match=re.search(r"(?:float|uint\d+_t)\s+"+name+r"\s*=\s*([\d.]+)[fFuU]?\s*;",sender)
        if match is None: raise ValueError("literal sender constant not found: "+name)
        return match.group(1)
    program=r'''
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <array>
#include "uart_v3_transport.h"
float g_freq_ref=0, g_vdc=325, g_v_limit=0.577f*325, g_vf_v_per_hz=0.577f*325/50;
float g_vf_start_boost_v=6;
float clampf(float x,float a,float b){return x<a?a:(x>b?b:x);}
uint16_t q15_unit(float x){return static_cast<uint16_t>(clampf(x,0,1)*32767);}
'''
    for name in ("VF_START_BOOST_MIN_FREQ_HZ","VF_START_BOOST_TAPER_HZ"):
        program+="constexpr float "+name+"="+repr(float(constant(name)))+"f;\n"
    program+=helper+r'''
using Frame=std::array<uint8_t,UV3_FRAME>;
Frame frame(uint8_t seq,uint16_t magnitude){
 Frame f{};f[0]=0xaa;f[1]=0x55;f[2]=3;f[3]=1;f[4]=3;f[5]=seq;
 uint32_t frequency=5000;for(unsigned i=0;i<4;++i) f[6+i]=frequency>>(8*i);
 f[10]=magnitude;f[11]=magnitude>>8;uv3_seal(f.data());return f;
}
uv3_result feed(uv3_rx& rx,const Frame& f,uint32_t t,bool noise){
 uv3_result r=UV3_WAIT;for(unsigned i=0;i<f.size();++i)
  r=uv3_byte(&rx,f[i],noise&&i==10?UV3_NE:0,t+i/12);
 return r;
}
unsigned checks=0;
void check(bool value){++checks;if(!value)std::abort();}
int main(){
 unsigned legacy_reject=0,fixed_accept=0;
 for(unsigned trial=0;trial<1000;++trial){
  uv3_rx legacy{},fixed{};uv3_init(&legacy,true);uv3_init(&fixed,true);
  for(unsigned i=0;i<4;++i){
   g_freq_ref=.15f+.05f*i;
   Frame old=frame(static_cast<uint8_t>(trial+i),bp_scalar_vmag_q15());
   Frame corrected=frame(static_cast<uint8_t>(trial+i),0);
   check(feed(legacy,old,i*50,false)==UV3_READY);uv3_commit(&legacy,i*50+4,true,false,false);
   check(feed(fixed,corrected,i*50,false)==UV3_READY);uv3_commit(&fixed,i*50+4,true,false,false);
  }
  g_freq_ref=.35f;
  Frame old=frame(static_cast<uint8_t>(trial+4),bp_scalar_vmag_q15());
  Frame corrected=frame(static_cast<uint8_t>(trial+4),0);
  check(uv3_crc_ok(old.data())&&uv3_crc_ok(corrected.data()));
  check(feed(legacy,old,200,true)==UV3_NOISE_REJECTED);++legacy_reject;
  check(feed(fixed,corrected,200,true)==UV3_READY);++fixed_accept;
  uv3_commit(&fixed,204,true,false,false);
  corrected=frame(static_cast<uint8_t>(trial+5),0);corrected[8]^=1;
  check(feed(fixed,corrected,250,false)==UV3_BAD_CRC);
 }
 std::printf("{\"checks\":%u,\"legacy_intact_ne_rejected\":%u,\"canonical_intact_ne_accepted\":%u}",checks,legacy_reject,fixed_accept);
}
'''
    compiler=shutil.which("g++")
    if not compiler:raise RuntimeError("g++ required")
    with tempfile.TemporaryDirectory() as folder:
        unit=Path(folder)/"test.cpp";exe=Path(folder)/"test.exe"
        unit.write_text(program,encoding="utf-8")
        built=subprocess.run([compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
            "-I",str(snapshot/"UNOQ_MOTOR"),str(unit),"-o",str(exe)],capture_output=True,text=True)
        (out/"compile.log").write_text(built.stdout+built.stderr,encoding="utf-8")
        (out/"host.cpp").write_text(program,encoding="utf-8")
        if built.returncode:raise RuntimeError("host compile failed: "+built.stderr)
        result=json.loads(subprocess.check_output([str(exe)],text=True))
    result.update(hardware_commands=0,physical_cause_proven=False,
        scope="real magnitude helper + frozen installed transport; synthetic intact NE, not physical EMI",
        installed_images_modified=False,
        source_sha256={"sender":hashlib.sha256(sender.encode()).hexdigest(),
                       "receiver":hashlib.sha256(receiver.encode()).hexdigest()})
    result["pass"]=True
    result["distinct_sequence_values"]=256
    result["sequence_trials_include_repeated_wrap_values"]=True
    (out/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
