"""Synthetic schema5 capture uses actual ARM output; all153 mixtures replay exactly."""
import ctypes as ct,json,shutil,struct,subprocess
from pathlib import Path
import prepare_observer_pair_noise as p
from check_observer_equations_offline import Motor,Observer
from replay_observer_pair_noise import pair_arm_step,replay_pair_record
from release_observer_decoder import load_decoder


def main():
 out=p.OUT/'verification';old=p.read(p.BASE/'verification/capture_test.cpp')
 old=old[:old.index('extern "C" __declspec(dllexport) unsigned checks()')]
 old=old.replace('static od_sample row(', 'static unsigned capture_pairs;\nstatic od_sample row(')
 old=old.replace('r.window_count=16;', 'r.window_count=16U|(capture_pairs<<8);')
 old=old.replace('int rc,uint8_t*blob)', 'int rc,unsigned pairs,uint32_t fpscr,uint8_t*blob)')
 old=old.replace('od_capture c={};od_begin', 'capture_pairs=pairs;od_capture c={};od_begin')
 old=old.replace('od_replay_stage(&c,prior,m,v[0],v[1],v[2],v[3],v[4]);',
                 'od_replay_stage_pairs(&c,prior,m,v[0],v[1],v[2],v[3],v[4],pairs);c.blob.replay.fpscr=fpscr;')
 old=old.replace('2026111714','2026111716')
 source=out/'pair_capture.cpp';source.write_text(old,encoding='utf8');dll=source.with_suffix('.dll')
 run=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-shared','-Wall','-Wextra','-Werror',
                      '-I',str(p.OUT/'nucleo/Inc'),str(source),'-o',str(dll)],capture_output=True,text=True)
 (out/'pair_capture_build.log').write_text(run.stdout+run.stderr,encoding='utf8');run.check_returncode()
 lib=ct.CDLL(str(dll));lib.capture.argtypes=[ct.POINTER(Observer),ct.POINTER(Observer),ct.POINTER(Motor),ct.POINTER(ct.c_float),ct.c_int,ct.c_uint,ct.c_uint32,ct.POINTER(ct.c_ubyte)]
 saved=json.loads(p.read(p.BASE/'FOC_5Hz_r1/observer_trace_decoded.json'))['first_nis_replay'];raw=bytes.fromhex(saved['raw_hex'])
 prior=raw[:168]+bytes(28)+raw[168:176];motor=raw[176:228]
 # Synthetic larger beta residual ensures an eligible NIS event for every R.
 inputs=bytearray(raw[228:248]);struct.pack_into('<f',inputs,4,.95);inputs=bytes(inputs)
 elf=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
 decoder=load_decoder(p.OUT);n=0;sample=None
 for n0 in range(17):
  for n1 in range(17-n0):
   counts=[n0,n1,16-n0-n1];packed=sum(k<<(5*i) for i,k in enumerate(counts))
   rc,post,noise=pair_arm_step(elf,prior,motor,inputs,saved['fpscr'],packed)
   before=Observer.from_buffer_copy(prior);after=Observer.from_buffer_copy(post);m=Motor.from_buffer_copy(motor)
   v=(ct.c_float*5).from_buffer_copy(inputs);blob=(ct.c_ubyte*1888)()
   assert lib.capture(ct.byref(before),ct.byref(after),ct.byref(m),v,rc,packed,saved['fpscr'],blob)==1
   record=bytes(blob);got=decoder(record.hex(),p.NEW[1]);assert got['first_nis_replay']['pair_counts']==counts
   assert got['samples'][0]['pair_counts']==counts
   replay=replay_pair_record(record,elf,p.NEW[1]);assert replay['passed'] and replay['bit_exact'];n+=1
   if counts==[0,16,0]:sample=record
 assert sample is not None
 (out/'synthetic_schema5_ARM.bin').write_bytes(sample)
 for folder,cap,fw in [
   (p.BASE,p.BASE/'FOC_5Hz_r1',2026111714),
   (p.ROOT/'artifacts/live_bench_20261116/observer_current_window_r1',p.ROOT/'artifacts/live_bench_20261116/observer_current_window_r1/FOC_5Hz_20261117_r1',2026111612),
   (p.ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1',p.ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1/FOC_trial_r1',2026111606)]:
  got=decoder((cap/'observer_trace.bin').read_bytes().hex(),fw);assert got['schema'] in (2,3,4)
 # Exact actual noise covariance and posterior are covered by the record CRC.
 corrupt=bytearray(sample);corrupt[-1]^=1
 try:replay_pair_record(corrupt,elf,p.NEW[1])
 except ValueError:pass
 else:raise AssertionError('Corrupt pair metadata accepted')
 r=dict(passed=True,synthetic_fixture=True,hardware_commands=0,ARM_replays=n,words_each=51,
        legacy_schemas=[2,3,4],pair_metadata_matches=True,physical_run_performed=False,target_timing_measured=False)
 (out/'pair_replay_report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf8');print(json.dumps(r))


if __name__=='__main__':main()
