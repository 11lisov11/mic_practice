from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import statistics
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing, Rect, Line, PolyLine
from reportlab.lib import colors
from PIL import Image

import rewrite_article as base

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,r'C:\mic_theory')
from tools import study_current_only_speed_loop as experiment

HERE=Path(__file__).resolve().parent
ASSETS=HERE/'review_assets'
ASSETS.mkdir(exist_ok=True)
RAW_PATH=Path(r'C:\mic_theory\experiments\parameter_adaptive_speed\confirmation_20261006\results.json')
RAW=json.loads(RAW_PATH.read_text(encoding='utf-8'))
RAW_SHA=hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()
assert RAW_SHA=='92f344e804b47553f8aa9cfe741c2b31501c4fabc36189144692a9c7f7041d5a'
NOM=experiment.nominal_motor(json.loads(experiment.DEFAULT_BUNDLE.read_text(encoding='utf-8')))
R=experiment.calibrated_covariance('anisotropic_noise','full_covariance_ekf')
M=base.METRICS
METHODS=['fixed_reference','joint_only','direct_feedback','confidence_feedback']
CASES=['parameter_drift','composite']
TITLE='СРАВНЕНИЕ СПОСОБОВ ПАРАМЕТРИЧЕСКОЙ АДАПТАЦИИ В СИСТЕМЕ УПРАВЛЕНИЯ АСИНХРОННЫМ ЭЛЕКТРОПРИВОДОМ'
TITLE_EN='Comparison of Parameter Adaptation Methods in an Induction Motor Drive Control System'
OUT=base.layout.ROOT/'Марикин_Параметрическая_адаптация_ТЭБТРАНС_2026.docx'
base.OUT=OUT;base.layout.TITLE=TITLE;base.layout.TITLE_EN=TITLE_EN

ERRORS={}
for case in CASES:
    rows=[r for r in RAW['rows'] if r['scenario']==case and r['method']=='confidence_feedback']
    ERRORS[case]={}
    for j,key in enumerate(['rs','rr','lm']):
        values=[]
        for row in rows:
            truth=row['actual_initial_parameters'][key]*(1.3 if key=='rs' else 1.)
            estimated=getattr(NOM,key)*math.exp(row['parameter_logs'][j])
            values.append(100*abs(estimated/truth-1))
        ERRORS[case][key]=statistics.mean(values)

ABSTRACT={
    'Цель:':'Сопоставить способы параметрической адаптации бездатчикового асинхронного электропривода по точности регулирования скорости, токовой нагрузке и электрическим потерям.',
    'Методы:':'Исследованы базовая система, адаптация только наблюдателя, прямое и взвешенное обновление параметров регулятора. Выполнено численное моделирование при изменении параметров двигателя и возмущениях измерений. Дополнительно оценена погрешность восстановления электрических параметров.',
    'Результаты:':'Взвешенное обновление уменьшило погрешность скорости на 66,2–67,5% относительно базовой системы при изменении средних максимальных токов менее чем на 1% и росте энергии потерь в обмотке статора на 2,6–3,0%. Адаптация только наблюдателя дала меньшую погрешность и примерно на 5% меньшие потери, но повысила средние максимальные токи на 32,7–38,4%. Средний модуль относительной ошибки оценки сопротивления статора в конце расчёта составил около 21%.',
    'Практическая значимость:':'Сравнение позволяет оценивать компромисс между точностью и токовой нагрузкой при выборе структуры управления вспомогательными приводами транспорта. Полученные модельные результаты требуют проверки с параметрами конкретной машины и нагрузочной характеристикой механизма.',
}
KEYWORDS='асинхронный электропривод; векторное управление; параметрическая адаптация; наблюдатель состояния; токовая нагрузка; численное моделирование.'
INTRO=[
    'Вспомогательные асинхронные электроприводы применяются в вентиляционном, насосном и компрессорном оборудовании транспорта. При изменении нагрузки требуется поддерживать заданную частоту вращения с учётом электрической нагрузки двигателя и преобразователя. Для предварительного выбора системы управления необходимо установить, как повышение точности связано с максимальными токами и потерями в обмотках. В работе рассматривается обобщённый режим со скачком момента нагрузки; привязка к конкретному механизму требует его нагрузочной характеристики и паспортных ограничений машины.',
    'В предыдущих работах авторов рассмотрены управление с оптронным датчиком [1], нейроуправление в цифровом двойнике [2], программно-аппаратное управление с учётом потокосцепления ротора [3] и применение искусственного интеллекта [4]. Настоящая работа продолжает исследование качества управления при изменении параметров двигателя. Оценивание сопротивлений расширенным фильтром Калмана и использование параметрических оценок в бездатчиковом векторном управлении известны [5, 6]; влияние настройки наблюдателя исследовано в [7]. Предмет данной работы — количественное сопоставление способов использования оценок по нескольким эксплуатационно значимым показателям.',
    'Изменение сопротивлений и индуктивностей вызывает рассогласование объекта и расчётной модели векторного регулятора. В частности, постоянная времени роторной цепи T<sub>r</sub> = L<sub>r</sub>/R<sub>r</sub> и коэффициент k<sub>r</sub> = L<sub>m</sub>/L<sub>r</sub> входят в оценивание потокосцепления и расчёт управляющего напряжения. Поэтому адаптация наблюдателя и обновление параметров регулятора могут по-разному влиять на замкнутую систему. Цель исследования — установить этот компромисс при одинаковых внешних воздействиях и ограничениях управления.',
    'Структура системы показана на рисунке 1. По токам статора и восстановленному напряжению наблюдатель оценивает скорость, потокосцепление, момент нагрузки и электрические параметры. Оценка момента нагрузки включена в формирование задания электромагнитного момента наряду с обратной связью по скорости. Параметрические оценки могут использоваться только внутри наблюдателя либо дополнительно поступать в регулятор.',
]

