"""Run actual instrumented ADC IRQ, capture, page transport and HMI decoder on host."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import current_shunt_irq_selftest as old
import audit_production_pwm_filters as extract

ROOT=Path(__file__).resolve().parents[1]
EXTRA=r'''
#include "peak_core.h"
#include "peak_wire.h"
struct Dwt {uint32_t CYCCNT;};static Dwt dwt;
#define DWT (&dwt)
#define ADC_ISR_JQOVF 1024U
static struct Vf {float fFlux_Freq_Hz=40;} vf;
static Vf *pACIM_VF_Component_M1=&vf;
'''
TEST=r'''
int main(){
 regression_main();
 cm_init(&state);state.zero_ready=1;
 for(unsigned i=0;i<4;++i)state.offset[i]=zero[i];
 pc_init(&peak);lost_sync=0;pending_pair=0;pending_valid=1;pending_active=1;
 timer={2656,2656,2656,4928,5100,0,5312,32768};
 mic_current_update_epoch();
 for(unsigned i=0;i<20;++i){dwt.CYCCNT+=10625;conversion(2000+i/16,78,-39,-39);}
 check(!peak.frozen && !peak.triggered);
 dwt.CYCCNT+=10625;conversion(2002,1162,-581,-581);
 check(peak.triggered && !peak.frozen);
 for(unsigned i=0;i<6;++i){dwt.CYCCNT+=10625;conversion(2003+i/16,78,-39,-39);}
 check(peak.frozen && peak.blob.header.count==12 && peak.blob.header.flags==PC_PEAK);
 check(peak.blob.header.trigger_sequence+6==peak.blob.header.frozen_sequence);
 auto before=peak.blob;
 for(unsigned i=0;i<10;++i)conversion(2004,1500,-750,-750);
 check(memcmp(&before,&peak.blob,sizeof(before))==0);
 uint8_t packet[UV3_FRAME];
 check(!mic_current_peak_packet(packet,0,2026102502)); // never transmit under PWM
 timer.BDTR=0;
 pc_receiver rx{};
 for(int page=34;page>=0;--page) {
  check(mic_current_peak_packet(packet,(uint8_t)page,2026102502));
  check(!pc_receive(&rx,packet,2026102502,false,1));
  check(!pc_receive(&rx,packet,2026102412,true,1));
  check(pc_receive(&rx,packet,2026102502,true,1));
  check(rx.complete==(page==0));
 }
 check(rx.complete && memcmp(rx.data,&peak.blob,1024)==0);
 check(pc_receive(&rx,packet,2026102502,true,2));
 packet[20]^=1;check(!pc_receive(&rx,packet,2026102502,true,2));
 uv3_seal(packet);check(!pc_receive(&rx,packet,2026102502,true,2));
 FILE *file=fopen("trace.bin","wb");check(file!=nullptr);
 check(fwrite(&peak.blob,1,1024,file)==1024);fclose(file);
 // STOP without reaching threshold is a trace, not a claimed captured peak.
 pc_capture simple{};pc_sample sample{};
 for(unsigned i=0;i<3;++i)pc_push(&simple,&sample,i,1,1,10);
 pc_push(&simple,&sample,4,0,0,0);
 check(simple.frozen && simple.blob.header.flags==PC_NO_PEAK && simple.blob.header.trigger_slot==65535);
 pc_init(&simple);pc_push(&simple,&sample,1,1,1,700);pc_push(&simple,&sample,2,0,0,0);
 check(simple.frozen && simple.blob.header.flags==(PC_PEAK|PC_SHORT));
 printf("{\"passed\":true,\"checks\":%u,\"actual_irq\":true,\"off_only_wire\":true,\"hardware_commands\":0}\n",checks);
}
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate',type=Path,required=True)
    ap.add_argument('--outdir',type=Path,required=True)
    args=ap.parse_args();c=args.candidate.resolve();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    source=(c/'nucleo/Src/current_shunt.c').read_text(encoding='utf-8')
    globals_=source[source.index('static cm_core state;'):source.index('void mic_current_init(void)')]
    irq=source[source.index('void mic_current_adc_irq(void)'):source.index('static uint16_t ma_u')]
    cases=old.CASES.replace('int main() {','int regression_main() {').replace(' printf("{\\"passed', ' printf("{\\"passed')
    # Original main needs a return when called as an ordinary regression function.
    cases=cases[:cases.rfind('}')]+ 'return 0;\n}\n'
    unit=out/'actual_peak_irq.cpp'
    peer=json.loads((c/'manifest.json').read_text(encoding='utf-8'))['pair_compatibility_ids'][1]
    preamble=old.PREAMBLE
    if 'static void mic_zero_record(' in source:
        from prepare_current_zero_noise import REPORT_DECL
        preamble=preamble.replace('#include "current_core.h"',REPORT_DECL+'#include "current_core.h"')
    unit.write_text(preamble+EXTRA+globals_+irq+'\n'+extract.function(source,'mic_current_peak_packet')+'\n'+cases+TEST.replace('2026102502',str(peer)))
    with tempfile.TemporaryDirectory() as temp:
        exe=Path(temp)/'test.exe'
        b=subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers',
            '-I',str(c/'nucleo/Inc'),'-I',str(c/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True,timeout=60)
        (out/'build.log').write_text(b.stdout+b.stderr);b.check_returncode()
        t=subprocess.run([str(exe)],cwd=out,capture_output=True,text=True,timeout=30)
        (out/'run.log').write_text(t.stdout+t.stderr);t.check_returncode()
    # Existing regression emits its own JSON before the new report.
    result=json.loads(t.stdout[t.stdout.rfind('{'):])
    import importlib.util,sys
    spec=importlib.util.spec_from_file_location('tested_peak_hmi',c/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    env=h.__dict__
    raw=(out/'trace.bin').read_bytes();decoded=env['decode_adc_peak_hex'](raw.hex())
    assert decoded['sample_count']==12 and decoded['peak_seen'] and not decoded['post_short']
    trigger=next(x for x in decoded['samples'] if x['is_trigger'])
    assert decoded['samples'].index(trigger)==5 and trigger['reference_hz']==40
    assert trigger['counts_uvw']==[1162,-581,-581]
    assert all(x['epoch_consistent'] for x in decoded['samples'])
    assert all(x['accepted_by_existing_monitor'] for x in decoded['samples'])
    for damaged in [raw[:-1],bytes([raw[0]^1])+raw[1:]]:
        try:env['decode_adc_peak_hex'](damaged.hex())
        except ValueError:pass
        else:raise AssertionError('Decoder accepted a corrupt record')
    wrong=bytearray(raw);wrong[8:12]=(2026102412).to_bytes(4,'little');wrong[60:64]=b'\0'*4
    wrong[60:64]=env['current_crc32c'](wrong).to_bytes(4,'little')
    try:env['decode_adc_peak_hex'](wrong.hex())
    except ValueError:pass
    else:raise AssertionError('Decoder accepted foreign peer')
    result.update(hmi_roundtrip=True,trigger_index=5,post_samples=6,crc_negative_controls=True,
                  trace_bytes=1024,physical_measurements=False)
    (out/'decoded.json').write_text(json.dumps(decoded,indent=2)+'\n')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
