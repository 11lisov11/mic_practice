#!/usr/bin/env python3
"""Generate the current MIC_AI Nucleo wiring package.

The document is intentionally separate from the legacy Blue Pill schematic.
It describes the accepted NUCLEO-G431RB + X-NUCLEO-IHM09M2 +
STEVAL-IPM15B architecture and emits PDF, SVG, PNG, CSV, Markdown, and a manifest
from one data model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "hardware" / "nucleo_system_wiring"
SVG_DIR = OUT_DIR / "svg"
PDF_DIR = ROOT / "output" / "pdf"
PNG_DIR = ROOT / "output" / "png" / "MIC_AI_NUCLEO_SYSTEM_WIRING"
PDF_PATH = PDF_DIR / "MIC_AI_NUCLEO_SYSTEM_WIRING.pdf"
CSV_PATH = OUT_DIR / "MIC_AI_NUCLEO_CONNECTIONS.csv"
README_PATH = OUT_DIR / "ASSEMBLY_RU.md"
MANIFEST_PATH = OUT_DIR / "manifest.json"

DOCUMENT_CODE = "MIC-AI.Э4.NUCLEO.001"
REVISION = "1.0"
REVISION_DATE = "2026-08-26"
TOTAL_PAGES = 7

INK = "#111111"
GRID = "#666666"
LIGHT = "#f4f4f4"
SAFE_FILL = "#f7f7f7"
HOT_FILL = "#fff8f0"
DANGER = "#9b1c1c"
DANGER_FILL = "#fff0f0"


@dataclass(frozen=True)
class CablePin:
    pin: int
    ihm09: str
    steval: str
    state: str


@dataclass(frozen=True)
class Connection:
    section: str
    source_ref: str
    source_contact: str
    signal: str
    destination_ref: str
    destination_contact: str
    state: str
    note: str


CABLE_PINS = (
    CablePin(1, "PA6/PA11 — DIAG/ENABLE/BKIN1", "Emergency stop", "USED: PA6/TIM1_BKIN"),
    CablePin(2, "GND", "GND", "USED: HOT_GND"),
    CablePin(3, "PA8 — UH_PWM", "PWM-1H", "USED"),
    CablePin(4, "GND", "GND", "USED: HOT_GND"),
    CablePin(5, "PA7/PB15 — UL_PWM", "PWM-1L", "USED: PA7"),
    CablePin(6, "GND", "GND", "USED: HOT_GND"),
    CablePin(7, "PA9 — VH_PWM", "PWM-2H", "USED"),
    CablePin(8, "GND", "GND", "USED: HOT_GND"),
    CablePin(9, "PB0 — VL_PWM", "PWM-2L", "USED"),
    CablePin(10, "GND", "GND", "USED: HOT_GND"),
    CablePin(11, "PA10 — WH_PWM", "PWM-3H", "USED"),
    CablePin(12, "GND", "GND", "USED: HOT_GND"),
    CablePin(13, "PB1 — WL_PWM", "PWM-3L", "USED"),
    CablePin(14, "PA1 — VBUS_sensing", "HV bus voltage", "USED"),
    CablePin(15, "PA0 — Curr_fdbk_PhA", "Current phase A", "USED"),
    CablePin(16, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(17, "PC1 — Curr_fdbk_PhB", "Current phase B", "USED"),
    CablePin(18, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(19, "PC0 — Curr_fdbk_PhC", "Current phase C", "USED"),
    CablePin(20, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(21, "PC10 — NTC bypass", "NTC bypass relay", "UNUSED S1; NO EXT RELAY"),
    CablePin(22, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(23, "PC11 — brake/OCP disable", "Dissipative brake PWM", "UNUSED S1"),
    CablePin(24, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(25, "E5V", "+V power", "USED: NUCLEO VIN REQUIRED"),
    CablePin(26, "PC2 — Temperature feedback", "Heat sink temperature", "USED"),
    CablePin(27, "NC on IHM09M2", "PFC sync", "UNUSED"),
    CablePin(28, "+3V3 per IHM09M2 schematic", "VDD_m", "USED: 3.3 V POWER"),
    CablePin(29, "NC on IHM09M2", "PWM VREF", "UNUSED"),
    CablePin(30, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(31, "PA15 — Encoder A/Hall H1", "Measure phase A", "UNUSED S1"),
    CablePin(32, "NC on IHM09M2", "GND", "CABLE ONLY"),
    CablePin(33, "PB3 — Encoder B/Hall H2", "Measure phase B", "UNUSED S1"),
    CablePin(34, "PB10 — Encoder Z/Hall H3", "Measure phase C", "UNUSED S1"),
)


CONTROL_ROWS = (
    ("PA6", "CN10-13", "TIM1_BKIN / M1_OCP", "J7-1", "J2-1 Emergency stop"),
    ("PA8", "CN10-23", "TIM1_CH1 / UH", "J7-3", "J2-3 PWM-1H"),
    ("PA7", "CN10-15", "TIM1_CH1N / UL", "J7-5", "J2-5 PWM-1L"),
    ("PA9", "CN10-21", "TIM1_CH2 / VH", "J7-7", "J2-7 PWM-2H"),
    ("PB0", "CN7-34", "TIM1_CH2N / VL", "J7-9", "J2-9 PWM-2L"),
    ("PA10", "CN10-33", "TIM1_CH3 / WH", "J7-11", "J2-11 PWM-3H"),
    ("PB1", "CN10-24", "TIM1_CH3N / WL", "J7-13", "J2-13 PWM-3L"),
    ("PA1", "CN7-30", "ADC1_IN2 / VBUS", "J7-14", "J2-14 HV bus voltage"),
    ("PA0", "CN7-28", "ADC1_IN1 / I_A", "J7-15", "J2-15 current A"),
    ("PC1", "CN7-36", "ADC1/2_IN7 / I_B", "J7-17", "J2-17 current B"),
    ("PC0", "CN7-38", "ADC2_IN6 / I_C", "J7-19", "J2-19 current C"),
    ("PC2", "CN7-35", "ADC1_IN8 / TEMP", "J7-26", "J2-26 heat sink temp"),
    ("E5V", "CN7-6", "control power", "J7-25", "J2-25 +V power"),
    ("+3V3", "CN7-16", "logic reference", "J7-28", "J2-28 VDD_m"),
    ("PC10", "CN7-1", "NTC bypass", "J7-21", "J2-21 UNUSED"),
    ("PC11", "CN7-2", "brake/OCP disable", "J7-23", "J2-23 UNUSED S1"),
)


def build_connections() -> list[Connection]:
    rows: list[Connection] = []
    rows.extend(
        [
            Connection("UART", "UNO_Q", "D1 / PB6 / USART1_TX", "UART_CMD", "NUCLEO_G431RB", "PB7 / CN7-21 / USART1_RX", "USED", "direct 3.3 V UART, 115200 8N1"),
            Connection("UART", "NUCLEO_G431RB", "PB6 / CN10-17 / USART1_TX", "UART_TELEMETRY", "UNO_Q", "D0 / PB7 / USART1_RX", "USED", "direct 3.3 V UART, 115200 8N1"),
            Connection("UART", "UNO_Q", "GND", "HOT_GND", "NUCLEO_G431RB", "GND", "USED", "common reference; UNO Q becomes HOT"),
            Connection("WIRELESS", "PHONE_OR_PC", "Wi-Fi client", "HTTPS/HTTP HMI", "UNO_Q", "wlan0", "USED", "no galvanic connection to inverter"),
            Connection("LOGS", "UNO_Q", "eMMC log store", "LOG_ARCHIVE", "PHONE_OR_PC", "Wi-Fi download", "USED", "download only over Wi-Fi while HV is present"),
        ]
    )
    for item in CABLE_PINS:
        rows.append(
            Connection(
                "FC34_1_TO_1",
                "X_NUCLEO_IHM09M2",
                f"J7-{item.pin}",
                item.ihm09,
                "STEVAL_IPM15B",
                f"J2-{item.pin}",
                item.state,
                item.steval,
            )
        )
    rows.extend(
        [
            Connection("AUX_POWER", "PS_15V", "+15V", "HOT_15V", "STEVAL_IPM15B", "J4 positive", "USED", "J4 accepts up to 20 VDC"),
            Connection("AUX_POWER", "PS_15V", "0V", "HOT_GND", "STEVAL_IPM15B", "J4 negative", "USED", "becomes HOT in assembled inverter"),
            Connection("UNOQ_POWER", "PS_15V", "+15V", "HOT_15V", "UNO_Q", "VIN", "USED", "UNO Q VIN accepts 7-24 V; size supply for wireless peaks"),
            Connection("UNOQ_POWER", "PS_15V", "0V", "HOT_GND", "UNO_Q", "GND", "USED", "UNO Q is enclosed HOT equipment"),
            Connection("NUCLEO_POWER", "PS_15V", "+15V", "HOT_15V", "BUCK_9V", "IN+", "USED", "derive 7-12 V for Nucleo VIN"),
            Connection("NUCLEO_POWER", "BUCK_9V", "OUT+ 9V", "NUCLEO_VIN", "NUCLEO_G431RB", "VIN / CN7-24", "USED", "JP5 1-2 per ST ACIM guide"),
            Connection("HV", "RECTIFIER", "+", "DC_BUS_PLUS", "STEVAL_IPM15B", "J7-1 positive", "USED", "125-400 VDC board range"),
            Connection("HV", "RECTIFIER", "-", "DC_BUS_MINUS", "STEVAL_IPM15B", "J7-2 negative", "USED", "non-isolated rectified mains is HOT"),
            Connection("HOT_REFERENCE", "STEVAL_IPM15B", "J2 GND / J4 negative", "HOT_GND_EQUALS_DC_MINUS", "STEVAL_IPM15B", "J7-2 DC-", "INTERNAL", "UM2014: VDC- is the common reference ground; board circuits are not line-isolated"),
            Connection("MOTOR", "STEVAL_IPM15B", "J3-1 phase A", "MOTOR_U", "AIR56B2", "U1", "USED", "delta 220 V"),
            Connection("MOTOR", "STEVAL_IPM15B", "J3-2 phase B", "MOTOR_V", "AIR56B2", "V1", "USED", "delta 220 V"),
            Connection("MOTOR", "STEVAL_IPM15B", "J3-3 phase C", "MOTOR_W", "AIR56B2", "W1", "USED", "delta 220 V"),
            Connection("MOTOR", "AIR56B2", "U1", "DELTA_LINK_1", "AIR56B2", "W2", "USED", "terminal bridge"),
            Connection("MOTOR", "AIR56B2", "V1", "DELTA_LINK_2", "AIR56B2", "U2", "USED", "terminal bridge"),
            Connection("MOTOR", "AIR56B2", "W1", "DELTA_LINK_3", "AIR56B2", "V2", "USED", "terminal bridge"),
            Connection("PE", "AC_INPUT", "PE", "PROTECTIVE_EARTH", "AIR56B2", "frame/PE stud", "USED", "also bond metal enclosure"),
            Connection("AS5600_S3", "UNO_Q", "QWIIC +3V3 OUT", "HOT_3V3", "AS5600", "VCC", "OPTION S3", "not active in first S1 start"),
            Connection("AS5600_S3", "UNO_Q", "QWIIC GND", "HOT_GND", "AS5600", "GND", "OPTION S3", "sensor and cable remain inside enclosure"),
            Connection("AS5600_S3", "UNO_Q", "PD13 / I2C4_SDA", "HOT_AS5600_SDA", "AS5600", "SDA", "OPTION S3", "use pull-ups once"),
            Connection("AS5600_S3", "UNO_Q", "PD12 / I2C4_SCL", "HOT_AS5600_SCL", "AS5600", "SCL", "OPTION S3", "use pull-ups once"),
        ]
    )
    return rows


class DualPage:
    def __init__(self, pdf: canvas.Canvas, svg_path: Path, width: float, height: float):
        self.pdf = pdf
        self.svg_path = svg_path
        self.width = width
        self.height = height
        self.svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]

    def _sy(self, y: float) -> float:
        return self.height - y

    @staticmethod
    def _color(value: str) -> colors.Color:
        return colors.HexColor(value)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = INK, width: float = 1.0, dash: tuple[int, ...] | None = None) -> None:
        self.pdf.setStrokeColor(self._color(color))
        self.pdf.setLineWidth(width)
        self.pdf.setDash(dash or [])
        self.pdf.line(x1, y1, x2, y2)
        dash_attr = f' stroke-dasharray="{",".join(map(str, dash))}"' if dash else ""
        self.svg.append(
            f'<line x1="{x1:.2f}" y1="{self._sy(y1):.2f}" x2="{x2:.2f}" y2="{self._sy(y2):.2f}" '
            f'stroke="{color}" stroke-width="{width}"{dash_attr}/>'
        )

    def rect(self, x: float, y: float, w: float, h: float, stroke: str = INK, fill: str = "#ffffff", width: float = 1.0) -> None:
        self.pdf.setStrokeColor(self._color(stroke))
        self.pdf.setFillColor(self._color(fill))
        self.pdf.setLineWidth(width)
        self.pdf.rect(x, y, w, h, stroke=1, fill=1)
        self.svg.append(
            f'<rect x="{x:.2f}" y="{self._sy(y + h):.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'
        )

    def circle(self, x: float, y: float, radius: float = 2.5, color: str = INK) -> None:
        self.pdf.setFillColor(self._color(color))
        self.pdf.setStrokeColor(self._color(color))
        self.pdf.circle(x, y, radius, stroke=1, fill=1)
        self.svg.append(f'<circle cx="{x:.2f}" cy="{self._sy(y):.2f}" r="{radius:.2f}" fill="{color}"/>')

    def text(self, x: float, y: float, value: str, size: float = 9, color: str = INK, bold: bool = False, anchor: str = "start") -> None:
        font = "Arial-Bold" if bold else "Arial"
        self.pdf.setFont(font, size)
        self.pdf.setFillColor(self._color(color))
        if anchor == "middle":
            self.pdf.drawCentredString(x, y, value)
        elif anchor == "end":
            self.pdf.drawRightString(x, y, value)
        else:
            self.pdf.drawString(x, y, value)
        weight = "700" if bold else "400"
        self.svg.append(
            f'<text x="{x:.2f}" y="{self._sy(y):.2f}" font-family="Arial, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" fill="{color}">{escape(value)}</text>'
        )

    def multiline(self, x: float, y: float, lines: Iterable[str], size: float = 8.5, leading: float = 12, color: str = INK, bold_first: bool = False) -> None:
        for index, value in enumerate(lines):
            self.text(x, y - index * leading, value, size=size, color=color, bold=bold_first and index == 0)

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: Iterable[str], fill: str = "#ffffff", stroke: str = INK) -> None:
        self.rect(x, y, w, h, stroke=stroke, fill=fill, width=1.2)
        self.rect(x, y + h - 24, w, 24, stroke=stroke, fill=LIGHT, width=1.0)
        self.text(x + 8, y + h - 17, title, size=10, bold=True)
        self.multiline(x + 8, y + h - 39, lines, size=8.2, leading=11.5)

    def arrow(self, x1: float, y1: float, x2: float, y2: float, label: str = "", color: str = INK, width: float = 1.5) -> None:
        self.line(x1, y1, x2, y2, color=color, width=width)
        angle = math.atan2(y2 - y1, x2 - x1)
        for delta in (2.55, -2.55):
            self.line(x2, y2, x2 + 8 * math.cos(angle + delta), y2 + 8 * math.sin(angle + delta), color=color, width=width)
        if label:
            self.text((x1 + x2) / 2, (y1 + y2) / 2 + 8, label, size=7.5, bold=True, anchor="middle")

    def table(self, x: float, y_top: float, widths: list[float], headers: list[str], rows: Iterable[Iterable[str]], row_h: float = 22, size: float = 7.6) -> float:
        x_pos = x
        for width, header in zip(widths, headers):
            self.rect(x_pos, y_top - row_h, width, row_h, stroke=GRID, fill="#e9e9e9", width=0.8)
            self.text(x_pos + 4, y_top - row_h + 7, header, size=size, bold=True)
            x_pos += width
        y = y_top - row_h
        for index, row in enumerate(rows):
            y -= row_h
            x_pos = x
            fill = "#ffffff" if index % 2 == 0 else "#f7f7f7"
            for width, value in zip(widths, row):
                self.rect(x_pos, y, width, row_h, stroke="#999999", fill=fill, width=0.5)
                font_size = size
                if len(str(value)) > max(12, int(width / 5.2)):
                    font_size = max(6.0, size - 1.0)
                self.text(x_pos + 4, y + 7, str(value), size=font_size)
                x_pos += width
        return y

    def frame(self, page_no: int, title: str, subtitle: str) -> None:
        self.rect(18, 18, self.width - 36, self.height - 36, stroke=INK, fill="#ffffff", width=1.8)
        self.rect(28, 94, self.width - 56, self.height - 132, stroke=INK, fill="#ffffff", width=0.8)
        self.text(38, self.height - 49, title, size=15, bold=True)
        self.text(38, self.height - 66, subtitle, size=8.5, color="#333333")
        self.line(28, self.height - 78, self.width - 28, self.height - 78, width=1.0)

        stamp_x = self.width - 540
        stamp_y = 24
        stamp_w = 512
        stamp_h = 62
        self.rect(stamp_x, stamp_y, stamp_w, stamp_h, width=1.0)
        self.line(stamp_x, stamp_y + 31, stamp_x + stamp_w, stamp_y + 31, width=0.7)
        self.line(stamp_x + 285, stamp_y, stamp_x + 285, stamp_y + stamp_h, width=0.7)
        self.line(stamp_x + 405, stamp_y, stamp_x + 405, stamp_y + stamp_h, width=0.7)
        self.text(stamp_x + 8, stamp_y + 43, "Схема электрическая подключений", size=8.5, bold=True)
        self.text(stamp_x + 8, stamp_y + 12, "MIC_AI: Nucleo — IHM09M2 — IPM15B", size=8)
        self.text(stamp_x + 293, stamp_y + 43, DOCUMENT_CODE, size=8, bold=True)
        self.text(stamp_x + 293, stamp_y + 12, f"Рев. {REVISION}   {REVISION_DATE}", size=7.5)
        self.text(stamp_x + 413, stamp_y + 43, f"Лист {page_no}", size=8.5, bold=True)
        self.text(stamp_x + 413, stamp_y + 12, f"Листов {TOTAL_PAGES}   A3", size=7.5)
        self.text(32, 37, "Э4-подобный монтажный документ; не сертифицированный комплект КД", size=7.2)

    def finish(self) -> None:
        self.svg.append("</svg>")
        self.svg_path.write_text("\n".join(self.svg), encoding="utf-8")
        self.pdf.showPage()


def draw_page_1(p: DualPage) -> None:
    p.frame(1, "Общая блок-схема стенда", "Автономный HOT-узел; наружу при силовой работе выходит только Wi-Fi")
    p.rect(42, 128, 330, 610, stroke=GRID, fill=SAFE_FILL, width=1.4)
    p.rect(398, 128, 350, 610, stroke="#8b5a2b", fill=HOT_FILL, width=1.4)
    p.rect(774, 128, 370, 610, stroke=DANGER, fill=DANGER_FILL, width=1.4)
    p.text(57, 714, "ОПЕРАТОР: гальванически не подключён", 11, bold=True)
    p.text(413, 714, "HOT: автономное управление", 11, bold=True)
    p.text(789, 714, "СИЛОВАЯ ЧАСТЬ: 230 VAC / ~310 VDC", 11, color=DANGER, bold=True)

    p.box(72, 578, 270, 100, "A1 — телефон / ноутбук", ["браузер HMI", "START/STOP и телеметрия", "выгрузка архивов логов", "никаких кабелей к стенду"], fill="#ffffff")
    p.box(72, 390, 270, 105, "A2 — Wi-Fi", ["режим station через роутер", "или автономная точка доступа", "WPA2/WPA3 + ключ HMI", "heartbeat оператора 1 Hz"], fill="#ffffff")
    p.box(72, 205, 270, 105, "A3 — сервисный режим", ["USB/ST-Link только без силовой части", "сеть, BR1 и J7 физически сняты", "DC-link разряжен и измерен", "после сервиса кабели убрать"], fill="#ffffff")

    p.box(438, 575, 270, 105, "A4 — Arduino UNO Q", ["Linux: Wi-Fi HMI, логи, AI", "MCU: команды/телеметрия", "D1/TX; D0/RX; GND", "VIN 15 V; вся плата HOT"], fill="#ffffff", stroke=DANGER)
    p.box(438, 390, 270, 105, "A5 — NUCLEO-G431RB", ["STM32G431RBT6", "MCSDK 6.4.2, S1 V/f", "PWM/ADC/BKIN", "PB6/PB7 — прямой UART"], fill="#ffffff", stroke=DANGER)
    p.box(438, 205, 270, 105, "A6 — X-NUCLEO-IHM09M2", ["ставится сверху на Morpho", "J1 jumper OFF", "J7 — 34 контакта", "не отдельный контроллер"], fill="#ffffff", stroke=DANGER)

    p.box(814, 585, 290, 95, "A7 — STEVAL-IPM15B", ["J2 control, J4 +15V", "J7 DC 125...400 V", "J3 фазы A/B/C", "SW1/2/4, SW3, SW5...SW8"], fill="#ffffff", stroke=DANGER)
    p.box(814, 430, 290, 95, "A8 — AIR56B2", ["0.25 kW; 220 V Δ; 50 Hz", "J3 A/B/C -> U1/V1/W1", "PE -> корпус двигателя", "S1: бездатчиковое V/f"], fill="#ffffff", stroke=DANGER)
    p.box(814, 250, 290, 120, "A9 — входное питание", ["2P отключение + аппаратный E-STOP", "F1 + MOV + автономный soft-start", "мост + DC-link + bleeder", "никакого провода управления к MCU"], fill="#ffffff", stroke=DANGER)
    p.box(814, 145, 290, 70, "A10 — питание управления", ["15 V -> STEVAL J4 и UNO Q VIN", "15 V -> buck 9 V -> Nucleo VIN"], fill="#ffffff", stroke=DANGER)

    p.arrow(342, 628, 438, 628, "Wi-Fi only")
    p.arrow(573, 575, 573, 495, "D1/PB7; PB6/D0; GND")
    p.arrow(573, 390, 573, 310, "Morpho")
    p.line(708, 257, 760, 257, width=1.5)
    p.line(760, 257, 760, 632, width=1.5)
    p.arrow(760, 632, 814, 632, "FC-34P 1:1")
    p.arrow(959, 585, 959, 525, "J3")
    p.line(814, 310, 790, 310, color=DANGER, width=1.5)
    p.line(790, 310, 790, 615, color=DANGER, width=1.5)
    p.arrow(790, 615, 814, 615, "J7 DC", color=DANGER)

    p.rect(42, 100, 1102, 22, stroke=DANGER, fill=DANGER_FILL, width=1.0)
    p.text(593, 107, "UNO Q, Nucleo, AS5600, IHM09M2, шлейф и STEVAL — HOT. В работе корпус закрыт; USB, Ethernet и измерительные провода отсутствуют.", size=8.2, color=DANGER, bold=True, anchor="middle")
    p.finish()


def draw_page_2(p: DualPage) -> None:
    p.frame(2, "Автономная связь: Wi-Fi + прямой UART", "UNO Q и Nucleo имеют общую HOT_GND; проводного интерфейса наружу при HV нет")
    p.box(55, 530, 250, 160, "Телефон / ноутбук", ["браузер", "Wi-Fi station или AP", "контрольный ключ HMI", "скачивание логов", "физически не соединён со стендом"], fill=SAFE_FILL)
    p.box(455, 515, 280, 190, "Arduino UNO Q / HOT", ["wlan0: HMI :8080", "D1/PB6/USART1_TX -> команды", "D0/PB7/USART1_RX <- телеметрия", "GND -> HOT_GND", "VIN <- 15 V", "eMMC: логи и архивы"], fill=HOT_FILL, stroke=DANGER)
    p.box(885, 530, 250, 160, "NUCLEO-G431RB / HOT", ["PB7/CN7-21/USART1_RX", "PB6/CN10-17/USART1_TX", "GND -> HOT_GND", "VIN <- 9 V", "PB4 = NC"], fill=HOT_FILL, stroke=DANGER)
    p.arrow(305, 625, 455, 625, "Wi-Fi only")
    p.arrow(735, 635, 885, 635, "D1/TX -> PB7/RX")
    p.arrow(885, 575, 735, 575, "PB6/TX -> D0/RX")
    p.line(735, 545, 885, 545, color=INK, width=2.0)
    p.text(810, 552, "GND <-> GND = HOT_GND", 7.8, color=DANGER, bold=True, anchor="middle")

    p.box(55, 330, 330, 120, "Режим через роутер", ["UNO Q подключается к заданному SSID", "адрес через DHCP + mDNS", "HMI открывается по IP/имени", "heartbeat браузера каждые 1 s", "потеря >3 s -> STOP/ESTOP"], fill="#ffffff")
    p.box(430, 330, 330, 120, "Автономная точка доступа", ["UNO Q поднимает WPA2 hotspot", "телефон подключается напрямую", "статический адрес HMI", "пароль AP и ключ управления различаются", "режим выбирается до подачи HV"], fill="#ffffff")
    p.box(805, 330, 330, 120, "Логи", ["кольцевой журнал 64 MiB на eMMC", "статус и события сохраняются локально", "выгрузка через /api/logs по Wi-Fi", "скачивание требует ключ HMI", "после сбоя питания журнал остаётся"], fill="#ffffff")

    rows = [
        ("UNO Q D1/TX", "Nucleo PB7/RX", "команды", "3.3 V, 115200 8N1"),
        ("Nucleo PB6/TX", "UNO Q D0/RX", "телеметрия", "3.3 V, 115200 8N1"),
        ("UNO Q GND", "Nucleo GND", "общая точка отсчёта", "вся цепь HOT"),
        ("UNO Q Wi-Fi", "телефон/роутер", "HMI и логи", "единственная рабочая связь наружу"),
    ]
    p.table(90, 295, [245, 245, 245, 275], ["источник", "приёмник", "назначение", "условие"], rows, row_h=22, size=7.8)
    p.rect(55, 96, 1080, 56, stroke=DANGER, fill=DANGER_FILL, width=1.0)
    p.text(68, 128, "Сервисный USB/ST-Link:", 9, color=DANGER, bold=True)
    p.text(205, 128, "разрешён только после OFF, физического снятия сети/BR1/J7 и измерения разряда DC-link.", 8.2, color=DANGER)
    p.text(68, 106, "Во время HV запрещены USB-C, Ethernet-донгл, HDMI, JTAG/SWD, UART-адаптер и любой провод от UNO Q/Nucleo к внешнему устройству.", 8.2, color=DANGER)
    p.finish()


def draw_page_3(p: DualPage) -> None:
    p.frame(3, "NUCLEO-G431RB и X-NUCLEO-IHM09M2", "Переходник ставится на Morpho; отдельные провода PWM/ADC не требуются")
    p.box(45, 620, 310, 85, "Механическая сборка", ["IHM09M2 установить сверху Nucleo", "совместить CN7 и CN10 без смещения", "J1 на IHM09M2: jumper OFF", "перед включением осмотреть все ряды"], fill="#ffffff")
    p.box(410, 620, 310, 85, "Питание E5V", ["Nucleo VIN: 7...12 VDC", "для проекта принят buck 9 V", "JP5: pins 1-2 по ST ACIM guide", "E5V выходит на J7-25"], fill=HOT_FILL)
    p.box(775, 620, 350, 85, "Настройки STEVAL-IPM15B", ["SW3 = 2-3 (NTC)", "SW1, SW2, SW4 = 1-2 (amplified)", "SW5, SW6 open; SW7, SW8 closed", "трёхшунтовая конфигурация"], fill=HOT_FILL)

    p.table(45, 585, [90, 105, 225, 90, 520], ["MCU", "Morpho", "IHM09M2 функция", "J7", "STEVAL J2"], CONTROL_ROWS, row_h=24, size=7.5)

    p.rect(45, 115, 1080, 54, stroke=DANGER, fill=DANGER_FILL, width=1.0)
    p.text(58, 146, "Неиспользуемые линии:", 9, color=DANGER, bold=True)
    p.text(185, 146, "PC10/J7-21/J2-21 физически присутствует в шлейфе, но прошивка S1 им не управляет; внешнего bypass-реле от MCU нет.", 8.2, color=DANGER)
    p.text(58, 125, "PB4 остаётся NC. Для программирования используется SWD; освобождать PB4 для ST-Link не требуется.", 8.2, color=DANGER)
    p.finish()


def cable_half_rows(items: Iterable[CablePin]) -> list[tuple[str, str, str, str]]:
    return [(str(item.pin), item.ihm09, item.steval, item.state) for item in items]


def draw_page_4(p: DualPage) -> None:
    p.frame(4, "Шлейф FC-34P 2×17, шаг 2.54 мм", "Прямой гнездо–гнездо: IHM09M2 J7 pin N соединяется со STEVAL J2 pin N")
    p.box(45, 650, 1080, 66, "Ориентация", ["Красная жила = pin 1. Ключи IDC-корпусов должны совпасть с выемками разъёмов.", "Перед подачей питания прозвонить 1->1, 2->2, ... 34->34 и отсутствие соседних замыканий. Не использовать rollover-кабель."], fill="#ffffff")
    p.text(302, 625, "Контакты 1...17", 10, bold=True, anchor="middle")
    p.text(855, 625, "Контакты 18...34", 10, bold=True, anchor="middle")
    p.table(42, 610, [34, 207, 178, 114], ["№", "IHM09M2 J7", "STEVAL J2", "состояние"], cable_half_rows(CABLE_PINS[:17]), row_h=25, size=6.8)
    p.table(595, 610, [34, 207, 178, 114], ["№", "IHM09M2 J7", "STEVAL J2", "состояние"], cable_half_rows(CABLE_PINS[17:]), row_h=25, size=6.8)
    p.rect(42, 115, 1081, 46, stroke=DANGER, fill=DANGER_FILL, width=1.0)
    p.text(55, 143, "Важно:", 8.5, color=DANGER, bold=True)
    p.text(105, 143, "NC означает отсутствие электрической связи на плате IHM09M2, но проводник в прямом шлейфе физически существует.", 7.8, color=DANGER)
    p.text(55, 123, "J7-28 = +3V3 подтверждён принципиальной схемой IHM09M2; J2-28 питает VDD_m STEVAL. J7-29/PWM VREF не используется.", 7.8, color=DANGER)
    p.finish()


def draw_page_5(p: DualPage) -> None:
    p.frame(5, "Силовое питание и питание управления", "Автономный soft-start расположен перед выпрямителем и не соединяется с GPIO")
    y = 625
    boxes = [
        (45, 120, "X1 230 VAC", ["L", "N", "PE"]),
        (190, 120, "QF1", ["2-полюсное", "отключение"]),
        (335, 120, "F1 + MOV", ["F1 по расчёту", "MOV после F1"]),
        (480, 155, "Soft-start", ["L_IN/N_IN", "L_OUT/N_OUT", "4×NTC + реле"]),
        (665, 120, "BR1", ["~  ~", "+  -"]),
        (810, 150, "DC-link", ["Cdc 450 V", "Rbleed HV", "измерить разряд"]),
        (995, 120, "STEVAL J7", ["1 = DC+", "2 = DC-"])
    ]
    for x, w, title, lines in boxes:
        p.box(x, y, w, 92, title, lines, fill="#ffffff", stroke=DANGER)
    for x1, x2, label in [(165, 190, "L/N"), (310, 335, "L/N"), (455, 480, "L/N"), (635, 665, "L/N"), (785, 810, "+/-"), (960, 995, "+/-")]:
        p.arrow(x1, y + 46, x2, y + 46, label, color=DANGER)
    p.line(105, y, 105, 545, color="#2e7d32", width=1.8)
    p.arrow(105, 545, 1085, 545, "PE -> металлический корпус и корпус двигателя", color="#2e7d32")

    p.box(45, 390, 220, 105, "PS1 — 15 V / >=30 W", ["вход после QF1/F1", "выход +15V / HOT_GND", "мощность уточнить измерением", "весь выход считать HOT"], fill=HOT_FILL, stroke=DANGER)
    p.box(305, 390, 180, 105, "STEVAL J4", ["positive <- +15V", "negative <- HOT_GND", "до 20 VDC", "проверить полярность"], fill=HOT_FILL, stroke=DANGER)
    p.box(525, 390, 180, 105, "UNO Q VIN", ["VIN <- +15V", "GND <- HOT_GND", "USB-C отключён", "плата внутри корпуса"], fill=HOT_FILL, stroke=DANGER)
    p.box(745, 390, 155, 105, "Buck 9 V", ["IN: +15V/GND", "OUT: 9V/GND", "настроить без", "нагрузки"], fill=HOT_FILL, stroke=DANGER)
    p.box(940, 390, 185, 105, "Nucleo VIN", ["VIN/CN7-24 <- 9V", "GND <- HOT_GND", "JP5 1-2", "E5V -> cable pin25"], fill=HOT_FILL, stroke=DANGER)
    p.line(265, 420, 285, 420, color=DANGER, width=1.5)
    p.line(285, 420, 285, 360, color=DANGER, width=1.5)
    p.line(285, 360, 823, 360, color=DANGER, width=1.5)
    p.text(555, 368, "+15V / HOT_GND distribution", 7.5, color=DANGER, bold=True, anchor="middle")
    p.arrow(395, 360, 395, 390, color=DANGER)
    p.arrow(615, 360, 615, 390, color=DANGER)
    p.arrow(823, 360, 823, 390, color=DANGER)
    p.arrow(900, 442, 940, 442, "9V", color=DANGER)

    p.box(45, 220, 335, 115, "DC-link", ["STEVAL-IPM15B не заменяет внешний bulk Cdc", "ёмкость и допустимый ripple — по расчёту", "Rbleed выполнить цепочкой HV-rated резисторов", "после OFF измерять <60 V перед касанием"], fill=DANGER_FILL, stroke=DANGER)
    p.box(425, 220, 335, 115, "Первый запуск", ["сначала низкое безопасное DC", "двигатель и 230 VAC отключены", "проверить UART/BKIN/PWM disabled", "затем отдельно проверить soft-start и DC bus"], fill=DANGER_FILL, stroke=DANGER)
    p.box(805, 220, 320, 115, "При 230 VAC", ["никакого USB/ST-Link к Nucleo", "никакого заземлённого осциллографа", "ограждение, PE, аварийное отключение", "работа квалифицированным персоналом"], fill=DANGER_FILL, stroke=DANGER)

    p.rect(45, 115, 1080, 54, stroke=DANGER, fill=DANGER_FILL, width=1.0)
    p.text(58, 146, "Нет управляющей линии soft-start:", 9, color=DANGER, bold=True)
    p.text(253, 146, "PB4 = NC; PC10/J2-21 не соединять с внешним модулем. Модуль самостоятельно шунтирует свои NTC внутренним реле.", 8.2, color=DANGER)
    p.text(58, 125, "На STEVAL: HOT_GND = J7 DC- (UM2014, общий опорный GND). PE и N с этой сетью не объединять; весь контур опасен.", 8.2, color=DANGER)
    p.finish()


def draw_page_6(p: DualPage) -> None:
    p.frame(6, "Двигатель AIR56B2 и датчик AS5600", "S1 запускается без датчика; AS5600 вводится позже как эталон этапа S3")
    p.box(55, 555, 260, 130, "STEVAL-IPM15B J3", ["J3-1 = phase A", "J3-2 = phase B", "J3-3 = phase C", "силовой кабель 3 фазы + PE", "направление меняют перестановкой 2 фаз"], fill=HOT_FILL, stroke=DANGER)
    p.box(455, 505, 310, 205, "AIR56B2, клеммная коробка", ["Верхний ряд: U1   V1   W1", "Нижний ряд: W2   U2   V2", "J3-1/A -> U1", "J3-2/B -> V1", "J3-3/C -> W1", "перемычка U1—W2", "перемычка V1—U2", "перемычка W1—V2", "PE -> отдельный винт корпуса"], fill="#ffffff", stroke=DANGER)
    p.arrow(315, 640, 455, 640, "A -> U1", color=DANGER)
    p.arrow(315, 605, 455, 605, "B -> V1", color=DANGER)
    p.arrow(315, 570, 455, 570, "C -> W1", color=DANGER)
    p.box(865, 555, 260, 130, "Номинальный режим S1", ["соединение: Δ 220 V", "частота: до 50 Hz", "1 пара полюсов", "0.25 kW; 1.24 A; 2720 rpm", "MCSDK phase-neutral: 127 V"], fill="#ffffff", stroke=DANGER)

    p.box(55, 300, 300, 135, "Arduino UNO Q QWIIC / HOT", ["+3V3 OUT", "GND / HOT_GND", "PD13 / I2C4_SDA", "PD12 / I2C4_SCL", "не использовать D0/D1 для датчика"], fill=HOT_FILL, stroke=DANGER)
    p.box(455, 300, 310, 135, "AS5600 module / HOT", ["VCC <- QWIIC +3V3", "GND <- QWIIC GND", "SDA <- PD13/I2C4_SDA", "SCL <- PD12/I2C4_SCL", "OUT, DIR = NC; pull-ups только один комплект"], fill=HOT_FILL, stroke=DANGER)
    p.arrow(355, 390, 455, 390, "SDA", color=DANGER)
    p.arrow(355, 360, 455, 360, "SCL", color=DANGER)
    p.arrow(355, 330, 455, 330, "3.3V/GND", color=DANGER)
    p.box(865, 300, 260, 135, "STEVAL J9", ["1 Hall1 / Encoder A", "2 Hall2 / Encoder B", "3 Hall3 / Encoder Z", "4 3.3/5 V; 5 GND", "для I2C AS5600 оставить NC"], fill="#ffffff")

    p.box(55, 155, 500, 95, "Этап S1", ["AS5600 и J9 не подключены. Nucleo выполняет бездатчиковое V/f.", "Цель — проверить направление, ток, температуру, Vbus и все защиты на ограниченном режиме."], fill="#ffffff")
    p.box(625, 155, 500, 95, "Этап S3", ["AS5600 подключается к QWIIC UNO Q и становится частью HOT-контура внутри корпуса.", "Перед влиянием AI на управление обязательны shadow-режим, сравнение и HIL-проверка fallback."], fill=HOT_FILL, stroke=DANGER)
    p.finish()


def draw_page_7(p: DualPage) -> None:
    p.frame(7, "Монтажный порядок и контроль", "Краткий маршрут сборки без чтения README")
    left = [
        "1. Проверить маркировку плат: G431RB, IHM09M2, IPM15B.",
        "2. Выставить IHM09M2 J1 OFF.",
        "3. Выставить STEVAL: SW3 2-3; SW1/2/4 1-2.",
        "4. STEVAL: SW5/6 open; SW7/8 closed.",
        "5. Установить IHM09M2 на CN7/CN10 Nucleo.",
        "6. Прозвонить FC-34P 1:1; отметить красную жилу pin 1.",
        "7. Соединить IHM09 J7 с STEVAL J2.",
        "8. Собрать прямой UART и общую HOT_GND внутри корпуса.",
        "9. Подать 15 V на J4/UNO Q и 9 V на VIN без J7/HV.",
        "10. Настроить station/AP, ключ HMI и автозапуск сервиса.",
    ]
    right = [
        "11. Собрать AIR56B2 треугольником 220 V.",
        "12. J3-1/2/3 -> U1/V1/W1; PE -> корпус.",
        "13. Собрать QF/F1/MOV/soft-start/BR1/DC-link.",
        "14. Проверить bleeder и измеряемое время разряда.",
        "15. Полностью убрать USB/ST-Link/Ethernet и приборы ПК.",
        "16. Первый силовой тест — ограниченный и ограждённый.",
        "17. Контролировать Vbus, ток, температуру, шум и вибрацию.",
        "18. При fault/тайм-ауте PWM обязан отключиться.",
        "19. AS5600 подключать только после принятия S1.",
        "20. Проверить останов при потере Wi-Fi/heartbeat; записать HIL.",
    ]
    p.box(45, 430, 520, 290, "Последовательность 1", left, fill="#ffffff")
    p.box(605, 430, 520, 290, "Последовательность 2", right, fill="#ffffff")

    rows = [
        ("UNO Q GND ↔ Nucleo GND", "< 1 Ω", "общая HOT_GND"),
        ("HOT_GND (= J7 DC-) ↔ PE", "обрыв", "до подключения сети"),
        ("FC-34P N ↔ N", "< 1 Ω", "все 34 контакта"),
        ("FC-34P N ↔ N±1", "обрыв", "нет соседних КЗ"),
        ("PB4", "NC", "никакого реле"),
        ("PC10/J2-21", "UNUSED", "нет внешнего soft-start control"),
        ("Потеря heartbeat", "STOP/ESTOP <=3 s", "испытать без нагрузки"),
        ("Аппаратный E-STOP", "снимает силовое разрешение", "не зависит от Wi-Fi/Linux"),
        ("DC-link после OFF", "измерить <60 V", "не полагаться только на таймер"),
    ]
    p.table(90, 390, [280, 250, 480], ["Проверка", "критерий", "примечание"], rows, row_h=20, size=7.4)

    p.box(45, 100, 1080, 70, "Источники распиновки", ["ST UM3030 Rev 1 — X-NUCLEO-IHM09M2; ST schematic pack X-NUCLEO-IHM09M2", "ST UM2014 Rev 3 — STEVAL-IPM15B; ST MCSDK 6.4.2 AC induction motor guide", "Arduino UNO Q datasheet/pinout ABX00162; текущие файлы проекта main.c и UNOQ_MCSDK_UART_CONTRACT_RU.md"], fill="#ffffff")
    p.finish()


def register_fonts() -> None:
    regular = Path("C:/Windows/Fonts/arial.ttf")
    bold = Path("C:/Windows/Fonts/arialbd.ttf")
    if not regular.exists() or not bold.exists():
        raise FileNotFoundError("Arial fonts are required for Cyrillic output")
    pdfmetrics.registerFont(TTFont("Arial", str(regular)))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(bold)))


def validate(connections: list[Connection]) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    pins = [item.pin for item in CABLE_PINS]
    if pins != list(range(1, 35)):
        errors.append("FC-34P map must contain pins 1..34 exactly once")
    if CABLE_PINS[27].state != "USED: 3.3 V POWER":
        errors.append("IHM09M2 J7-28 / STEVAL J2-28 power mapping is missing")
    if any("PB4" in row.source_contact or "PB4" in row.destination_contact for row in connections):
        errors.append("PB4 must stay unconnected")
    if not all(row.signal.startswith("HOT_") for row in connections if row.section == "AS5600_S3"):
        errors.append("AS5600 teacher must be explicitly marked as HOT")
    if not any(row.source_contact.startswith("D1") and "PB7 / CN7-21" in row.destination_contact for row in connections):
        errors.append("direct UNO Q TX -> Nucleo PB7 path is missing")
    if not any("PB6 / CN10-17" in row.source_contact and row.destination_contact.startswith("D0") for row in connections):
        errors.append("direct Nucleo PB6 -> UNO Q RX path is missing")
    if not any(row.section == "UART" and row.signal == "HOT_GND" for row in connections):
        errors.append("common UNO Q / Nucleo HOT_GND is missing")
    if not any(row.section == "HOT_REFERENCE" and row.signal == "HOT_GND_EQUALS_DC_MINUS" for row in connections):
        errors.append("STEVAL HOT_GND = J7 DC- internal reference is missing")
    if not any(item.pin == 21 and "UNUSED" in item.state for item in CABLE_PINS):
        errors.append("J2-21 must be explicitly unused")
    if not any(row.section == "PE" for row in connections):
        errors.append("protective earth connection is missing")
    warnings.append("Hardware HIL and mains safety acceptance remain external to document generation")
    return {
        "pass": not errors,
        "errors": errors,
        "warnings": warnings,
        "connection_count": len(connections),
        "cable_pin_count": len(CABLE_PINS),
    }


def write_csv(connections: list[Connection]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Section", "SourceRef", "SourceContact", "Signal", "DestinationRef", "DestinationContact", "State", "Note"])
        for row in connections:
            writer.writerow([row.section, row.source_ref, row.source_contact, row.signal, row.destination_ref, row.destination_contact, row.state, row.note])


def write_readme() -> None:
    README_PATH.write_text(
        r"""# MIC_AI: схема соединения Nucleo

