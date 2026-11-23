"""Nominal engineering sheets and exact-arc lamination DXF; NOT released.

No donor interface, cutting compensation or fits have been inferred.
DXF uses mm, closed LWPOLYLINE with bulges on open-slot bore/surface arcs.
"""
import json,math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle,Polygon,Rectangle
from geometry import geometry,package,stator_slot,rotor_slot,bar_profile

def dxf(path,circles,outline=None):
    rows=['0','SECTION','2','HEADER','9','$INSUNITS','70','4','9','$MEASUREMENT','70','1','0','ENDSEC','0','SECTION','2','ENTITIES']
    for r in circles:rows += ['0','CIRCLE','8','NOMINAL_CUT_NOT_RELEASED','10','0','20','0','30','0','40',f'{r:.10f}']
    if outline:
        rows+=['0','LWPOLYLINE','8','NOMINAL_CUT_NOT_RELEASED','90',str(len(outline)),'70','1']
        for x,y,b in outline:rows+=['10',f'{x:.10f}','20',f'{y:.10f}','42',f'{b:.12f}']
    rows += ['0','ENDSEC','0','EOF'];Path(path).write_text('\n'.join(rows)+'\n',encoding='ascii')

def outline(g,kind):
    n=48 if kind=='stator' else 50;rs=g['stator_outer_radius_mm'];r=rs if kind=='stator' else rs+g['air_gap_radial_mm']
    w=g['slot_mouth_width_mm'] if kind=='stator' else g['rotor_slot_opening_mm'];da=math.asin(w/(2*r))
    bulge=math.tan((2*math.pi/n-2*da)/4);out=[]
    for j in range(n):
        points=stator_slot(g,j) if kind=='stator' else rotor_slot(g,j)
        out += [(x,y,bulge if i==len(points)-1 else 0) for i,(x,y) in enumerate(points)]
    return out

def section(ax,g,colors=True):
    rs=g['stator_outer_radius_mm'];rb=g['stator_bore_radius_mm'];rg=rs+g['air_gap_radial_mm'];ro=g['rotor_outer_radius_mm']
    ax.add_patch(Circle((0,0),ro,facecolor='#767e87',edgecolor='#1d2933',lw=.8))
    ax.add_patch(Circle((0,0),rg,facecolor='white',edgecolor='#1d2933',lw=.4))
    ax.add_patch(Circle((0,0),rs,facecolor='#a4adb5',edgecolor='#1d2933',lw=.4))
    ax.add_patch(Circle((0,0),rb,facecolor='white',edgecolor='#1d2933',lw=.8))
    for j in range(48):ax.add_patch(Polygon(stator_slot(g,j),facecolor='white',edgecolor='#344450',lw=.35))
    for j in range(50):
        ax.add_patch(Polygon(rotor_slot(g,j),facecolor='white',edgecolor='#344450',lw=.3))
        ax.add_patch(Polygon(bar_profile(g,j),facecolor='#b76c29' if colors else 'white',edgecolor='#344450',lw=.3))
    ax.axhline(0,color='#8393a0',lw=.5,ls='-.');ax.axvline(0,color='#8393a0',lw=.5,ls='-.')
    ax.set(xlim=(-ro*1.08,ro*1.08),ylim=(-ro*1.08,ro*1.08));ax.set_aspect('equal');ax.axis('off')

def sheet(title,number,tag):
    fig=plt.figure(figsize=(16.54,11.69),facecolor='white')
    fig.text(.045,.945,title,fontsize=20,weight='bold',color='#172f42')
    fig.text(.045,.908,'ПРОЕКТНАЯ ГЕОМЕТРИЯ P1 · Размеры в мм · Посадки и допуски не назначены',fontsize=11,color='#536677')
    fig.text(.045,.035,'НЕ ДЛЯ ИЗГОТОВЛЕНИЯ · Габариты Ninebot не измерены · Клетка и магнитопровод металлические',fontsize=10,color='#9b351d')
    fig.text(.955,.035,f'{tag}   |   Лист {number}',ha='right',fontsize=10,color='#536677')
    return fig

