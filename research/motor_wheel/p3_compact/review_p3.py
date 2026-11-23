"""Mass, nominal drawings, printable cold-test kit and P3 review PDF."""
import collections,csv,json,math,struct,sys,re
from pathlib import Path
import numpy as np
from calculate import ROOT,P2
from model import stator_slot,rotor_slot,cage_bar
from review import dxf,contour,mesh,Report
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,white

CASE=ROOT/'P3_L30_M145';OUT=ROOT/'REVIEW';OUT.mkdir(exist_ok=True);BLUE='#173a50';ORANGE='#bb5732'

def stl_kit(audit):
    dest=ROOT/'PRINT_KIT_COLD';dest.mkdir(exist_ok=True);out=[]
    for name,note in [('13_POLYMER_RING_100T','Один венец, холодная примерка'),('14_POLYMER_PLANET_40T','Четыре сателлита, холодная примерка'),('30_PRINTED_COIL_FORMER','Формер пробной катушки'),('31_PRINTED_BEARING_FIT_COUPON','Калибр посадок16/26мм')]:
        path=CASE/'CAD'/('P3_L30_M145_'+name+'.STL');data=bytearray(path.read_bytes());n=struct.unpack_from('<I',data,80)[0]
        if len(data)!=84+50*n:raise ValueError('Expected binary STL:'+str(path))
        vertices=[]
        for j in range(n):
            for k in range(3):vertices.append(struct.unpack_from('<3f',data,84+50*j+12+12*k))
        pts=np.asarray(vertices);z0=float(pts[:,2].min());cx,cy=((pts.max(axis=0)+pts.min(axis=0))/2)[:2];edges=collections.Counter()
        for j in range(n):
            tri=[]
            for k in range(3):
                off=84+50*j+12+12*k;x,y,z=struct.unpack_from('<3f',data,off);struct.pack_into('<3f',data,off,x-cx,y-cy,z-z0);tri.append(tuple(round(q,4) for q in (x,y,z)))
            for u,v in zip(tri,tri[1:]+tri[:1]):edges[tuple(sorted([u,v]))]+=1
        target=dest/(name+'.STL');target.write_bytes(data)
        out.append({'file':str(target),'name':name,'note':note,'triangles':n,'dimensions_mm':(pts.max(axis=0)-pts.min(axis=0)).tolist(),'nonmanifold_edges':sum(v!=2 for v in edges.values()),'z_rebased_mm':z0,'xy_center_before_mm':[float(cx),float(cy)]})
    (dest/'manifest.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8');return out

