from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from reportlab.graphics import renderSVG
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String, Circle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
DATA = Path(r"C:\mic_theory\experiments\parameter_adaptive_speed\confirmation_20261006")
REFERENCE = next(Path(r"C:\Study\Статьи и конференции\ET2025\Статья").glob("*.docx"))
DOCX = OUT / "Марикин_Оценка_токовых_ТЭБТРАНС_2026.docx"
FONT = "Times New Roman"
pdfmetrics.registerFont(TTFont(FONT, r"C:\Windows\Fonts\times.ttf"))

CASES = ["nominal", "parameter_drift", "composite", "slow_composite"]
METHODS = ["fixed_reference", "joint_only", "direct_feedback", "confidence_feedback"]
CODES = ["F", "A", "D", "C"]
CASE_LABELS = ["1", "2", "3", "4"]
FILLS = [colors.white, colors.HexColor("#cecece"), colors.HexColor("#888888"), colors.HexColor("#252525")]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_and_check():
    raw = json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    analysis = json.loads((DATA / "analysis.json").read_text(encoding="utf-8"))
    assert sha(DATA / "results.json") == analysis["provenance"]["raw_sha256"]
    assert len(raw["rows"]) == 320
    assert Counter((r["scenario"], r["method"]) for r in raw["rows"]) == Counter({(c, m): 20 for c in CASES for m in METHODS})
    assert sorted(set(r["seed"] for r in raw["rows"])) == list(range(97200, 97220))
    assert all(r["failure"] is None and r["completed_steps"] == 25000 for r in raw["rows"])
    assert all(not r["current_limit_violated"] for r in raw["rows"])
    assert all(sha(Path(p)) == h for p, h in raw["source_sha256"].items())
    keys = ["tracking_mae_rad_s", "peak_current_a", "copper_energy_j", "steady_torque_std_nm"]
    means = {}
    for case in CASES:
        for method in METHODS:
            rows = [r for r in raw["rows"] if r["scenario"] == case and r["method"] == method]
            means[case, method] = {k: float(np.mean([r[k] for r in rows])) for k in keys}
            saved = next(r for r in analysis["aggregates"] if r["scenario"] == case and r["method"] == method)
            assert all(abs(saved[k] - means[case, method][k]) < 1e-11 for k in keys)
    audit = dict(
        reference_path=str(REFERENCE), reference_sha256=sha(REFERENCE),
        raw_path=str(DATA / "results.json"), raw_sha256=sha(DATA / "results.json"),
        rows=320, paired_seed_clusters=20, verified_source_hashes=len(raw["source_sha256"]),
        independently_checked_aggregate_metrics=len(means) * len(keys),
        maximum_individual_peak_a=max(r["peak_current_a"] for r in raw["rows"]),
        no_failed_incomplete_or_over_2p8_a_trials=True,
        requirements_2026_retrieved=False,
        formatting_basis="User supplied ET2025 reference and publicly readable official TEBTRANS rules; exact 2026 DOCX unavailable",
        official_2026_requirements_url="https://www.pgups.ru/upload/medialibrary/17b/zz5v8mowlqbwtkcoza8l5nz3h429pcvt/Trebovaniya-k-oformleniyu-statey-TEBTRANS_2026.docx",
        self_citations=[
            "10.20295/1815-588X-2025-3-667-675",
            "10.20295/1815-588X-2026-3-596-603",
        ],
        deliberate_reference_changes=["Entire article body rewritten", "Three requested authors", "Title-first conference author block", "14 pt text throughout", "Old figures replaced", "One data table added", "Two newly plotted JPEG figures", "Bibliography and author information replaced"],
    )
    with ZipFile(REFERENCE) as z:
        audit["reference_package"] = {n: dict(bytes=len(z.read(n)), sha256=hashlib.sha256(z.read(n)).hexdigest()) for n in z.namelist()}
    (HERE / "source_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "verified_metrics.json").write_text(json.dumps({f"{c}/{m}": v for (c, m), v in means.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw, analysis, means


def text(d, x, y, value, size=10, anchor="start", bold=False):
    d.add(String(x, y, value, fontName=FONT, fontSize=size, fillColor=colors.black, textAnchor=anchor))


def legend(d, y):
    labels = ["F — постоянные параметры", "A — адаптация наблюдателя", "D — прямое обновление", "C — взвешенное обновление"]
    for i, label in enumerate(labels):
        x = 8 if i % 2 == 0 else 238
        yy = y - (i // 2) * 15
        d.add(Rect(x, yy - 2, 10, 8, fillColor=FILLS[i], strokeColor=colors.black, strokeWidth=.6))
        text(d, x + 15, yy - 1, label, 10)


def create_figures(means, analysis):
    d = Drawing(454, 246)
    legend(d, 235)
    for panel, (metric, title, ymax, step) in enumerate([
        ("tracking_mae_rad_s", "а  Погрешность скорости MAE, рад/с", 6., 1.),
        ("peak_current_a", "б  Средний максимум тока, А", 2., .5),
    ]):
        x = 32 + panel * 228
        text(d, x + 88, 194, title, 10.5, "middle")
        bc = VerticalBarChart()
        bc.x, bc.y, bc.width, bc.height = x, 59, 186, 121
        bc.data = [[means[c, m][metric] for c in CASES] for m in METHODS]
        bc.categoryAxis.categoryNames = CASE_LABELS
        bc.categoryAxis.labels.fontName = FONT
        bc.categoryAxis.labels.fontSize = 9
        bc.categoryAxis.labels.boxAnchor = "n"
        bc.categoryAxis.labels.dy = -4
        bc.categoryAxis.strokeWidth = .6
        bc.valueAxis.valueMin, bc.valueAxis.valueMax, bc.valueAxis.valueStep = 0., ymax, step
        bc.valueAxis.labels.fontName, bc.valueAxis.labels.fontSize = FONT, 10
        bc.valueAxis.labelTextFormat = lambda value: f"{value:g}".replace(".", ",")
        bc.valueAxis.strokeWidth = .6
        bc.valueAxis.visibleGrid = True
        bc.valueAxis.gridStrokeColor = colors.HexColor("#dddddd")
        bc.valueAxis.gridStrokeWidth = .35
        bc.groupSpacing = 7
        bc.barSpacing = .5
        bc.bars.strokeWidth = .6
        for i, fill in enumerate(FILLS):
            bc.bars[i].fillColor = fill
            bc.bars[i].strokeColor = colors.black
        d.add(bc)
    text(d, 227, 35, "Режимы: 1 — номинальный; 2 — изменение параметров двигателя;", 9.5, "middle")
    text(d, 227, 22, "3 — совместные возмущения; 4 — совместные возмущения при 3 рад/с.", 9.5, "middle")
    text(d, 227, 8, "Средние значения по 20 независимым реализациям для каждого режима", 9.5, "middle")
    (HERE / "figure_1.svg").write_text(renderSVG.drawToString(d), encoding="utf-8")

    d = Drawing(454, 184)
    for panel, (metric, title, xmin, xmax, ticks) in enumerate([
        ("tracking_mae_rad_s", "а  Отношение MAE  C / F", 0., 1.1, [0., .25, .5, .75, 1.]),
        ("peak_current_a", "б  Отношение максимумов тока  C / F", .94, 1.06, [.94, .98, 1., 1.02, 1.05]),
    ]):
        x0 = 62 + panel * 229
        y0, w, h = 42, 150, 92
        tx = lambda v: x0 + (v - xmin) / (xmax - xmin) * w
        text(d, x0 + w/2, 163, title, 10.5, "middle")
        d.add(Line(x0, y0, x0 + w, y0, strokeColor=colors.black, strokeWidth=.6))
        for tick in ticks:
            xx = tx(tick)
            d.add(Line(xx, y0, xx, y0 - 3, strokeColor=colors.black, strokeWidth=.6))
            text(d, xx, y0 - 15, f"{tick:g}".replace(".", ","), 9.5, "middle")
        d.add(Line(tx(1.), y0, tx(1.), y0+h+5, strokeColor=colors.HexColor("#777777"), strokeWidth=.7, strokeDashArray=[3,2]))
        if panel == 1:
            d.add(Line(tx(1.05), y0, tx(1.05), y0+h+5, strokeColor=colors.black, strokeWidth=.7, strokeDashArray=[1,2]))
            text(d, tx(1.05), 143, "1,05", 9, "middle")
        for i, row in enumerate(analysis["primary"]):
            yy = y0 + h - 17 - i * 45
            label = "Параметры" if row["scenario"] == "parameter_drift" else "Возмущения"
            text(d, x0 - 5, yy - 3, label, 9.5, "end")
            item = row["metrics"][metric]
            lo, hi = item["ratio_ci975"]
            d.add(Line(tx(lo), yy, tx(hi), yy, strokeColor=colors.black, strokeWidth=1.1))
            for bound in [lo, hi]:
                d.add(Line(tx(bound), yy-4, tx(bound), yy+4, strokeColor=colors.black, strokeWidth=.8))
            d.add(Circle(tx(item["ratio"]), yy, 2.7, strokeColor=colors.black, fillColor=colors.black))
            text(d, x0 + w/2, yy-19, f'{item["ratio"]:.3f} [{lo:.3f}; {hi:.3f}]'.replace(".", ","), 9.5, "middle")
    text(d, 227, 5, "Точки — отношения средних значений; отрезки — доверительные интервалы уровня 97,5%", 9.5, "middle")
    (HERE / "figure_2.svg").write_text(renderSVG.drawToString(d), encoding="utf-8")


def set_font(run, size=14, bold=None, italic=None):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is not None:
        for k in ("ascii", "hAnsi", "eastAsia", "cs"):
            fonts.set(qn("w:" + k), FONT)


def add_text(p, value, *, bold=False, italic=False, size=14):
    for part in re.split(r"(<sub>.*?</sub>|<sup>.*?</sup>)", value):
        if not part: continue
        is_sub, is_sup = part.startswith("<sub>"), part.startswith("<sup>")
        if is_sub or is_sup: part = part[5:-6]
        r = p.add_run(part)
        set_font(r, size, bold, italic)
        if is_sub: r.font.subscript = True
        if is_sup: r.font.superscript = True


def paragraph(doc, value="", *, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True,
              bold=False, italic=False, before=0, after=0, keep=False, style=None):
    p = doc.add_paragraph(style=style)
    p.alignment = align
    f = p.paragraph_format
    f.first_line_indent = Cm(1.25 if indent else 0)
    f.left_indent = Cm(0)
    f.right_indent = Cm(0)
    f.space_before, f.space_after = Pt(before), Pt(after)
    f.line_spacing = 1.
    f.keep_with_next = keep
    f.widow_control = True
    add_text(p, value, bold=bold, italic=italic)
    return p


def section_heading(doc, value):
    return paragraph(doc, value, indent=False, bold=True, before=6, after=3, keep=True)


def figure(doc, index, caption):
    p = paragraph(doc, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=5, keep=True)
    run = p.add_run()
    shape = run.add_picture(str(HERE / f"figure_{index}.jpg"), width=Cm(16))
    shape._inline.docPr.set("descr", caption)
    paragraph(doc, f"Рисунок {index} – {caption}", align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=5)


def fnum(x, n=3):
    return f"{x:.{n}f}".replace(".", ",")


def results_table(doc, means):
    paragraph(doc, "Таблица 1 – Средние показатели в двух режимах с возмущениями", indent=False, before=4, after=3, keep=True)
    t = doc.add_table(rows=1, cols=5)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    widths = [2.9, 2.0, 3.2, 3.6, 4.3]
    headers = ["Режим", "Метод", "MAE,\nрад/с", "Средний\nпик, А", "Медь\nстатора, Дж"]
    for i, (c, v) in enumerate(zip(t.rows[0].cells, headers)):
        c.width = Cm(widths[i])
        c.text = v
    for case, label in [("parameter_drift", "Дрейф"), ("composite", "Смеш.")]:
        for method, code in zip(METHODS, CODES):
            m = means[case, method]
            row = t.add_row()
            vals = [label, code, fnum(m["tracking_mae_rad_s"]), fnum(m["peak_current_a"]), fnum(m["copper_energy_j"], 2)]
            for i, (c, value) in enumerate(zip(row.cells, vals)):
                c.width = Cm(widths[i])
                c.text = value
    for i, width in enumerate(widths):
        t.columns[i].width = Cm(width)
    for ri, row in enumerate(t.rows):
        trpr = row._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if ri == 0: trpr.append(OxmlElement("w:tblHeader"))
        for c in row.cells:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tcpr = c._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            for side in ["top", "left", "bottom", "right"]:
                el = OxmlElement("w:" + side)
                el.set(qn("w:val"), "single")
                el.set(qn("w:sz"), "5")
                el.set(qn("w:color"), "D9D9D9")
                borders.append(el)
            tcpr.append(borders)
            margins = OxmlElement("w:tcMar")
            for side, amount in [("top", "35"), ("bottom", "35"), ("left", "60"), ("right", "60")]:
                el=OxmlElement("w:"+side);el.set(qn("w:w"),amount);el.set(qn("w:type"),"dxa");margins.append(el)
            tcpr.append(margins)
            if ri == 0:
                shd=OxmlElement("w:shd");shd.set(qn("w:fill"),"EEEEEE");tcpr.append(shd)
            for p in c.paragraphs:
                p.alignment=WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.first_line_indent=Cm(0)
                p.paragraph_format.space_before=Pt(0)
                p.paragraph_format.space_after=Pt(0)
                p.paragraph_format.line_spacing=1.
                for r in p.runs: set_font(r,14,bold=ri==0)
    return t


def build_doc(means, analysis):
    for index in [1,2]:
        picture=HERE/f'figure_{index}.jpg'
        # A JFIF header is needed by python-docx's JPEG recognizer.
        if b'JFIF' not in picture.read_bytes()[:32]:
            im=Image.open(picture).convert('RGB')
            im.save(picture,format='JPEG',quality=98,subsampling=0,dpi=(400,400))
    # Start from the retained user reference. The entire article body is an editable slot.
    shutil.copy2(REFERENCE, HERE / "article_working_copy.docx")
    doc = Document(HERE / "article_working_copy.docx")
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"): body.remove(child)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin=sec.bottom_margin=sec.left_margin=sec.right_margin=Cm(2.5)
    normal=doc.styles['Normal']
    normal.font.name=FONT;normal.font.size=Pt(14)
    try:
        title=doc.styles['Title']
    except KeyError:
        title=doc.styles.add_style('Title',WD_STYLE_TYPE.PARAGRAPH,builtin=True)
    title.font.name=FONT;title.font.size=Pt(14);title.font.bold=True;title.font.color.rgb=RGBColor(0,0,0)
    doc.core_properties.title="Оценка токовых нагрузок и качества регулирования асинхронного электропривода при параметрической адаптации"
    doc.core_properties.author="А. Н. Марикин; В. Г. Жемчугов; А. Д. Онофрийчук"
    doc.core_properties.subject="Статья для конференции ТЭБТРАНС"
    doc.core_properties.keywords="асинхронный электропривод; параметрическая адаптация; токовые нагрузки; бездатчиковое управление"
    doc.core_properties.comments=""

    paragraph(doc,"УДК 681.518:621.313.333",indent=False,after=6)
    paragraph(doc,"ОЦЕНКА ТОКОВЫХ НАГРУЗОК И КАЧЕСТВА РЕГУЛИРОВАНИЯ АСИНХРОННОГО ЭЛЕКТРОПРИВОДА ПРИ ПАРАМЕТРИЧЕСКОЙ АДАПТАЦИИ",align=WD_ALIGN_PARAGRAPH.CENTER,indent=False,bold=True,after=14,keep=True,style="Title")
    paragraph(doc,"А. Н. Марикин, В. Г. Жемчугов, А. Д. Онофрийчук",align=WD_ALIGN_PARAGRAPH.CENTER,indent=False,after=7,keep=True)
    paragraph(doc,"Петербургский государственный университет путей сообщения Императора Александра I, Санкт-Петербург, Россия\nE-mail: 11lisov11@gmail.com",align=WD_ALIGN_PARAGRAPH.CENTER,indent=False,after=7)
    p=paragraph(doc,indent=False,after=4)
    add_text(p,"Аннотация. ",bold=True)
    add_text(p,"Выполнено сравнительное моделирование четырёх способов построения бездатчикового асинхронного электропривода. В 320 прогонах оценены ошибка скорости, пиковый ток и энергия медных потерь статора. При дрейфе параметров и совокупности возмущений адаптация наблюдателя с обновлением параметров регулятора уменьшила среднюю ошибку скорости на 66–69%. Для варианта с ковариационным взвешиванием средние пики изменились менее чем на 1%, а энергия медных потерь возросла на 2,6–3,0%. Установлены ограничения адаптации в номинальном и малоскоростном режимах.")
    p=paragraph(doc,indent=False,after=5)
    add_text(p,"Ключевые слова: ",bold=True)
    add_text(p,"асинхронный электропривод, бездатчиковое управление, параметрическая адаптация, расширенный фильтр Калмана, токовые нагрузки, техносферная безопасность.")

    section_heading(doc,"Актуальность и цель исследования")
    paragraph(doc,"Для вспомогательных приводов транспортной инфраструктуры существенны точность регулирования, токовые нагрузки и потери, определяющие условия работы электрической машины и преобразователя. Снижение ошибки скорости само по себе не характеризует допустимость режима. В предыдущих работах авторов рассмотрены управление с оптронным датчиком [1] и нейроуправление с обучением в математической модели [2]. Настоящее исследование посвящено параметрической адаптации без механического датчика скорости.")
    paragraph(doc,"Совместная оценка состояний и сопротивлений двигателя с помощью расширенного фильтра Калмана (РФК), а также оценка индуктивности намагничивания известны [3, 4]. Зависимость настройки наблюдателя от режима подтверждается и современными сравнительными исследованиями [5]. Цель работы — количественно сопоставить способы использования адаптивных оценок в регуляторе по точности скорости, токовым нагрузкам и энергии потерь.")

    section_heading(doc,"Модель и варианты управления")
    paragraph(doc,"Использована линейная модель асинхронного двигателя в неподвижных осях αβ с токами статора, потокосцеплением ротора и уравнением движения. Исходные параметры расчётного образца: R<sub>s</sub> = 7,868 Ом, R<sub>r</sub> = 20,832 Ом, L<sub>m</sub> = 0,4824 Гн; индуктивности рассеяния статора и ротора — 2,491 и 1,935 мГн; момент инерции — 7,646·10<sup>−5</sup> кг·м². Это модельный набор, не идентифицированный по испытаниям конкретного двигателя. Напряжение усреднено, насыщение не учитывается; объект интегрируется методом Рунге — Кутты четвёртого порядка.")
    paragraph(doc,"Наблюдатель получает измеренные токи и историю восстановленного напряжения. Истинные скорость, поток, нагрузка и параметры используются только моделью объекта и при вычислении метрик. В адаптивном РФК девять состояний: два тока, два потокосцепления ротора, скорость, момент нагрузки и логарифмы относительных R<sub>s</sub>, R<sub>r</sub>, L<sub>m</sub>. Логарифмическое представление сохраняет положительность параметров; изменение L<sub>m</sub> сохраняет заданные индуктивности рассеяния.")
    paragraph(doc,"Сравниваются четыре варианта: F — РФК с фиксированными электрическими параметрами; A — совместная адаптация наблюдателя при фиксированных параметрах векторного регулятора; D — непосредственное обновление параметров регулятора из РФК; C — то же обновление с весом от нуля до единицы по уменьшению диагональной ковариации логарифмов параметров относительно начальной дисперсии 0,04. Вариант C является эвристикой; уменьшение ковариации не доказывает идентифицируемость. Все варианты используют одинаковые токовые регуляторы, обработку задержек и подавление выбросов.")

    section_heading(doc,"Организация вычислительного эксперимента")
    paragraph(doc,"Проверочная серия содержит 20 парных случайных реализаций, четыре режима и четыре варианта управления, всего 320 прогонов по 2,5 с. В каждой паре совпадают исходные параметры, нагрузка и случайные возмущения. Шаг объекта и управления — 100 мкс; напряжение звена постоянного тока — 325 В; ограничение задания момента — 0,6 Н·м, настройка токового ограничения — 2,8 А. Настройки зафиксированы до проверки. Для F ковариация нагрузки отдельно выбрана по обучающей серии в каждом режиме; скрытая метка неисправности в ходе управления не передаётся.")
    paragraph(doc,"Во всех режимах начальные R<sub>s</sub>, R<sub>r</sub>, инерция и трение случайно изменяются на ±5%. При дрейфе L<sub>m</sub> уменьшена на 15%, индуктивности рассеяния увеличены на 20%, а R<sub>s</sub> дополнительно возрастает на 30% за 1,2 с. Смешанный режим включает задержку 0,3 мс, квантование 2 мА, пропуски 0,5% отсчётов и импульсные помехи. В трёх режимах скорость нарастает до 150 рад/с; в малоскоростном смешанном режиме — до 3 рад/с. Нагрузка 0,25–0,45 Н·м прикладывается в случайный момент 0,95–1,25 с.")
    paragraph(doc,"Средняя абсолютная ошибка скорости MAE вычисляется по физической скорости после 0,8 с. Индивидуальный пик — максимум модуля вектора тока αβ за весь прогон; в таблице приведено среднее этих максимумов. Энергия меди статора рассчитана за 2,5 с интегрированием полуторакратного произведения R<sub>s</sub> на квадрат модуля тока в амплитудно-инвариантном преобразовании Кларка. Независимая статистическая единица — случайная реализация. Для двух заранее заданных сравнений C/F использованы 10 000 парных бутстреп-выборок и 97,5%-ные интервалы с поправкой Бонферрони для двух скоростных гипотез. Сравнения A и D являются вторичными.")

    section_heading(doc,"Результаты и обсуждение")
    paragraph(doc,"Все 320 прогонов завершены без численных отказов и превышения 2,8 А; наибольший индивидуальный пик равен 2,324 А. Независимый пересчёт исходных строк воспроизвёл 64 групповых показателя; контрольные суммы 14 исходных файлов совпали. На рисунке 1 сопоставлены все режимы, в таблице 1 детализированы два режима с возмущениями.")
    figure(doc,1,"Ошибка скорости и средние индивидуальные максимумы тока для четырёх вариантов управления")
    results_table(doc,means)
    paragraph(doc,"При дрейфе вариант C уменьшает MAE с 3,721 до 1,258 рад/с (66,18%); в смешанном режиме — с 3,769 до 1,224 рад/с (67,52%). Отношения MAE C/F составляют 0,338 и 0,325; верхние границы интервалов ниже единицы (рисунок 2). Изменения среднего индивидуального пика равны −0,15 и +0,84%; верхние границы отношений пиков 1,020 и 1,027 ниже заранее заданного критерия 1,05.",before=4)
    figure(doc,2,"Отношения показателей C/F и интервалы неопределённости в двух заранее заданных сравнениях")
    paragraph(doc,"Выигрыш точности сопровождается ростом энергии меди статора на 2,99 и 2,63%. Стандартное отклонение момента после 1,7 с уменьшается на 34,34 и 31,83%. Вариант A даёт меньшую ошибку скорости — 0,713 и 0,772 рад/с, однако повышает средние пики на 32,71 и 38,42% и не проходит принятый сравнительный критерий. Следовательно, выбор по единственной метрике скорости изменил бы оценку практической предпочтительности.")
    paragraph(doc,"Прямое обновление D обеспечивает MAE 1,230 и 1,181 рад/с, несколько меньшую, чем C. Дополнительная польза ковариационного взвешивания не подтверждена. В номинальном режиме MAE C равна 1,614 против 0,879 рад/с у F, то есть выше на 83,60%. При задании 3 рад/с MAE C составляет 2,076 рад/с — 69,2% задания; ни одна из 20 реализаций не достигла после скачка нагрузки непрерывного 100-мс интервала с ошибкой менее 0,3 рад/с. Эти результаты ограничивают область применения адаптации.")

    section_heading(doc,"Выводы")
    paragraph(doc,"Моделирование подтверждает существенное улучшение регулирования при изменении параметров, когда адаптивные оценки используются в регуляторе. Принятие такого решения требует совместного контроля ошибки скорости, индивидуальных токовых максимумов и потерь. Уменьшение ошибки не означает снижения энергопотребления или доказанной безопасности. Полученные значения относятся к линейной усреднённой модели и 20 парным реализациям; модель объекта и предиктор используют одну систему уравнений. Коммутационные потери, температура и вероятность отказа не оценивались. Перенос результатов на вспомогательные приводы транспорта требует идентификации машины, проверки защит и стендовых испытаний.")

    section_heading(doc,"Библиографический список")
    refs=[
        "Марикин А. Н., Евстафьев А. М., Жемчугов В. Г., Онофрийчук А. Д., Хвостова О. В. Векторное управление асинхронным двигателем с оптронным датчиком — формирователем алгоритма // Известия Петербургского университета путей сообщения. 2025. Т. 22, № 3. С. 667–675. DOI: 10.20295/1815-588X-2025-3-667-675.",
        "Марикин А. Н., Евстафьев А. М., Жемчугов В. Г., Онофрийчук А. Д. Исследование особенностей нейроуправления асинхронным двигателем с обучением в цифровом двойнике // Известия Петербургского университета путей сообщения. 2026. Т. 23, № 3. С. 596–603. DOI: 10.20295/1815-588X-2026-3-596-603.",
        "Özsoy E. E., Gökaşan M., Estrada O. S. Simultaneous rotor and stator resistance estimation of squirrel cage induction machine with a single extended Kalman filter // Turkish Journal of Electrical Engineering and Computer Sciences. 2010. Vol. 18, no. 5. P. 853–864. DOI: 10.3906/elk-0906-50.",
        "İnan R., Barut M. Bi input-extended Kalman filter-based speed-sensorless control of an induction machine capable of working in the field-weakening region // Turkish Journal of Electrical Engineering and Computer Sciences. 2014. Vol. 22, no. 3. P. 588–604. DOI: 10.3906/elk-1208-31.",
        "Hassan A., Bazzi A. M., Jensen F., Karaki S. H. Analysis and Comparison of Nonlinear Kalman Filters for Sensorless Induction Motor Drives To Achieve Multiple Model Estimation // IEEE Transactions on Industry Applications. 2025. Vol. 61, no. 4. P. 6422–6433. DOI: 10.1109/TIA.2025.3546902.",
    ]
    for i,value in enumerate(refs,1):
        p=paragraph(doc,f"{i}. {value}",align=WD_ALIGN_PARAGRAPH.LEFT,indent=False,after=3)
        p.paragraph_format.left_indent=Cm(.6)
        p.paragraph_format.first_line_indent=Cm(-.6)

    section_heading(doc,"Сведения об авторах")
    paragraph(doc,"Марикин Александр Николаевич — доктор технических наук, профессор ПГУПС. Жемчугов Валерий Григорьевич — кандидат технических наук, доцент ПГУПС. Онофрийчук Андрей Дмитриевич — аспирант ПГУПС, 11lisov11@gmail.com.",indent=False)

    # Remove all nonessential inherited title borders and orphan header/footer fields.
    for p in doc.paragraphs:
        ppr=p._p.find(qn('w:pPr'))
        if ppr is not None:
            for el in list(ppr):
                if el.tag==qn('w:pBdr'):ppr.remove(el)
    used_image_ids=set(doc._element.xpath('//@r:embed'))
    for rid, rel in list(doc.part.rels.items()):
        if rel.reltype.endswith('/image') and rid not in used_image_ids:
            doc.part.drop_rel(rid)
    doc.save(DOCX)
    preserve_parts=['_rels/.rels','word/numbering.xml','word/settings.xml','customXml/_rels/item1.xml.rels']
    with ZipFile(DOCX) as generated, ZipFile(REFERENCE) as reference:
        all_parts={n:(generated.getinfo(n),generated.read(n)) for n in generated.namelist()}
        for name in preserve_parts:
            all_parts[name]=(reference.getinfo(name),reference.read(name))
    temp_docx=DOCX.with_suffix('.tmp.docx')
    with ZipFile(temp_docx,'w') as package:
        for name,(info,blob) in all_parts.items():package.writestr(info,blob)
    temp_docx.replace(DOCX)
    assert sha(REFERENCE)==json.loads((HERE/'source_audit.json').read_text(encoding='utf-8'))['reference_sha256']
    paras=[p.text for p in doc.paragraphs]
    assert not any('<sub>' in p or '<sup>' in p for p in paras)
    print(json.dumps(dict(output=str(DOCX),paragraphs=len(paras),words=len(' '.join(paras).split()),figures=len(doc.inline_shapes),tables=len(doc.tables)),ensure_ascii=False))


if __name__ == "__main__":
    raw,analysis,means=load_and_check()
    if len(sys.argv)>1 and sys.argv[1]=="prepare":
        create_figures(means,analysis)
        print("Verified 320 rows, 20 paired seeds, 64 aggregate values and 14 source hashes; SVG figures written")
    else:
        build_doc(means,analysis)