METHODS_A=[
    'Наблюдатель построен на расширенном фильтре Калмана. Вектор его состояния включает i<sub>sα</sub>, i<sub>sβ</sub>, ψ<sub>rα</sub>, ψ<sub>rβ</sub>, ω, M<sub>L</sub> и три логарифмических параметра θ<sub>j</sub> = ln(â<sub>j</sub>/a<sub>j0</sub>), где a<sub>j</sub> ∈ {R<sub>s</sub>, R<sub>r</sub>, L<sub>m</sub>}. Базовый наблюдатель содержит первые шесть состояний. Измеряются две составляющие тока; остальные состояния оцениваются по модели двигателя. Параметры, используемые в регуляторе, определяются выражением',
]
RULES=[
    'a<sub>j,рег</sub> = a<sub>j0</sub> exp(w<sub>j</sub>θ<sub>j</sub>),     |θ<sub>j</sub>| ≤ 0,7;     (1)',
    'w<sub>j</sub> = min{1; max[0; 1 − P<sub>θjθj</sub>/0,04]}.     (2)',
]
METHODS_B=[
    'Здесь a<sub>j0</sub> — номинальный параметр, P<sub>θjθj</sub> — диагональный элемент ковариационной матрицы его логарифмической оценки. При адаптации только наблюдателя w<sub>j</sub> = 0; при прямом обновлении w<sub>j</sub> = 1; для взвешенного обновления используется (2). В базовой системе электрические параметры наблюдателя и регулятора постоянны. Уменьшение расчётной ковариации рассматривается как основание для взвешивания, а точность физического восстановления параметров проверяется отдельно.',
    'Задание момента формирует ПИ-регулятор скорости с добавлением оценки M<sub>L</sub> и ограничением ±0,6 Н·м. Его коэффициенты K<sub>pω</sub> = 2Jβ<sub>ω</sub>, K<sub>iω</sub> = Jβ<sub>ω</sub><sup>2</sup>. В токовом контуре K<sub>pi</sub> = L<sub>экв</sub>β<sub>i</sub>, K<sub>ii</sub> = R<sub>s</sub>β<sub>i</sub>, где L<sub>экв</sub> = L<sub>s</sub> − L<sub>m</sub><sup>2</sup>/L<sub>r</sub>. Применены компенсация взаимосвязей и ограничение накопления интегральной составляющей при насыщении напряжения. Общие настройки приведены в таблице 1.',
]
METHODS_C=[
    'Модель двигателя составлена в осях αβ при линейной магнитной цепи и усреднённом напряжении преобразователя. Расчётные параметры: R<sub>s</sub> = 7,868 Ом, R<sub>r</sub> = 20,832 Ом, L<sub>m</sub> = 0,4824 Гн; индуктивности рассеяния — 2,491 и 1,935 мГн; J = 7,646·10<sup>−5</sup> кг·м²; коэффициент вязкого трения B = 1,1804·10<sup>−4</sup> Н·м·с; число пар полюсов p = 1. В преобразователе учтено эквивалентное падение напряжения величиной 1 В + 0,05 Ом·|i<sub>s</sub>| вдоль вектора тока; наблюдатель восстанавливает его по оценке тока. Значения характеризуют расчётный пример и не получены стендовой идентификацией машины.',
    'Рассмотрены номинальный режим, изменение параметров, совместное действие параметрических и измерительных возмущений и тот же режим при заданной скорости 3 рад/с. В режиме изменения параметров L<sub>m</sub> уменьшена на 15%, индуктивности рассеяния увеличены на 20%, R<sub>s</sub> возрастает на 30% между 0,8 и 2,0 с. При совместных возмущениях добавлены задержка 0,3 мс, квантование 2 мА, потеря 0,5% отсчётов и импульсные помехи. Шум токов имеет стандартные отклонения 0,01 и 0,03 А с корреляцией 0,4; вероятность импульсной помехи на отсчёт равна 0,001, её стандартное отклонение — 0,5 А.',
    'В основных режимах задание скорости линейно возрастает от нуля до 150 рад/с между 0,25 и 0,75 с. Скачок момента нагрузки 0,25–0,45 Н·м прикладывается в случайный момент 0,95–1,25 с. Начальные R<sub>s</sub>, R<sub>r</sub>, J и B варьируют на ±5%. Выполнены 320 численных экспериментов: четыре способа управления, четыре режима и 20 независимых реализаций случайных воздействий. Продолжительность — 2,5 с, шаг интегрирования и управления — 100 мкс. Для всех способов используются одинаковые воздействия, пределы тока и момента.',
    'Настройки определены до контрольных расчётов. Базовую систему предварительно настраивали отдельно для каждого режима; в процессе управления сведения о типе возмущения ей не передавались. Средняя абсолютная погрешность скорости (MAE) рассчитывается по отклонению действительной скорости от заданной после 0,8 с, стандартное отклонение момента — после 1,7 с. Максимум модуля тока определяется за каждый эксперимент и усредняется по 20 реализациям. Энергия потерь в меди статора определяется интегрированием за 2,5 с: E<sub>Cu</sub> = ∫(3/2)R<sub>s</sub>|i<sub>s</sub>|<sup>2</sup>dt при амплитудно-инвариантном преобразовании Кларка.',
    'Для заранее выбранного взвешенного варианта проверяли уменьшение MAE не менее чем на 20% и увеличение среднего максимума тока не более чем на 5% относительно базы. Последний порог задаёт сравнительный критерий данного исследования. Абсолютная уставка модели составляет 2,8 А; эксплуатационные пределы конкретной машины не определялись. Доверительные интервалы уровня 97,5% получены парным методом повторных выборок с возвращением (10 000 выборок), с поправкой Бонферрони для двух основных гипотез о погрешности скорости.',
]
BEFORE_TRACE=[
    'Рисунок 2 показывает переходные процессы при совместном действии возмущений для первой реализации, выбранной до анализа результатов. Задание скорости на показанном интервале постоянно и равно 150 рад/с, момент нагрузки приложен при t = 1,154 с. Иллюстрация позволяет сопоставить отклонение скорости и токовую реакцию на одну нагрузку. Кривые сохранены с шагом 5 мс; все итоговые показатели и индивидуальные максимумы рассчитаны с шагом 100 мкс.',
]
RESULTS=[
    'В таблице 2 представлены усреднённые результаты всех четырёх способов. Адаптация только наблюдателя обеспечивает наименьшие MAE — 0,713 и 0,772 рад/с — и примерно на 5% меньшие потери относительно базы. Одновременно средние максимальные токи увеличиваются на 32,7 и 38,4%. Уставка 2,8 А не превышена ни в одном из 320 экспериментов, поэтому данный вариант нельзя исключать только по признаку превышения абсолютного ограничения тока.',
    'Прямое и взвешенное обновление регулятора уменьшают MAE относительно базы приблизительно втрое. При взвешивании снижение составляет 66,2 и 67,5%, изменение среднего максимума тока — −0,15 и +0,84%, рост потерь — 3,0 и 2,6%. При прямом обновлении получены несколько меньшие MAE 1,230 и 1,181 рад/с; изменение средних максимумов тока составляет −0,38 и +1,51%. Самостоятельное преимущество взвешивания по совокупности показателей не установлено.',
    'Для взвешенного варианта отношения MAE к базе равны 0,338 и 0,325; верхние границы доверительных интервалов — 0,473 и 0,428. Для отношений средних максимумов тока верхние границы равны 1,020 и 1,027, что удовлетворяет принятому сравнительному порогу 1,05. Эти результаты подтверждают заданный компромисс между точностью и максимальным током. При отсутствии обоснованного ограничения на увеличение тока вариант с адаптацией только наблюдателя сохраняет преимущества по точности и потерям.',
]
PARAMETER_TEXT=[
    'Повышение точности регулирования не тождественно точному восстановлению параметров машины. На рисунке 3 сопоставлены действительные значения и оценки R<sub>s</sub> и L<sub>m</sub> на выходе наблюдателя взвешенного варианта для той же реализации. Показаны оценки наблюдателя до применения весов (2); значения параметров внутри регулятора по этим кривым непосредственно не определяются.',
]
DISCUSSION=[
    'Дополнительный анализ выполнен по конечным значениям всех 20 реализаций. В режиме изменения параметров средние модули относительных ошибок оценки R<sub>s</sub>, R<sub>r</sub>, L<sub>m</sub> составили 21,4; 1,26; 4,85%, при совместных возмущениях — 21,4; 1,21; 4,84%. Ошибки определены в момент 2,5 с относительно действительных параметров соответствующей реализации. Это оценка точности параметрического восстановления в конце расчёта, а не на всём переходном процессе.',
    'Индуктивности рассеяния в объекте изменены, тогда как в наблюдателе они сохраняются постоянными. При таком рассогласовании полученные оценки могут выполнять компенсирующую функцию в расчётной модели. Поэтому снижение MAE подтверждает полезность определённой корректировки управления, но само по себе не доказывает точной физической идентификации R<sub>s</sub>, R<sub>r</sub>, L<sub>m</sub>. Причины смещения оценок требуют отдельного анализа.',
    'В номинальном режиме MAE взвешенного варианта равна 1,614 рад/с против 0,879 рад/с у базы; при задании 3 рад/с она составляет 2,076 рад/с, или 69,2% задания. Результаты ограничены рассмотренной моделью, где объект и прогноз наблюдателя основаны на одной системе уравнений. Для применения во вспомогательном оборудовании транспорта необходимо задать конкретную машину, зависимость момента механизма от скорости и допустимые токовые и тепловые режимы. Выбор алгоритма должен учитывать эти требования; универсально предпочтительный способ в исследовании не установлен.',
]
CONCLUSIONS=[
    '1. Сопоставлены четыре варианта управления при одинаковых воздействиях и ограничениях. Получены количественные различия по погрешности скорости, максимальному току, колебаниям момента и потерям в обмотке статора.',
    '2. Взвешенное обновление параметров регулятора в двух основных режимах уменьшило MAE на 66,2 и 67,5% при изменении средних максимальных токов менее чем на 1%. Потери в меди статора выросли на 2,6–3,0%. Прямое обновление дало близкие результаты; преимущество взвешивания не установлено.',
    '3. Адаптация только наблюдателя обеспечила меньшие MAE и примерно на 5% меньшие потери при увеличении средних максимальных токов на 32,7–38,4%. Это компромисс с вариантом обновления регулятора, который следует оценивать по требованиям конкретного механизма.',
    '4. Взвешенный вариант уменьшил стандартное отклонение момента на 31,8–34,3%, однако средний модуль относительной ошибки конечной оценки R<sub>s</sub> сохранился на уровне около 21%. Улучшение регулирования и точность параметрической идентификации требуют раздельной оценки.',
]
EN_ABSTRACT=[
    ('Objective: ','To compare parameter adaptation methods for a sensorless induction motor drive in terms of speed regulation accuracy, current loading and electrical losses. '),
    ('Methods: ','Fixed-parameter control, observer-only adaptation, and direct and covariance-weighted controller parameter updates were compared by numerical modelling. Terminal parameter estimation errors were also evaluated. '),
    ('Results: ','Under parameter variations and combined disturbances, the weighted update reduced mean absolute speed error by 66.2–67.5% relative to the baseline, with changes in mean individual current maxima below 1% and stator copper-loss energy increases of 2.6–3.0%. Observer-only adaptation achieved lower speed errors and approximately 5% lower copper losses but increased mean current maxima by 32.7–38.4%. The terminal mean absolute relative error of the stator resistance estimate remained approximately 21%. No universally preferable method was identified. '),
    ('Practical significance: ','The comparison quantifies accuracy/current-loading tradeoffs when selecting control structures for auxiliary transport drives. Application requires validation using the parameters of a specific machine and the load characteristic of the driven mechanism.'),
]


