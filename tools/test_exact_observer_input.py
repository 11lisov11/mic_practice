"""Actual C recorder, adverse timelines and backward-compatible HMI; PC only."""
import ast,ctypes as ct,json,shutil,struct,subprocess
from pathlib import Path
from audit_nis_1716_saved_step import ROOT,BASE,CAP,OUT,sha
from observer_exact_peak_decode import decode_exact_adc_peak_hex,exact_pc_crc

CPP=r'''
#include <cassert>
#include "peak_core.h"
extern "C" __declspec(dllexport) unsigned sizes(){return sizeof(pc_capture);}
static pc_sample point(uint32_t origin,unsigned n,unsigned corrupt){
 pc_sample s={};s.cycles=origin+n*10624U;s.epoch_before=s.epoch_after=n;
 s.raw[0]=(uint16_t)(2070U+n%13U);s.raw[1]=(uint16_t)(2050U+n%17U);
 s.pair=(uint8_t)(n%3U);s.flags=111;s.arr=5312;s.bus_v=320;
 for(unsigned i=0;i<4;++i){s.offset[i]=(uint16_t)(2060U+i);s.active_ccr[i]=(uint16_t)(2000U+300U*i+n%9U);}
 s.active_ccr[3]=5184;
 if(corrupt==1&&n==95)s.flags|=128;
 if(corrupt==2&&n==95)s.cycles+=100000U;
 if(corrupt==3&&n>=98)s.offset[0]++;
 if(corrupt==4&&n==95)s.active_ccr[1]=9000;
 return s;
}
extern "C" __declspec(dllexport) unsigned fixture(uint32_t origin,unsigned late,unsigned corrupt,unsigned wrong,uint8_t*blob){
 pc_capture c;pc_init(&c);
 for(unsigned n=1;n<=100U+late;++n){auto s=point(origin,n,corrupt);pc_push(&c,&s,n,1,1,0);}
 REQUEST
 for(unsigned n=101U+late;n<=108U+late&&!c.frozen;++n){auto s=point(origin,n,corrupt);pc_push(&c,&s,n,1,1,0);}
 assert(c.frozen);auto frozen=c.blob;
 REQUEST
 auto later=point(origin,500,0);pc_push(&c,&later,500,1,1,10000);
 assert(!memcmp(&frozen,&c.blob,sizeof(frozen)));
 c.blob.header.firmware=2026111716U;c.blob.header.crc=pc_crc((const uint8_t*)&c.blob);
 memcpy(blob,&c.blob,1024);return c.blob.header.flags;
}
extern "C" __declspec(dllexport) unsigned peak_stop(uint8_t*blob){
 unsigned checks=0;pc_capture c;pc_init(&c);auto s=point(0,1,0);
 pc_push(&c,&s,0,0,1,1000);assert(!c.frozen&&!c.count);++checks;
 for(unsigned n=1;n<=100;++n){s=point(0,n,0);pc_push(&c,&s,n,1,1,n==50?626:0);}
 assert(c.frozen&&c.total==56&&c.blob.header.flags==PC_PEAK);++checks;
 auto before=c.blob;REQUEST
 assert(!memcmp(&before,&c.blob,sizeof(before)));++checks;
 pc_init(&c);s=point(0,1,0);pc_push(&c,&s,1,1,1,0);s=point(0,2,0);pc_push(&c,&s,2,0,1,0);
 assert(c.frozen&&c.blob.header.flags==PC_NO_PEAK);++checks;
 memcpy(blob,&c.blob,1024);return checks;
}
#ifdef EXACT_REBUILD
#include "observer_current_window.h"
#include "observer_applied_voltage.h"
#include "current_core.h"
static void input(const pc_sample&s,float*v){
 cm_core z={};memcpy(z.offset,s.offset,sizeof(s.offset));int16_t count[3];
 assert(cm_reconstruct(&z,s.pair,s.raw[0],s.raw[1],count));
 const float scale=(float)(3.3f/(4095.0*.04f*2.1f));
 v[0]=count[0]*scale;v[1]=(v[0]+2.f*count[1]*scale)*.5773502692f;
 ma_geometry g={5312,5184,771,112,240,229};
 assert(!ma_applied_voltage(&g,s.active_ccr,s.arr,s.bus_v,v[0],v[1],&v[2],&v[3]));
}
extern "C" __declspec(dllexport) int rebuild(uint32_t origin,unsigned late){
 uint8_t bytes[1024];fixture(origin,late,0,0,bytes);pc_blob b;memcpy(&b,bytes,1024);
 assert(b.header.flags&PC_EXACT);ow_state live;ow_reset(&live,origin+4U*10624U);ow_bin expected={};
 for(unsigned n=5;n<=100;++n){auto s=point(origin,n,0);float v[4];input(s,v);
  int rc=ow_push_pair(&live,s.cycles,31875,v[0],v[1],v[2],v[3],&expected,s.pair);assert(rc==(n%16U==4U));
 }
 unsigned slot=b.header.trigger_slot>=24?b.header.trigger_slot-24:b.header.trigger_slot+36;
 ow_state replay={};replay.n=8;replay.last=b.samples[slot].cycles;
 replay.previous_center=replay.last-8U*10624U;ow_bin got={};
 for(unsigned k=1;k<25;++k){slot=pc_next(slot);const auto&r=b.samples[slot];pc_sample s={};s.cycles=r.cycles;
  s.raw[0]=r.packed[0]|((r.packed[1]&15U)<<8);s.raw[1]=(r.packed[1]>>4)|(r.packed[2]<<4);
  uint64_t cc=0;for(unsigned i=0;i<7;++i)cc|=(uint64_t)r.packed[3+i]<<(8U*i);
  for(unsigned i=0;i<4;++i)s.active_ccr[i]=(uint16_t)((cc>>(13U*i))&8191U);
  s.pair=(r.meta>>9)&3U;s.bus_v=r.meta&511U;s.arr=b.header.arr;memcpy(s.offset,b.header.offset,sizeof(s.offset));
  float v[4];input(s,v);int rc=ow_push_pair(&replay,s.cycles,31875,v[0],v[1],v[2],v[3],&got,s.pair);
  assert(rc==(k==8||k==24));
 }
 assert(!memcmp(&got,&expected,sizeof(got)));return 1;
}
#endif
'''


