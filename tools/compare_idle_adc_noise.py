"""Compare intact, real OFF-only ADC captures. Offline; no board commands."""
import argparse
import hashlib
import json
from pathlib import Path
from collect_idle_adc_noise import decode
from configure_multi_algorithm import crc32c


def load(folder):
    raw=(folder/'capture.bin').read_bytes()
    transport=json.loads((folder/'transport.json').read_text(encoding='utf-8'))
    assert transport['source_kind']=='hardware'
    assert transport['sha256']==hashlib.sha256(raw).hexdigest()
    assert transport['crc']==crc32c(raw)
    status=transport['status']
    assert status['state']=='SAFE' and status['pwm']==0 and not(status['bp_status']&0x22)
    assert 0<=status['mc_age_ms']<300 and status['noise_complete']==1
    assert status['noise_crc']==transport['crc'] and status['noise_bad']==0
    d=decode(raw)
    assert d['all_cases_complete'] and not d['fault']
    return dict(folder=str(folder),sha256=transport['sha256'],crc32c=transport['crc'],
                firmware=status['fw_build'],native=status['mc_fw_build'],decoded=d)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    a=parser.parse_args()
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    before,after=load(a.before.resolve()),load(a.after.resolve())
    assert before['sha256']!=after['sha256'],'No fresh capture'
    assert (before['firmware'],before['native'])==(after['firmware'],after['native'])
    assert before['decoded']['registers']==after['decoded']['registers']
    rows=[]
    for x,y in zip(before['decoded']['cases'],after['decoded']['cases']):
        assert x['name']==y['name'] and x['paths'].keys()==y['paths'].keys()
        for path in x['paths']:
            p,q=x['paths'][path],y['paths'][path]
            rows.append(dict(case=x['name'],path=path,n_before=p['n'],n_after=q['n'],
                standard_deviation_before=p['standard_deviation_counts'],
                standard_deviation_after=q['standard_deviation_counts'],
                sd_ratio=q['standard_deviation_counts']/p['standard_deviation_counts'],
                mean_before=p['mean'],mean_after=q['mean'],span_before=p['span'],span_after=q['span']))
    x,y=before['decoded']['cases'][3],after['decoded']['cases'][3]
    common_ratio=y['common_component_sd_counts']/x['common_component_sd_counts']
    report=dict(passed=True,source_kind='hardware',analysis_kind='offline comparison',hardware_commands=0,
        start_commands=0,clear_commands=0,ack_commands=0,before=before,after=after,
        raw_buffers_crc_verified=True,fresh_capture=True,same_firmware_and_adc_configuration=True,
        physical_change='User confirmed J4 15V OFF, Nucleo B2 RESET; J1 remained OFF, USB and wiring unchanged. Before capture had 15V ON.',
        per_path=rows,same_input_summary=dict(
            common_sd_before=x['common_component_sd_counts'],common_sd_after=y['common_component_sd_counts'],
            common_sd_ratio=common_ratio,observed_common_sd_change_percent=(common_ratio-1)*100,
            difference_sd_before=x['same_input_difference_sd_counts'],difference_sd_after=y['same_input_difference_sd_counts'],
            correlation_before=x['correlation'],correlation_after=y['correlation']),
        result='Turning15V off did not remove the observed common ADC fluctuation. This does not identify whether the common analog input/bias or ADC reference is responsible.',
        limitations=['128 pairs per case (64 per path in alternating case); short sequential captures, not a full noise spectrum.',
            'No formal significance claim: serial correlation and run-to-run variability are not fully characterized.',
            'Same-input sampling shares VREF and changes input loading; its correlation cannot separate those mechanisms.',
            'No physical ampere-scale calibration, noise reduction qualification or inductance estimate.'],
        current_noise_cause_fully_identified=False,inductance_identified=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    table='\n'.join('| '+r['case']+' | '+r['path']+f" | {r['standard_deviation_before']:.3f} | {r['standard_deviation_after']:.3f} |" for r in rows)
    text=f'''# Шум АЦП:15В включены / выключены

Оба аппаратных буфера получены при выключенном ШИМ; J1 выключен. Пользователь
отключил только15В наJ4 и нажал B2 Nucleo, не меняя USB и проводку. Пара2941/2940
и регистры АЦП в обоих захватах совпали. CRC и SHA256 проверены; буферы различны.
Скрипт сравнения не обращается к платам. Во время выгрузки выбирались только
readonly-страницы; START/CLEAR/ACK не отправлялись.

| Режим | Канал | σ при15В, коды АЦП | σ без15В, коды АЦП |
|---|---|---:|---:|
{table}

Один физический входV на обоих АЦП: общий компонент
{x['common_component_sd_counts']:.3f}→{y['common_component_sd_counts']:.3f}кода
(наблюдаемое изменение{(common_ratio-1)*100:.2f}%). Отклонение разности
{x['same_input_difference_sd_counts']:.3f}→{y['same_input_difference_sd_counts']:.3f}кода,
корреляция{x['correlation']:.4f}→{y['correlation']:.4f}.

Отключение15В не устранило общий шум. Утверждать, что15В совсем не влияют,
по этим коротким захватам нельзя; существенного исчезновения помехи нет.
Оставшиеся варианты — общий аналоговый вход/смещение/питание3,3В и VREF.
Здесь они ещё не различены. Это не доказательство неисправности одного АЦП,
не измеренные физические токи и не пригодная оценка индуктивности.

В каждом режиме128пар; режимы записаны последовательно, а не одновременно.
Формальный вывод о значимости небольших изменений не делается без учёта
коррелированности последовательных отсчётов. Сохранены все сырые значения.

До: CRC{before['crc32c']}, SHA256`{before['sha256']}`.
После: CRC{after['crc32c']}, SHA256`{after['sha256']}`.

Состояние после опыта по подтверждению пользователя: J1/J4 выключены, платы на
USB ПК, проводка без изменений. Исправление публикации тока на границе RMS-окна
остаётся установленным; пороги защит не менялись. Новых пусков не было.
'''
    (out/'REPORT_RU.md').write_text(text,encoding='utf-8')
    print(json.dumps(dict(passed=True,hardware_commands=0,raw_crc_verified=True,**report['same_input_summary'])))


if __name__=='__main__':main()
