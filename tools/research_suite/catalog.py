# Embedded into the frozen HMI. Only native verified capabilities admit actuation.
RESEARCH_ORDER = ('VF_FIXED','FOC_FIXED','ADAPTIVE_PWM','FOC_CLASSICAL','AI_SHADOW','AI_ACTIVE','EXTREMUM_SEARCH')
RESEARCH_LABELS = {
    'VF_FIXED':'Скалярный V/f — старт/стоп и задания частоты',
    'FOC_FIXED':'Векторный FOC с фиксированным потоком',
    'ADAPTIVE_PWM':'Адаптивный ШИМ',
    'FOC_CLASSICAL':'FOC с классической оптимизацией потока',
    'AI_SHADOW':'ИИ — расчёт предложения без управления',
    'AI_ACTIVE':'ИИ — управление через ограничения',
    'EXTREMUM_SEARCH':'Ограниченный поиск экстремума',
}
RESEARCH_BLOCKS = {
    'FOC_FIXED':('FOC_KERNEL_AND_MOTOR_MODEL_REQUIRED','Нужны действующий FOC-контур, измеренные Rr/Lm/индуктивности и проверка наблюдателя.'),
    'ADAPTIVE_PWM':('ADAPTIVE_PWM_PORT_AND_ADC_QUALIFICATION_REQUIRED','Алгоритм из модели не перенесён; окна АЦП проверены для фиксированных 16 кГц.'),
    'FOC_CLASSICAL':('QUALIFIED_FOC_REQUIRED','Сначала нужен проверенный FOC и идентифицированная модель потерь.'),
    'AI_SHADOW':('TRAINED_MODEL_REQUIRED','Пока есть офлайн-инструменты обучения; модели, обученной на новых опытах АИР, нет.'),
    'AI_ACTIVE':('QUALIFIED_FOC_AND_AI_POLICY_REQUIRED','Нужны проверенный FOC, обученная политика и проверка ограничений.'),
    'EXTREMUM_SEARCH':('QUALIFIED_BASELINE_AND_POWER_MEASUREMENT_REQUIRED','Нужны пригодная базовая система и измерение активной мощности; RMS токов её не заменяет.'),
}


def research_catalog(data):
    known=(data.get('fw_build'),data.get('mc_fw_build'))==(2026102911,2026102912)
    native=known and data.get('research_native_valid')==1 and data.get('research_native_caps')==1
    rows=[]
    for name in RESEARCH_ORDER:
        ready=name=='VF_FIXED' and native
        if ready:code,text='','Алгоритм доступен; перед пуском проверяются питание, токи и защиты.'
        elif name=='VF_FIXED':code,text='NATIVE_CAPABILITIES_UNAVAILABLE','Нет свежего подтверждения режима от Nucleo.'
        else:code,text=RESEARCH_BLOCKS[name]
        rows.append(dict(id=name,label=RESEARCH_LABELS[name],hardware_ready=ready,
                         status='available' if ready else 'blocked',reason_code=code,reason=text))
    return rows


def with_research_suite(data):
    if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026102911,2026102912):return data
    data['research_algorithms']=research_catalog(data)
    data['research_suite_version']=1
    data['research_actuator_algorithm']='VF_FIXED' if data.get('mc_capabilities')==1 else None
    data['research_program_autostart']=False
    data['research_missing_motor_parameters']=['Rr','Lls','Llr','Lms','Imagn']
    data['research_rotation_feedback_valid']=False
    return data