def drawings(data,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);p=data['parameters'];g=data['geometry'];pk=data['package']
    tag=f'D{p["stator_diameter_mm"]:g}_L{g["active_length_mm"]:g}'
    dxf(out/'STATOR_LAMINATION_NOMINAL.dxf',[g['stator_bore_radius_mm']],outline(g,'stator'))
    dxf(out/'ROTOR_LAMINATION_NOMINAL.dxf',[g['rotor_outer_radius_mm']],outline(g,'rotor'))
    dxf(out/'CAGE_ENDRING_NOMINAL.dxf',[pk['endring_inner_radius_mm'],pk['endring_outer_radius_mm']])
    dxf(out/'CAGE_BAR_NOMINAL.dxf',[],[(x,y,0) for x,y in bar_profile(g,0)])
    if data.get('selected') is None:return None
    w=data['selected']['winding'];q=data['selected']['points']['flat15']['36.0']
    pdf=out/'ACIM_HUB_P1_Engineering.pdf'
    with PdfPages(pdf) as pp:
        fig=sheet('Асинхронное мотор-колесо — компоновка',1,tag)
        ax=fig.add_axes([.045,.18,.51,.66]);section(ax,g)
        ax.text(0,-g['rotor_outer_radius_mm']*1.13,'Поперечное сечение активной части',ha='center',fontsize=12)
        rows=[['Параметр','Проектное значение'],['Статор / пакет',f'Ø{2*g["stator_outer_radius_mm"]:g} × {g["active_length_mm"]:g}'],
          ['Ротор, наружный Ø',f'{pk["rotor_iron_OD_mm"]:.3f}'],['Корпус, наружный Ø',f'{pk["housing_OD_mm"]:.3f}'],
          ['Корпус / с кожухами по оси',f'{pk["total_housing_width_mm"]:g} / {pk["total_housing_width_mm"]+5:g}'],['Радиальный зазор',f'{g["air_gap_radial_mm"]:g}'],
          ['Пазы / полюса / стержни','48 / 8 / 50'],['Лист / номинальное число',f'0.5 / {g["lamination_count_nominal"]}'],
          ['Вал / подшипники','Ø20 / 2 × 6204 (20×47×14)'],['Питание','10S Li-ion: 30–42 В'],
          ['Обмотка',f'{w["turns_per_coil"]} витков × {w["wire_strands_in_hand"]} жилы Ø{w["wire_bare_diameter_mm"]:g}'],
          ['Соединение / шаг','Y / 5 пазов'],['Витков на фазу / kw',f'{w["turns_series_per_phase"]} / {w["winding_factor"]:.4f}']]
        axt=fig.add_axes([.59,.31,.36,.52]);axt.axis('off');tb=axt.table(cellText=rows[1:],colLabels=rows[0],loc='upper center',cellLoc='left',colWidths=[.56,.44]);tb.auto_set_font_size(False);tb.set_fontsize(11);tb.scale(1,1.9)
        fig.text(.59,.21,'Напечатать: холодные кожухи и оснастку.\nЗаказать: пакеты стали, клетку, вал, несущие детали.\nСхема катушек — winding_48_coils.csv.',fontsize=12,linespacing=1.7)
        pp.savefig(fig);fig.savefig(out/'01_layout.png',dpi=110);plt.close(fig)
        fig=sheet('Магнитопровод, клетка и паз',2,tag)
        a=fig.add_axes([.045,.39,.43,.46]);section(a,g,False)
        a.text(0,-g['rotor_outer_radius_mm']*1.14,f'Статор Ø{2*g["stator_outer_radius_mm"]:g}; отверстие Ø{2*g["stator_bore_radius_mm"]:.3f}',ha='center',fontsize=11)
        a=fig.add_axes([.55,.4,.39,.44]);pts=stator_slot(g,0);a.add_patch(Polygon(pts,fc='#e7eef4',ec='#253c4f'))
        a.set_aspect('equal');a.axis('off');a.set_xlim(g['slot_bottom_radius_mm']-3,g['stator_outer_radius_mm']+2);a.set_ylim(-7,7)
        for x,width,label in [(g['slot_bottom_radius_mm'],g['slot_bottom_width_mm'],'Дно'),(g['slot_shoulder_radius_mm'],g['slot_shoulder_width_mm'],'Плечо'),(g['stator_outer_radius_mm'],g['slot_mouth_width_mm'],'Шлиц')]:
            a.annotate('',xy=(x,-width/2),xytext=(x,width/2),arrowprops={'arrowstyle':'<->','color':'#b24f21'})
            a.text(x,5.2,f'{label}\n{width:.3f}',ha='center',fontsize=10)
        a.text((g['slot_bottom_radius_mm']+g['stator_outer_radius_mm'])/2,-5.8,'Один паз, увеличено; осевая длина = пакет',ha='center',fontsize=11)
        text=(f'СТАТОР: 48 пазов с шагом 7.5°. Радиусы дна / плеча / основания шлица: '
              f'{g["slot_bottom_radius_mm"]:.3f} / {g["slot_shoulder_radius_mm"]:.3f} / {g["slot_mouth_base_radius_mm"]:.3f}.\n'
              f'РОТОР: 50 пазов с шагом 7.2°, сдвиг относительно статора 2.232°. Стержень: '
              f'{g["rotor_bar_width_mm"]:.3f} × {g["rotor_bar_depth_mm"]:.3f}; шлиц 1.000.\n'
              f'КЛЕТКА: 50 медных стержней длиной {g["active_length_mm"]:g} + 2 торцевых кольца; '
              f'кольцо Ø{2*pk["endring_outer_radius_mm"]:.3f} / Ø{2*pk["endring_inner_radius_mm"]:.3f} × {g["ring_axial_mm"]:.3f}.\n'
              f'ПАЗОВАЯ ЧАСТЬ: площадь {g["slot_copper_gross_mm2"]:.3f} мм²; медь {100*w["bare_slot_fill"]:.1f}% без эмали и изоляции.\n'
              'DXF содержит замкнутые контуры с точными дугами. Компенсация реза не задана.\n'
              'Сборку клетки и электрические контакты заказать изготовителю. Радиусы, заусенцы, покрытие и пакетирование согласовать.')
        fig.text(.065,.26,text,fontsize=12,linespacing=1.9,va='top')
        pp.savefig(fig);fig.savefig(out/'02_laminations.png',dpi=110);plt.close(fig)
        fig=sheet('Продольная компоновка и границы деталей',3,tag)
        a=fig.add_axes([.06,.28,.88,.56]);h=g['active_length_mm']/2;m=p['mechanical'];z=pk['cover_inner_z_mm'];ro=g['rotor_outer_radius_mm'];rs=g['stator_outer_radius_mm'];rb=g['stator_bore_radius_mm'];r0=rs+g['air_gap_radial_mm']
        def box(z0,z1,r0,r1,color,label=None):
            for sign in [-1,1]:a.add_patch(Rectangle((z0,sign*r0 if sign>0 else -r1),z1-z0,r1-r0,fc=color,ec='#324659',lw=.6))
            if label:a.text((z0+z1)/2,(r0+r1)/2,label,rotation=90,ha='center',va='center',fontsize=8)
        box(-m['shaft_total_length_mm']/2,m['shaft_total_length_mm']/2,0,10,'#8694a0')
        box(-h,h,10,rb,'#ccd9e2','Носитель');box(-h,h,rb,rs,'#9ca7af','Статор');box(-h,h,r0,ro,'#67737e','Ротор')
        box(-z,z,ro,pk['outer_housing_radius_mm'],'#b2bec8')
        for sign in [-1,1]:
            z0,z1=sorted((sign*h,sign*(h+m['endwinding_overhang_mm_assumed'])));box(z0,z1,g['slot_bottom_radius_mm']-.5,pk['endturn_envelope_outer_radius_mm'],'#d4a078')
            z0,z1=sorted((sign*h,sign*(h+g['ring_axial_mm'])));box(z0,z1,pk['endring_inner_radius_mm'],pk['endring_outer_radius_mm'],'#bc6f2c')
            z0,z1=sorted((sign*z,sign*pk['cover_outer_z_mm']));box(z0,z1,23.5,pk['outer_housing_radius_mm'],'#c9d5df')
            z0,z1=sorted((sign*(pk['cover_outer_z_mm']-14),sign*pk['cover_outer_z_mm']));box(z0,z1,10,23.5,'#475563');box(z0,z1,23.5,27.5,'#c9d5df')
        a.axhline(0,lw=.5,ls='-.',color='#536677');a.set_aspect('equal');a.set(xlabel='Ось z, мм',ylabel='Радиус, мм',xlim=(-80,80),ylim=(-pk['outer_housing_radius_mm']-6,pk['outer_housing_radius_mm']+6));a.grid(alpha=.15)
        fig.text(.065,.20,f'Пакет: {2*h:g}; вылет лобовых частей принят {m["endwinding_overhang_mm_assumed"]:g} на сторону. '
          f'Зазор лобовой части до крышки: {m["cover_clearance_mm"]:g}.\n'
          f'Радиальный запас между лобовой частью и кольцом: {pk["endturn_ring_radial_clearance_mm"]:.3f}. '
          'Форму катушки проверить намоточным образцом.\n'
          'Удержание ротора, крепёж крышек, посадки, шпонки/шлицы, вывод проводов и интерфейс обода требуют деталировки.\n'
          'Модель оси сплошная и гладкая. Подшипники представлены покупными габаритами.',fontsize=12,linespacing=1.8,va='top')
        pp.savefig(fig);fig.savefig(out/'03_section.png',dpi=110);plt.close(fig)
        fig=sheet('Расчётные режимы и нагрев',4,tag)
        ax=fig.add_axes([.065,.53,.39,.32]);sweep=data['torque_speed'];ax.plot([r['speed_kmh'] for r in sweep],[r['max_torque_Nm_electrical_screen_30V'] for r in sweep],label='Предел по току/напряжению, 30 В')
        from engine import road
        speeds=np.linspace(0,30,121);ax.plot(speeds,[road(p,float(v))['torque_Nm'] for v in speeds],label='Дорога: ровно, 120 кг',color='#b76c29');ax.set(xlabel='Скорость, км/ч',ylabel='Момент, Н·м',ylim=(0,12));ax.legend(fontsize=9);ax.grid(alpha=.2)
        ax=fig.add_axes([.56,.53,.38,.32]);t=data['thermal_flat15_36V']
        for name,label in [('winding_C','Обмотка'),('stator_C','Статор'),('rotor_C','Ротор')]:ax.plot(np.array(t['times_s'])/60,t[name],label=label)
        ax.axhline(90,color='#a93c25',ls='--',label='Экран 90 °C');ax.set(xlabel='Время, мин',ylabel='Температура, °C',xlim=(0,120));ax.legend(fontsize=9);ax.grid(alpha=.2)
        txt=(f'РЕЖИМ 15 км/ч: {q["rpm"]:.1f} об/мин, {q["useful_torque_Nm"]:.3f} Н·м, {q["shaft_W"]:.1f} Вт на валу.\n'
          f'Фазный ток {q["I_phase_rms_A"]:.2f} A RMS / {q["I_phase_peak_A"]:.2f} A peak; частота {q["frequency_hz"]:.2f} Гц; скольжение {q["slip_hz"]:.2f} Гц.\n'
          f'Потери двигателя {q["motor_loss_W"]:.1f} Вт; КПД модели {100*q["motor_efficiency_model"]:.1f}%. '
          f'Потребление батареи при 36 В: {q["battery_W_bounds_assumed"][0]:.0f}–{q["battery_W_bounds_assumed"][1]:.0f} Вт.\n'
          f'R фазы при 20 °C = {w["Rphase20_ohm"]:.4f} Ом. Провода с запасом: {w["order_wire_m_with_15pct_reserve"]:.0f} м Ø{w["wire_bare_diameter_mm"]:g}.\n'
          'Кривая момента — электрический предел, не длительная мощность. Тепловые сопротивления не измерены.\n'
          'Плата 45 В: батарея 10S до 42 В оставляет только 3 В до заявленного предела. Рекуперация не разрешена этим расчётом.\n'
          'Оценки MOSFET, пульсаций и потерь стали условные. Управление ACIM требует собственной прошивки STM32 G431.')
        fig.text(.065,.36,txt,fontsize=12,linespacing=1.85,va='top')
        pp.savefig(fig);fig.savefig(out/'04_performance.png',dpi=110);plt.close(fig)
    return pdf
