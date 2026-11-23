"""Prepare a permanent timing fix from installed 2931/2932; no board commands."""
import os,json,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/standstill_commissioning_r1'
OUT=ROOT/'artifacts/live_bench_20261029/standstill_timing_r1'
NEW=(2026102933,2026102934)
def main():
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  assert not (OUT/folder).exists()
  def copy(src,dest):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dest);return dest
   return shutil.copy2(src,dest)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    s=read(f);n=s.replace('2026102931','2026102933').replace('2026102932','2026102934')
    if s!=n:write(f,n)
 f=OUT/'web_hmi/server.py';s=read(f)
 s=s.replace('(2026102933,2026102934)', '(2026102931,2026102932), (2026102933,2026102934)') if False else s
 # Only measurement-identity allowlists need the predecessor too; runtime pair
 # checks remain exact. The persistent calibration itself is never rewritten.
 s=s.replace('(2026102921,2026102922), (2026102933,2026102934)',
  '(2026102921,2026102922), (2026102931,2026102932), (2026102933,2026102934)')
 write(f,s)
 f=OUT/'nucleo/Inc/identify_core.h';s=read(f)
 s=once(s,'float peak,min_bus,max_bus;','float peak,min_bus,max_bus,axis_cos,axis_sin;')
 s=once(s,'s->voltage_amplitude=fminf(24,fabsf(c->amplitude)*c->rs);return 1;',
  's->axis_cos=cosf(c->axis);s->axis_sin=sinf(c->axis);\n  s->voltage_amplitude=fminf(24,fabsf(c->amplitude)*c->rs);return 1;')
 s=once(s,'const float ca=cosf(c->axis),sa=sinf(c->axis);','const float ca=s->axis_cos,sa=s->axis_sin;')
 s=once(s,'ma_modulate(&s->modulation,g,MA_ADAPTIVE,va,vb,x->bus,out)',
  'ma_modulate(&s->modulation,g,MA_FOC,va,vb,x->bus,out)')
 s=once(s,'  uint8_t fault=0;','  uint8_t fault=0;\n  const float current_sq=x->ia*x->ia+x->ib*x->ib;')
 s=once(s,'else if(hypotf(x->ia,x->ib)>.45f)','else if(!(current_sq<=.45f*.45f))')
 s=once(s,'phase=6.2831853072f*c->frequency*t;sv=sinf(phase);\n    unsigned cycle=(unsigned)(c->frequency*t),settle=mi_settle_cycles(c);',
  'const float cycle_position=c->frequency*t;\n    unsigned cycle=(unsigned)cycle_position,settle=mi_settle_cycles(c);\n    phase=6.2831853072f*(cycle_position-cycle);sv=sinf(phase);')
 s=once(s,'s->peak=fmaxf(s->peak,hypotf(x->ia,x->ib));','if(current_sq>s->peak*s->peak)s->peak=sqrtf(current_sq);\n    ')
 s=once(s,'float record_phase=c->kind==MI_AC?6.2831853072f*c->frequency*ts:0;','float record_phase=0;')
 s=once(s,'float cycles=c->frequency*ts;unsigned complete=(unsigned)cycles;',
  'float cycles=c->frequency*ts;unsigned complete=(unsigned)cycles;\n      record_phase=6.2831853072f*(cycles-complete);')
 write(f,s)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  f=OUT/folder/'identify_wire.h';s=read(f)
  s=s.replace('duration_ms,accepted,good,bad','duration_ms,timing_cycles,good,bad')
  s=once(s,'nonce&&nonce==m->config_crc&&!manual&&','nonce&&nonce==m->config_crc&&!manual&&!m->fault&&m->timing_cycles>0&&m->timing_cycles<=4800U&&')
  s=once(s,'p[2]!=ID_STATUS_WIRE||p[3]!=1','p[2]!=ID_STATUS_WIRE||p[3]!=2')
  s=once(s,'m->accepted=id_u32(p+34)','m->timing_cycles=id_u32(p+34)');write(f,s)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'static uint8_t id_configured;',
  'static uint8_t id_configured,id_prepared,id_profile_attempted;\nstatic uint32_t id_profile_cycles;\nstatic void mi_native_profile_off(void);')
 s=once(s,'if(algorithm==4)return id_configured&&!id_state.ready&&!id_state.done;',
  'if(algorithm==4)return id_configured&&!id_state.ready&&!id_state.done&&id_profile_cycles>0&&id_profile_cycles<=4800U;')
 s=once(s,'  if(mi_native_service())return;',
  '  mi_native_profile_off();\n  if(mi_native_service())return;')
 s=once(s,'  memset(&cached_sample,0,sizeof(cached_sample));running=0;return 1;',
  '''  if(!id_profile_cycles||id_profile_cycles>4800U||!mi_begin(&id_state,&id_config,0))return 0;
  id_state.active=0;id_prepared=1;
  memset(&cached_sample,0,sizeof(cached_sample));running=0;return 1;''')
 s=once(s,'id_config=id_staged;id_configured=1;id_stage_mask=0;',
  'id_config=id_staged;id_configured=1;id_prepared=0;id_stage_mask=0;')
 s=once(s,'if(op==6&&index==0&&mi_ack(&id_state,raw)){id_configured=0;',
  'if(op==6&&index==0&&mi_ack(&id_state,raw)){id_configured=0;id_prepared=0;')
 s=once(s,'  const uint32_t begin=DWT->CYCCNT;ma_current_sample sample;',
  '  if(!LL_TIM_IsEnabledAllOutputs(TIM1))return MC_NO_ERROR;\n  const uint32_t begin=DWT->CYCCNT;ma_current_sample sample;')
 s=once(s,'if(!id_configured||!mi_begin(&id_state,&id_config,sample.cycles))return MC_SW_ERROR;',
  'if(!id_configured||!id_prepared)return MC_SW_ERROR;\n    id_state.start=sample.cycles;id_state.active=1;id_prepared=0;')
 s=once(s,'p[2]=ID_STATUS_WIRE;p[3]=1;', 'p[2]=ID_STATUS_WIRE;p[3]=2;')
 s=once(s,'id_put(p+34,id_state.accepted);','id_put(p+34,id_profile_cycles);')
 s+='\n'+read(ROOT/'tools/motor_commissioning/native_profile_off.inc');write(f,s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 anchor='    s += " id_valid=";s += String(id_fresh?1:0);'
 s=once(s,anchor,anchor+'\n    s += " id_timing_cycles=";s += String((unsigned long)g_id_meta.timing_cycles);')
 write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 anchor='                "id_valid": int(kv.get("id_valid","0")),'
 s=once(s,anchor,anchor+'\n                "id_timing_cycles": int(kv.get("id_timing_cycles","0")),');write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2931-commissioning','2933-timing'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.standstill_timing.v1',pair=list(NEW),base_pair=[2026102931,2026102932],
  built=False,installed=False,physical_qualification=False,thresholds_changed=False,adc_guard_changed=False,
  start_commands=0,off_profile_is_synthetic=True),indent=2))
 print('2933/2934 source prepared; no hardware commands')
if __name__=='__main__':main()
