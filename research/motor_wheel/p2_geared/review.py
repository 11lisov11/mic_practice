"""Reproducible P2 mass, thermal sensitivity, nominal drawings and review PDF.

All outputs are research estimates, not a production release or a road test.
"""
import csv,json,math,collections
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon as Poly
from shapely.affinity import rotate,translate
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle,Polygon
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor,white
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph,Table,TableStyle
from reportlab.lib.styles import ParagraphStyle
from model import ROOT,stator_slot,rotor_slot,cage_bar,xy
from planetary import config,gear_outline,load_screen
from optimise import road,wheel_op,thermal

OUT=ROOT/'REVIEW';OUT.mkdir(exist_ok=True)
BLUE='#173a50';ORANGE='#bb5732';GREY='#597080'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18})

def bom(tag,winding):
    a=json.loads((ROOT/tag/'CAD/cad_audit.json').read_text());counts=collections.Counter(x['name'] for x in a['placements']);parts={x['part']:x for x in a['parts']};rows=[]
    for n,c in counts.items():
        if n.startswith(('80','81','82')):continue
        rho=2700;category='Алюминий, заказ';scope='insert'
        if n.startswith(('01','02')):rho=7650*.95;category='Электросталь 0,35 мм, заказ'
        elif n.startswith('03'):rho=8960;category='Медь, клетка под заказ'
        elif n.startswith(('05','06','07','11','12','15','16','20','21','22','24')):rho=7850;category='Сталь / покупной металл'
        elif n.startswith(('13','14')):rho=1410;category='POM, заказ / квалифицированный печатный полимер'
        elif n.startswith(('25','26')):rho=1270;category='Пластик, печать; температура требует проверки'
        elif n.startswith('27'):rho=0;category='Два покупных вентилятора, оценка';scope='cooling'
        if n.startswith(('90','91','92')):scope='donor_reference';category='УСЛОВНЫЙ алюминиевый корпус, не замер Ninebot'
        mass=parts[n]['solid_volume_mm3']*1e-9*rho*c
        if n.startswith('27'):mass=.070
        rows.append({'part':n,'quantity':c,'mass_kg':mass,'scope':scope,'method':'nominal volume*density; bearings solid envelope upper estimate','material':category})
    rows.append({'part':'WINDING_COPPER','quantity':1,'mass_kg':winding['copper_mass_kg'],'scope':'insert','method':'wire length and copper area','material':'Медь, обмотка; эмаль и пропитка сверх оценки'})
    with (ROOT/tag/'BOM_RU.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.DictWriter(f,fieldnames=rows[0].keys());wr.writeheader();wr.writerows(rows)
    insert=sum(r['mass_kg'] for r in rows if r['scope']=='insert');donor=sum(r['mass_kg'] for r in rows if r['scope']=='donor_reference')
    c=config(a['gear']['module_mm']);case={p['part']:p for p in a['parts']};back=case['90_DONOR_REAR_COVER_REFERENCE']['bbox_mm'][2]
    end=case['21_OUTPUT_NEEDLE_NK17_16']['bbox_mm'][5]
    return {'insert_kg':insert,'external_fans_kg_estimate':.07,'assumed_donor_metal_kg':donor,'comparable_no_tyre_kg':insert+donor+.07,
      'not_in_mass':['tire','nuts/screws omitted from envelopes','wires/connectors','impregnation/slot insulation','fan mounts and duct redesign','inverter/battery'],
      'active_assembly_outer_d_mm':2*c['ring_outer_r_mm'],'reference_rim_OD_mm':2*c['donor_rim_outer_r_mm_ASSUMED'],
      'main_axial_width_mm':end-back,'axial_bounds_mm':[back,end],'axle_length_mm':155,
      'with_cooling_axial_span_mm':end-(-77),'cooling_plenum_OD_mm':160,'donor_fit_verified':False,'rows':rows}

def mesh(module):
    sun=Poly(gear_outline(20,module));planet=Poly(gear_outline(40,module,phase=math.pi/40));hole=Poly(gear_outline(100,module,True))
    ring=Poly([(200*math.cos(a),200*math.sin(a)) for a in np.linspace(0,2*math.pi,721)],holes=[list(hole.exterior.coords)])
    worst=0
    for deg in np.linspace(0,90,91):
        s=rotate(sun,6*deg,origin=(0,0));ps=[]
        for j in range(4):
            a=math.radians(deg+90*j);p=translate(rotate(planet,-1.5*deg,origin=(0,0)),30*module*math.cos(a),30*module*math.sin(a));ps.append(p)
            worst=max(worst,s.intersection(p).area,ring.intersection(p).area)
        for i in range(4):
            for j in range(i):worst=max(worst,ps[i].intersection(ps[j]).area)
    return {'module_mm':module,'carrier_angles_checked':91,'full_repeat_deg':90,'max_overlap_area_mm2':worst,'gears_valid':all(x.is_valid for x in [sun,planet,ring])}

def dxf(path,circles=(),polys=()):
    s=['0','SECTION','2','HEADER','9','$INSUNITS','70','4','0','ENDSEC','0','SECTION','2','ENTITIES']
    for radius in circles:s+=['0','CIRCLE','8','NOMINAL_MM','10','0','20','0','40',str(radius)]
    for pts in polys:
        s+=['0','LWPOLYLINE','8','NOMINAL_MM','90',str(len(pts)),'70','1']
        for p in pts:s+=['10',f'{p[0]:.9f}','20',f'{p[1]:.9f}','42',f'{p[2] if len(p)>2 else 0:.12f}']
    s+=['0','ENDSEC','0','EOF'];path.write_text('\n'.join(s)+'\n',encoding='ascii')

def contour(g,rotor=False):
    Z=g['rotor_bars'] if rotor else g['stator_slots'];r=g['stator_bore_mm']/2-(g['gap_mm'] if rotor else 0);w=g['rotor_opening_w_mm'] if rotor else g['slot_mouth_w_mm']
    pts=[];bulge=math.tan((2*math.pi/Z-2*math.asin(w/(2*r)))/4)
    for j in range(Z):
        q=rotor_slot(g,j) if rotor else stator_slot(g,j)
        pts.extend([(x,y,bulge if k==len(q)-1 else 0) for k,(x,y) in enumerate(q)])
    return pts

def drawings(r):
    g=r['geometry'];dr=OUT/'drawings';dr.mkdir(exist_ok=True)
    dxf(dr/'STATOR_24S_NOMINAL.dxf',[54],[contour(g)])
    dxf(dr/'ROTOR_29B_NOMINAL.dxf',[16],[contour(g,True)])
    dxf(dr/'CAGE_BAR_NOMINAL.dxf',[],[cage_bar(g,0)])
    dxf(dr/'CAGE_ENDRING_NOMINAL.dxf',[22.4,30])
    for m in [1.6,1.25]:
        dxf(dr/f'SUN20_M{m:g}_NOMINAL.dxf',[8.7],[gear_outline(20,m)])
        dxf(dr/f'PLANET40_M{m:g}_NOMINAL.dxf',[11],[gear_outline(40,m)])
        dxf(dr/f'RING100_M{m:g}_NOMINAL.dxf',[50*m+10],[gear_outline(100,m,True)])
    fig,axes=plt.subplots(1,2,figsize=(11.2,4.4))
    a=axes[0];a.add_patch(Circle((0,0),54,fc='#627784'));a.add_patch(Circle((0,0),30,fc='white'))
    for j in range(24):a.add_patch(Polygon(stator_slot(g,j),fc='#eee7dd',ec='none'))
    a.add_patch(Circle((0,0),29.75,fc='#aebcc4'));a.add_patch(Circle((0,0),16,fc='white'))
    for j in range(29):a.add_patch(Polygon(rotor_slot(g,j),fc='white',ec='none'));a.add_patch(Polygon(cage_bar(g,j),fc='#cb7947',ec='none'))
    a.set(xlim=(-58,58),ylim=(-58,58),aspect='equal',title='Электромагнитная часть: Ø108 × 40 мм');a.set_xlabel('мм');a.set_ylabel('мм')
    a=axes[1];m=1.6;a.add_patch(Circle((0,0),90,fc='#d2c3a2'));a.add_patch(Polygon(gear_outline(100,m,True),fc='white',ec=BLUE,lw=.4));a.add_patch(Polygon(gear_outline(20,m),fc='#627784',ec=BLUE,lw=.4))
    pts=np.array(gear_outline(40,m,phase=math.pi/40))
    for j in range(4):
        x,y=xy(48,j*math.pi/2);a.add_patch(Polygon(pts+[x,y],fc='#d2c3a2',ec=BLUE,lw=.4));a.add_patch(Circle((x,y),11,fc='white',ec=BLUE))
    a.set(xlim=(-94,94),ylim=(-94,94),aspect='equal',title='Планетарный ряд 20 / 40 / 100, i = 6');a.set_xlabel('мм')
    fig.tight_layout();fig.savefig(OUT/'sections.png',dpi=160);plt.close(fig)

def plots(r):
    x=r['torque_speed_30V'];fig,axes=plt.subplots(1,2,figsize=(11.2,3.8));a=axes[0]
    a.plot([q['speed_kmh'] for q in x],[q['road_torque_Nm'] for q in x],color=BLUE,label='Сопротивление, ровно, 120 кг',lw=2)
    for I,col in [(9,'#508ca4'),(10.5,ORANGE)]:a.plot([q['speed_kmh'] for q in x],[q[f'max_wheel_T_I{I}_Nm'] for q in x],color=col,label=f'Тяга: {I:g} А RMS, ≤15 А пик')
    a.set(xlim=(0,30),ylim=(0,10),xlabel='Скорость, км/ч',ylabel='Момент на колесе, Н·м',title='30 В на шине, расчётный предел тяги');a.legend(fontsize=8)
    a=axes[1];th=r['thermal']['flat20_30V']
    for key,label,col in [('winding_C','Обмотка',ORANGE),('stator_C','Статор',BLUE),('rotor_C','Ротор','#508ca4')]:a.plot(np.array(th['times_s'])/60,th[key],label=label,color=col)
    a.axhline(55,color='#888',ls=':',label='55°C: принятый предел PETG');a.set(xlabel='Время, мин',ylabel='Температура, °C',title='20 км/ч, 30 В; условный принудительный обдув');a.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'traction_thermal.png',dpi=160);plt.close(fig)
    f=json.loads(Path(r['field_source']).read_text());ref=json.loads((ROOT/'C108_L40_G025_R29_CU3/femm_refine/refined.json').read_text());m=r['model'];freq=np.geomspace(.5,16,200);L=m['L_leak_total_2d_h']+m['M_effective_h']/(1+1j*2*np.pi*freq*m['tau_rotor_s'])
    fig,axes=plt.subplots(1,2,figsize=(11.2,3.6))
    for ax,key,vals,label in [(axes[0],'L_real_h',L.real,'Действительная часть L, мГн'),(axes[1],'L_imag_h',L.imag,'Мнимая часть L, мГн')]:
        ax.semilogx(freq,vals*1000,color=BLUE,label='Подбор обратной Γ-схемы');ax.scatter([x['frequency_hz'] for x in f['rows']],[x[key]*1000 for x in f['rows']],color=ORANGE,label='FEMM, основная сетка');ax.scatter([x['frequency_hz'] for x in ref['rows']],[x[key]*1000 for x in ref['rows']],marker='x',color='#111',label='FEMM, мелкая сетка');ax.set(xlabel='Частота скольжения, Гц',ylabel=label);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/'field_fit.png',dpi=160);plt.close(fig)