def compile_dll(out,name,folder,new):
    request=('pc_request_observer(&c,origin+85U*10624U+(wrong==1),origin+100U*10624U+(wrong==2),503);'
             if new else 'pc_request_observer(&c);')
    source=('#define EXACT_REBUILD\n' if new else '')+CPP.replace('REQUEST',request)
    # peak_stop has no origin/wrong variables; its stopped/peak record must not change.
    source=source.replace('auto before=c.blob;'+request,
        'auto before=c.blob;'+('pc_request_observer(&c,85U*10624U,100U*10624U,503);' if new else 'pc_request_observer(&c);'))
    path=out/(name+'.cpp');path.write_text(source,encoding='utf-8');dll=path.with_suffix('.dll')
    run=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror',
        '-Wno-misleading-indentation','-Wno-unused-parameter','-I',str(folder/'nucleo/Inc'),str(path),'-o',str(dll)],capture_output=True,text=True)
    (out/(name+'_build.log')).write_text(run.stdout+run.stderr,encoding='utf-8');run.check_returncode()
    lib=ct.CDLL(str(dll));lib.fixture.argtypes=[ct.c_uint]*4+[ct.POINTER(ct.c_ubyte)]
    lib.peak_stop.argtypes=[ct.POINTER(ct.c_ubyte)]
    return lib


def hmi_decoder(path):
    names={'current_crc32c','exact_pc_crc','decode_exact_adc_peak_hex','decode_adc_peak_hex'}
    tree=ast.parse(path.read_text(encoding='utf-8'));body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    scope={'struct':struct};exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),scope)
    return scope['decode_adc_peak_hex']