def mass(r):
    a=json.loads((CASE/'CAD/cad_audit.json').read_text());rows=[];counts=collections.Counter(p['name'] for p in a['placements']);parts={p['part']:p for p in a['parts']}
    for name,num in counts.items():
        if name.startswith(('80','81','82')):continue
        rho=2700;scope='insert';material='Al / заказ'
        if name.startswith(('01','02')):rho=7650*.95;material='Электросталь0.35мм / заказ'
        elif name.startswith('03'):rho=8960;material='Медная клетка / заказ'
        elif name.startswith(('05','06','07','11','12','15','16','20','21','22','24','28')):rho=7850;material='Сталь / изготовить или купить'
        elif name.startswith(('13','14')):rho=1410;material='POM для оценки массы / рабочий печатный материал не выбран'
        elif name.startswith(('25','26')):rho=1270;material='Печатный пластик, только после проверки температуры'
        elif name.startswith('27'):rho=0;scope='external_cooling';material='Два вентилятора, пакетная оценка'
        if name.startswith(('90','91','92')):scope='donor_reference';material='Условный корпус Al; не замер Max Pro'
        kg=parts[name]['solid_volume_mm3']*1e-9*rho*num
        if name.startswith('27'):kg=.070
        rows.append({'part':name,'quantity':num,'mass_kg':kg,'scope':scope,'material':material})
    rows.append({'part':'WINDING_COPPER','quantity':1,'mass_kg':r['winding']['copper_mass_kg'],'scope':'insert','material':'Медь по длине проводника'})
    with (CASE/'BOM_RU.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    sums={s:sum(x['mass_kg'] for x in rows if x['scope']==s) for s in ['insert','donor_reference','external_cooling']}
    return {'scope_masses_kg':sums,'comparable_no_tire_kg':sum(sums.values()),'rows':rows,'audit':a}

def analyse(r):
    b=mass(r);n=json.loads((CASE/'femm_start_hot/nonlinear.json').read_text())['rows'][0];T=(n['torque_mst_Nm']-.008)*6*.94
    out={'date':'2026-11-18','status':'RESEARCH_CANDIDATE_DONOR_FIT_AND_SERVICE_LIFE_UNVERIFIED','mass':{k:v for k,v in b.items() if k!='audit'},
      'packaging':{'ring_OD_mm':165,'reference_rim_OD_mm':177,'main_width_mm':94.5,'axial_bounds_mm':[-42,52.5],'with_external_cooling_span_mm':124.5,
      'axle_length_mm':155,'fit_verified':False,'endturn_overhang_mm_target_not_proven':12},
      'mesh':mesh(1.45),'initial_hot_nonlinear':n,'initial_hot_wheel_torque_Nm':T,
      'initial_start_target03_confirmed':False,'drive_hardware_modified':False,'bench_peak_trip_A_unchanged':1.35}
    # Use the rest road load explicitly for the launch result.
    from optimise import road
    out['initial_hot_accel_m_s2']=(T/.127-road(r['geometry'],0)['force_N'])/122.5
    adj=CASE/'femm_launch_adjusted_hot/nonlinear.json'
    if adj.exists():
        n=json.loads(adj.read_text())['rows'][0];T=(n['torque_mst_Nm']-.008)*6*.94;current=n['current_peak_A']/.8;ripple=r['points']['30']['start03']['I_peak_with_ripple_A']-r['points']['30']['start03']['I_peak_A']
        out['adjusted_hot_nonlinear']=n;out['adjusted_hot_launch']={'wheel_torque_Nm':T,'accel_m_s2':(T/.127-road(r['geometry'],0)['force_N'])/122.5,
          'I_phase_peak_A':current,'I_phase_peak_plus_ripple_30V_A':current+ripple,'I_phase_rms_A':current/math.sqrt(2),'not_bench_measurement':True}
    Tw=r['thermal']['30']['steady_C']['stator'];P=r['points']['30']['flat20']['transmission_loss_W'];out['gear_thermal_sensitivity_C']={str(R):35+(P+(Tw-35)/6)/(1/R+1/6) for R in [1,1.5,2,4]}
    # Stress screen of the new key. Not a fatigue or notch-factor analysis.
    Fkey=9/.0085;out['reaction_key_screen']={'torque_Nm':9,'tangential_N':Fkey,'shear_MPa':Fkey/(5*12),
      'collar_contact_MPa_upper_using_2mm_height':Fkey/(2*12),'notch_and_axle_fatigue_verified':False}
    out['print_kit']=stl_kit(b['audit']);(OUT/'review_data.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8');return out

def drawings(r):
    g=r['geometry'];d=OUT/'drawings';d.mkdir(exist_ok=True)
    dxf(d/'STATOR_24S_NOMINAL.dxf',[54],[contour(g)]);dxf(d/'ROTOR_29B_NOMINAL.dxf',[16],[contour(g,True)])
    dxf(d/'CAGE_BAR_NOMINAL.dxf',[],[cage_bar(g,0)]);dxf(d/'CAGE_ENDRING_NOMINAL.dxf',[22.4,30])
    from planetary import gear_outline
    dxf(d/'SUN20_M1p45_NOMINAL.dxf',[8.7],[gear_outline(20,1.45)])
    dxf(d/'PLANET40_M1p45_NOMINAL.dxf',[8],[gear_outline(40,1.45)])
    dxf(d/'RING100_M1p45_NOMINAL.dxf',[82.5],[gear_outline(100,1.45,True)])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.2})
    fig,ax=plt.subplots(figsize=(11,3.5));items=[('Обдув / пакет вентиляторов',-72,-52,18,'#8db5c7'),('Крышка и опора, условно',-42,-32,35,'#a8b3bb'),('Рёбра теплоотвода',-38.5,-30,68.5,'#667d8a'),('Пакет двигателя',-15,15,54,BLUE),('Лобовые части, цель',-27,27,48.5,'#dfac7a'),('Планетарный ряд',30,44,82.5,'#bba474'),('Передняя опора HK1712',40.5,52.5,11.5,ORANGE)]
    for j,(name,z0,z1,rad,col) in enumerate(items):ax.broken_barh([(-27,12),(15,12)] if name.startswith('Лобовые') else [(z0,z1-z0)],(j-.3,.6),facecolors=col)
    ax.set(yticks=range(len(items)),yticklabels=[x[0] for x in items],xlabel='Координата по оси, мм',xlim=(-80,65));ax.axvline(-42,ls=':',c=ORANGE);ax.axvline(52.5,ls=':',c=ORANGE)
    fig.tight_layout();fig.savefig(OUT/'axial_layout.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,3.6));a=axes[0]
    a.plot([x['speed_kmh'] for x in r['curves']],[x['road_T_Nm'] for x in r['curves']],lw=2,c=BLUE,label='Нагрузка ровной дороги')
    for V,col in [(30,ORANGE),(36,'#4f8ea7')]:a.plot([x['speed_kmh'] for x in r['curves']],[x[f'Tmax_{V}V_Nm']*.9 for x in r['curves']],c=col,label=f'{V} В, минус10% момента')
    a.set(xlim=(0,30),ylim=(0,9),xlabel='Скорость, км/ч',ylabel='Момент колеса, Н·м',title='Принятая оценка тяги, 120 кг');a.legend(fontsize=8)
    a=axes[1];xs=[float(x) for x in r['thermal_sensitivity_Rsa']];ys=[v['winding'] for v in r['thermal_sensitivity_Rsa'].values()]
    a.plot(xs,ys,marker='o',c=ORANGE);a.axhline(120,ls='--',c=BLUE,label='Принятый предел 120°C');a.set(xlabel='R статор-воздух, К/Вт',ylabel='Установившаяся температура, °C',title='Обмотка, 20 км/ч, 30 В, воздух 35°C');a.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'traction_and_heat.png',dpi=150);plt.close(fig)