def plain_table(doc,title,widths,rows,groups=(),size=11):
    p=base.layout.new_p(doc,35,title,keep=True)
    p.paragraph_format.first_line_indent=Cm(0);p.paragraph_format.left_indent=Cm(0);p.paragraph_format.right_indent=Cm(0)
    p.paragraph_format.space_before=Pt(8);p.paragraph_format.space_after=Pt(4)
    t=doc.add_table(rows=0,cols=len(widths));t.autofit=False;t.alignment=WD_TABLE_ALIGNMENT.CENTER
    for col,width in zip(t.columns,widths):col.width=Cm(width)
    for ri,values in enumerate(rows):
        row=t.add_row()
        if ri in groups:row.cells[0].merge(row.cells[-1]).text=values[0]
        else:
            for cell,width,value in zip(row.cells,widths,values):
                cell.width=Cm(width);cell.text='';p=cell.paragraphs[0]
                for token in re.split(r'(<sub>.*?</sub>|<sup>.*?</sup>)',value):
                    if not token:continue
                    sub=token.startswith('<sub>');sup=token.startswith('<sup>')
                    r=p.add_run(re.sub(r'</?(?:sub|sup)>','',token))
                    if sub:r.font.subscript=True
                    if sup:r.font.superscript=True
        trpr=row._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
        if ri==0:trpr.append(OxmlElement('w:tblHeader'))
        for ci,cell in enumerate(row.cells):
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            pr=cell._tc.get_or_add_tcPr();borders=OxmlElement('w:tcBorders')
            for edge in ['top','left','bottom','right']:
                n=OxmlElement('w:'+edge)
                for k,v in [('val','single'),('sz','4'),('color','000000')]:n.set(qn('w:'+k),v)
                borders.append(n)
            pr.append(borders)
            for p in cell.paragraphs:
                p.alignment=WD_ALIGN_PARAGRAPH.LEFT if ci==0 and ri and ri not in groups else WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.line_spacing=1.;p.paragraph_format.space_before=Pt(2);p.paragraph_format.space_after=Pt(2)
                p.paragraph_format.keep_with_next=ri<len(rows)-1
                for r in p.runs:r.font.name=base.FONT;r.font.size=Pt(size);r.bold=ri==0 or ri in groups
    return t


