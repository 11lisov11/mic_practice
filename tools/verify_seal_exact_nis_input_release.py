"""Check and seal1801/1802 offline. No programmer, network or device APIs."""
import ast,ctypes as ct,json,shutil,struct,subprocess,sys,types
from pathlib import Path
from elftools.elf.elffile import ELFFile
import prepare_exact_nis_input_release as p
from replay_observer_pair_noise import pair_arm_step,replay_pair_record


def write(path,v):p.write(path,json.dumps(v,ensure_ascii=False,indent=2)+'\n')


def load_test(name,source):
    m=types.ModuleType(name);m.__file__=str(p.ROOT/'tools'/(name+'.py'))
    exec(compile(source,m.__file__,'exec'),m.__dict__)
    m.OUT=p.OUT;m.BASE=p.BASE;m.CAP=p.BASE/'FOC_5Hz_r2';return m


def compile_dll(name,source,include):
    path=p.OUT/'verification'/(name+'.cpp');p.write(path,source);dll=path.with_suffix('.dll')
    cmd=[shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror','-include','initializer_list',
         '-I',str(include),str(path),'-o',str(dll)]
    r=subprocess.run(cmd,capture_output=True,text=True);p.write(path.with_suffix('.log'),r.stdout+r.stderr);r.check_returncode()
    return ct.CDLL(str(dll))