class P3Report(Report):
    def __init__(self):
        for n,f in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(n,'C:/Windows/Fonts/'+f))
        self.c=canvas.Canvas(str(OUT/'ACIM_P3_REVIEW_RU.pdf'),pagesize=(842,595));self.c.setTitle('P3: более короткое асинхронное мотор-колесо');self.page=0
    def spacing(self,text):
        text=re.sub(r'([А-Яа-яЁё])(?=\d)',r'\1 ',str(text));text=re.sub(r'(\d)(?=[А-Яа-яЁё])',r'\1 ',text)
        text=re.sub(r',(?=[^\s\d])',', ',text);text=re.sub(r'(?<=[А-Яа-яЁёA-Za-z²%]),(?=\d)',', ',text)
        text=re.sub(r'([;:])(?=\S)',r'\1 ',text);return re.sub(r'(?<=%)(?=[А-Яа-яЁё])',' ',text)
    def p(self,text,*args,**kwargs):return super().p(self.spacing(text),*args,**kwargs)
    def table(self,rows,*args,**kwargs):return super().table([[self.spacing(x) for x in row] for row in rows],*args,**kwargs)
    def new(self,title):
        if self.page:self.c.showPage()
        self.page+=1;c=self.c;c.setFillColor(HexColor(BLUE));c.rect(0,550,842,45,fill=1,stroke=0);c.setFillColor(white);c.setFont('Arial-Bold',17);c.drawString(30,565,title)
        c.setFillColor(HexColor('#597080'));c.setFont('Arial',8);c.drawString(30,18,'P3 • 18.11.2026 • Расчёт и номинальная CAD. Посадка Max Pro и ресурс не подтверждены.');c.drawRightString(812,18,str(self.page))

