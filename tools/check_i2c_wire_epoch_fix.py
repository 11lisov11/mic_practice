"""Replay the REAL existing reset branch before/after, including CT reset order."""
import json,subprocess
import prepare_i2c_wire_epoch_fix as p
from ipm_break_wifi_selftest import load_module
def main():
    v=p.OUT/'verification';fixture=p.BASE/'manual_usb_capture_r1/wire.bin'
    common='''#include "peer_epoch.h"
#include "encoder_health_wire.h"
#include "current_wire.h"
#include "peak_wire.h"
#include "zero_wire.h"
#include <cassert>
#include <cstdio>
#include <cstring>
static pe_records g_encoder_records;
static pe_history g_encoder_history;
[[maybe_unused]] static eh_receiver g_encoder_health;
static bw_receiver g_break_wire;
static bkw_receiver g_bkin_wave;
static urw_receiver g_uart_reject;
static ct_receiver g_current;
static pc_receiver g_peak;
static zh_receiver g_zero_history;
void dispatch(uint32_t previous_build,uint32_t g_bp_fw_build,uint16_t previous_good,uint16_t g_bp_good_cnt,uint32_t previous_age){
BRANCH
}
int main(int argc,char**argv){
  assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);uint8_t raw[WC_BYTES];assert(fread(raw,1,WC_BYTES,f)==WC_BYTES);fclose(f);
  memcpy(g_encoder_records.wire.bytes,raw,WC_BYTES);g_encoder_records.wire.valid=true;g_encoder_records.wire.crc=uv3_crc32c(raw,WC_BYTES);
  g_current.has_quality=true;g_current.quality[10]=42;
  dispatch(WC_PEER,WC_PEER,60000,3,20);
  assert(!g_current.has_quality); // Existing branch invalidates the fallback's old timestamp.
EXPECT
  puts("{\\"passed\\":true}");
}
'''
    results={}
    for name,folder in [('before',p.BASE),('after',p.OUT)]:
        source=p.read(folder/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
        a=source.index('  if (bkw_peer_reset(');b=source.index('  g_manual_reference_valid=',a);branch=source[a:b]
        expected='assert(g_encoder_records.wire.valid&&g_encoder_history.epoch==0);' if name=='before' else '''
  assert(!g_encoder_records.wire.valid&&g_encoder_history.epoch==1&&g_encoder_history.previous_valid);
  assert(g_encoder_history.previous.wire.crc==uv3_crc32c(raw,WC_BYTES));
  assert(!memcmp(g_encoder_history.previous.wire.bytes,raw,WC_BYTES));
  dispatch(WC_PEER,WC_PEER,3,4,20);assert(g_encoder_history.epoch==1);
  dispatch(WC_PEER,WC_PEER,4,5,301);assert(g_encoder_history.epoch==2&&g_encoder_history.previous_valid);
  assert(!memcmp(g_encoder_history.previous.wire.bytes,raw,WC_BYTES));
  // A new complete waveform after reset must be accepted, not rejected as immutable old data.
  raw[32]^=1;
  for(unsigned page=0;page<WC_PAGES;page++){
    uint8_t packet[43];wc_frame(packet,page,uv3_crc32c(raw,WC_BYTES));
    unsigned off=page*24,n=WC_BYTES-off;if(n>24)n=24;memcpy(packet+14,raw+off,n);uv3_seal(packet);
    assert(wc_receive(&g_encoder_records.wire,packet,WC_PEER,true));
  }assert(g_encoder_records.wire.valid&&!memcmp(g_encoder_records.wire.bytes,raw,WC_BYTES));
'''
        f=v/(name+'.cpp');p.write(f,common.replace('BRANCH',branch).replace('EXPECT',expected))
        exe=v/(name+'.exe');q=subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I',str(folder/'UNOQ_MOTOR'),str(f),'-o',str(exe)],capture_output=True,text=True)
        p.write(v/(name+'_compile.log'),q.stdout+q.stderr);assert q.returncode==0,q.stderr
        q=subprocess.run([str(exe),str(fixture)],capture_output=True,text=True);p.write(v/(name+'.log'),q.stdout+q.stderr);assert q.returncode==0,q.stderr
        results[name]=json.loads(q.stdout)
    before=p.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino');after=p.read(p.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino')
    assert after==p.once(p.once(before,'FW_BUILD_ID = 2026102811U','FW_BUILD_ID = 2026102813U'),p.OLD_BLOCK,p.NEW_BLOCK)
    for folder in ('UNOQ_MOTOR','libraries'):
        for f in (p.BASE/folder).rglob('*'):
            if f.is_file() and f.name!='UNOQ_MOTOR.ino':assert p.sha(f)==p.sha(p.OUT/folder/f.relative_to(p.BASE/folder))
    assert p.sha(p.BASE/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')==p.sha(p.OUT/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin')
    h=load_module(p.OUT/'web_hmi/server.py')
    sample=json.loads(p.read(p.BASE/'manual_usb_capture_r1/captured_status.json'));sample['fw_build']=p.NEW[0]
    assert h.with_i2c_first_fault(sample)['enc_wire_record']['manual']
    assert h._vbus_calibration_identity_matches(dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1),dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1))
    r=dict(passed=True,before_bug_reproduced=results['before']['passed'],after_reset_flow_fixed=results['after']['passed'],
      previous_raw_retained=True,new_record_after_reset_accepted=True,reset_criteria_unchanged=True,UART_motor_protections_unchanged=True,hardware_commands=0)
    p.write(v/'native_report.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
