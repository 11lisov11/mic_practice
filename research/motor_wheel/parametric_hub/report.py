"""Human-readable calculation dossier, BOM and conditional drive model."""
import csv,hashlib,html,json,math,re
from pathlib import Path
from geometry import ROOT

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def write_report():
    d=read(ROOT/'D150_L40/results.json');g=d['geometry'];p=d['parameters'];pk=d['package'];w=d['selected']['winding'];q=d['selected']['points']['flat15']['36.0'];t=d['thermal_flat15_36V'];me=d['mechanical']
    cad=read(ROOT/'D150_L40/CAD/cad_verification.json');mass=d['masses']
    # Material-density estimate excludes keep-out and stylised copper volumes,
    # replacing them with the winding copper length calculation.
    extras=0.;bom=[]
    for r in cad['parts']:
        name=r['component'];kg=None;kind='Заказать металл / детализировать'
        if '01_STATOR' in name:kg=mass['stator_steel_kg'];kind='Заказать пакет, 80 номинальных листов0.5мм'
        elif '02_ROTOR' in name:kg=mass['rotor_steel_kg'];kind='Заказать пакет, 80 номинальных листов0.5мм'
        elif '03_COPPER' in name:kg=mass['cage_copper_kg'];kind='Заказать готовую клетку: 50 стержней+2 кольца'
        elif any(x in name for x in ['04_STATOR_HEAT','06_ROTOR_SHELL','07_COVER']):kg=r['volume_mm3']*2.70e-6;extras+=kg
        elif '05_SHAFT' in name:kg=r['volume_mm3']*7.85e-6;extras+=kg
        elif '08_BEARING' in name:kg=.104;extras+=kg;kind='Купить6204, габарит20x47x14; исполнение и зазор выбрать после посадок'
        elif '09_PRINTED' in name:kg=r['volume_mm3']*1.27e-6;extras+=kg;kind='Печатать PETG: ненесущий холодный кожух; крепление ещё детализировать'
        elif '10_WINDING' in name:kind='Габарит пазовой части; реальную медь считать по схеме намотки'
        elif '11_ENDTURN' in name:kind='Резерв пространства под лобовые части; не отдельная деталь'
        bom.append([name,1,kind,'' if kg is None else f'{kg:.3f}'])
    total=sum(mass.values())+extras
    bom.append(['Обмотка медная',1,f'48 катушек, {w["turns_per_coil"]}витков, {w["wire_strands_in_hand"]}xØ{w["wire_bare_diameter_mm"]}; купить около{w["order_wire_m_with_15pct_reserve"]:.0f}м',f'{w["winding_copper_kg"]:.3f}'])
    bom.append(['Оправка для пробной катушки',1,'Печатать PETG; STL12_PRINTED_WINDING_FORMER, не входит в массу мотора',''])
    bom.append(['Пазовая и межфазная изоляция, клинья, выводы',1,'Покупные материалы под выбранный тепловой класс; размеры подтвердить намоточным образцом',''])
    with (ROOT/'D150_L40/BOM_RU.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['Деталь','Количество','Получение и состояние','Масса_кг_оценка']);writer.writerows(bom)
    profile={'status':'RESEARCH_ONLY_NOT_MCSDK_IMPORT_NOT_HARDWARE_LIMITS','MCU':'NUCLEO-G431RB / STM32G431',
      'power_stage':'Assembled DRV8302 SKU71451, assumed user-selected; exact received revision unverified',
      'command_interface':'6 complementary PWM from motor-control timer; enable, fault, current ADC channels to be mapped from received board',
      'battery':p['battery'],'connection':'star','pole_pairs':4,'phase_convention':'amplitude invariant dq; dq current and voltage are phase PEAK',
      'winding':w,'model_topology':'effective inverse-Gamma; NOT split T-equivalent Lm/Lls/Llr',
      'reference20C':{'Rs_phase_ohm':w['Rphase20_ohm'],'Rr_effective_ohm':d['model']['Rr_effective_20_ohm']*(w['turns_per_coil']/10)**2,
        'M_effective_h':q['Lm_effective_h'],'Lleak_effective_h':q['Lleak_effective_h']},
      'design_screen_only':p['inverter'],'benchmark_flat15kmh_36V':q,
      'notes':['Does not change existing IHM/IPM bench firmware or1.35A peak trip','Requires standstill identification, ADC calibration and board-specific ACIM firmware before power testing','UNO Q remains supervisory/research computer, G431 owns fast PWM/current loop']}
    (ROOT/'D150_L40/drive_profile_RESEARCH_ONLY.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
    fields=read(ROOT/'D150_L40/femm/linear.json');ref=read(ROOT/'D150_L40/femm/refined.json');nl=read(ROOT/'D150_L40/femm/nonlinear.json')['rows'][0]
    mesh=max(abs(complex(r['L_real_h'],r['L_imag_h'])/complex(next(b for b in fields['rows'] if b['frequency_hz']==r['frequency_hz'])['L_real_h'],next(b for b in fields['rows'] if b['frequency_hz']==r['frequency_hz'])['L_imag_h'])-1) for r in ref['rows'])
    lines=[
      'АСИНХРОННОЕ МОТОР-КОЛЕСО P1 — РАСЧЁТ И ПАРАМЕТРИЧЕСКАЯ CAD, 17.11.2026',
      '',
      'Результат: проектная модель D150_L40 под готовую плату DRV8302 SKU71451 и STM32G431.',
      'Это воспроизводимая инженерная прикидка и номинальная компоновка. Выпуск в производство и дорожные испытания не разрешаются фактом этого расчёта.',
      'Неизвестные размеры Ninebot заменены явно заданными проектными размерами; файл донорских измерений оставлен без подстановки выдуманных данных.',
      '',
      'ФАЙЛЫ И СМЕНА ДИАМЕТРА',
      'Открыть D150_L40/CAD/ACIM_HUB_D150_L40.SLDASM. Детали сохранены в native SOLIDWORKS2020, эскизы и выдавливания доступны для редактирования.',
      'Мастер параметров: parameters.json + geometry.py. CHANGE_DIAMETER.cmd запрашивает диаметр СТАТОРА и длину пакета. Режим1 строитCAD/DXF, режим2 также запускает новый FEMM и расчёт обмотки.',
      'Варианты110x30,130x30,150x40 уже построены. Диапазон генератора110..170мм и пакет20..50мм. Это диапазон геометрии, а не гарантия работоспособности каждого размера.',
      'Радиальный зазор0.4мм, вал20мм и подшипники6204 не масштабируются вместе с диаметром. Наружный размер корпуса пересчитывается отдельно.',
      'Глобальные переменные в текущихSLDPRT справочные. Изменение диаметра всего двигателя выполняется генератором, не одной размерной правкой внутри произвольной детали.',
      'Все компоненты сборки зафиксированы в общей системе координат. Кинематические сопряжения/анимация вращения не создавались.',
      '',
      'ИСХОДНЫЕ ДАННЫЕ',
      f'СтаторØ150; отверстиеØ{2*g["stator_bore_radius_mm"]:.3f}; пакет40; роторØ{pk["rotor_iron_OD_mm"]:.3f}; корпусØ{pk["housing_OD_mm"]:.3f}x{pk["total_housing_width_mm"]:g}, с кожухами осевая ширина95.',
      '48 пазов, 8 полюсов, 50 стержней, двухслойная обмотка, укороченный шаг5пазов. Сталь0.5мм, коэффициент заполнения0.95.',
      'Материал магнитопровода не выбран у изготовителя. Линейная оценкаμr=2000 и нелинейная проверка по справочнойM19 из библиотекиFEMM.',
      'Колесо по качению254мм; масса самокат+человек120кг; Crr=0.015; CdA=0.6м²; воздух1.225кг/м³. Это допущения, не измеренные характеристики.',
      'Плата производителем заявлена5.5–45В и15А; неизвестно, относятся15А к пику, фазному RMS или другому режиму. Принят консервативный потолок15А peak с расчётной пульсацией и9АRMS.',
      'MOSFET Rds_hot=20мОм, шунт≈5мОм, deadtime0.5мкс, PWM16кГц — расчётные допущения, а не идентификация полученной платы.',
      '10S Li-ion:30–42В, номинал36В. До45В от полностью заряженной батареи остаётся3В: защита шины/рекуперация/паразитные выбросы требуют отдельной схемной проверки.48В13S(54.6В) сюда не подходит.',
      '',
      'МЕТОДИКА И ФОРМУЛЫ',
      'Fдор=m*g*(sinθ+Crr*cosθ)+0.5*rho*CdA*v²+m*a; Tкол=Fдор*Rкол; Pвал=Tкол*ωм.',
      'FEMM: полный360° срез, неподвижная геометрия, комплексный ток фаз1A peak; частота0.5,1,2,4,8,16Гц идентифицирует зависимостьL(fslip).',
      'L(fslip)=Lleak+M/(1+j*2π*fslip*τr); Rr=M/τr. Концевые кольца введены фундаментальной поправкой к проводимости клетки.',
      'При смене числа витков M,Lleak,Rr умножаются на(N/Nref)². Пазовая медь иRфазы пересчитываются по выбранному проводу и средней длине витка.',
      'ψr=M*id; Te=1.5*p*M*id*iq; ωsl=(Rr/M)*iq/id; ωe=p*ωm+ωsl.',
      'ud=Rs*id−ωe*Lleak*iq_total; uq=Rs*iq_total+ωe*(M+Lleak)*id; Iphase_rms=sqrt(id²+iq_total²)/sqrt2.',
      'SVPWM экран: |u_pwm|≤0.9*Vdc/sqrt3−1В; MOSFET иdeadtime добавлены вдоль вектора тока. Ток потерь стали учтён отдельно от тока момента.',
      'Pcu=1.5*Rs*(id²+iq_total²); Pcage=1.5*Rr*iq²=Te*ωsl/p; прочие тепловые потери добавляются без фиктивного увеличения момента.',
      'Модель стали:3.5Вт/кг при1.5Т50Гц, смесь60%гистерезис+40%вихревые; коэффициенты не измерены. PWM/добавочные потери=3Вт+1.5%(Pвал+Pcage).',
      'Пульсация тока оцененаVdc/(8*fPWM*Lleak) как половина размаха. Это скрининг, не временная модель всех векторовSVPWM.',
      '',
      'ОБМОТКА D150_L40',
      f'48 катушек по7витков, в4параллельных проводаØ0.85мм. Звезда;16катушек последовательно на фазу;112витков на фазу;kw={w["winding_factor"]:.6f}.',
      f'Медь в проводнике{w["copper_area_mm2"]:.4f}мм²; площадь пазовой части{g["slot_copper_gross_mm2"]:.3f}мм²; голая медь в пазу{100*w["bare_slot_fill"]:.2f}%.',
      f'Средняя длина витка{w["mean_turn_length_m_assumed"]*1000:.2f}мм; длина одной жилы фазы{w["phase_length_one_strand_m"]:.2f}м; суммарно{w["total_wire_m"]:.1f}м; с15%запасом{w["order_wire_m_with_15pct_reserve"]:.1f}м.',
      f'Rфазы20°C={w["Rphase20_ohm"]:.5f}Ом; между фазами звезды={w["Rline20_ohm_star"]:.5f}Ом. Сначала проверить посадку эмалированного провода с реальной пазовой/межслойной изоляцией на одной пробной катушке.',
      'Полная раскладка и знаки вD150_L40/winding_48_coils.csv: катушкаj занимает верхний слойj и нижнийj+5 по модулю48; A+,C−,B+,A−,C+,B− по фазным поясам.',
      '',
      'РАБОЧАЯ ТОЧКА15КМ/Ч, РОВНО,120КГ,36В',
      f'{q["rpm"]:.2f}об/мин; Tполезный={q["useful_torque_Nm"]:.3f}Нм; Pвал={q["shaft_W"]:.2f}Вт; Iф={q["I_phase_rms_A"]:.3f}A RMS /{q["I_phase_peak_A"]:.3f}A peak.',
      f'id={q["Id_peak_A"]:.3f}A peak; iq момента={q["Iq_torque_peak_A"]:.3f}A peak; f={q["frequency_hz"]:.3f}Гц; fскольжения={q["slip_hz"]:.3f}Гц; Bзазора={q["Bg_peak_T"]:.3f}Т.',
      f'Потери: обмотка{q["copper_W"]:.2f}Вт; клетка{q["cage_W"]:.2f}Вт; сталь{q["stator_iron_W_assumed"]+q["rotor_iron_W_assumed"]:.2f}Вт; трение{q["friction_W_assumed"]:.2f}Вт; добавочные{q["stray_PWM_W_assumed"]:.2f}Вт.',
      f'Всего потерь{q["motor_loss_W"]:.2f}Вт; КПД двигателя модели{100*q["motor_efficiency_model"]:.1f}%; батарея≈{q["battery_W_bounds_assumed"][0]:.1f}–{q["battery_W_bounds_assumed"][1]:.1f}Вт ({q["battery_current_A_bounds_assumed"][0]:.2f}–{q["battery_current_A_bounds_assumed"][1]:.2f}A при36В).',
      '500Вт полезной мощности, резкий разгон и подъём5% эта связка с принятыми токами не обеспечивает. Задача текущей модели — исследовательский привод, а не подтверждённая замена серийному самокату.',
      '',
      'ТЕПЛО',
      '3узла: обмотка, статор, ротор. Rобм-статор=0.7К/Вт; Rстатор-среда=1.2; Rротор-среда=0.9; Rстатор-ротор=4.0. ВсеRтепл допущены.',
      'Учитывается рост сопротивления медиα=0.00393/К при постоянныхid/iq; плотность/теплоёмкости по номинальным материалам. Модель не заменяет термоиспытание.',
      f'При25°C среды через60мин: обмотка{t["temperatures_at_60min_C"]["winding"]:.1f}°C, статор{t["temperatures_at_60min_C"]["stator"]:.1f}°C, ротор{t["temperatures_at_60min_C"]["rotor"]:.1f}°C.',
      f'Асимптотическая температура обмотки≈{t["steady_state_C_if_stable"]["winding"]:.1f}°C; экран90°C достигается примерно за{t["time_to_90C_s"]/60:.1f}мин. Длительный режим15км/ч под90°C НЕ подтверждён даже этой сетью.',
      'Для длительного режима требуется проработка теплопути к наружному металлу, затем измерения. PLA/PETG в горячие пазы, несущую обойму или посадки подшипников не закладываются.',
      '',
      'МЕХАНИКА И МАССА',
      f'Идеализированный гладкий сплошной валØ20мм: нагрузка{me["radial_total_N"]:.0f}Н (60%массы на заднее колесо,3g), пролёт130мм; момент20Нм.',
      f'σизг={me["shaft_bending_MPa_smooth_solid"]:.2f}МПа; τ={me["shaft_torsion_MPa_smooth_solid"]:.2f}МПа; σэкв={me["shaft_von_Mises_MPa_smooth_solid"]:.2f}МПа; запас к условным235МПа={me["shaft_yield_safety_at_235MPa_no_notches"]:.2f}.',
      f'Прогиб оси≈{me["shaft_center_deflection_mm_ideal"]:.4f}мм. После назначенных резервов биения, эксцентриситета, люфта и температуры остаётся{me["airgap_budget_mm"]["remaining_for_cover_flex_and_assembly"]:.3f}мм на деформации крышек и сборку.',
      f'Активная сталь{mass["stator_steel_kg"]+mass["rotor_steel_kg"]:.2f}кг, клетка{mass["cage_copper_kg"]:.2f}кг, обмотка{mass["winding_copper_kg"]:.2f}кг. Номинальная компоновка с металлом и кожухами≈{total:.1f}кг без шины, крепежа и проводки.',
      'Эта масса велика для100Вт рабочего режима. Она показывает необходимость облегчения и использования измеренных деталей донора перед заказом; преимущественно пластиковым такой электромагнитный узел не получится.',
      'Проверка вала не учитывает резьбу, лыски, паз, кабельное отверстие и усталость. Крепление магнитопровода/ротора, крышек и оси, стопоры подшипников, крепёж и интерфейс обода ещё не детализированы. ВCAD это прямо отмечено.',
      '',
      'ВЕРИФИКАЦИЯ',
      'Три диаметра: в каждой сборке16компонентов,110твёрдых тел; SOLIDWORKS kernel Check3:0ошибок; номинальных объёмных пересечений0, скрытые детали включены, касания исключены.',
      'Площадь точных контуровDXF с дугами независимо совпала с объёмами nativeCAD для обоих пакетов при всех трёх диаметрах.',
      f'FEMM D150:127742элемента; уточнение188710. Изменение комплексной индуктивности на проверенных частотах≤{100*mesh:.3f}%. Ошибка аппроксимацииL(f)={100*fields["fit"]["relative_complex_fit_rms"]:.4f}%.',
      f'Нелинейная проверка M19:12.728A peak,2Гц; Bзазора={nl["Bg_fund_peak_t"]:.3f}Т; максимум стали по выборке={nl["steel_sample_max_t"]:.3f}Т; Te={nl["torque_mst_nm"]:.3f}Нм. Это отдельный блокированный режим приNref=10, а не тяговой момент на36В.',
      '9групп физических проверок: баланс мощностей/скольжения, peak/RMS/напряжения, дискретная обмотка и заполнение, CAD/DXF, сохранение зазора, сеткаFEMM/момент, независимая ЭДСФарадея, корректное отклонение неподходящих режимов.',
      '',
      'ГРАНИЦЫ ГОТОВНОСТИ',
      'Есть: параметрический источник геометрии; nativeCAD/STEP; номинальныеDXF;STLхолодных кожухов/оправки; обмоточная таблица; FEMMфайлы; электромеханический и тепловой скрининг; BOM.',
      'Остаются до изготовления: реальные размеры донора/рамы, материал ламелей, технологические скругления/изоляция/пакетирование, реальные лобовые части и соединения клетки, крепёж/посадки/удержание, механическаяFEA, балансировка, thermal/drive tests.',
      'Прошивка инвертора и текущий стенд не изменялись. Исследовательские эквивалентные параметры нельзя напрямую переименовать вLm/Lls/Llr MCSDK.',
      '',
      'ПЕРВИЧНЫЕ ИСТОЧНИКИ',
      'EC BUYING, готовая платаSKU71451: https://www.ecbuyingbom.com/drv8302-high-power-motor-drive-module-st-foc-vector-control-bldc-product/',
      'TI, DRV8302,3.3В/5В и3/6PWM; предел микросхемы не является пределом всей платы: https://www.ti.com/product/DRV8302',
      'David Meeker/FEMM, Induction Motor Example, идентификация эквивалентной схемы статическимиACрешениями: https://www.femm.info/wiki/InductionMotorExample',
      'SKF,6204: https://www.skf.com/fr/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings/productid-6204-2RSH',
      'W.Chan, mini_IM, источник идеи учебного печатного асинхронного двигателя; лицензия оригиналаCC-BY-NC4.0: https://github.com/wchan29/mini_IM',
      'Новая геометрия наружного ротора иCAD созданы для этого проекта; исходныйmini_IM сохранён отдельно вreference_mini_IM со своей лицензией.',
      'Подробные числа, все отброшенные обмотки и ограничения: D150_L40/results.json; версия исходников и результатыSHA256_manifest.json.'
    ]
    text='\n'.join(lines)+'\n'
    text=re.sub(r'(?<=\d)(?=[А-Яа-я])|(?<=[а-я])(?=\d)|(?<=[а-я])(?=[A-Z])|(?<=[A-Za-z])(?=[а-я])',' ',text)
    text=text.replace('под90','под 90').replace('D150:127742','D150: 127742')
    (ROOT/'READ_ME_RU.txt').write_text(text,encoding='utf-8')
    (ROOT/'CALCULATION_RU.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>ACIM Hub P1</title><style>body{max-width:1100px;margin:42px auto;padding:0 24px;font:17px/1.6 system-ui;color:#183044}pre{white-space:pre-wrap;font:inherit}a{color:#12679a}img{width:100%}</style><h1>Асинхронное мотор-колесо P1</h1><p><a href="D150_L40/drawings/ACIM_HUB_P1_Engineering.pdf">Четыре расчётных листа PDF</a> · <a href="CHANGE_DIAMETER.cmd">Изменить диаметр</a> · <a href="D150_L40/CAD/ACIM_HUB_D150_L40.SLDASM">Сборка SOLIDWORKS</a></p><img src="D150_L40/drawings/01_layout.png"><pre>'+html.escape(text)+'</pre></html>',encoding='utf-8')
    summary={'main_case':'D150_L40','approximate_motor_mass_kg_no_tire_fasteners':total,'mass_method':'CAD volumes and assumed nominal densities; winding length; bearing0.104kg each','thermal_time90_s_screen':t['time_to_90C_s'],'manufacturing_release':False}
    (ROOT/'project_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':write_report()