Главный документ: `../../output/pdf/MIC_AI_NUCLEO_SYSTEM_WIRING.pdf`.

## Принятая архитектура

`Телефон/ноутбук <-Wi-Fi-> Arduino UNO Q -> прямой UART -> NUCLEO-G431RB -> X-NUCLEO-IHM09M2 -> FC-34P 1:1 -> STEVAL-IPM15B -> AIR56B2`.

- S1: бездатчиковое V/f, AIR56B2 соединён треугольником 220 В.
- AS5600 вводится только на S3 и подключается к QWIIC UNO Q; датчик и его кабель являются частью HOT-контура.
- Внешний soft-start автономный; управляющего провода от MCU нет.
- `PB4` не подключён; `PC10/J2-21` физически есть в 34-жильном шлейфе, но не используется прошивкой.
- UNO Q и Nucleo соединены прямым UART 3.3 В и общей `HOT_GND`; их шины 3.3 В не соединяются.
- На STEVAL `HOT_GND` электрически является `J7 DC-` (общая опорная точка VDC- по UM2014); это не SELV.
- При сетевом выпрямителе UNO Q, Nucleo, AS5600 и STEVAL являются HOT-стороной и находятся в закрытом корпусе.
- В силовом режиме наружу выходит только Wi-Fi. USB/ST-Link/Ethernet/HDMI разрешены только при физически снятом J7, отключённой сети и измеренно разряженном DC-link.
- HMI работает через существующий роутер (STA) или автономную WPA2-точку доступа UNO Q (AP); журналы хранятся на UNO Q и скачиваются через HMI.
- Команды и скачивание логов защищены отдельным ключом; потеря операторского heartbeat более 3 секунд вызывает STOP/ESTOP.