def pdf(r,a):
    b=P3Report();w=r['winding'];m=a['mass'];q=r['points']['30']['flat20'];q36=r['points']['36']['flat20'];th=r['thermal']['30']['steady_C'];n=a.get('adjusted_hot_nonlinear');start=a.get('adjusted_hot_launch')
    b.new('P3: ширина меньше, двигатель и редуктор остаются в колесе')
    y=b.p('Продолжение P2: пакет двигателя укорочен до30 мм, зубчатый ряд до14 мм. Использованы компактные подшипники688VV иHK1712. Добавлено металлическое соединение реактивного момента со шпонкой. Плата DRV8302 и питание10S сохранены как расчётная база.',30,528,782,11)
    y=b.table([['Параметр','P2 основной','P2 меньший Ø','Новый P3'],['Активная длина / обмотка','40 мм /7 витков','40 мм /7 витков','30 мм /8 витков'],['Венец Ø / условный корпус Ø','180 /192 мм','145 /157 мм','165 /177 мм'],['Ширина с опорами, без бокового обдува','110,5 мм','118,5 мм','94,5 мм'],['Осевой габарит вместе с боковым обдувом','140,5 мм','148,5 мм','124,5 мм'],['Масса с условным корпусом, без шины','5,46 кг','4,95 кг',f'{m["comparable_no_tire_kg"]:.2f} кг'],['Новый узел без условного обода и вентиляторов','4,53 кг','4,24 кг',f'{m["scope_masses_kg"]["insert"]:.2f} кг']],30,y,[287,165,165,165],10)
    y=b.p('Выигрыш по ширине относительно радиально компактного P2 -24 мм. Это получено увеличением диаметра венца со145 до165 мм и уменьшением осевой длины. Внутренние размеры Max Pro пока не известны: наш корпус177 мм является условным референсом, не заводским чертежом.',30,y,782,10)
    b.p('Масса рассчитана по CAD-объёмам и плотностям. Не включены шина, часть крепежа, проводка, пазовая изоляция/пропитка и окончательное крепление обдува. Подшипники оценены сплошными кольцами. Проект пока не выдан в изготовление металла и не подтверждён поездкой.',30,y,782,10,ORANGE)

    b.new('Расположение узлов и металлический путь нагрузки')
    image=CASE/'CAD/P3_REVIEW.PNG'
    if image.exists():b.im(image,30,282,370,245)
    y=b.table([['Узел','Новое исполнение'],['Пакет двигателя','Ø108 ×30 мм; зазор0,25 мм'],['Редуктор','20 /40 /100 зубьев, модуль1,45; i=6'],['Ширина зубчатых деталей','Солнце10; сателлиты12; венец14 мм'],['Сателлиты','По 2 × 688VV (8×16×5) на каждый'],['Опоры колеса','6003 сзади; HK1712 17×23×12 спереди'],['Реактивный момент','Al-ступица Ø28; стальная шпонка5×5×12']],423,526,[180,209],10)
    b.im(OUT/'axial_layout.png',30,45,782,200)
    b.p('В CAD 60 компонентов,114тел: ошибок ядра0,пересечений0. Ось, водила, пальцы и тяги металлические. Пазы шпонки выполнены в нативной CAD; окончательные посадки, обработка концов, усталость оси и удержание оси в вилке ещё требуют деталировки.',30,282,782,10)

    b.new('Обмотка, тяга и проверка пуска с насыщением')
    y=b.table([['Показатель','Значение','Условия / ограничения'],['Обмотка',f'8 витков ×4 жилы Ø0,85 мм;64 витка/фазу,звезда','24 катушки;8 последовательно на фазу; CSV приложен'],['Провод / сопротивление',f'{w["order_wire_m_15pct"]:.1f} м с15%запаса; Rф20 = {w["Rs20_ohm"]:.5f} Ом','Заполнение голой медью39,91%; нужна пробная катушка'],['20 км/ч,30 В',f'{q["I_rms_A"]:.2f} А RMS; {q["I_peak_with_ripple_A"]:.2f} А пик с пульсацией',f'Потери мотора {q["motor_loss_W"]:.1f} Вт; батарея {q["battery_A"]:.2f} А'],['20 км/ч,36 В',f'{q36["I_rms_A"]:.2f} А RMS; {q36["I_peak_with_ripple_A"]:.2f} А пик с пульсацией',f'Потери мотора {q36["motor_loss_W"]:.1f} Вт; батарея {q36["battery_A"]:.2f} А'],['Нагрузка дороги','161 Вт и3,68 Н·м на колесе','120 кг, Crr=0,015,CdA=0,6 м²; КПД редуктора0,94 принят'],['Тяговые ограничения','25 км/ч не обеспечены во всём разряде; подъём5% не проходит','Сохраняется потолок15 А пикового фазного тока с оценкой пульсаций']],30,528,[183,285,314],10)
    y=b.p(f'Для двигателя30 мм использовано отдельное решение FEMM, а не масштабирование результата40 мм. В первой горячей нелинейной точке получено {a["initial_hot_wheel_torque_Nm"]:.2f} Н·м на колесе и около {a["initial_hot_accel_m_s2"]:.2f} м/с² начального разгона. Линейная цель0,3 м/с² этой точкой не подтверждается.',30,y,782,10)
    if n and start:y=b.p(f'Вторая проверка:4,1 Гц скольжения, медь клетки85°C, ток фазы {start["I_phase_rms_A"]:.2f} А RMS / {start["I_phase_peak_plus_ripple_30V_A"]:.2f} А пик с пульсацией при30 В. FEMM даёт {n["torque_mst_Nm"]:.3f} Н·м электромагнитного момента, Bg {n["Bg_fund_peak_t"]:.3f} Т; с КПД редуктора0,94 получается {start["accel_m_s2"]:.2f} м/с². Это ещё не стендовое измерение.',30,y,782,10)
    b.p(f'Разгон0-20 км/ч с условным запасом10% по моменту: {r["acceleration"]["0.9"]["time_20kmh_s"]:.1f} с при30 В. Полная нелинейная тяговая характеристика и динамика регулятора не рассчитаны. Лобовые части по12 мм - цель, которая может изменить итоговую ширину после намотки.',30,y,782,10,ORANGE)

    b.new('Нагрев и пластиковые шестерни ограничивают облегчение')
    b.im(OUT/'traction_and_heat.png',30,245,782,285)
    y=b.p(f'При35°C воздуха,30 В и20 км/ч: обмотка {th["winding"]:.1f}°C,статор {th["stator"]:.1f}°C,ротор {th["rotor"]:.1f}°C, если R статор-воздух =1,5 К/Вт. При2,5 К/Вт модель даёт127°C в обмотке - выбранный предел120°C уже превышен. Само значение1,5 К/Вт пока является требованием к обдуву.',30,233,782,10)
    y=b.p('Обдув по-прежнему внешний. Пакеты50×50×20 мм в CAD не являются готовыми посадками конкретной воздуходувки. При суммарных3 л/с и53 Вт потерь мотора нагрев воздуха около15°C; перепад давления, утечки, теплоотдача рёбер и контактов должны быть проверены. Полностью закрытый корпус без обдува этим расчётом не подтверждён.',30,y,782,10)
    temps=a['gear_thermal_sensitivity_C'];y=b.p(f'Отдельная грубая тепловая оценка редуктора: при R к воздуху1,5 К/Вт примерно {temps["1.5"]:.1f}°C,при2 К/Вт {temps["2"]:.1f}°C,при4 К/Вт {temps["4"]:.1f}°C. Предполагается6 К/Вт между мотором и редуктором. Поэтому iglidur i150 с заявленным длительным пределом65°C нельзя назначать без измерения температуры и износа.',30,y,782,10)
    b.p('Оценка Льюиса для полимерного зуба:8,29 МПа при9 Н·м, с коэффициентами1,5 на распределение и1,2 на динамику. При12 Н·м получается11,05 МПа - выше принятого условного допуска10 МПа. Переход на больший ток без нового расчёта шестерён исключён; ресурс по усталости ещё не определён.',30,y,782,10,ORANGE)

    b.new('Что уже можно печатать и как продолжить без переделки')
    y=b.table([['Файл в PRINT_KIT_COLD','Назначение','Критерий проверки'],['30_PRINTED_COIL_FORMER.STL','Сформировать пробную катушку8 витков4×0,85','Реальные размеры пучка и лобовой части;12мм пока не доказаны'],['31_PRINTED_BEARING_FIT_COUPON.STL','Проба отверстий16 и26мм','Подшипник входит без трещин; после остывания нет недопустимого люфта'],['14_POLYMER_PLANET_40T.STL ×4','Холодная проверка зацепления и посадок','Свободное вращение без закусывания; размер по STL около60,9×60,9×12мм'],['13_POLYMER_RING_100T.STL','Холодная примерка венца Ø165мм','Не использовать первый PETG-комплект для поездки']],30,528,[291,244,247],9)
    y=b.p('STL приведены к Z=0; единицы мм. Начальная пробная печать:0,16мм слой,6 стенок,100%заполнение, температуры из проверенного профиля своего PETG. Эти настройки предназначены для примерки. Рабочие шестерни требуют материала, который сохраняет прочность и износостойкость при измеренной температуре.',30,y,782,10)
    y=b.p('Повторяемая смена диаметра: python rebuild.py --ring-od 165 --cad. Диапазон венца165-180мм: меняются зубчатый ряд, водила и условный корпус; мотор108×30 и обмотка сохраняются. Новая геометрия требует проверки пересечений. Нативные файлы перестраиваются Python, общих уравнений между деталями SW нет.',30,y,782,10)
    y=b.p('Для окончательной привязки Max Pro по-прежнему нужны внутренний Ø корпуса, глубина между крышками, расположение подшипников и расстояние между перьями. Без них нельзя назначить резьбы/лыски оси, штатное крепление крышек и выдать металл в изготовление. Текущий стенд и его отключение1,35 А пик не изменялись.',30,y,782,10,ORANGE)
    b.p('Источники размеров: JTEKT HK1712 (17×23×12); NSK Bearing Replacement Guide,688VV (8×16×5; открытый688 может иметь ширину4мм). Тепловой предел igus i150 -65°C. Полные адреса и исходные условия сохранены в SOURCES.txt и results.json. Файлы DXF в REVIEW/drawings номинальные, без производственных галтелей и допусков.',30,y,782,9)
    b.end()

def run():
    r=json.loads((CASE/'results.json').read_text());a=analyse(r);drawings(r);pdf(r,a)
    print(json.dumps({'mass_kg':a['mass']['comparable_no_tire_kg'],'insert_kg':a['mass']['scope_masses_kg']['insert'],'packaging':a['packaging'],'mesh':a['mesh'],'adjusted_start':a.get('adjusted_hot_launch'),'print_kit':[{k:x[k] for k in ['name','dimensions_mm','nonmanifold_edges']} for x in a['print_kit']]}),flush=True)

if __name__=='__main__':run()