def settings_table(doc):
    rows=[
        ['Параметр','Принятое значение'],
        ['Токовый и скоростной контуры','β<sub>i</sub> = 400 рад/с; β<sub>ω</sub> = 80 рад/с; задание потокосцепления 0,35 Вб; предварительное намагничивание 0,25 с'],
        ['Ограничения','U<sub>dc</sub> = 325 В; |u| ≤ 0,95U<sub>dc</sub>/√3; |M*| ≤ 0,6 Н·м; |i*| ≤ 2,8 А'],
        ['Ковариация измерений R, А²','R<sub>11</sub> = 9,7891·10⁻⁵; R<sub>12</sub> = R<sub>21</sub> = 1,0990·10⁻⁴; R<sub>22</sub> = 8,7448·10⁻⁴; оценена по 4000 отсчётам модельного шума'],
        ['Начальная ковариация P<sub>0</sub>','diag(0,0025; 0,0025; 0,0025; 0,0025; 900; 0,0025; 0,04; 0,04; 0,04) в порядке компонентов адаптивного наблюдателя; для базы — первые шесть компонентов'],
        ['Интенсивности шума процесса Q<sub>c</sub>','Для адаптивного наблюдателя: diag(0,02; 0,02; 10⁻⁵; 10⁻⁵; 4; q<sub>M</sub>; 10⁻⁵; 10⁻⁵; 10⁻⁵). Для базы — первые шесть компонентов. Q за шаг = Q<sub>c</sub>·100 мкс'],
        ['Параметр q<sub>M</sub> модели нагрузки','Адаптивные варианты: 0,01. База: 0,0001 в двух основных режимах; 0,1 в номинальном режиме; 0,001 при 3 рад/с'],
        ['Обработка измерений','История 16 шагов; учёт временной метки; при нормированном квадрате невязки >25 ковариация измерения увеличивается пропорционально превышению порога'],
    ]
    plain_table(doc,'Таблица 1 – Основные настройки наблюдателя и регулятора',[5.1,10.8],rows,size=11)


