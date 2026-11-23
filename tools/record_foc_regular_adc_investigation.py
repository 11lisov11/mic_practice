"""Preserve causal limits and candidate state; no hardware writes."""
import json,hashlib,math,urllib.request
import prepare_foc_regular_adc_fix as p
def main():
 out=p.OUT;assert not (out/'investigation.json').exists()
 sample=json.loads(p.read(p.BASE/'powered_FOC_CPU_IRQ_20261030_r2/ADC_peak_decoded.json'))
 previous,bad=sample['samples'][9:11]
 m=json.loads(p.read(out/'manifest.json'));assert m['built'] and not m['installed']
 # No independent current reference was recorded. Do not relabel this as a
 # known false trip or raise threshold to hide it.
 info=dict(classification='measurement error suspected, not proven',
  measured_raw_step_ADC1=83,measured_raw_step_ADC2=3,
  normal_regular_EOC_sequence=2089,trip_regular_EOC_sequence=2097,
  regular_EOC_not_sufficient_to_classify=True,
  raw_previous=previous,raw_bad=bad,
  unique_real_vs_ADC_classification_not_possible_from_two_sensors_and_reconstruction=True,
  independent_current_reference_recorded=False,
  physical_model_is_estimated_not_identified=True,
  concrete_source_defect='MCSDK RCM_ExecRegularConv used synchronously on ADC1 while injected current conversions active, contrary to its source API contract.',
  correction='RUN: launch one regular conversion from ADC IRQ tail only in middle down-count window. SysTick uses completed caches; TIM1 checks safety freshness and stops on failure.',
  launch_guard_ticks=dict(after_apex=512,before_bottom=1024),
  regular_conversion_nominal_ticks=240,setup_budget_before_bottom_ticks=784,
  safety_sampling_per_channel_nominal_Hz=8000,original_safety_task_Hz=2000,
  cache_watchdog_ms=1,unknown_exact_hardware_setup_cycles=True,
  unchanged=dict(current_trip_A=1.35,ADC_guard_ticks=2048,ADC_feedback_math=True,
   window_guards=True,IRQ_priorities=True,observer_and_motor_profile=True,hardware_BKIN=True),
  no_smoothing_or_spike_discard_added=True,
  verified=dict(actual_C_manager_frames=80000,simulated_seconds=5,physical_seconds_tested=0,
   timer_policy_cases=10626,missing_EOC_stale_cache_and_wrap=True,
   source_safety_task_still_checks_bus_and_temperature=True,
   actual_fault_still_returns_MA_CURRENT=True),
  silicon_revision='X; CubeProgrammer readback log',
  errata_review='Commonly suggested ADC errata either excludeRevX or do not meet mode/clock/time conditions. Cannot use them to prove this event.',
  official_source='https://www.st.com/resource/en/errata_sheet/es0431-stm32g431xx441xx-device-errata-stmicroelectronics.pdf',
  pair=list(p.NEW),built=True,installed=False,new_START=0,new_CLEAR=0,new_flash=0,
  discarded_offline_draft='foc_regular_adc_fix_r1 is unbuilt and never installed; use onlyr2',
  hardware_confirmation_pending=True)
 op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with op.open('http://192.168.1.138:8080/api/status',timeout=8) as response:obj=json.load(response)
 s=obj['data'];assert (s['fw_build'],s['mc_fw_build'])==(2026103003,2026103004)
 assert s['state']=='SAFE' and s['pwm']==0
 p.write(out/'status_after_analysis.json',json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
 p.write(out/'investigation.json',json.dumps(info,ensure_ascii=False,indent=2)+'\n')
 f=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(f);idx=old.index('## 2026-10-30:')
 note='''## 2026-10-30:готовы3005/3006,разведеныregular/injectedADC;ещёнепрошиты

По3004захватуADC1шаг+83кода,ADC2+3;реконструкциядаётложно/реально1,363А,
порог1,35по-прежнемусрабатывает. EOCregularестькаквхорошем2089,такиплохом2097;
временистарта/channelрегулярнойгруппыинезависимоготоканет,поэтомуНЕЛЬЗЯ
утверждатьдоказаннуюошибкуАЦПилиреальныйвыброс. Вероятноизмерение,нефакт.
STLinkпоказываетRevX,errata2.5.8(Z)/2.5.10(Y)неподходят;2.5.9нетпаузы>1мс,
2.5.11ADC1/2ASYNC_DIV1исключены. SourceES0431st.comпроверен.

Подтверждёндефектинтеграции:SafetySysTickиспользуетблокирующий
RCM_ExecRegularConvнадADC1,занятыминжектированнымитоками,вопрекитекстуAPIST.
Исправление3006:ADCIRQtailсначалачитаетзавершённыйregular,запускаетследующий
тольковсерединеспада(CNT>1024иCNT<ARR-512). Regular47.5+12.5ADCcycles=240TIMticks.
TIM1послерегуляторапроверяетhealthcache,SysTickRUNберётготовыеданныебезSQR/ADSTART.
ПропавшийEOC/неподдерживаемыеADCпараметры/возрастcache>=1мсдаютMC_SW_ERROR
иШИМOFF,обетемпературная/шиннаязащитысохранены. OFFстарыйblockingAPIсохранён.
ADCfeedback/модель/наблюдатель/токовый1,35А/2048/5312/IRQприоритетыпрежние,
фильтраилиотбрасыванияскачканедобавлено. НовыхIRQmaskнет.

ПК:реальныйCmanager80000тактов(симуляция5сек),10626timerусловий,
cache-onlyRUN/потеряEOC/старениекэша/wrap/реальныйTSKостанавливаетШИМприhealthfault.
Записанныйвекторпо-прежнемудётMA_CURRENT. Обасобраныбезошибок,ELFprofileи
источникипроверены. 1045старыхфайловсохранены. Реальное5секподШИМНЕдоказано.
КандидатТОЛЬКОartifacts/live_bench_20261029/foc_regular_adc_fix_r2/manifest.json,
investigation.json. r1черновикнепостроен/неустановлен,неиспользовать.
Установлены3003/3004,ШИМOFF,питаниепользовательнеменял:J1ON/15ВON/повербанки.
START/CLEAR/flash0вэтомэтапе. ДлязаписикандидатанужноJ1OFF,метр<20В,обеUSBПК,
15Вимотор/шлейфоставить. install_foc_regular_adc_fix.py,readbackиOFFtiming;
новогосиловогопускавэтомэтапенебудет.

'''
 p.write(f,old[:idx]+note+old[idx:]);print(json.dumps(dict(pair=list(p.NEW),built=True,installed=False,
  outputs_off=True,classification_not_proven=True,old_files_preserved=m['preserved_files_verified'],new_hardware_commands=0)))
if __name__=='__main__':main()
