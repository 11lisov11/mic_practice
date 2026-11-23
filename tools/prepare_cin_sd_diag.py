"""Prepare 3101/3102 from verified 3013/3014, entirely offline."""
import hashlib,json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261030/boot_reset_capture_r1'
OUT=ROOT/'artifacts/live_bench_20261031/cin_sd_diag_r1'
NEW=(2026103101,2026103102)
SOURCE=ROOT/'tools/cin_sd_diag'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert not OUT.exists(),'Never overwrite a prepared package or evidence'
 for rel,h in json.loads(read(BASE/'source_hashes.json')).items():assert sha(BASE/rel)==h,rel
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def cp(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    a=read(f);b=a.replace('2026103013',str(NEW[0])).replace('2026103014',str(NEW[1])).replace('3013-boot-capture','3101-cin-sd-diag')
    if a!=b:write(f,b)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):write(OUT/folder/'cin_wire.h',read(SOURCE/'cin_wire.h'))
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'static void mic_send_boot_page(uint32_t now_ms){',read(SOURCE/'native.inc')+'\nstatic void mic_send_boot_page(uint32_t now_ms){')
 s=once(s,'      mic_send_boot_page(now_ms);','      mic_send_cin_page(now_ms);\n      mic_send_boot_page(now_ms);')
 s=once(s,'  /* USER CODE BEGIN ADC2_Init 2 */','  /* USER CODE BEGIN ADC2_Init 2 */\n  cin_diag_init();')
 s=once(s,'    uno_link_poll();','    cin_diag_service(HAL_GetTick(),!LL_TIM_IsEnabledAllOutputs(TIM1)&&!uno_link.command_enabled,mic_current_zero_is_ready()!=0U);\n    uno_link_poll();')
 # Reject native enable frames before the MCSDK start/reference branch. No
 # safety threshold or CLEAR/STOP semantics is changed by this diagnostic gate.
 s=once(s,'  if((mode==9U||mode==6U)&&ma_native_complete()){uno_stop_motor();return;}',
  '  /* CIN diagnostic build: no motor enable, even if a host sends START. */\n  if(flags==UNO_FLAG_ENABLE){uno_stop_motor();return;}\n  if((mode==9U||mode==6U)&&ma_native_complete()){uno_stop_motor();return;}')
 write(f,s)
 f=OUT/'nucleo/Inc/current_shunt.h';s=read(f);s=once(s,'void mic_current_init(void);','void mic_current_init(void);\nuint8_t mic_current_zero_is_ready(void);');write(f,s)
 f=OUT/'nucleo/Src/current_shunt.c';write(f,read(f)+'\n/* Read-only diagnostic eligibility; zero thresholds are unchanged. */\nuint8_t mic_current_zero_is_ready(void){return state.zero_ready;}\n')
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'static mb_receiver g_native_boot={};','static mb_receiver g_native_boot={};\n#include "cin_wire.h"\nstatic cd_receiver g_cin_diag={};')
 s=once(s,'      if(buf[2]==MB_WIRE){','''      if(buf[2]==CD_WIRE){
        const uint32_t now=millis();
        const bool off=g_bp_mcsdk_telemetry&&!g_pwm_enabled&&!(g_bp_status&0x22U)&&(uint32_t)(now-g_bp_last_rsp_ms)<300U;
        (void)cd_receive(&g_cin_diag,buf,g_bp_fw_build,off,now);continue;
      }
      if(buf[2]==MB_WIRE){''')
 a='      memset(&g_native_boot,0,sizeof(g_native_boot));';assert s.count(a)==2
 s=s.replace(a,a+'\n      memset(&g_cin_diag,0,sizeof(g_cin_diag));')
 s=once(s,'    s += " mc_boot_packet_hex=";', '''    s += " cin_packet_hex=";
    if(g_cin_diag.received){static const char digits[]="0123456789abcdef";
      for(unsigned i=0;i<UV3_FRAME;++i){s+=digits[g_cin_diag.packet[i]>>4];s+=digits[g_cin_diag.packet[i]&15U];}
    }else s+="-";
    s += " cin_fresh=";s+=String(cd_fresh(&g_cin_diag,g_bp_fw_build,native_fresh&&!g_pwm_enabled&&!(g_bp_status&0x22U),millis())?1:0);
    s += " cin_good=";s+=String((unsigned long)g_cin_diag.good);
    s += " cin_bad=";s+=String((unsigned long)g_cin_diag.bad);
    s += " mc_boot_packet_hex=";''')
 s=once(s,'        (void)mb_receive(&g_native_boot,buf,g_bp_fw_build,fresh,now);continue;',
 '''        const bool previous_boot=g_native_boot.received;
        const uint32_t previous_crc=previous_boot?mb_u32(g_native_boot.packet+30):0;
        if(mb_receive(&g_native_boot,buf,g_bp_fw_build,fresh,now)&&previous_boot&&
           previous_crc!=mb_u32(g_native_boot.packet+30))memset(&g_cin_diag,0,sizeof(g_cin_diag));
        continue;''')
 write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 s=once(s,'def boot_wire_status(kv):',read(SOURCE/'web_status.py')+'\n\ndef boot_wire_status(kv):')
 s=once(s,'                **boot_wire_status(kv),','                **boot_wire_status(kv),\n                **cin_sd_status(kv),')
 a='def command_guard_check(cmd: str, data: Optional[dict], cfg: CommandGuardConfig) -> tuple[bool, str]:'
 s=once(s,a,a+'\n    if command_requests_start(cmd) or command_requests_service_output(cmd):\n        return False,"CIN_DIAGNOSTIC_ONLY: motor and service starts disabled"')
 a='        """Confirm safety, then wait for the autonomous AC soft-start and PWM."""'
 s=once(s,a,a+'\n        return False,"CIN_DIAGNOSTIC_ONLY: no motor start",None')
 write(f,s)
 f=OUT/'web_hmi/static/app.js';s=read(f)
 s=once(s,'  const sdText = data.mc_sd_live?.summary_ru || "Текущий SD: нет измерения";',
  '  const sdText = data.mc_sd_live?.summary_ru || "Текущий SD: нет измерения";\n  const cinText=data.cin_sd?.summary_ru||"CIN: ожидание отсчёта";')
 s=once(s,'· ${sdText}`;','· ${sdText} · ${cinText}`;')
 s=once(s,'    startBtn.disabled = !manualStartAllowed(data, hvArmed);','    startBtn.disabled = true; // CIN diagnostic build: motor starts disabled')
 write(f,s)
 # Keep hashes of existing captures; do not modify any archived package/manifest.
 preserved={}
 for folder in (ROOT/'artifacts/live_bench_20261031',BASE):
  for f in folder.rglob('*'):
   if f.is_file() and OUT not in f.parents and f.suffix.lower() in ('.sal','.bin') and ('readback' in f.name or 'wave' in f.name or 'RAM' in f.name or f.suffix.lower()=='.sal'):
    preserved[f.relative_to(ROOT).as_posix()]=sha(f)
 write(OUT/'preserved_capture_hashes.json',json.dumps(preserved,indent=2))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.cin_sd_off_diag.v1',pair=list(NEW),base_pair=[2026103013,2026103014],built=False,installed=False,
  hardware_commands=0,START=0,CLEAR=0,flash_commands=0,thresholds_changed=False,adc_injected_changed=False,
  motor_starts_disabled=True,adc_input='PB11 / CN10-18 / ADC2_IN14',SD_input='PA6 / existing TIM1_BKIN',
  sampling='OFF-only, 10Hz after zero-ready + 5s boot settling',reference_mv_nominal=3290,voltage_is_approximate=True,
  current_trip_A=1.35,ADC_guard_ticks=2048,estimate_age_limit_ms=2,fast_budget_cycles=5312),indent=2))
 print(json.dumps(dict(prepared=True,pair=NEW,preserved_files=len(preserved),hardware_commands=0)))
if __name__=='__main__':main()
