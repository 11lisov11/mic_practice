"""Record the authorized single trial and replay its ADC timing gates offline."""
import hashlib,json,shutil,subprocess,urllib.request
import prepare_foc_fast_budget_fix as p

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()

def main():
    pre=p.OUT/'powered_FOC_CPU_IRQ_20261030_r1'
    out=p.OUT/'powered_FOC_CPU_IRQ_20261030_r2'
    assert not (out/'analysis.json').exists(),'Never overwrite a recorded analysis'
    report=json.loads(p.read(out/'report.json'));s=report['after'];timing=s['foc_runtime'];fault=timing['first_fault']
    adc=json.loads(p.read(out/'ADC_peak_decoded.json'));sd=json.loads(p.read(out/'SD_before_decoded.json'))
    assert report['clear_commands']==report['start_commands']==1 and report['arm_commands']==1
    assert not report['passed'] and report['runtime_record_received'] and report['ADC_record_received']
    assert s['pwm']==0 and s['state']=='SAFE' and fault['reason_code']==2
    assert s['algorithm_fast_cycles']==4880 and s['algorithm_fast_cycles']<=5312
    assert s['mc_fault_current_mask']==s['mc_fault_occurred_mask']==128
    assert fault['sample_flags']==6 and fault['adc_age_us']<187.5 and fault['estimate_age_us']<2000
    assert report['prior_SD_record_retained']
    assert (pre/'SD_before.bin').read_bytes()==(out/'SD_before.bin').read_bytes()==(out/'SD_after.bin').read_bytes()
    matched=[row for row in adc['samples'] if row['cycles']==fault['adc_cycles']]
    assert len(matched)==1;failed=matched[0]
    assert failed['index']==10 and failed['sequence']==31759 and failed['timer_cnt_at_update']==2226
    assert failed['flags']==687 and not failed['accepted_by_monitor']
    assert failed['epoch_before']==failed['epoch_after'] and not failed['pending_epoch_mismatch']
    for field in ('three_leg_window_rejected','queue_overflow_observed','publish_deadline_missed','injected_queue_not_empty'):
        assert not failed[field],field
    assert all(16<=raw<=4079 for raw in failed['raw_adc'])
    rows=[]
    for row in adc['samples']:
        rows.append('{'+','.join(map(str,[row['timer_arr'],row['timer_cnt_at_update'],row['timer_dir_at_update'],
            *row['ccr_at_update'][:3],row['ccr_at_update'][3],row['pair'],row['timer_cnt_entry'],row['timer_dir_entry']]))+'}')
    source='''#include <cstdio>
#include "current_adc_deadline.h"
#include "current_adc_window_plan.h"
int main(){
 const unsigned rows[][10]={'''+','.join(rows)+'''};
 for(unsigned i=0;i<sizeof(rows)/sizeof(rows[0]);++i){const unsigned*r=rows[i];
  printf("%u,%d,%d,%d\\n",i,mic_adc_bottom_update(r[0],r[1],r[2]),
   mic_current_window_safe((uint8_t)r[7],r[3],r[4],r[5],r[6],771,112),
   mic_adc_publish_in_time(r[0],r[8],r[9],r[6]));
 }
}
'''
    cpp=out/'ADC_timing_replay.cpp';p.write(cpp,source);exe=cpp.with_suffix('.exe')
    compiled=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
        '-I',str(p.OUT/'nucleo/Inc'),str(cpp),'-o',str(exe)],capture_output=True,text=True)
    p.write(out/'ADC_timing_replay_build.log',compiled.stdout+compiled.stderr);compiled.check_returncode()
    played=subprocess.run([str(exe)],capture_output=True,text=True,check=True)
    p.write(out/'ADC_timing_replay.csv','index,bottom_update_ok,three_leg_window_ok,publish_in_time\n'+played.stdout)
    values=[list(map(int,line.split(','))) for line in played.stdout.splitlines()]
    assert len(values)==12 and values[10]==[10,0,1,1]
    assert all(row[1:]==[1,1,1] for row in values[:10])
    # Only GET after completed STOP, to freeze latest latch/SD state.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    for name,path in (('observed_after_analysis','/api/status'),('SD_after_decoded','/api/bkin-trace'),('SD_after_snapshots','/api/break-snapshot')):
        req=urllib.request.Request('http://192.168.1.138:8080'+path,headers={'X-UNOQ-Control-Token':token},method='GET')
        with opener.open(req,timeout=8) as response:obj=json.load(response)
        assert obj['ok'];p.write(out/(name+'.json'),json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    now=json.loads(p.read(out/'observed_after_analysis.json'))['data']
    assert now['state']=='SAFE' and now['pwm']==0 and now['run_id']==1
    preserved={}
    for rel in ('verification/preserved_captures_sha256.json','installation_verified_r1/preserved_installation_evidence.json'):
        preserved.update(json.loads(p.read(p.OUT/rel)))
    for rel,h in preserved.items():assert sha(p.ROOT/rel)==h,rel
    for name,h in json.loads(p.read(pre/'saved_files_sha256.json')).items():assert sha(pre/name)==h,name
    result=dict(trial_completed_5s=False,pair=list(p.NEW),clear_commands=1,start_commands=1,repeat_starts=0,
        flash_commands=0,reset_commands=0,outputs_off=True,physical_rotation_verified=False,
        run_session_elapsed_ms_not_exact_PWM_time=s['run_elapsed_ms'],
        ADC_frames=adc['total_samples'],ADC_frames_time_s_at_16kHz=adc['total_samples']/16000,
        frozen_retained_rows=len(adc['samples']),nominal_peak_in_retained_rows_A=max(abs(x) for row in adc['samples'] for x in row['nominal_currents_a']),
        real_current_scale_qualified=False,ADC_peak_trigger_seen=adc['peak_seen'],ADC_binary_sha256=sha(out/'ADC_peak.bin'),
        exact_first_reason='FT_ADC_INVALID',reason_code=2,algorithm_fault='MA_STALE',MCSDK_fault='MC_SW_ERROR',
        first_fault=fault,runtime_CPU_IRQ=timing,
        full_adapter_observed_max_cycles=s['algorithm_fast_cycles'],full_adapter_limit_cycles=5312,
        full_adapter_observed_max_us=s['algorithm_fast_cycles']/170,
        observed_fast_deadline_exceeded=False,no_guarantee_for_unobserved_paths=True,
        observed_observer_steps=fault['observer_steps'],
        exact_fault_row=failed,actual_C_timing_replay_passed=True,
        actual_C_bad_row_result=dict(bottom_update_ok=False,three_leg_window_ok=True,publish_in_time=True),
        proven_invalid_gate='mic_adc_bottom_update: update_cnt2226 >= unchanged2048',
        update_stamp_offset_us=2226/170,bottom_stamp_limit_us=2048/170,
        reason_for_late_update_stamp_not_proven=True,
        possible_latency_sources_not_diagnoses=['foreground PRIMASK critical sections','same-priority IRQ execution','exception-entry/stamping delay'],
        startup_SD_low_us=sd['channels']['pa6_bkin']['selected_pulse']['width_us'],
        startup_SD_at_PWM_off=True,startup_SD_preserved_unchanged=True,
        TP23_PA4_disconnected_do_not_interpret_second_trace_channel=True,
        old_files_preserved=len(preserved),firmware_and_protection_thresholds_unchanged=True,
        next_step='Read-only investigation of TIM1 UPDATE latency and masked sections, preserving unchanged2048 guard. No automatic CLEAR/START/RESET/reflash.')
    p.write(out/'analysis.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    text='''# FOC3001/3002: одна попытка, останов по недействительному кадру АЦП

30.10.2026 пользователь подтвердил повербанки,PC/SaleaeOFF,15ВON,J1ON.
Первый preflight(r1) не послалSTART/CLEAR/ARM: до пуска SDLOW61,6мкс при MOE0,
активная маска0,защёлкнуто0x0400MC_DP_FAULT. Полный320байтныйSDснимок сохранён.
Пользователь затем явно разрешил одинCLEAR и одинFOCпуск при восстановленной
защите. В r2 выполнены ровноCLEAR1/START1, послеCLEAR SDHIGH/BIE/config_ok,
все маски0; повторов/прошивки/RESET0. СнимокSDдо/после побитно неизменён.
TP23→PA4 ранее снят: вторую дорожку PA4 нельзя считать независимымSDдатчиком.

Пять секунд НЕ завершены. Штатный защитный останов, затем финальныйSTOP;
SAFE/PWM0,run_id1. Сеанс2060мс не равен точному времени физических выходов.
АЦП31760кадров (около1,985с при16кГц), все35страниц/1024байта получены.
Сохранены12крайних строк,номинальныйpeak0,585208А; масштабу ампер это
физическую калибровку не даёт.6Атриггера не было. Вращение не подтверждено.

Прежний быстрый дедлайн в этом прогоне не нарушен: максимум4880тактов
(28,706мкс) при прежнем5312(31,247мкс). Это наблюдённый максимум этой попытки,
не доказательство WCET всех путей. Наблюдатель выполнил1984шага.
Последний observerwall565,124мкс=IRQbodylower446,024+CPUupper119,100мкс.
Максимумыwall688,724/IRQbody561,741/CPUupper217,859мкс относятся к разным
вызовам,не складывать. CPUupper включает вход/выход исключений/границы
профилировщика,IRQbody — нижняя граница. Счётчик ошибок измерителя0.

Первый замороженныйreason2=FT_ADC_INVALID,MA_STALE3. В этом месте
MCSDKмаска0x0080=MC_SW_ERROR. ADCage19,359мкс<187,5мкс,
estimateage874,912мкс<2000мкс: вход свежий. sample_flags6:
zero1,running1,valid0. Вызов наблюдателя уже завершился,observer_inflightfalse.
Это не сообщение об устаревшем наблюдателе и не повтор прошлого5317>5312.

Причинный кадр точно найден поadc_cycles2733414013:sequence31759,index10.
Сырые2032/2120 в диапазоне,геометрия окна всехтрёхплеч проходит,очередьпустая,
JQOVF0,stamp/pendingepoch совпадают,публикация успевает. Но меткаUPDATE
снята приCNT2226/вверх,тогдакак mic_adc_bottom_update допускаетCNT<2048.
Поэтому context_ok0,eligible0,вfeedback опубликованvalid0,иFOCправильно
отказался его использовать. Replay фактическихCзаголовков наПК подтвердил
12строк:первые10проходят,причиннаястрока bottom0/window1/publish1.
Причина,почему сама меткаUPDATE запоздала, этим захватом не определяется.
Порог2048 и все остальные защиты оставлены без изменения.

SDпослеHIGH,BIEвключён; first_start_window не содержитновогоBreak.
Нынешний отказ — валидностьADC,а не сохранившийсяSDснимок до пуска.
UARTCRC/hardware/transport/RPCtimeouts0,шинаоколо324В.
908старых/установочныхфайлов проверены плюс сохранён первыйpreflight.

Далее:без новых пусков/сбросов/прошивки найти задержку TIM1 UPDATE,
проверить участкиPRIMASK и длительность телISR/метки. Не расширять
допуск2048,не приниматьнедостоверный отсчёт и не подменять его старым.
Текущее питание/подключения пользователь не менял;новых переключений не нужно.
'''
    p.write(out/'REPORT_RU.md',text)
    p.write(out/'saved_files_sha256.json',json.dumps({f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name!='saved_files_sha256.json'},indent=2)+'\n')
    manifest=json.loads(p.read(p.OUT/'manifest.json'))
    manifest.update(powered_test_attempted=True,powered_5s_completed=False,
        powered_full_adapter_observed_max_cycles=4880,powered_observer_steps=1984,
        full_powered_adapter_timing_verified=False,target_timing_qualification_pending=True,
        powered_first_fault_reason=2,powered_trial_report='powered_FOC_CPU_IRQ_20261030_r2/analysis.json',
        start_commands=1,clear_commands=1)
    p.write(p.OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n')
    status=p.ROOT/'CURRENT_BENCH_STATUS_RU.md';old=p.read(status);idx=old.index('## 2026-10-30:')
    section='''## 2026-10-30:3001/3002 FOC остановлен после~2с;FT_ADC_INVALID из-за поздней меткиUPDATE

Poweredr1START0:startupSDLOW61,6мкс/MOE0,снимоксохранён. Пользовательявно
разрешилодинCLEARиодинпуск. Poweredr2CLEAR1/START1,защитыпослеCLEARготовы;
повторов/RESET/flash0. ПятьсекундНЕзавершены,SAFE/PWM0/run_id1,session2060мс.
31760ADCкадров~1,985с;полные1024байта/35страниц получены,12строкконца,
номинальныйpeak0,585208А,масштабампернефизическиквалифицирован.
Быстрыйпутьmax4880<5312,наблюдатель1984шага. Runtimewalllast565,124мкс,
IRQlower446,024/CPUupper119,100;maxwall688,724/maxIRQ561,741/maxCPU217,859,
разныеmaxнескладывать,metererrors0.
Первыйreason2FT_ADC_INVALID,MA_STALE3,MCSDK128MC_SW_ERROR. Входсвежий:
ADC19,359мкс/оценка874,912мкс,ноvalid0(sample_flags6). ПричинныйADCindex10,
sequence31759,cycles2733414013. МеткаUPDATECNT2226>=допустимого2048,
направлениевверх. ReplayнафактическихCзаголовках:bottom0/window1/publish1,
сырые2032/2120,очередь/JQOVF/epochбезошибок;context_ok0правильноотвергнут.
ПОЧЕМУсамаUPDATEметказадержанаещёНЕдоказано. Допуск2048/защитыНЕменять.
StartupSDснимокпобитносохранён;PA4отTP23снят,егоHIGHничегонеотделяет.
SDHIGH/BIE/config_ok,новогоfirst_startBreakнет,UART/hardware/transport/RPC0.
908прежнихфайловпроверены. Отчёт:
artifacts/live_bench_20261029/foc_fast_budget_fix_r1/powered_FOC_CPU_IRQ_20261030_r2/REPORT_RU.md.
ДалееанализлатентностиUPDATE/PRIMASKбезновыхпусков/сбросов/прошивок,
питаниепользовательоставилJ1ON/15ВON/повербанки/PCиSaleaeOFF.
ТекущиеразрешенияCLEARиSTARTужеизрасходованы,повторнесогласован.

'''
    p.write(status,old[:idx]+section+old[idx:])
    print(json.dumps(dict(completed_5s=False,START=1,CLEAR=1,outputs_off=True,
        fast_max_cycles=4880,first_fault=2,bad_ADC_sequence=31759,
        actual_C_replay=True,late_update_stamp_CNT=2226,unchanged_guard=2048,preserved_files=len(preserved))))

if __name__=='__main__':main()