def comparison_table(doc):
    rows=[['Показатель','Базовая\nсистема','Только\nнаблюдатель','Прямое\nобновление','Взвешенное\nобновление']]
    groups=[]
    specs=[('MAE, рад/с','tracking_mae_rad_s',1,3),('Средний максимум тока, А','peak_current_a',1,3),('Стандартное отклонение момента, мН·м','steady_torque_std_nm',1000,3),('Энергия потерь в обмотке, Дж','copper_energy_j',1,2)]
    for case,name in zip(CASES,['Изменение параметров двигателя','Совместное действие возмущений']):
        groups.append(len(rows));rows.append([name])
        for title,key,mult,digits in specs:
            rows.append([title]+[base.number(M[case+'/'+method][key]*mult,digits) for method in METHODS])
    plain_table(doc,'Таблица 2 – Сравнение четырёх способов управления',[4.7,2.8,2.8,2.8,2.8],rows,groups,size=11)
    (HERE/'review_comparison_table.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')


def equation(doc,text):
    p=base.rich(doc,text)
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.first_line_indent=Cm(0)
    p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(4)
    return p


STYLES=[(colors.black,None),(colors.HexColor('#777777'),[5,2]),(colors.black,[2,2]),(colors.black,[7,2,1,2])]


def chart(d,x,y,w,h,xmin,xmax,ymin,ymax,xticks,yticks,title):
    tx=lambda v:x+(v-xmin)/(xmax-xmin)*w
    ty=lambda v:y+(v-ymin)/(ymax-ymin)*h
    for val in yticks:
        yy=ty(val);d.add(Line(x,yy,x+w,yy,strokeColor=colors.HexColor('#dddddd'),strokeWidth=.35))
        base.label(d,x-7,yy-3,str(val).replace('.',','),10,anchor='end')
    d.add(Line(x,y,x+w,y,strokeColor=colors.black,strokeWidth=.65));d.add(Line(x,y,x,y+h,strokeColor=colors.black,strokeWidth=.65))
    for val in xticks:
        xx=tx(val);d.add(Line(xx,y,xx,y-3,strokeColor=colors.black,strokeWidth=.6));base.label(d,xx,y-14,str(val).replace('.',','),10)
    base.label(d,x,y+h+10,title,12,anchor='start')
    return tx,ty