## Генерация

```powershell
& C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\tools\generate_nucleo_system_wiring.py
```

Генератор одновременно обновляет PDF, семь SVG-листов, CSV соединений и `manifest.json`.
""",
        encoding="utf-8",
    )


def write_pdf_and_svg() -> list[Path]:
    register_fonts()
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A3)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=(width, height), pageCompression=1)
    pdf.setTitle("MIC_AI Nucleo System Wiring")
    pdf.setAuthor("Codex / MIC_AI project")
    pages = [draw_page_1, draw_page_2, draw_page_3, draw_page_4, draw_page_5, draw_page_6, draw_page_7]
    svg_paths: list[Path] = []
    for index, draw in enumerate(pages, start=1):
        path = SVG_DIR / f"page_{index:02d}.svg"
        draw(DualPage(pdf, path, width, height))
        svg_paths.append(path)
    pdf.save()
    return svg_paths


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def render_png() -> list[Path]:
    candidates = [
        shutil.which("pdftoppm"),
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
        ),
    ]
    executable = next((item for item in candidates if item and Path(item).is_file()), None)
    if executable is None:
        raise FileNotFoundError("pdftoppm is required to render the seven PNG sheets")
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    prefix = PNG_DIR / "page"
    subprocess.run(
        [executable, "-png", "-r", "120", str(PDF_PATH), str(prefix)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    paths = [PNG_DIR / f"page-{index}.png" for index in range(1, TOTAL_PAGES + 1)]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError("PNG rendering did not create: " + ", ".join(missing))
    return paths


def generate() -> dict:
    connections = build_connections()
    validation = validate(connections)
    if not validation["pass"]:
        raise RuntimeError("; ".join(validation["errors"]))
    write_csv(connections)
    write_readme()
    svg_paths = write_pdf_and_svg()
    png_paths = render_png()
    files = [PDF_PATH, CSV_PATH, README_PATH, *svg_paths, *png_paths]
    manifest = {
        "document_code": DOCUMENT_CODE,
        "revision": REVISION,
        "date": REVISION_DATE,
        "architecture": "Phone/laptop <-Wi-Fi-> UNO Q -> direct UART -> NUCLEO-G431RB -> X-NUCLEO-IHM09M2 -> FC-34P -> STEVAL-IPM15B -> AIR56B2",
        "primary_pdf": str(PDF_PATH.relative_to(ROOT)).replace("\\", "/"),
        "validation": validation,
        "files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = generate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
