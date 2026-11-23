"""Exercise actual reset-record C and wire code, and replay archived epochs."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from elftools.elf.elffile import ELFFile
import prepare_boot_reset_capture as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True)
    common.p=p
    code=r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include "boot_wire.h"
static uint32_t rng=0x17382945U;
static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(){
 const uint32_t fw=2026103014U;unsigned checks=0;
 mb_record empty={},r=mb_next(&empty,fw,MB_BOR|(1U<<26));
 assert(mb_valid(&r,fw)&&r.sequence==1&&r.flags==0&&r.previous_csr==0);++checks;
 mb_confirm_clear(&r,0U);assert(r.flags==MB_CURRENT_CLEARED);++checks;
 auto warm=mb_next(&r,fw,1U<<26);
 assert(warm.sequence==2&&warm.flags==(MB_PREVIOUS_VALID|MB_PREVIOUS_CLEARED));++checks;
 assert(warm.previous_csr==r.csr&&warm.software_tag==0);++checks;
 mb_confirm_clear(&warm,0U);mb_note_software(&warm,MB_MCP_RESET);
 auto sw=mb_next(&warm,fw,MB_SOFTWARE|(1U<<26));
 assert(sw.sequence==3&&sw.software_tag==MB_MCP_RESET&&!(sw.flags&MB_PENDING_SOFTWARE));++checks;
 mb_confirm_clear(&sw,0U);auto pin=mb_next(&sw,fw,1U<<26);
 assert(pin.software_tag==0);++checks;
 auto bor=mb_next(&sw,fw,MB_BOR);assert(bor.sequence==1&&bor.previous_csr==0&&bor.flags==0);++checks;
 auto upgrade=mb_next(&sw,fw+1U,MB_SOFTWARE);assert(upgrade.sequence==1&&upgrade.flags==0);++checks;
 auto uncleared=mb_next(&empty,fw,MB_SOFTWARE);mb_confirm_clear(&uncleared,MB_SOFTWARE);
 assert(!(uncleared.flags&MB_CURRENT_CLEARED));
 auto following=mb_next(&uncleared,fw,1U<<26);assert(!(following.flags&MB_PREVIOUS_CLEARED));++checks;
 auto saturated=sw;saturated.sequence=0xffffffffU;saturated.crc=mb_crc(&saturated);
 assert(mb_next(&saturated,fw,1U<<26).sequence==1);++checks;
 for(unsigned n=0;n<10000;++n){
   mb_record garbage;auto words=reinterpret_cast<uint32_t*>(&garbage);
   for(unsigned i=0;i<8U;++i)words[i]=next();
   auto first=mb_next(&garbage,fw,1U<<26);
   assert(first.sequence==1&&first.flags==0);++checks;
 }
 // Every retained-record bit corruption must invalidate the old chain.
 for(unsigned i=0;i<sizeof(sw)*8U;++i){
   auto damaged=sw;reinterpret_cast<uint8_t*>(&damaged)[i/8]^=1U<<(i%8);
   assert(!mb_valid(&damaged,fw));assert(mb_next(&damaged,fw,1U<<26).sequence==1);++checks;
 }
 uint8_t wire[UV3_FRAME];mb_packet(wire,&sw,2000);mb_record decoded;
 assert(mb_decode(wire,fw,&decoded)&&memcmp(&sw,&decoded,sizeof(sw))==0);++checks;
 assert(!mb_decode(wire,fw+1,&decoded));++checks;
 for(unsigned i=0;i<UV3_FRAME*8U;++i){
   uint8_t damaged[UV3_FRAME];memcpy(damaged,wire,UV3_FRAME);damaged[i/8]^=1U<<(i%8);
   assert(!mb_decode(damaged,fw,&decoded));++checks;
 }
 uint8_t altered[UV3_FRAME];memcpy(altered,wire,UV3_FRAME);altered[14]^=1U;uv3_seal(altered);
 assert(!mb_decode(altered,fw,&decoded));++checks;
 mb_receiver rx={};assert(!mb_receive(&rx,wire,fw,false,100));assert(!rx.received);++checks;
 assert(mb_receive(&rx,wire,fw,true,0xfffffff0U));assert(mb_fresh(&rx,fw,true,0x20));++checks;
 assert(!mb_fresh(&rx,fw,false,0x20)&&!mb_fresh(&rx,fw,true,0x600));++checks;
 // Persist the actual generated frame for the independent Python decoder.
 printf("{\"checks\":%u,\"packet_hex\":\"",checks);
 for(unsigned i=0;i<UV3_FRAME;++i)printf("%02x",wire[i]);printf("\"}\n");
}
'''
    native=json.loads(common.compile_run(out,'boot_core_wire',code))
    spec=importlib.util.spec_from_file_location('boot_test_hmi',p.OUT/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    kv=dict(bp_fw_build=str(p.NEW[1]),mc_boot_packet_hex=native['packet_hex'],mc_boot_fresh='1')
    decoded=hmi.boot_wire_status(kv)['native_boot']
    assert decoded['available'] and decoded['previous_boot_continuity'] and decoded['fresh']
    assert decoded['retained_sequence']==3 and decoded['software_request_tag']==0x4D435031
    recorder=hmi.MotorFaultRecorder()
    sample=dict(native_boot=decoded,linux_boot_id='test-linux-id')
    first=recorder.observe(sample,now=0)
    assert sum(line.startswith('MC_BOOT_RECORD ') for line in first)==1
    assert not any(line.startswith('MC_BOOT_RECORD ') for line in recorder.observe(sample,now=1))
    changed=json.loads(json.dumps(sample));changed['native_boot']['retained_sequence']=4
    assert any(line.startswith('MC_BOOT_RECORD ') for line in recorder.observe(changed,now=2))
    assert not hmi.boot_wire_status(dict(kv,bp_fw_build='1'))['native_boot']['available']
    assert not hmi.boot_wire_status(dict(kv,mc_boot_packet_hex='00'))['native_boot']['available']
    assert not hmi.boot_wire_status(dict(kv,mc_boot_fresh='0'))['native_boot']['fresh']
    assert not hmi.boot_wire_status({})['native_boot']['available']
    parsed=hmi.RpcBridge._parse_status_string('DATA state=SAFE mode=VF '+
        ' '.join(str(k)+'='+str(v) for k,v in kv.items()))
    assert parsed and parsed['native_boot']['available'] and parsed['native_boot']['fresh']
    assert parsed['native_boot']['software_request_tag']==0x4D435031
    # Replay saved fields: no reset reason may be fabricated from old firmware.
    replay=[]
    for name,file in [('current_trip_after_reset_20261030_r1','final_status.json'),
                      ('current_repeat_powered_preflight_20261030_r1','followup_status.json')]:
        d=json.loads(p.read(p.BASE/name/file))['data']
        assert not hmi.boot_wire_status(d)['native_boot']['available']
        packet=bytes.fromhex(d['mc_current_detail_hex'])
        replay.append(dict(folder=name,tick=int.from_bytes(packet[10:14],'little'),
            zero_ready=d['mc_current_zero_ready'],algorithm=d['algorithm_selected'],reset_reason_recoverable=False))
    assert replay[1]['tick']<replay[0]['tick']
    # Every control/ADC/observer/IRQ file is byte-identical except build identity.
    changed={'nucleo/Src/main.c','nucleo/Src/mcp.c','nucleo/Src/system_stm32g4xx.c',
             'UNOQ_MOTOR/UNOQ_MOTOR.ino','web_hmi/server.py','web_hmi/static/app.js'}
    unchanged=0
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for f in (p.BASE/folder).rglob('*'):
            if not f.is_file() or '__pycache__' in f.parts:continue
            rel=f.relative_to(p.BASE).as_posix()
            if rel in changed:continue
            expected=p.read(f).replace('2026103011',str(p.NEW[0])).replace('2026103012',str(p.NEW[1])).replace('3011-observer-schedule','3013-boot-capture')
            assert p.read(p.OUT/rel)==expected,rel
            unchanged+=1
    for name in ('uno_handle_valid_frame','uno_rearm_break_irq','mic_local_stop_clear','mic_local_stop_enable_outputs'):
        assert function(p.read(p.BASE/'nucleo/Src/main.c'),name)==function(p.read(p.OUT/'nucleo/Src/main.c'),name)
    main=p.read(p.OUT/'nucleo/Src/main.c')
    send=function(main,'mic_send_boot_page')
    assert 'LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled' in send
    assert '!mic_last_control_reply_safe_off' in send and '500U' in send
    target=p.read(p.OUT/'nucleo/Src/system_stm32g4xx.c')
    early=function(target,'mic_boot_capture_early')
    assert early.index('mic_boot_store(&r)')<early.index('RCC->CSR|=RCC_CSR_RMVF')
    init=function(target,'SystemInit')
    assert init.index('SCB->CPACR')<init.index('__DSB();__ISB();')<init.index('mic_boot_capture_early();')
    assert all(x not in early for x in ('HAL_Init','HAL_GetTick','malloc','float','Flash'))
    # Native linker puts early evidence outside .bss and flash initialization.
    ef=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    with ef.open('rb') as stream:
        elf=ELFFile(stream);noinit=elf.get_section_by_name('.noinit');bss=elf.get_section_by_name('.bss')
        assert noinit['sh_type']=='SHT_NOBITS' and noinit['sh_size']==32
        assert noinit['sh_addr']>=bss['sh_addr']+bss['sh_size']
        ram=sum(elf.get_section_by_name(s)['sh_size'] for s in ('.data','.bss','.noinit','._user_heap_stack'))
        assert ram<32768
    report=dict(passed=True,native=native,decoded=decoded,replayed_epochs=replay,
        unchanged_source_files=unchanged,RAM_allocated=ram,retained_bytes=32,
        START=0,CLEAR=0,RESET=0,flash=0,guards_unchanged=True,hardware_validated=False)
    p.write(out/'selftest.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(passed=True,C_checks=native['checks'],unchanged_source_files=unchanged,RAM_allocated=ram)))


if __name__=='__main__':main()