def curve(d,tx,ty,points,color,dash=None,width=1.):
    coords=[(tx(x),ty(y)) for x,y in points]
    if len(coords)>1:d.add(PolyLine(coords,strokeColor=color,strokeWidth=width,strokeDashArray=dash))


def draw_assets():
    # Reuse the established scientific diagram and correct its state-feedback label.
    base.ASSETS=ASSETS
    original=base.label;original_block=base.block
    def diagram_label(d,x,y,value,*args,**kwargs):
        value={'Оценки скорости':'Оценки состояния','и потокосцепления':'и момента нагрузки'}.get(value,value)
        return original(d,x,y,value,*args,**kwargs)
    def diagram_block(d,x,y,w,h,lines,*args,**kwargs):
        if lines[0]=='Адаптивный наблюдатель':lines=['Адаптивный наблюдатель','Скорость, потокосцепление,','нагрузка и параметры']
        return original_block(d,x,y,w,h,lines,*args,**kwargs)
    base.label=diagram_label;base.block=diagram_block;base.draw_assets();base.label=original;base.block=original_block
    traces={m:next(t['trace'] for t in RAW['traces'] if t['scenario']=='composite' and t['method']==m) for m in METHODS}
    d=Drawing(600,475)
    names=['Базовая система','Только наблюдатель','Прямое обновление','Взвешенное обновление']
    for i,(name,(color,dash)) in enumerate(zip(names,STYLES)):
        x=35+(i%2)*300;y=460-(i//2)*17
        d.add(PolyLine([(x,y),(x+25,y)],strokeColor=color,strokeDashArray=dash,strokeWidth=1.2));base.label(d,x+31,y-3,name,11,anchor='start')
    load=next(r['load_start_s'] for r in RAW['rows'] if r['seed']==97200 and r['scenario']=='composite' and r['method']=='confidence_feedback')
    panels=[('speed_true',300,120,160,[120,130,140,150,160],'а  Угловая скорость, рад/с'),('current_a',168,0.5,1.6,[0.5,1.0,1.5],'б  Модуль вектора тока, А'),('torque_nm',36,-.05,.55,[0,.2,.4],'в  Электромагнитный момент, Н·м')]
    audit=[]
    for key,y,lo,hi,ticks,title in panels:
        tx,ty=chart(d,70,y,500,95,.8,2.5,lo,hi,[.8,1.2,1.6,2.0,2.4],ticks,title)
        for method,(color,dash) in zip(METHODS,STYLES):
            values=[(r['time_s'],r[key]) for r in traces[method] if .8<=r['time_s']<=2.5]
            assert min(v for _,v in values)>=lo and max(v for _,v in values)<=hi,(key,method,min(v for _,v in values),max(v for _,v in values))
            curve(d,tx,ty,values,color,dash)
            audit.append({'metric':key,'method':method,'points':len(values),'min':min(v for _,v in values),'max':max(v for _,v in values)})
        d.add(Line(tx(load),y,tx(load),y+95,strokeColor=colors.HexColor('#888888'),strokeWidth=.7,strokeDashArray=[2,2]))
        if key=='speed_true':
            d.add(Line(tx(.8),ty(150),tx(2.5),ty(150),strokeColor=colors.HexColor('#999999'),strokeWidth=.6,strokeDashArray=[1,3]))
            base.label(d,tx(load)+4,y+80,'Нагрузка',10,anchor='start')
    base.label(d,570,7,'Время, с',11,anchor='end')
    (ASSETS/'figure_2.svg').write_text(renderSVG.drawToString(d),encoding='utf-8')

    trace=traces['confidence_feedback'];d=Drawing(600,270)
    for i,(name,dash) in enumerate([('Действительное значение',None),('Оценка наблюдателя',[5,2])]):
        x=55+i*300;d.add(PolyLine([(x,254),(x+25,254)],strokeColor=colors.black,strokeDashArray=dash,strokeWidth=1.1));base.label(d,x+31,251,name,11,anchor='start')
    for j,(key,actual,nominal,lo,hi,ticks,title) in enumerate([
        (0,'actual_rs',NOM.rs,7.0,10.7,[7,8,9,10],'а  Сопротивление статора, Ом'),
        (2,'actual_lm',NOM.lm,.38,.60,[.40,.45,.50,.55,.60],'б  Индуктивность намагничивания, Гн'),
    ]):
        tx,ty=chart(d,55+j*300,45,230,165,0,2.5,lo,hi,[0,1,2],[*ticks],title)
        curve(d,tx,ty,[(r['time_s'],r[actual]) for r in trace],colors.black)
        estimates=[(r['time_s'],nominal*math.exp(r['parameter_logs'][key])) for r in trace]
        assert all(lo<=v<=hi for _,v in estimates),(key,min(v for _,v in estimates),max(v for _,v in estimates))
        curve(d,tx,ty,estimates,colors.black,[5,2])
        base.label(d,285+j*300,14,'Время, с',11,anchor='end')
    (ASSETS/'figure_3.svg').write_text(renderSVG.drawToString(d),encoding='utf-8')
    (HERE/'review_analysis.json').write_text(json.dumps({'raw_sha256':RAW_SHA,'nominal_motor':asdict(NOM),'measurement_covariance':R.tolist(),'terminal_parameter_mape':ERRORS,'trace_seed':97200,'trace_case':'composite','trace_step_s':.005,'full_metric_step_s':.0001,'trace_curve_ranges':audit,'parameter_plot':'observer output before covariance weighting, not controller parameter'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Three scientific figures prepared; original raw data unchanged.')


def build():
    doc=Document(base.layout.REF)
    for c in list(doc._element.body):
        if c.tag!=qn('w:sectPr'):doc._element.body.remove(c)
    n=base.layout.new_p;a=base.layout.add;proto=base.layout.prototype
    n(doc,0,'УДК 681.518:621.313.333');n(doc,1,TITLE,keep=True)
    p=n(doc,2,keep=True)
    for i,name in enumerate(['А. Н. Марикин','В. Г. Жемчугов','А. Д. Онофрийчук'],1):
        if i>1:a(p,', ',proto=proto(2,0))
        a(p,name,proto=proto(2,0));a(p,str(i),proto=proto(2,1))
    n(doc,3,base.layout.SOURCE.paragraphs[3].text.strip(),keep=True);base.layout.short_citation(doc)
    n(doc,5,'Аннотация.',keep=True)
    for key,value in ABSTRACT.items():base.layout.labelled(doc,key,value)
    base.layout.labelled(doc,'Ключевые слова:',KEYWORDS,index=9)
    for i,text in enumerate(INTRO):base.rich(doc,text,10 if i==0 else 11)
    base.ASSETS=ASSETS;base.picture(doc,1,'Структура векторного управления с оцениванием состояния, нагрузки и параметров двигателя')
    for text in METHODS_A:base.rich(doc,text)
    for text in RULES:equation(doc,text)
    for text in METHODS_B:base.rich(doc,text)
    settings_table(doc)
    for text in METHODS_C:base.rich(doc,text)
    for text in BEFORE_TRACE:base.rich(doc,text)
    base.picture(doc,2,'Переходные процессы при совместном действии возмущений; штриховая вертикаль — приложение нагрузки; горизонталь на графике а — задание скорости')
    for text in RESULTS:base.rich(doc,text)
    comparison_table(doc)
    for text in PARAMETER_TEXT:base.rich(doc,text)
    base.picture(doc,3,'Сопоставление действительных значений параметров и оценок наблюдателя для той же реализации')
    for text in DISCUSSION:base.rich(doc,text)
    n(doc,37,'По результатам исследования сформулированы следующие выводы.',keep=True)
    for text in CONCLUSIONS:base.rich(doc,text,38)
    p=n(doc,45,'Библиографический список',keep=True);p.paragraph_format.space_before=Pt(12)
    for i,text in enumerate(base.layout.RU_REFS):p=n(doc,46 if i==0 else 47,text);p.paragraph_format.keep_together=True
    n(doc,58,'Контактная информация',keep=True)
    n(doc,59,'МАРИКИН Александр Николаевич — доктор техн. наук, профессор',keep=True)
    n(doc,61,'ЖЕМЧУГОВ Валерий Григорьевич — канд. техн. наук, доцент, zhem@mail.ru',keep=True)
    p=n(doc,62,'ОНОФРИЙЧУК Андрей Дмитриевич — аспирант, 11lisov11@gmail.com')
    for r in p.runs:r.font.name=base.FONT;r.font.size=Pt(12)
    n(doc,63,TITLE_EN,keep=True);n(doc,64,'A. N. Marikin, V. G. Zhemchugov, A. D. Onofriychuk',keep=True)
    n(doc,65,base.layout.SOURCE.paragraphs[65].text.strip(),keep=True);base.layout.short_citation(doc,english=True)
    p=n(doc,67);a(p,'Summary\n',proto=proto(67,0),bold=True,size=12)
    for key,value in EN_ABSTRACT:a(p,key,proto=proto(67,2),bold=True,size=12);a(p,value,proto=proto(67,3),bold=False,size=12)
    p=n(doc,68);a(p,'Keywords: ',proto=proto(68,0),bold=True,size=12)
    a(p,'induction motor drive; vector control; parameter adaptation; state observer; current loading; numerical modelling.',proto=proto(68,1),size=12)
    n(doc,69,'References',keep=True)
    old=Document(HERE/'before_narrative_rewrite.docx');texts=[p.text for p in old.paragraphs]
    start=texts.index('References')+1;end=next(i for i in range(start,len(texts)) if texts[i].startswith('Author’s information'))
    for i,text in enumerate(texts[start:end]):p=n(doc,70 if i==0 else 71,text);p.paragraph_format.keep_together=True
    p=n(doc,81);a(p,'Author’s information\n',proto=proto(81,0),bold=True,size=12)
    a(p,'MARIKIN Alexander Nikolaevich — Doctor of Technical Sciences, Professor',proto=proto(81,2),bold=False,size=12)
    n(doc,83,'ZHEMCHUGOV Valery Grigoryevich — Candidate of Technical Sciences, Associate Professor')
    n(doc,84,'ONOFRIYCHUK Andrey Dmitrievich — Postgraduate student, 11lisov11@gmail.com')
    doc.core_properties.title=TITLE.capitalize();doc.core_properties.author='А. Н. Марикин; В. Г. Жемчугов; А. Д. Онофрийчук'
    doc.core_properties.subject='Сравнение способов параметрической адаптации и компромиссов точности, тока и потерь';doc.core_properties.comments=''
    base.package_save(doc)
    assert hashlib.sha256(RAW_PATH.read_bytes()).hexdigest()==RAW_SHA
    print(OUT)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='figures':draw_assets()
    else:build()
