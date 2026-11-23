"""Prepare a continuous low-frequency V/f envelope; never accesses hardware."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261021/uart_clean_confirm_r1'
OUT=ROOT/'artifacts/live_bench_20261024/vf_smooth_start_r1'
OLD,NEW=(2026102103,2026102104),(2026102401,2026102402)
VF='nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/acim_vf_control.c'
def read(p):return p.read_text(encoding='utf-8-sig')
def write(p,s):p.write_text(s,encoding='utf-8',newline='\n')
def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b)

OLD_CURVE='''  if(fFreqHzAbs >= pHandle->fMinFreq_TH_Hz)
  {
    pHandle->VoltageAmpl = 2.0f*PI*fFreqHzAbs * pHandle->fFlux_K;
  }
  else
  {
   pHandle->VoltageAmpl = pHandle->fVoltage_Offset;
  }'''
NEW_CURVE='''  /* C1 low-speed envelope: V(0)=0, V(F/2)=configured low-speed
     anchor, V(F)=k*F and dV/df(F)=k. Above F the original linear
     characteristic is unchanged. No DC boost is applied at zero Hz.
     For this drive: F=10 Hz, V(5 Hz)=20 V phase peak. */
  const float slope=2.0f*(float)PI*pHandle->fFlux_K;
  pHandle->VoltageAmpl=2.0f*PI*fFreqHzAbs*pHandle->fFlux_K;
  if(pHandle->fMinFreq_TH_Hz>0.0f && fFreqHzAbs<pHandle->fMinFreq_TH_Hz)
  {
    const float linear_at_join=slope*pHandle->fMinFreq_TH_Hz;
    const float boost=pHandle->fVoltage_Offset-0.5f*linear_at_join;
    if(boost>0.0f)
    {
      /* d[x(1-x)^2]/dx >= -1/3. Reject a profile that could make
         voltage decrease with increasing frequency, before writing CCR. */
      if(!mic_float_isfinite(linear_at_join) || boost>0.375f*linear_at_join)
        return MC_SW_ERROR;
      const float x=fFreqHzAbs/pHandle->fMinFreq_TH_Hz;
      const float tail=1.0f-x;
      pHandle->VoltageAmpl+=8.0f*boost*x*tail*tail;
    }
  }
  if(!mic_float_isfinite(pHandle->VoltageAmpl) || pHandle->VoltageAmpl<0.0f)
    return MC_SW_ERROR;'''

def main():
    if OUT.exists():raise RuntimeError('preserve existing candidate')
    m=json.loads(read(BASE/'manifest.json'));assert m['installed'] and m['built'] and m['selftest_pass']
    for rel,value in m['source_sha256'].items():
        assert hashlib.sha256((BASE/rel).read_bytes()).hexdigest()==value,rel
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('build','Debug','Release','.metadata','.settings','__pycache__','.lock'))
    for rel in ('build/nucleo','build/uno','selftest'):(OUT/rel).mkdir(parents=True)
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():
                s=read(p);new=s.replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
                if new!=s:write(p,new)
    write(OUT/VF,once(read(OUT/VF),OLD_CURVE,NEW_CURVE))
    p=OUT/'nucleo/Inc/acim_vf_parameters.h'
    s=once(read(p),'/* The voltage offset to compensate the voltage drop on stator winding under a minimum frequency */',
        '/* Phase-peak voltage anchor at MIN_FREQUENCY_TH/2 for the smooth low-speed envelope. */')
    s=once(s,'/* Minimum frequency threshold for voltage offset impressing */',
        '/* Join frequency: voltage and slope match the original linear V/f branch here. */')
    write(p,s)
    p=OUT/'web_hmi/server.py';s=read(p)
    lines=[]
    for line in s.splitlines(keepends=True):
        if 'not in (' in line:
            line=line.replace(',2026102104)',',2026102104,2026102402)').replace(', 2026102104)',', 2026102104, 2026102402)')
        if 'mc_fw_build' in line and ' in (2026102102,2026102104):' in line:
            line=line.replace(' in (2026102102,2026102104):',' in (2026102102,2026102104,2026102402):')
        lines.append(line)
    s=''.join(lines)
    s=once(s,'        (2026102103, 2026102104),','        (2026102103, 2026102104),\n        (2026102401, 2026102402),')
    s=once(s,'(2026102103,2026102104)) and','(2026102103,2026102104),(2026102401,2026102402)) and')
    write(p,s)
    m=dict(schema='mic_ai.vf_smooth_start.v1',predecessor=str(BASE),pair_compatibility_ids=list(NEW),
        built=False,selftest_pass=False,installed=False,record_schema=5,record_bytes=320,
        pwm_or_motor_control_changed=True,vf_envelope_changed=True,
        low_frequency_envelope='linear + 8*max(0,Vanchor-k*F/2)*x*(1-x)^2, x=f/F; below F only',
        join_frequency_hz=10,half_join_frequency_phase_peak_anchor_v=20,
        zero_frequency_phase_peak_v=0,linear_branch_from_hz=10,
        calibration_changed=False,break_filter_changed=False,control_protocol_changed=False,
        uart_changed=False,uart_tx_backend_changed=False,watchdogs_changed=False,
        recovery_budget_changed=False,automatic_restart_added=False,
        hardware_commands=0,motor_commands=0,mcu_flash_commands=0,operationally_qualified=False,
        limitations=['Host ramp/PWM tests do not establish physical motor stability or pin timing',
            'Starting torque below5Hz changes and needs later motor qualification',
            'Sinusoidal-PWM bus-voltage limitation is preserved',
            'This envelope correction does not prove a physical UART or SD fault cause'])
    write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