def analyse(r):
    summaries={t:bom(t,r['winding']) for t in ['P2_HUB','P2_HUB_SMALL']};meshchecks=[mesh(m) for m in [1.6,1.25]]
    lin=json.loads(Path(r['field_source']).read_text());fine=json.loads((ROOT/'C108_L40_G025_R29_CU3/femm_refine/refined.json').read_text());ref=[]
    for b in fine['rows']:
        a=next(x for x in lin['rows'] if x['frequency_hz']==b['frequency_hz']);ref.append({'Hz':b['frequency_hz'],'L_complex_relative_change':abs(complex(b['L_real_h'],b['L_imag_h'])/complex(a['L_real_h'],a['L_imag_h'])-1),'torque_relative_change':abs(b['torque_mst_Nm']/a['torque_mst_Nm']-1)})
    q=r['points']['30']['flat20']['9'];Ts=r['thermal']['flat20_30V']['steady_C']['stator'];Ta=35;P=q['transmission_loss_W'];gear={}
    for Rga in [2,4]:gear[str(Rga)]=Ta+(P+(Ts-Ta)/6)/(1/Rga+1/6)
    smallg=json.loads(json.dumps(r['geometry']));smallg['design_screens']['stator_to_ambient_forced_K_W_assumed']=1.5
    smallth=thermal(smallg,r['winding'],q)
    I=math.pi*(.017**4-.006**4)/64;F=120*9.81*2.5;span=.0975;left=.042;right=span-left;M=F*left*right/span;sigma=M*.0085/I/1e6;tau=12*.0085/(2*I)/1e6
    result={'status':'RESEARCH_REVIEW_NOT_RELEASED','donor':'Ninebot Max Pro (user identification); interior unmeasured','mass':summaries,'mesh':meshchecks,'mesh_refinement':ref,
      'gear_load_screens':{str(m):load_screen(module=m) for m in [1.6,1.25]},'gear_thermal':{'ambient_C':Ta,'motor_stator_C':Ts,'gear_loss_W':P,'Rmotor_gear_K_W_assumed':6,'Tgear_for_Rgear_ambient_C':gear,'rated':False},
      'compact_motor_thermal_if_Rsa1p5':smallth['steady_C'],
      'axle_screen':{'radial_load_N_2p5g_full_mass':F,'support_span_mm_assumed':span*1000,'bending_moment_Nm':M,'bending_MPa':sigma,'torsion_MPa':tau,'von_mises_MPa':math.sqrt(sigma*sigma+3*tau*tau),'flats_threads_and_real_dropouts_not_included':True},
      'field_torque_identity_max_relative_error':max(abs(x['torque_mst_Nm']/x['torque_from_cage_Nm']-1) for x in lin['rows']),
      'continuous_motor_rating_measured':False,'drive_hardware_modified':False,'bench_peak_trip_A_unchanged':1.35}
    hot=ROOT/'C108_L40_G025_R29_CU3/femm_launch_hot/nonlinear.json'
    if hot.exists():
        n=json.loads(hot.read_text())['rows'][0];result['nonlinear_hot_launch']=n
        Tw=(n['torque_mst_Nm']-.008)*6*.94
        result['nonlinear_hot_launch_wheel_torque_Nm']=Tw
        result['nonlinear_hot_launch_acceleration_m_s2']=(Tw/(.254/2)-road(r['geometry'],0)['force_N'])/122.5
    (OUT/'review_data.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

class Report:
    def __init__(self):
        for n,f in [('Arial','arial.ttf'),('Arial-Bold','arialbd.ttf')]:pdfmetrics.registerFont(TTFont(n,'C:/Windows/Fonts/'+f))
        self.c=canvas.Canvas(str(OUT/'ACIM_P2_REVIEW_RU.pdf'),pagesize=(842,595));self.c.setTitle('Асинхронное мотор-колесо P2: расчёт и компоновка');self.page=0
    def new(self,title):
        if self.page:self.c.showPage()
        self.page+=1;c=self.c;c.setFillColor(HexColor(BLUE));c.rect(0,550,842,45,fill=1,stroke=0);c.setFillColor(white);c.setFont('Arial-Bold',17);c.drawString(30,565,title)
        c.setFillColor(HexColor(GREY));c.setFont('Arial',8);c.drawString(30,18,'P2 • 17.11.2026 • Расчётный проект. Посадка Max Pro и ресурс не подтверждены.');c.drawRightString(812,18,f'{self.page}')
    def p(self,text,x,y,w=782,size=11,color=BLUE):
        p=Paragraph(text,ParagraphStyle('p',fontName='Arial',fontSize=size,leading=size*1.35,textColor=HexColor(color)));_,h=p.wrap(w,1000);p.drawOn(self.c,x,y-h);return y-h-8
    def table(self,rows,x,y,widths,size=10):
        sty=ParagraphStyle('t',fontName='Arial',fontSize=size,leading=size*1.25,textColor=HexColor(BLUE))
        cells=[[Paragraph(str(c),sty) for c in row] for row in rows];t=Table(cells,colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),HexColor('#e4eef3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,HexColor(BLUE)),('LINEBELOW',(0,1),(-1,-1),.3,HexColor('#ced9df')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));_,h=t.wrap(sum(widths),1000);t.drawOn(self.c,x,y-h);return y-h-10
    def im(self,path,x,y,w,h):self.c.drawImage(ImageReader(str(path)),x,y,width=w,height=h,preserveAspectRatio=True,anchor='c')
    def end(self):self.c.save()

def report(r,a):
    b=Report();q30=r['points']['30']['flat20']['9'];q36=r['points']['36']['flat20']['9'];w=r['winding'];big=a['mass']['P2_HUB'];small=a['mass']['P2_HUB_SMALL']
    b.new('Облегчённый P2: мотор и редуктор внутри колеса')
    y=b.p('Результат: вместо прямого привода на оборотах колеса - асинхронный мотор Ø108 × 40 мм и планетарный редуктор 6:1. Прежние 100 Вт были сопротивлением движению при 15 км/ч, а не измеренной номинальной мощностью двигателя.',30,530)
    y=b.table([['Показатель','P1, прямой привод','P2, основной','P2, меньший диаметр'],['Масса без шины и мелкого крепежа','9,68 кг',f'{big["comparable_no_tyre_kg"]:.2f} кг',f'{small["comparable_no_tyre_kg"]:.2f} кг'],['Из них новый узел без условного обода','- ',f'{big["insert_kg"]:.2f} кг',f'{small["insert_kg"]:.2f} кг'],['Наружный Ø кольца редуктора','- ','180 мм','145 мм'],['Условный металлический корпус Ø','- ','192 мм','157 мм'],['Ширина узла с опорами, без обдува','- ',f'{big["main_axial_width_mm"]:.1f} мм',f'{small["main_axial_width_mm"]:.1f} мм'],['Расчётная дорога при 120 кг','15 км/ч, 100 Вт','20 км/ч, 161 Вт на колесе','Та же электромагнитная часть']],30,y,[264,166,176,176],10)
    y=b.p('Масса P2 получена из CAD-объёмов и плотностей: включены условный обод с крышками и 70 г вентиляторов. Реальная шина, проводка, пропитка, недостающий крепёж и окончательный воздуховод добавятся. Подшипники оценены сплошными кольцами, поэтому их масса завышена.',30,y,782,10)
    b.p('Главное ограничение: P2 ещё не является заменой, которая заведомо встаёт в Ninebot. Модель Max Pro установлена со слов владельца; внутренних размеров корпуса и расстояния между перьями пока нет. Производственные посадки, удержание оси и ресурс пластиковых шестерён требуют следующей проверки.',30,y,782,11,ORANGE)

    b.new('CAD: два диаметра, общий двигатель и обмотка')
    b.im(ROOT/'P2_HUB/CAD/P2_REVIEW.PNG',30,252,382,280);b.im(ROOT/'P2_HUB_SMALL/CAD/P2_REVIEW.PNG',430,252,382,280)
    y=b.table([['Компоновка','Кольцо Ø / условный обод Ø','Осевые границы, мм','С боковым охлаждением'],['Основная, модуль 1,6','180 / 192 мм','-47 … +63,5; 110,5 мм','140,5 мм по оси'],['Радиально компактная, модуль 1,25','145 / 157 мм','-47 … +71,5; 118,5 мм','148,5 мм по оси']],30,245,[208,204,190,180],10)
    y=b.p('Меньший Ø требует вынести передний игольчатый подшипник за плоскость сателлитов: поэтому узел становится шире. Общая ось в CAD длиной 155 мм - условная заготовка без штатных лысок и резьб. Воздуховод Ø160 мм и два пакета вентиляторов 50 × 50 × 20 мм расположены сбоку от колеса.',30,y,782,10)
    b.p('Обе сборки: по 59 компонентов, 113 твёрдых тел; ошибок ядра 0, объёмных пересечений 0, скрытые детали включены в проверку. Совпадающие контактные поверхности допустимы. Это проверка номинальной геометрии, а не допусков, сборочности или прочности.',30,y,782,10)

    b.new('Магнитопровод, клетка и обмотка под 30-42 В')
    b.im(OUT/'sections.png',30,212,782,315)
    y=b.table([['Узел','Значение','Статус изготовления'],['Статор / ротор','24 паза, 4 полюса; 29 стержней; зазор 0,25 мм','Пакеты электростали 0,35 мм под заказ; марка ещё не выбрана'],['Обмотка','7 витков на катушку, 4 × Ø0,90 мм; 24 катушки','8 катушек последовательно на фазу, 56 витков, звезда'],['Медь / сопротивление',f'{w["order_wire_m_15pct"]:.1f} м с запасом 15%; фаза {w["Rs20_ohm"]:.4f} Ом при 20°C','Заполнение медью 39,15%; эмаль и пазовая изоляция требуют пробы'],['Клетка ротора','Стержни 2,5 × 6,4 мм; кольца 7,6 × 6 мм','Медь, пайка/соединение на заказ; проверить контактное сопротивление']],30,208,[145,330,307],9)
    b.p('Лобовые части по 12 мм с каждой стороны - цель для формовки, ещё не доказанная намоткой. Протяжённость магнитной цепи 40 мм не кратна 0,35 мм: число листов, покрытие и сжатие назначаются по реальному пакету, а не простым округлением.',30,y,782,9,ORANGE)

    b.new('Что сможет самокат: тяга, токи и ограничения')
    b.im(OUT/'traction_thermal.png',30,240,782,285)
    y=b.table([['Режим','Ток фазы RMS / пик с пульсацией','Потери мотора','Питание с инвертором и 10 Вт вспом.'],['20 км/ч, 30 В',f'{q30["I_rms_A"]:.2f} / {q30["I_peak_with_ripple_A"]:.2f} А',f'{q30["motor_loss_W"]:.1f} Вт',f'{q30["battery_W_with_10W_aux"]:.0f} Вт; {q30["battery_A"]:.2f} А батареи'],['20 км/ч, 36 В',f'{q36["I_rms_A"]:.2f} / {q36["I_peak_with_ripple_A"]:.2f} А',f'{q36["motor_loss_W"]:.1f} Вт',f'{q36["battery_W_with_10W_aux"]:.0f} Вт; {q36["battery_A"]:.2f} А батареи'],['Целевой пуск 0,4 м/с²','10,08 / 14,75 А, линейная модель','Нелинейность уменьшает момент','При горячей клетке проверенная точка даёт около 0,35 м/с²']],30,232,[150,249,120,263],9)
    y=b.p(f'Линейный расчёт разгона 0-20 км/ч: {r["time_to20kmh_s_electrical_screen"]:.1f} с; с условным запасом 10% по моменту: {r["time_to20kmh_s_with10pct_torque_allowance"]:.1f} с при 30 В. Учтены 120 кг и 2,5 кг эквивалентной инерции. Это расчёт, не дорожный тест: динамика регулятора и намагничивания не моделировались. Crr = 0,015; CdA = 0,6 м².',30,y,782,9)
    b.p('25 км/ч проходит лишь при 42 В, но не во всём разряде 10S. Подъём 5% при 10 км/ч не проходит лимит 15 А пик. Поэтому обещание 350 Вт непрерывно или штатной тяги Max Pro этими расчётами не подтверждается.',30,y,782,10,ORANGE)

    b.new('Электромагнитный расчёт и независимые проверки')
    b.im(OUT/'field_fit.png',30,275,782,250)
    y=b.p('FEMM: полная окружность 360°, 55 089 узлов / 109 816 элементов, шесть частот скольжения 0,5-16 Гц. Клетка с поправкой на сопротивление колец и выступание стержней; 2D-модель не учитывает трёхмерные поля концов, перекос пазов и дефекты соединений.',30,263,782,10)
    y=b.p(f'Обратная Γ-схема, опорные 10 витков: M = {r["model"]["M_effective_h"]*1000:.4f} мГн, суммарная 2D-индуктивность рассеяния {r["model"]["L_leak_total_2d_h"]*1000:.4f} мГн; R′ротора при 20°C {r["model"]["Rr_effective_20_ohm"]:.5f} Ом; τ = {r["model"]["tau_rotor_s"]:.5f} с. Комплексная ошибка подбора {r["model"]["relative_complex_fit_rms"]*100:.3f}%. Это качество аппроксимации, не точность реального двигателя.',30,y,782,10)
    ref=a['mesh_refinement'];y=b.p('Сгущённая сетка: 83 586 узлов / 166 810 элементов. Изменение комплексной L при 1 и 4 Гц: '+', '.join(f'{x["L_complex_relative_change"]*100:.3f}%' for x in ref)+'; изменение момента: '+', '.join(f'{x["torque_relative_change"]*100:.3f}%' for x in ref)+'. Связь момента с потерями клетки расходится до 7,2% на 16 Гц; это ограничивает уверенность на больших скольжениях.',30,y,782,10)
    n=a.get('nonlinear_hot_launch')
    if n:y=b.p(f'Нелинейная проверка пуска: медь клетки 85°C, M-19 как справочная сталь, 3,026 Гц и 9,983 А пикового тока при опорных 10 витках. Момент {n["torque_mst_Nm"]:.3f} Н·м, Bg {n["Bg_fund_peak_t"]:.3f} Т, максимальная выборка стали {n["steel_sample_max_T"]:.3f} Т. Требуется уточнить реальную марку стали и подтвердить момент на стенде.',30,y,782,10)
    b.p('Энергетический баланс схемы, распределение фаз, кинематика зубьев и оба CAD проверяются повторяемым test_p2.py. Ресурс, шум, динамический дисбаланс, токовые выбросы и точность регулирования остаются экспериментальными задачами.',30,y,782,9)

    b.new('Тепло и печатный пластик: рабочие условия')
    th=r['thermal']['flat20_30V']['steady_C'];gth=a['gear_thermal']
    y=b.table([['Проверка','Расчёт / допущение','Практическое значение'],['Основной мотор, 20 км/ч, 30 В, воздух 35°C',f'Обмотка {th["winding"]:.1f}°C; статор {th["stator"]:.1f}°C; ротор {th["rotor"]:.1f}°C','R статор-воздух = 1,1 К/Вт, принудительный обдув; это целевой параметр'],['Компактный радиатор, R = 1,5 К/Вт',f'Обмотка {a["compact_motor_thermal_if_Rsa1p5"]["winding"]:.1f}°C','Меньший радиатор требует отдельной тепловой проверки'],['Редуктор: 10,28 Вт потерь, R мотор-редуктор = 6 К/Вт',f'При R к воздуху 2 К/Вт: {gth["Tgear_for_Rgear_ambient_C"]["2"]:.1f}°C; при 4 К/Вт: {gth["Tgear_for_Rgear_ambient_C"]["4"]:.1f}°C','PETG под нагрузкой не квалифицирован; температура зависит от вентиляции и контактов'],['Печатный материал','PETG: холодная оснастка, воздуховод, примерка','Шестерни: покупной POM либо квалифицированный печатный износостойкий полимер'],['Пределы домашнего принтера','Bambu A1: открытая камера; стандартные PA/PC не обещаны','Для PA нужны подтверждённый режим, сушка, образцы прочности и износа']],30,528,[270,242,270],10)
    y=b.p('Основной теплоотвод: фиксированная алюминиевая пластина с 48 рёбрами, алюминиевая рубашка статора, воздух снаружи через вентилируемую крышку. Предварительный расход 3 л/с суммарно при сопротивлении около 60 Па. Для двух BFB0512VHD-F00 по заводской P-Q кривой запас по этому режиму есть; это кандидат по аэродинамике, а не подтверждение наличия в продаже.',30,y,782,10)
    y=b.p('Габариты вентиляторов в CAD условные. BFB - центробежная воздуходувка с боковым выходом; показанные круглые отверстия не являются готовым посадочным чертежом. Воздуховод и крепление нужно завершить по реально купленному вентилятору. При 50 Вт тепла и 3 л/с нагрев потока порядка 14°C; внутреннее сопротивление теплоотдачи существенно.',30,y,782,10)
    b.p('Для полностью закрытого колеса без внешнего обдува этот тепловой результат неприменим. Износостойкий iglidur i150 печатается при умеренных температурах, но заявленный длительный предел 65°C оставляет мало запаса в редукторе. Назначать его для поездок без температурного и ресурсного теста нельзя.',30,y,782,10,ORANGE)

    b.new('Планетарный ряд, силовые детали и закупка')
    smallload=a['gear_load_screens']['1.25'];load=a['gear_load_screens']['1.6'];ax=a['axle_screen']
    y=b.table([['Деталь / функция','Материал и получение','Что уже посчитано / что ещё проверить'],['Магнитопроводы, клетка','Заказные пакеты электростали; медная клетка','Активная масса 2,64 кг вместе с обмоткой; фактические потери стали ещё неизвестны'],['Солнце / 4 сателлита / внутренний венец','Стальное солнце; полимерные сателлиты и венец','20 / 40 / 100, i=6; зубья проверены на 91 положении для обоих модулей'],['Корень зуба: грубая оценка Льюиса при 12 Н·м',f'Модуль 1,6: {load["planet_root_MPa_Lewis_screen"]:.2f} МПа; 1,25: {smallload["planet_root_MPa_Lewis_screen"]:.2f} МПа','Учтены 1,5 на неравномерность и 1,2 на динамику. 10 МПа - допущение, не предел выносливости'],['Водила, оси сателлитов и тяги','Водила Al, пальцы Ø8 сталь, металлические распорки','Пальцы 13,7-17,5 МПа изгиба. Водила требуют расчёта пластин и крепежа'],['Ось Ø17 с каналом Ø6','Закалённая / шлифованная дорожка под NK17/16',f'Грубый изгиб+кручение при 2,5g: {ax["von_mises_MPa"]:.0f} МПа; без лысок и резьб. Реальная вилка не проверена'],['Подшипники','2×6803; 8×608; 1×6003; 1×NK17/16','Покупные. Игольчатому подшипнику нужна полноценная дорожка на оси'],['Печатать на A1 сейчас','Формер катушек, калибр Ø22/26, холодная примерка шестерён','STL приложены. Рабочая посадка подшипников зависит от усадки и кондиционирования']],30,528,[248,242,292],9)
    b.p('В CAD не завершены: сопряжение со штатным ободом, лыски и резьбы оси, фиксация оси от реактивного момента, часть крепежа, выбор посадок, производственные галтели зубьев и защита от воды. Заказывать металл по этим номинальным файлам пока рано. DXF служат для обсуждения с изготовителем, а не готовым заказом резки.',30,y,782,10,ORANGE)

    b.new('Инвертор, параметры и следующий этап')
    y=b.p('Расчётная база: готовая плата DRV8302 SKU71451, NUCLEO-G431RB. У продавца указаны 5,5-45 В платы, выходной ток 15 А и диапазон измерения ±27 А. Соглашение RMS/пик у 15 А не установлено; в основном расчёте принят более строгий предел 15 А пикового фазного тока с оценкой пульсаций.',30,528,782,11)
    y=b.p('10S Li-ion: 30-42 В. У полностью заряженной батареи до предела платы 45 В остаётся только 3 В. До эксплуатации нужны проверенные перенапряжение/рекуперация и способность шины поглощать энергию. Даташит микросхемы на 60 В не повышает предельное напряжение готовой платы. Термическая квалификация MOSFET и калибровка датчиков тока обязательны для принятых токов.',30,y,782,10)
    y=b.p('Режим расчёта: PWM 16 кГц; dead time 0,5 мкс; горячий Rds(on) 20 мОм; шунт 5 мОм - допущения. Напряжение ограничено 0,9·Vdc/√3 минус 0,75 В; малый остаточный запас в таблицах уже после этого резерва. Реальная задержка, сопротивления и пульсации должны быть измерены. Существующий стенд и его отключение 1,35 А пик не менялись.',30,y,782,10)
    y=b.p('<b>Быстро менять наружный диаметр:</b> python rebuild.py --ring-od 145 --build-cad или --ring-od 180. Кольцо, межосевые расстояния, водила и условный корпус перестраиваются вместе. Электромагнитный мотор остаётся Ø108 × 40; изменение его диаметра в inputs.json требует нового FEMM и пересмотра обмотки, поэтому результаты нельзя просто масштабировать.',30,y,782,10)
    y=b.p('<b>Следующий определяющий шаг:</b> снять крышку Max Pro и получить внутренний Ø корпуса, полезную глубину, расстояние между перьями, расположение подшипников, диаметр и лыски оси. По ним выбрать компоновку или признать, что без новых крышек/корпуса текущий P2 не помещается. Пока производственный выпуск остановлен именно на этих неопределённостях.',30,y,782,10,ORANGE)
    b.p('<b>Первичные источники:</b> Segway Commercial: b2b.segway.com/max-pro и blog/segway-discovery-max-series-shared-scooters (10-дюймовые колёса; внутренних размеров нет). EcBuying: drv8302-high-power-motor-drive-module-st-foc-vector-control-bldc-product. TI: ti.com/product/DRV8302. FEMM: femm.info/doku/doku.php?id=InductionMotorExample. Delta: delta-fan.com/Download/Spec/BFB0512VHD-F00.pdf. Bambu Lab: Quick Start Guide for A1. igus: igus.com/product/iglidur_I150_PF. Полные адреса сохранены в SOURCES.txt.',30,y,782,8)
    b.end()

def run():
    r=json.loads((ROOT/'P2_HUB/results.json').read_text());a=analyse(r);drawings(r);plots(r);report(r,a)
    print(json.dumps({'masses':{k:{kk:vv for kk,vv in v.items() if kk!='rows'} for k,v in a['mass'].items()},'mesh':a['mesh'],'mesh_refinement':a['mesh_refinement'],'hot':a.get('nonlinear_hot_launch')}),flush=True)

if __name__=='__main__':run()