def main():
    assert not (p.OUT/'manifest.json').exists(),'Never overwrite a sealed release'
    native=json.loads(p.read(p.OUT/'nucleo_build_report.json'));assert native['passed'] and native['build_id']==p.NEW[1]
    uno=json.loads(p.read(p.OUT/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert uno['firmware_build_id']==p.NEW[0] and json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
    for a in uno['artifacts']:assert p.sha(p.OUT/'build/uno'/a['file'])==a['sha256'].lower()
    (p.OUT/'verification').mkdir(exist_ok=False)
    # Run the same adverse recorder/decoder tests against THIS identity and THIS source.
    src=p.read(p.ROOT/'tools/test_exact_observer_input.py').replace("overlay=OUT/'overlay'","overlay=OUT")
    src=src.replace("out=OUT/'verification_reconstruction'","out=OUT/'verification/capture'")
    src=src.replace('2026111716',str(p.NEW[1]))
    src=src.replace(f'legacy=decode(physical.hex(),{p.NEW[1]})','legacy=decode(physical.hex(),2026111716)')
    load_test('release_exact_capture_tests',src).main()
    src=p.read(p.ROOT/'tools/verify_exact_input_native.py').replace("overlay=OUT/'overlay'","overlay=OUT")
    src=src.replace("out=OUT/'verification_final'","out=OUT/'verification/adapter'")
    (p.OUT/'verification/adapter').mkdir()
    load_test('release_native_adapter_tests',src).main()
    guards=compile_dll('unchanged_math_guards',p.read(p.BASE/'verification/pair_kernel.cpp'),p.OUT/'nucleo/Inc').guards()
    assert guards==32
    wire_source='''#include <cassert>
#include "peak_wire.h"
extern "C" __declspec(dllexport) unsigned wire(const uint8_t*raw){
 pc_receiver r={};unsigned checks=0;
 for(unsigned page=0;page<35;++page){
  uint8_t p[UV3_FRAME]={};p[0]=0x55;p[1]=0xaa;p[2]=0xd8;p[3]=1;p[4]=1;p[5]=page;p[6]=35;
  unsigned len=page==34?4:30;p[7]=len;memcpy(p+8,raw+30*page,len);p[38]=1;uv3_seal(p);
  assert(!pc_receive(&r,p,CT_PEER_BUILD,false,1));++checks;
  assert(!pc_receive(&r,p,2026111716U,true,1));++checks;
  assert(pc_receive(&r,p,CT_PEER_BUILD,true,1));++checks;
 }assert(r.complete&&!memcmp(r.data,raw,1024));++checks;return checks;
}'''
    lib=compile_dll('schema3_wire',wire_source,p.OUT/'UNOQ_MOTOR');lib.wire.argtypes=[ct.POINTER(ct.c_ubyte)]
    raw=(p.OUT/'verification/capture/synthetic_exact_ADC.bin').read_bytes();buf=(ct.c_ubyte*1024).from_buffer_copy(raw)
    wire=lib.wire(buf);assert wire==106
    # Load only pure HMI functions, never the server or RPC constructors.
    names={'current_crc32c','exact_pc_crc','decode_exact_adc_peak_hex','decode_adc_peak_hex','with_adc_peak'}
    tree=ast.parse(p.read(p.OUT/'web_hmi/server.py'));functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    scope={'struct':struct};exec(compile(ast.Module(body=functions,type_ignores=[]),'release_HMI_pure','exec'),scope)
    hmi=0
    for late,valid in [(14,1),(36,0)]:
        c=ct.CDLL(str(p.OUT/'verification/capture/exact_core.dll'));c.fixture.argtypes=[ct.c_uint]*4+[ct.POINTER(ct.c_ubyte)]
        c.fixture(1000,late,0,0,buf)
        s=scope['with_adc_peak']({'fw_build':p.NEW[0],'mc_fw_build':p.NEW[1],'mc_adc_peak_hex':bytes(buf).hex()})
        assert s['mc_adc_peak_valid']==1 and s['mc_adc_peak_source_valid']==valid;hmi+=1
    s=scope['with_adc_peak']({'fw_build':p.NEW[0],'mc_fw_build':p.NEW[1],'mc_adc_peak_hex':'-','mc_adc_peak_source_valid':1})
    assert s['mc_adc_peak_source_valid']==0;hmi+=1
    s=scope['with_adc_peak']({'fw_build':p.NEW[0],'mc_fw_build':p.NEW[1],'mc_adc_peak_hex':raw.hex()[:-2]+'00'})
    # Full server syntax and legacy physical file are independently checked.
    compile(p.read(p.OUT/'web_hmi/server.py'),str(p.OUT/'web_hmi/server.py'),'exec')
    old_raw=(p.BASE/'FOC_5Hz_r2/ADC_peak.bin').read_bytes()
    assert scope['decode_adc_peak_hex'](old_raw.hex(),2026111716)['schema']==1;hmi+=1
    write(p.OUT/'verification/protocol_guards.json',dict(passed=True,guards=guards,wire_checks=wire,HMI_checks=hmi,
        wrong_peer_rejected=True,RUN_bulk_refused=True,hardware_commands=0))
    release=p.OUT/'release';release.mkdir(exist_ok=False)
    image=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    for ext in ('.elf','.hex','.bin'):shutil.copy2(image.with_suffix(ext),release/f'nucleo_{p.NEW[1]}_exact_source{ext}')
    shutil.copy2(p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin',release/f'uno_{p.NEW[0]}_exact_source.elf-zsk.bin')
    # HEX holes remain erasedFF. Do not invent expected bytes from a readback.
    memory={};upper=0;eof=False
    for line in image.with_suffix('.hex').read_text().splitlines():
        assert line.startswith(':');b=bytes.fromhex(line[1:]);assert len(b)==b[0]+5 and sum(b)&255==0
        n,addr,kind=b[0],int.from_bytes(b[1:3],'big'),b[3];data=b[4:4+n]
        if kind==0:
            for i,v in enumerate(data):
                a=upper+addr+i;assert a not in memory or memory[a]==v;memory[a]=v
        elif kind==4:assert n==2;upper=int.from_bytes(data,'big')<<16
        elif kind==1:eof=True
        else:assert kind==5,kind
    assert eof and min(memory)==0x08000000 and max(memory)<0x08020000
    expected=bytes(memory.get(a,255) for a in range(0x08000000,max(memory)+1))
    binary=image.with_suffix('.bin').read_bytes();assert len(binary)==len(expected)
    assert all(binary[a-0x08000000]==v for a,v in memory.items())
    assert 0x20000000<int.from_bytes(binary[:4],'little')<=0x20008000 and int.from_bytes(binary[4:8],'little')&1
    (release/f'nucleo_{p.NEW[1]}_expected_readback.bin').write_bytes(expected)
    with image.open('rb') as f:
        elf=ELFFile(f);ram=[s for s in elf.iter_sections() if s['sh_flags']&2 and 0x20000000<=s['sh_addr']<0x20010000]
        end=max(s['sh_addr']+s['sh_size'] for s in ram);remaining=0x20008000-end
    assert remaining>=1000
    # Execute new image math on the unchanged physical prior/input. Do NOT
    # relabel its old firmware header or claim a new physical observation.
    physical=p.BASE/'FOC_5Hz_r2/observer_trace_decoded.json';d=json.loads(p.read(physical))['first_nis_replay']
    raw=bytes.fromhex(d['raw_hex']);prior=raw[:168]+bytes(28)+raw[168:176]
    pairs=sum(n<<(5*i) for i,n in enumerate(d['pair_counts']))
    rc,post,noise=pair_arm_step(image,prior,raw[176:228],raw[228:248],d['fpscr'],pairs)
    old_steps,old_rejected=struct.unpack_from('<II',raw,168);packed=struct.unpack_from('<I',raw,452)[0];old_rc=packed&255
    want=raw[248:444]+struct.pack('<II',old_steps+(old_rc==0),struct.unpack_from('<I',raw,448)[0])
    assert rc==old_rc and post==want
    write(p.OUT/'verification/release_ARM_math_identity.json',dict(passed=True,bit_exact_words=51,
        source_physical_firmware=2026111716,candidate_firmware=p.NEW[1],physical_record_not_renumbered=True,hardware_commands=0))
    # Generate a NEW, clearly labelled synthetic schema5 record for releaseCLI.
    source=p.read(p.BASE/'verification/pair_capture.cpp').replace('2026111716',str(p.NEW[1]))
    c=compile_dll('synthetic_NIS_capture',source,p.OUT/'nucleo/Inc')
    from check_observer_equations_offline import Motor,Observer
    c.capture.argtypes=[ct.POINTER(Observer),ct.POINTER(Observer),ct.POINTER(Motor),ct.POINTER(ct.c_float),ct.c_int,ct.c_uint,ct.c_uint32,ct.POINTER(ct.c_ubyte)]
    before=Observer.from_buffer_copy(prior);after=Observer.from_buffer_copy(post);model=Motor.from_buffer_copy(raw[176:228]);inputs=(ct.c_float*5).from_buffer_copy(raw[228:248]);blob=(ct.c_ubyte*1888)()
    assert c.capture(ct.byref(before),ct.byref(after),ct.byref(model),inputs,rc,pairs,d['fpscr'],blob)==1
    synthetic=bytes(blob);assert replay_pair_record(synthetic,image,p.NEW[1])['passed']
    (p.OUT/'verification/synthetic_schema5_new_firmware.bin').write_bytes(synthetic)
    shutil.copy2(p.ROOT/'tools/replay_observer_pair_noise.py',release/'replay_observer_pair_noise.py')
    write(release/'replay_manifest.json',dict(firmware=p.NEW[1],elf=f'nucleo_{p.NEW[1]}_exact_source.elf',elf_sha256=p.sha(image),
        ABI='observer: R0=o,R1=model,R2=input,R3=noise; noise: R0=counts,R1=out',schema=5,hardware_validated=False,target_timing_measured=False))
    result=subprocess.run([sys.executable,str(release/'replay_observer_pair_noise.py'),'--record',str(p.OUT/'verification/synthetic_schema5_new_firmware.bin'),
        '--bundle',str(release),'--out',str(p.OUT/'verification/release_CLI_replay.json')],capture_output=True,text=True)
    p.write(p.OUT/'verification/release_CLI_replay.log',result.stdout+result.stderr);result.check_returncode()
    assert json.loads(p.read(p.OUT/'verification/release_CLI_replay.json'))['passed']
    # Everything must match the tested overlay after undoing identity changes.
    changed=[]
    intentional=set(json.loads(p.read(p.DIAG/'overlay_manifest.json'))['changed'])
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for file in (p.OUT/folder).rglob('*'):
            if not file.is_file() or '__pycache__' in file.parts:continue
            rel=file.relative_to(p.OUT).as_posix();canonical=p.DIAG/'overlay'/rel if rel in intentional else p.BASE/rel
            a=p.read(file).replace(str(p.NEW[0]),'2026111715').replace(str(p.NEW[1]),'2026111716')
            assert a==p.read(canonical),rel
            if p.sha(file)!=p.sha(p.BASE/rel):changed.append(rel)
    for rel,h in json.loads(p.read(p.OUT/'preserved_inputs_sha256.json')).items():assert p.sha(p.ROOT/rel)==h,rel
    sources={}
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','libraries','web_hmi'):
        for f in (p.OUT/folder).rglob('*'):
            if f.is_file() and '__pycache__' not in f.parts:sources[f.relative_to(p.OUT).as_posix()]=p.sha(f)
    write(p.OUT/'source_hashes.json',sources)
    write(release/'sha256.json',{f.name:p.sha(f) for f in release.iterdir() if f.is_file()})
    report=dict(built=True,installed=False,pair=p.NEW,predecessor_pair=[2026111715,2026111716],hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,
        capture_schema=3,observer_schema=5,source_window_rows=16,voltage_history_rows=25,raw_ring_rows=60,
        current_trip_A=1.35,OFF_fast_limit_cycles=4000,estimate_age_ms=2,ADC_UPDATE_ticks=2048,full_RUN_existing_limit_cycles=5312,NIS_limits=[25,50],
        NIS_safety_guard_retained=True,observer_math_unchanged=True,protections_and_limits_unchanged=True,
        NIS_algorithm_fixed=False,physical_NIS_root_cause_proven=False,actual_target_timing_measured=False,
        target_OFF64_and_ADC_IRQ_qualification_required_before_START=True,RAM_remaining_after_reserved_stack_bytes=remaining,
        host_capture_cases=108,host_adapter_checks=29,host_OFF_cases=64,guard_cases=guards,wire_cases=wire,HMI_cases=hmi,
        native_build_passed=True,uno_build_and_llext_passed=True,release_ARM_replay_bit_exact_words=51,
        expected_readback_from_HEX=True,HEX_gap_bytes=sum(a not in memory for a in range(0x08000000,max(memory)+1)),
        preserved_files_verified=len(json.loads(p.read(p.OUT/'preserved_inputs_sha256.json'))),source_changed_including_IDs=changed,
        artifacts={f.relative_to(p.OUT).as_posix():p.sha(f) for f in release.iterdir() if f.is_file()})
    write(p.OUT/'manifest.json',report)
    print(json.dumps({k:report[k] for k in ('built','installed','pair','host_capture_cases','release_ARM_replay_bit_exact_words','RAM_remaining_after_reserved_stack_bytes','preserved_files_verified','hardware_commands')}))


if __name__=='__main__':main()
