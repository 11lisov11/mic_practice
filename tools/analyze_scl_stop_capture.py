"""Offline audit of saved2704 I2C captures; no bench tools or network access."""
import hashlib,json,struct,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261027/nucleo_i2c_stop_recovery_r1'
OUT=ROOT/'artifacts/live_bench_20261027/scl_stop_audit_r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(exist_ok=True)
 rawfile=C/'powered_first_fault_5hz_r1/trial/first_i2c_capture.json'
 data=json.loads(rawfile.read_text(encoding='utf-8'));w=struct.unpack('<40I',bytes.fromhex(data['pwm_hex']))
 assert w[1]==2026102704 and w[5]==0x8011 and w[35]==0x8001 and w[36]&1 and w[37]&0x4000
 bitnames={0:'TXE',1:'TXIS',2:'RXNE',3:'ADDR',4:'NACKF',5:'STOPF',6:'TC',7:'TCR',8:'BERR',9:'ARLO',10:'OVR',15:'BUSY'}
 flags=lambda value:[name for bit,name in bitnames.items() if value&(1<<bit)]
 ccipr=(w[15]>>12)&3;cfgr=w[33];sysclk=w[32]
 hpre=(cfgr>>4)&15;ppre=(cfgr>>8)&7
 assert hpre==ppre==0 and ccipr==2
 kernel=16000000;ratio=sysclk/kernel
 assert not 1.5<=ratio<=3
 # Produce a discriminating counter deduction directly from the installed C
 # branches. Forced PE reset is either cleanup expiry or prepare2 preflight.
 a=json.loads((C/'powered_first_fault_5hz_r1/analysis.json').read_text(encoding='utf-8'))
 deductions=[]
 for run in a['runs']:
  v=run['counters'];preflight_forced=v['forced_resets']-v['cleanup_expired']
  assert preflight_forced==v['busy'] and v['setup']==0
  deductions.append(dict(run=run['name'],before_start_after_enable_errors=preflight_forced,reason='ec_finish(state0): forced iff prepare2; ec_recover: forced iff expired; primary_setup0'))
 # Identical readbacks admit two physically distinct hypotheses. GPIO IDR is
 # a wired-AND observation; it does not identify the source pulling LOW.
 observed=[]
 for owner in ('controller_output_low','external_line_low'):
  master_low=owner=='controller_output_low';external_low=not master_low
  scl_high=not(master_low or external_low)
  observed.append(dict(hypothesis=owner,terminal_gpio=(w[38]&~256)|(256 if scl_high else 0),isr=w[35],cr1=w[36],cr2=w[37],hypothetical_scl_after_PE0=0 if external_low else 1))
 assert observed[0]['terminal_gpio']==observed[1]['terminal_gpio']==w[38]
 for key in ('isr','cr1','cr2'):assert observed[0][key]==observed[1][key]
 exe=OUT/'probe_test.exe';cpp=ROOT/'tools/scl_stop_audit/probe_test.cpp'
 command=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)]
 for name,args in [('probe_compile',command),('probe_test',[str(exe)])]:
  r=subprocess.run(args,capture_output=True,text=True,timeout=20)
  (OUT/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
  if r.returncode:print(r.stdout+r.stderr);r.check_returncode()
 probe=json.loads(r.stdout);assert probe['passed']
 manifest=json.loads((C/'manifest.json').read_text(encoding='utf-8'))
 for table in ('source_sha256','build_sha256','verification_sha256'):
  for path,h in manifest[table].items():assert sha(C/path)==h,path
 result=dict(passed=True,scope='Offline exclusion/observability audit and differential diagnostic module tests, NOT a root-cause fix',hardware_commands=0,installed_sources_images_unchanged=True,physical_root_cause_identified=False,firmware_root_cause_fix_prepared=False,
  record=dict(sha256=sha(rawfile),first_flags=flags(w[5]),terminal_flags=flags(w[35]),first_gpio=w[7],terminal_gpio=w[38],terminal_cr2=hex(w[37]),age_us=w[25]*1e6/sysclk,cleanup_us=((w[39]-w[3])&0xffffffff)*1e6/sysclk,scl_before=False,scl_terminal=False,sda_terminal=bool(w[38]&512),post_PE_off_observation_present=False,continuous_scl_low_proven=False),
  clocks=dict(sysclk_hz=sysclk,apb1_hz=sysclk,i2c_kernel_hz=kernel,kernel_source='HSI16 per RCC_CCIPR',ratio=ratio,errata_2_11_5_frequency_condition_met=False,revision='X per saved programmer log'),
  exclusions_ru=[
   'AS5600 не выполняет штатный clock stretching: SCL у него вход. Это не исключает внешнюю электрическую нагрузку, потерю питания или повреждение.',
   'ISR не содержит TXIS/RXNE/TC/TCR: обычное ожидание обработки байта не объясняет конечный снимок. Незавершённое чтениепоследнегоRXNE из известного примера форума не соответствует этому событию.',
   'Условие ES0431 2.11.5: отношение APB/I2C от1.5до3; в записанной конфигурации10.625. Обход prefetch первого байта без выполнения условия не является доказанным исправлением.',
   'ПервыйNACK произошёл за278мкс при3мс бюджете. Увеличение deadline не исправляет его причину.',
   'NOSTRETCH нельзя устанавливать в controller mode. Увеличение тайм-аута, игнорированиеNACK/ARLO и ручные импульсы не обоснованы сохранённым захватом.'],
  counter_deductions=deductions,indistinguishable_hypotheses=observed,probe=probe,
  correction_ru='Слова «SCL оставался LOW все505мкс» были сильнее данных. LOW наблюдался в двух конечных точках; уровня между ними и послеPE0 в записи нет.',
  next_observation_ru='Нужны GPIO/ISR/CR1/CR2 непосредственно после уже выполняемого PE0 и при последующих OFF-проверках с настоящими временными отметками. HIGHпослеPE0 поддерживает версию контроллера, но само по себе не доказывает её; LOWпослеPE0 при корректной AF/OD конфигурации фиксирует сохранение внешнего уровня. Модуль pe_release_probe.h подготовлен и проверен отдельно, НЕ встроен в прошивку и НЕ записан.',
  proposed_integration_ru=['В capture_terminal при FORCED сохранить pending mask и terminal cycles/GPIO; исходные160Б не менять.','В существующем park сразу после PE0/readback/DSB снять первый snapshot; никаких дополнительных GPIOwrites.','В главном цикле получить отложенные samples при PE0, фактические DWTcycles; позднийpoll помечатьlate, не изображать5мкс.','Экспортировать отдельную CRC-версионированную extension с exact peer; не переопределять старый format2. Это следующая целевая диагностика, не уже готовая/установленная прошивка.'],
  sources=[{'url':'https://cdn.sparkfun.com/assets/f/a/b/b/a/AS5600_Datasheet.pdf','author':'ams','section':'I2C Interface, p10: SCL input, no clock stretching'}, {'url':'https://www.st.com.cn/resource/en/errata_sheet/es0431-stm32g431xx441xx-device-errata-stmicroelectronics.pdf','section':'ES0431 Rev9,2.11.1–2.11.6,especially2.11.5'}, {'url':'https://www.st.com/resource/en/reference_manual/rm0440-stm32g4-series-advanced-armbased-32bit-mcus-stmicroelectronics.pdf','section':'I2C master CR1 PE/NOSTRETCH, CR2 STOP, TXIS/TC/TCR/RXNE; relevant sections reviewed, full local PDF download failed'}])
 (OUT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:result[k] for k in ('passed','hardware_commands','installed_sources_images_unchanged','physical_root_cause_identified','firmware_root_cause_fix_prepared','counter_deductions','probe')}))
if __name__=='__main__':main()
