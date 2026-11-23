"""Record the completed install from readback and real stopped verification."""
import json
from datetime import datetime,timezone
import prepare_standstill_commissioning as p
def main():
 out=p.OUT/'hardware_install_r1'
 first=json.loads(p.read(out/'install_report.json'));recovery=json.loads(p.read(out/'runtime_recovery.json'))
 idle=json.loads(p.read(out/'idle_verification/report.json'))
 assert first['uno_readback_verified'] and first['nucleo_readback_verified']
 assert first['uno_flash_commands']==first['nucleo_flash_commands']==1
 assert recovery['passed'] and recovery['calibration_unchanged'] and recovery['archived_captures_unchanged']
 assert idle['passed'] and not idle['start_commands'] and not idle['execute_commands']
 s=idle['final_status'];assert (s['fw_build'],s['mc_fw_build'])==p.NEW and s['pwm']==0 and s['algorithm_selected']==1
 report=dict(passed=True,pair=list(p.NEW),completed_utc=datetime.now(timezone.utc).isoformat(),
  uno_flash_commands=1,nucleo_flash_commands=1,uno_readback_verified=True,nucleo_readback_verified=True,
  additional_flash_commands=0,verified_uno_restart_commands=recovery.get('verified_uno_restart_commands',0),
  calibration_unchanged=True,archived_captures_unchanged=True,preserved_capture_files=recovery['preserved_capture_files'],
  stopped_configuration_verified=True,algorithm_order=[x['algorithm'] for x in idle['states']],
  configuration_commands=idle['config_commands']+len(idle['states']),start_commands=0,clear_commands=0,execute_commands=0,
  references=['install_report.json','runtime_recovery.json','idle_verification/report.json'])
 p.write(out/'installation_summary.json',json.dumps(report,indent=2))
 m=json.loads(p.read(p.OUT/'manifest.json'));m.update(installed=True,readback_verified=True,
  hardware_configuration_switch_verified=True,hardware_commands_sent=report['configuration_commands'],
  installation_report='hardware_install_r1/installation_summary.json')
 p.write(p.OUT/'manifest.json',json.dumps(m,ensure_ascii=False,indent=2))
 f=p.OUT/'REPORT_RU.md';text=p.read(f)
 text=text.replace('**Эта пара не записывалась на платы, чтение обратно и измерение двигателя не выполнялись. Установленная пара остаётся 2921/2922.** START/CLEAR/ARM/RESET в этом этапе не отправлялись.',
  '**Пара 2931/2932 установлена, обе записи проверены чтением обратно. Измерение двигателя пока не выполнялось.** По одной записи на плату; для восстановления регистрации RPC выполнен дополнительный перезапуск проверенных образов без записи flash. START/CLEAR/ARM не отправлялись.')
 text=text.replace('До физического опыта нужно установить эту пару, проверить чтением обратно, связь и отсутствие самозапуска; затем отдельно проверить текущую сборку стенда перед подачей силового.',
  'Установка, чтение обратно, связь и отсутствие самозапуска проверены. Реальная последовательность V/f→FOC→адаптивный ШИМ→IDENT→V/f пройдена при ШИМ=0, подтверждены параметры IDENT по CRC. Профиль FOC не загружался; квалификация осталась 0. Перед физическим опытом требуется переход на автономное питание и проверка текущей сборки стенда.')
 p.write(f,text)
 print(json.dumps(report))
if __name__=='__main__':main()