def main():
    out=OUT/'verification_reconstruction';out.mkdir(exist_ok=False);overlay=OUT/'overlay'
    new=compile_dll(out,'exact_core',overlay,True);old=compile_dll(out,'old_core',BASE,False)
    fixture=(ct.c_ubyte*1024)();old_fixture=(ct.c_ubyte*1024)();cases=0
    decode=hmi_decoder(overlay/'web_hmi/server.py')
    for origin in (1000,0xffff0000):
        for late in range(36):
            new.fixture(origin,late,0,0,fixture);raw=bytes(fixture);d=decode(raw.hex(),2026111716)
            assert d['source_window_exact'] and not d['source_window_gap']
            assert len(d['source_samples'])==16 and len(d['source_voltage_history'])==25
            assert d['requested_first_cycles']==(origin+85*10624)&0xffffffff
            assert d['source_observer_step']==503
            assert [r['cycles'] for r in d['source_samples']]==[(origin+n*10624)&0xffffffff for n in range(85,101)]
            for r,n in zip(d['source_samples'],range(85,101)):
                assert r['raw_adc']==[2070+n%13,2050+n%17]
                assert r['ccr_at_update']==[2000+300*i+n%9 for i in range(3)]+[5184]
                assert r['bus_v']==320 and r['pair']==n%3
            cases+=1
    # At the measured ~0.9ms observer delay the old recorder has NONE of the
    # actual source16; the replacement retains all16 and prior voltage history.
    old.fixture(1000,14,0,0,old_fixture)
    old_dec=hmi_decoder(BASE/'web_hmi/server.py')(bytes(old_fixture).hex(),2026111716)
    assert not set(r['cycles'] for r in old_dec['samples'])&set(1000+n*10624 for n in range(85,101))
    new.fixture(1000,14,0,0,fixture);(out/'synthetic_exact_ADC.bin').write_bytes(bytes(fixture));cases+=1
    for late,corrupt,wrong in [(36,0,0),(40,0,0),(14,1,0),(14,2,0),(14,3,0),(14,4,0),(14,0,1),(14,0,2)]:
        new.fixture(1000,late,corrupt,wrong,fixture);d=decode(bytes(fixture).hex(),2026111716)
        assert d['source_window_gap'] and not d['source_window_exact'];cases+=1
    assert new.peak_stop(fixture)==old.peak_stop(old_fixture)==4;cases+=4
    # Deployed decoder still reads the real old schema1 without relabelling it.
    physical=(CAP/'ADC_peak.bin').read_bytes();legacy=decode(physical.hex(),2026111716)
    assert legacy['schema']==1 and len(legacy['samples'])==12;cases+=1
    good=(out/'synthetic_exact_ADC.bin').read_bytes()
    for offset in (4,8,20,28,36,40,44,64,72,80):
        bad=bytearray(good);bad[offset]^=1
        # All wire corruption fails CRC, without executing any hardware code.
        try:decode(bytes(bad).hex(),2026111716)
        except ValueError:pass
        else:raise AssertionError('Corrupt record accepted')
        cases+=1
    # Even an externally re-CRC'd wrong source identity/composition is rejected.
    for offset in (28,32,40,44):
        bad=bytearray(good);bad[offset]^=1;struct.pack_into('<I',bad,60,exact_pc_crc(bad))
        try:decode(bytes(bad).hex(),2026111716)
        except ValueError:pass
        else:raise AssertionError('Inconsistent source accepted')
        cases+=1
    new.rebuild.argtypes=[ct.c_uint,ct.c_uint]
    for origin in (1000,0xffff0000):
        for late in (0,14,32,35):assert new.rebuild(origin,late)==1;cases+=1
    report=dict(passed=True,cases=cases,hardware_commands=0,synthetic_cases_only=True,
        retained_source16=True,retained_voltage_history25=True,max_tested_delay_periods=35,
        deliberate_missing_history_is_GAP=True,clock_wrap_tested=True,frozen_blob_immutable=True,
        old_capture_missing_entire_source_at14_periods=True,legacy_physical_schema1_decoded=True,
        actual_C_mean16_and_intercenter_voltage_rebuilt_bit_exact=True,mean_rebuild_cases=8,
        storage_bytes_old=int(old.sizes()),storage_bytes_new=int(new.sizes()),payload_bytes_unchanged=1024,
        target_CPU_cycles_measured=False,physical_NIS_reduction_proven=False)
    (out/'capture_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))


if __name__=='__main__':main()
