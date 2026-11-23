"""Offline operator package: PC control, unchanged red-board firmware, no MCU images."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from load_bench.control import PROFILES,Limits,expected_parameters,readiness
from load_bench.simulation import simulate,export_csv

OUT=ROOT/'artifacts/t3d_stock_firmware_20261122'
PDF=ROOT/'output/pdf/T3D_LOAD_GUIDE_RU.pdf'


def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def csv_table(name,header,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f,delimiter=';');w.writerow(header);w.writerows(rows)


def guide(config,tests):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle,Flowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from xml.sax.saxutils import escape
    pdfmetrics.registerFont(TTFont('Arial',r'C:\Windows\Fonts\arial.ttf'))
    pdfmetrics.registerFont(TTFont('ArialBold',r'C:\Windows\Fonts\arialbd.ttf'))
    styles={k:ParagraphStyle(k,fontName='ArialBold' if k in ('T','H') else 'Arial',fontSize=size,
        leading=leading,spaceAfter=space,textColor=colors.HexColor('#173a55') if k in ('T','H') else colors.HexColor('#17232e'))
        for k,size,leading,space in [('T',25,30,14),('H',16,20,10),('B',10,14,9),('S',8.6,11.5,7),('C',8.4,11,0)]}
    story=[]
    def add(text,style='B'):story.append(Paragraph(text,styles[style]))
    def page(title):story.append(PageBreak());add(title,'T')
    def table(rows,widths):
        t=Table([[Paragraph(escape(str(c)),styles['C']) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9f2')),
            ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c5d1dd')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.extend([t,Spacer(1,12)])
    class Architecture(Flowable):
        def __init__(self):super().__init__();self.width=510;self.height=139
        def draw(self):
            c=self.canv;c.setFont('Arial',9)
            def box(x,y,w,lines):
                c.setStrokeColor(colors.HexColor('#7090aa'));c.setFillColor(colors.HexColor('#eef4f9'))
                c.roundRect(x,y,w,34,5,fill=1);c.setFillColor(colors.HexColor('#173a55'))
                for i,line in enumerate(lines.split('\n')):c.drawCentredString(x+w/2,y+21-11*i,line)
            def arrow(x,y,x2):
                c.setStrokeColor(colors.HexColor('#176b9b'));c.line(x,y,x2,y);c.line(x2,y,x2-5,y+3);c.line(x2,y,x2-5,y-3)
            for y,left,mid,right in [(101,'ПК: наша программа','USB: красная плата\nштатная прошивка','T3D: цифровые входы\nразрешение CZERO'),
                (53,'ПК: наша программа','Изолированный USB-RS485','T3D: момент и измерения'),
                (5,'АИР56 + его инвертор','Муфта / общий вал','Сервомотор T3D\nсоздаёт нагрузку')]:
                box(0,y,140,left);box(180,y,150,mid);box(370,y,140,right)
                arrow(140,y+17,180);arrow(330,y+17,370)
    add('Нагрузочный стенд T3D<br/>Штатная прошивка красной платы','T')
    add('Актуальное решение от 22 ноября 2026 года. Разрабатывается программа экспериментов на ПК. Красную плату, T3D, Nucleo и Uno Q в этой задаче не перепрошиваем. Отдельная Blue Pill не нужна.')
    story.extend([Architecture(),Spacer(1,12)])
    add('Что делает каждый блок','H')
    add('Красная BSMCE04U принимает USB-команды и выдаёт управляющие сигналы. Силовой блок из комплекта T3D сам управляет токами, энкодером и сервомотором. Прошивка красной платы уже умеет нужные операции; новая firmware для обычного управления не требуется.')
    table([['Команды T3D','Назначение'],['STEP/DIR','Позиционное движение, наладка вращения. Это само по себе не задание постоянного момента нагрузки.'],
        ['TRQ1/TRQ2','Выбор четырёх внутренних моментов P145..P148. Можно делать ступени штатными цифровыми выходами.'],
        ['RS485 / P145','Выбранный путь для плавных сценариев и чтения скорости/тока/оценки момента.'],
        ['Аналоговый вход','Возможен после проверки уровня, формы сигнала AVI, фильтра и нуля; в текущей схеме не используется.']],[115,395])
    add('Как открыть','H')
    add('Ярлык «Нагрузочный стенд T3D» или START_T3D_LOAD_CONSOLE.cmd. Симуляция и чтение платы доступны сейчас. Реальные опыты - после получения комплекта и наладки. DrufelCNC и наша программа используют одну плату по очереди: перед запуском нашего приложения закройте Drufel. Его настройки и совместимость сохранены.','S')

    page('Подключение и настройки')
    add('Ниже предварительная схема по T3D EN V2.3. Сверить реальную маркировку и ревизию полученного драйвера. Название выбранного комплекта - HLTNC-T3D-400W-3M-BRAKE; его поставка ещё ожидается.','S')
    table([['Узел / контакт','Подключение'],['T3D CN1 40 / 41 / 42','RS485 A / B / GND изолированной полевой стороны USB-RS485. USB GND не соединять с сигналом GND драйвера без проверки изоляции.'],
        ['T3D CN1/31','COM+ 12-24 В от сигнального источника.'],['DI1 CN1/16','Внешний SON; включение только на неподвижном валу с нулевым заданием.'],
        ['DI2 CN1/1','От OUT1 красной платы: разрешение CZERO. Полевые 24V/DCM платы - по её маркировке; DCM к 0 В сигнального источника. Проверить токи и полярность.'],
        ['DI3 CN1/17','Отдельная нормально замкнутая физическая цепь CZERO. Её размыкание задаёт ноль независимо от ПК. Отдельно действует аппаратный STOP АИР.'],
        ['DI4 CN1/2','Не используется. Красные OUT2..4, STEP/DIR и AVI в этой выбранной схеме не используются.'],
        ['DO1 / DO2 / DO4 / COM','CN1 20 / 5 / 6 / 23: SRDY / ALM / BRK / общий. Катушку тормоза питает отдельный согласованный каскад 24 В.'],
        ['Силовой кабель / CN2','Комплектный мотор подключается к T3D силовым и энкодерным кабелями. Красная плата не питает мотор.']],[125,385])
    table([['Параметры','Значения','Назначение'],['P004 / P026','2 / 1','Моментный режим / внутренний момент'],['P145..148','0 / 0 / 0 / 0','Сохранённые задания нулевые; программа меняет только оперативный P145'],
        ['P098 / P100','0 / 1','Без внутреннего включения SON; DI1 внешний SON'],['P101 / P102 / P103','-8 / -8 / 0','DI2 и DI3: обрыв включает CZERO; DI4 не используется'],
        ['P108..111','2 / 3 / 0 / 8','SRDY / ALM / выключено / BRK'],['P120..124','все 0','Без программного форсирования DI'],
        ['P065 / P066','25 / -25 %','Ограничения момента'],['P075 / P077 / P078','500 / 0 / 400','Ограничения скорости'],['P181 / P182 / P183','1 / 2 / 1','19200 8E1, адрес 1']],[125,100,285])
    add('P145 - адрес 145 десятичное = 0x0091. Профиль комплектного мотора P000/P001/P099 не заменять примерами. Постоянные настройки сохраняются на панели и перечитываются после перезапуска; программа не пишет EEPROM, JOG, SON или сброс аварий.','S')

    page('Первые опыты и остановка')
    add('Что реально проверено','H')
    add('Наша красная плата A720:F803, serial 816FAD79CE5, отвечает напрямую через штатный USB HID. На отдельной плате только с USB подтверждены включение и выключение OUT1..4 и обратная связь sequence/маски. Команд движения и перепрошивки не было. Электрические уровни на клеммах ещё не измерялись.')
    add('После аварийного выхода управляющего процесса OUT1 оставался ON во всех отчётах более 5 секунд. Это ограничение штатной платы при сбое ПК, а не причина менять firmware для обычных команд. Текущий режим - supervised_bench: короткие опыты под наблюдением оператора с отдельной физической цепью STOP/CZERO. Безнадзорный режим заблокирован.')
    add('Что делает программа','H')
    add('Проверяет параметры T3D, прошивки и свежесть статуса АИР, токовые окна, выбранный алгоритм, состояния DI/DO, скорость и знак момента. Только после свежего чтения и подтверждённой записи P145 включает OUT1. При нормальном окончании или обнаруженной ошибке выключает OUT1, записывает/перечитывает P145=0 и запрашивает штатный STOP АИР.')
    add('При зависании самого ПК программная остановка не гарантирована. SON из Python не сбрасывается: отдельная последовательность BRK не должна зажать ещё вращающийся общий вал. Её времена проверяются физически.','S')
    add('Начальный диапазон','H')
    table([['Ограничение','Первая стадия'],['Поле АИР / скорость','Не выше 5 Гц; 80-350 об/мин'],['Задание момента / мощности','До 0.12 Н*м / 5 Вт; при ожидаемых 1.27 Н*м команда 9% = 0.1143 Н*м'],['Один опыт','4 с; первые/последние 1 с ноль, цикл команд 0.5 с; программный бюджет 15 Дж'],['При потере host','Время автоматического отключения не задано. Предел 25% при границе 600 об/мин даёт около 19.95 Вт: требуем подтверждённый длительный отвод этой мощности.']],[155,355])
    add('Четыре секунды/15 Дж - программные ограничения при работающем ПК. Старый расчёт аварийной энергии за 1.2 с к штатной плате не применяется. Для тормозного узла проверяются реальная длительная мощность, резистор и тепловой режим; надпись 400 Вт на моторе это не подтверждает.','S')
    add('После доставки: сверить шильдики и проводку; сначала без муфты проверить SON/CZERO, знак, тормоз и остановку; затем соосность/муфту/ограждение и малую нагрузку. Готовность АИР к нагрузке ещё требует отдельного подтверждения. Штатные 1.35 А, NIS25 и установленные прошивки не изменялись.','S')

    page('Эксперименты, файлы и проверки')
    add('Программа на ПК','H')
    add('Пять форм: zero, step, ramp, sine, prbs. План - 5 форм x 3 алгоритма x 3 независимых повтора. Алгоритмы переключает штатный стенд; программа нагрузки проверяет его ID и не отправляет START/ARM/CLEAR. План не является очередью автоматического запуска.')
    table([['Запись','Практический смысл'],['JSONL / CSV','Сырые ответы и полный статус АИР, команды момента, интервалы чтения, причины остановки и идентификаторы прогона.'],
        ['RTU / HID trace','Реальные кадры и подтверждения; включение выхода подтверждается контроллером, физическая клемма проверяется отдельно.'],
        ['manifest / SHA-256 / seed','Воспроизводимость конфигурации и исходников. Симуляция явно отмечена и не подтверждает физику двигателя.'],
        ['Скорость / момент T3D','Медленный опрос энкодера и оценка электромагнитного момента; не синхронный высокочастотный эталон и не механический датчик момента.']],[140,370])
    add('Проверки','H')
    add(f'Проверки Python: {tests}, все пройдены. Они охватывают Modbus/CRC, ограничения и остановку, USB-идентичность, команды штатного I/O, отсутствие движения осей и запрет безнадзорного режима. Все пять эмуляционных сценариев проходят. Установка новой firmware не является условием запуска программы.')
    add('Файлы и команды','H')
    add('START_T3D_LOAD_CONSOLE.cmd - открыть панель; load_bench/config.template.json - исходная конфигурация; READ_ME_RU.txt - подробное подключение; parameters.csv - таблица T3D; experiment_plan.csv - план опытов.','S')
    add('python -X utf8 -m load_bench check<br/>python -X utf8 -m load_bench red-probe<br/>python -X utf8 -m load_bench simulate --profile step --out artifacts/t3d_demo_new','S')
    add('Дамп и исходные прошивки','H')
    add('Прошивки не менялись. Файл заводского дампа ещё не считан; его отсутствие не мешает штатному USB-управлению. Любая будущая запись/стирание запрещены до проверенной резервной копии по AGENTS.md. Старые кандидаты watchdog выведены из рабочей схемы и не включаются в этот пакет.','S')
    add('Источники','H')
    add('<link href="https://www.hlt-cnc.com/download" color="#176b9b">HLTNC T3D EN V2.3 и Modbus</link>: CN1 PDF 24-25, момент 66-67/91, DI 107-111, BRK 119-120. '
        '<link href="https://drufelcnc.com/?c=controllers&amp;p=BSMCE04U" color="#176b9b">DrufelCNC BSMCE04U</link>: схема штатного подключения драйверов. '
        'USB-совместимость: GRBL2MACH/docs/PROTOCOL.md, commit e172263aa72f9ffa5520c919ca0c482e10a094c8.','S')
    def footer(c,doc):
        c.setStrokeColor(colors.HexColor('#c5d1dd'));c.line(42,36,553,36)
        c.setFont('Arial',7.5);c.setFillColor(colors.HexColor('#526575'))
        c.drawString(42,25,'T3D / АИР56 - штатная прошивка, программа экспериментов на ПК')
        c.drawRightString(553,25,str(doc.page))
    PDF.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=39,leftMargin=42,topMargin=42,bottomMargin=48,
        title='T3D: штатная прошивка и управление с ПК',author='MIC project').build(story,onFirstPage=footer,onLaterPages=footer)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'load_bench/config.template.json').read_text(encoding='utf-8'))
    tests_root=ET.parse(OUT/'python_tests.xml').getroot()
    tests=sum(int(s.get('tests')) for s in tests_root.findall('testsuite'))
    assert all(s.get('failures')=='0' and s.get('errors')=='0' for s in tests_root.findall('testsuite'))
    results=[]
    with tempfile.TemporaryDirectory(prefix='t3d-stock-') as tmp:
        for profile in PROFILES:
            folder=Path(tmp)/profile
            m=simulate(config,profile,folder);export_csv(folder)
            shutil.copytree(folder,OUT/'simulation'/profile,dirs_exist_ok=True)
            results.append({k:m.get(k) for k in ('profile','completed','simulation','hardware_validated','permit_backend','autonomous_host_loss_shutdown')})
    dump(OUT/'simulation_summary.json',results)
    params=expected_parameters(config);params[145]=0
    csv_table('parameters.csv',['parameter','value'],[(f'P-{k:03}',v) for k,v in sorted(params.items())])
    plan=[(n,algorithm,profile,repeat,20261121+repeat,False) for n,(algorithm,profile,repeat) in enumerate(
        ((a,p,r) for a in ('scalar','FOC','adaptive_PWM') for p in PROFILES for r in (1,2,3)),1)]
    csv_table('experiment_plan.csv',['case','algorithm','profile','repeat','seed','auto_start'],plan)
    guide(config,tests)
    shutil.copy2(ROOT/'load_bench/READ_ME_RU.txt',OUT/'READ_ME_RU.txt')
    stock=ROOT/'artifacts/red_board_stock_20261122'
    evidence=OUT/'stock_tests';evidence.mkdir(exist_ok=True)
    for name in ('passive_probe.json','output_commands_initialized_v2.json','host_process_loss.json','final_state.json'):
        shutil.copy2(stock/name,evidence/name)
    validation=dict(python_tests=tests,permit_backend='stock_hid',experiment_mode='supervised_bench',
        firmware_changed=False,new_firmware_required=False,bluepill_required=False,swd_required_for_stock_control=False,
        autonomous_host_loss_shutdown=False,hardware_ready=False,missing=readiness(config),simulation_summary=results,
        original_dump_exists=False,air_firmware_changed=False,air_commands_sent_this_revision=0,t3d_commands_sent_this_revision=0)
    if (OUT/'ui_api_checks.json').exists():validation['ui_api_checks']=json.loads((OUT/'ui_api_checks.json').read_text())
    dump(OUT/'validation.json',validation)
    files={}
    def put(path,name):files[str(name).replace('\\','/')]=Path(path)
    for p in (ROOT/'load_bench').rglob('*'):
        if p.is_file() and not any(x in p.parts for x in ('.pio','__pycache__','build','watchdog_firmware','red_watchdog_firmware')) and p.name!='config.local.json':put(p,p.relative_to(ROOT))
    for rel in ('AGENTS.md','START_T3D_LOAD_CONSOLE.cmd','requirements-load-bench.txt','tests/test_t3d_load_bench.py','tests/test_red_board_load.py','tools/prepare_t3d_load_package.py','tools/prepare_t3d_stock_package.py','tools/check_red_board_stock.py'):
        put(ROOT/rel,rel)
    put(PDF,'T3D_LOAD_GUIDE_RU.pdf')
    for p in OUT.rglob('*'):
        if p.is_file() and p.suffix not in ('.zip','.exe') and 'render' not in p.parts:put(p,Path('review')/p.relative_to(OUT))
    hashes={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
    package=OUT/'T3D_STOCK_FIRMWARE_PACKAGE.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for n,p in files.items():z.write(p,n)
        z.writestr('SHA256_MANIFEST.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:assert z.testzip() is None
    print(json.dumps(dict(package=str(package),pdf=str(PDF),files=len(files)+1,tests=tests,firmware_required=False),ensure_ascii=False))


if __name__=='__main__':main()
