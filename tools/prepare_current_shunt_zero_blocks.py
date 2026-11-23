"""Bounded three-block zero verification, with unchanged span/bias limits."""
import json
import shutil
import prepare_current_shunt_monitor as util
import prepare_current_shunt_channels as previous

ROOT=util.ROOT
BASE=previous.OUT
OUT=BASE.parent/'current_shunt_monitor_r4'
OLD=(2026102409,2026102410)
NEW=(2026102411,2026102412)

def main():
    assert not OUT.exists()
    m=json.loads(util.read(BASE/'manifest.json'))
    assert m['installed'] and m['installation_flash_verified']
    for rel,digest in m['source_sha256'].items():assert util.sha(BASE/rel)==digest,rel
    for folder in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/folder,OUT/folder,ignore=shutil.ignore_patterns('Debug','__pycache__'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (OUT/folder).rglob('*'):
            if p.is_file():util.write(p,util.read(p).replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1])))
    for name,dest in [('current_core.h','nucleo/Inc/current_core.h'),('current_shunt.c','nucleo/Src/current_shunt.c'),('current_wire.h','UNOQ_MOTOR/current_wire.h')]:
        util.write(OUT/dest,util.read(ROOT/'tools/current_shunt_monitor'/name).replace('2026102406',str(NEW[1])))
    p=OUT/'nucleo/Src/main.c';s=util.read(p)
    s=util.once(s,'mic_current_packet(packet,(uint8_t)(slot==0U),MIC_NUCLEO_FW_BUILD_ID);',
                    'mic_current_packet(packet,(uint8_t)(slot==0U?1U:slot==2U?2U:0U),MIC_NUCLEO_FW_BUILD_ID);')
    util.write(p,s)
    p=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=util.read(p)
    s=util.once(s,'if(buf[2]==CT_SUMMARY || buf[2]==CT_DETAIL)',
                   'if(buf[2]==CT_SUMMARY || buf[2]==CT_DETAIL || buf[2]==CT_QUALITY)')
    rpc='''  s += " mc_current_quality_hex=";
  if(g_current.has_quality) for(unsigned i=0;i<UV3_FRAME;++i) {
    s += break_hex[g_current.quality[i]>>4];s += break_hex[g_current.quality[i]&15];
  } else s += "-";
  s += " mc_current_quality_age_ms=";s += String((unsigned long)(g_current.has_quality?millis()-g_current.quality_ms:999999U));
'''
    s=util.once(s,'  s += " mc_current_good=";',rpc+'  s += " mc_current_good=";');util.write(p,s)
    p=OUT/'web_hmi/server.py';s=util.read(p)
    a=s.index('# Imported as source into the HMI;');b=s.index('def with_motor_controller_aliases',a)
    decoder=s[a:b].replace(str(OLD[0]),str(NEW[0])).replace(str(OLD[1]),str(NEW[1]))
    decoder=util.once(decoder,'mc_current_flags=0, mc_current_coverage_pct=0,','mc_current_zero_spans=None, mc_current_zero_attempts=None, mc_current_zero_stable=None,\n                mc_current_flags=0, mc_current_coverage_pct=0,')
    decoder=util.once(decoder,'        detail_age = int(data.get(\'mc_current_detail_age_ms\', 999999))',
'''        quality_age = int(data.get('mc_current_quality_age_ms', 999999))
        if 0 <= quality_age < 1500:
            quality = packet('mc_current_quality_hex', 0xd7)
            lows = [int.from_bytes(quality[i:i+2], 'little') for i in range(14, 22, 2)]
            highs = [int.from_bytes(quality[i:i+2], 'little') for i in range(22, 30, 2)]
            if quality[5] > 8 or quality[30] > 3 or quality[32:36] != bytes((3, 8, 40, 2)):
                raise ValueError('Invalid zero quality contract')
            data.update(mc_current_zero_spans=[hi-lo for lo,hi in zip(lows,highs)],
                        mc_current_zero_attempts=quality[5], mc_current_zero_stable=quality[30],
                        mc_current_zero_last_reject=quality[31])
        detail_age = int(data.get('mc_current_detail_age_ms', 999999))''')
    decoder=decoder.replace("'Неверный или нестабильный ноль: проверьте токовые каналы'",
                            "'Автоноль отклонён после проверки нескольких блоков; смотрите разброс каналов'")
    s=s[:a]+decoder+s[b:]
    s=util.once(s,'        (2026102409, 2026102410),','        (2026102409, 2026102410),\n        (2026102411, 2026102412),')
    s=util.once(s,'(2026102409,2026102410)) and','(2026102409,2026102410),(2026102411,2026102412)) and')
    s=''.join(line.replace(',2026102410)',',2026102410,2026102412)').replace(', 2026102410)',', 2026102410, 2026102412)')
        if ('not in (' in line or ('mc_fw_build' in line and ' in (2026' in line)) else line
        for line in s.splitlines(keepends=True))
    s=util.once(s,'("mc_current_packet_hex", "mc_current_detail_hex")','("mc_current_packet_hex", "mc_current_detail_hex", "mc_current_quality_hex")')
    s=util.once(s,'("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_good", "mc_current_bad")',
                   '("mc_current_age_ms", "mc_current_detail_age_ms", "mc_current_quality_age_ms", "mc_current_good", "mc_current_bad")')
    util.write(p,s)
    p=OUT/'web_hmi/static/app.js';s=util.read(p)
    s=util.once(s,'  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS',
'''  if (Array.isArray(data.mc_current_zero_spans)) {
    document.getElementById("shuntCurrentAdc").textContent +=
      ` Разброс: ${data.mc_current_zero_spans.join(" / ")} отсч.; ` +
      `стабильных блоков ${data.mc_current_zero_stable}/3, проверено ${data.mc_current_zero_attempts}/8. Предел разброса 40.`;
    const why = [];
    const reject = Number(data.mc_current_zero_last_reject || 0);
    if (reject & 1) why.push("разброс блока больше 40");
    if (reject & 2) why.push("средний уровень вне 1600–2500");
    if (reject & 4) why.push("средние блоков расходятся больше чем на 2");
    if (why.length) document.getElementById("shuntCurrentAdc").textContent += ` Причина: ${why.join("; ")}.`;
  }
  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS''')
    util.write(p,s)
    for folder in ('build/uno','build/nucleo'):(OUT/folder).mkdir(parents=True)
    for key in ('source_sha256','build_sha256','verification_sha256','verification_summary','runtime_report','completion_report','installation_report'):
        m.pop(key,None)
    m.update(pair_compatibility_ids=list(NEW),predecessor=str(BASE),built=False,selftest_pass=False,
        installed=False,installation_flash_verified=False,installation_calibration_unchanged=False,
        installation_runtime_pair_verified=False,adc_idle_zero_verified=False,uart_idle_60s_verified=False,
        hmi_browser_panel_verified=False,zero_required_consecutive_blocks=3,zero_maximum_blocks=8,
        zero_span_limit_counts=40,zero_bias_range_counts=[1600,2500],zero_block_mean_spread_counts=2,
        zero_acceptance_unchanged=False,zero_per_block_limits_unchanged=True,zero_quality_version=0xd7,
        zero_uses_multiple_blocks=True,hardware_commands=0)
    util.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(OUT)

if __name__=='__main__':main()
