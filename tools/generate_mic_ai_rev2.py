#!/usr/bin/env python3
"""Generate the canonical MIC_AI revision 2 schematic artifacts.

The electrical model in this file is the single source of truth for the PDF,
SVG pages, EDIF netlist, BOM, connection list, and machine-readable manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "hardware" / "mic_ai_rev2"
SVG_DIR = OUT_DIR / "svg"
PDF_DIR = ROOT / "output" / "pdf"
PDF_PATH = PDF_DIR / "MIC_AI_REV2_SCHEMATIC.pdf"
EDIF_PATH = OUT_DIR / "MIC_AI_REV2_NETLIST.edif"
BOM_PATH = OUT_DIR / "MIC_AI_REV2_BOM.csv"
CONNECTIONS_PATH = OUT_DIR / "MIC_AI_REV2_CONNECTIONS.csv"
PINMAP_PATH = OUT_DIR / "MIC_AI_REV2_PINMAP.csv"
MANIFEST_PATH = OUT_DIR / "manifest.json"
ASSEMBLY_PATH = OUT_DIR / "ASSEMBLY_RU.md"

REVISION = "2.1"
REVISION_DATE = "2026-07-17"
TOTAL_PAGES = 6


@dataclass(frozen=True)
class Component:
    ref: str
    value: str
    ports: tuple[str, ...]
    footprint: str
    domain: str
    note: str = ""
    populate: str = "YES"


@dataclass
class ElectricalModel:
    components: dict[str, Component] = field(default_factory=dict)
    nets: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def add(self, component: Component) -> None:
        if component.ref in self.components:
            raise ValueError(f"duplicate component: {component.ref}")
        if len(component.ports) != len(set(component.ports)):
            raise ValueError(f"duplicate port in {component.ref}")
        self.components[component.ref] = component

    def connect(self, name: str, *endpoints: tuple[str, str]) -> None:
        if name in self.nets:
            raise ValueError(f"duplicate net: {name}")
        self.nets[name] = list(endpoints)

    def validate(self) -> dict:
        endpoint_owner: dict[tuple[str, str], str] = {}
        errors: list[str] = []
        warnings: list[str] = []

        for net_name, endpoints in self.nets.items():
            if len(endpoints) < 2:
                errors.append(f"net {net_name} has fewer than two endpoints")
            for ref, port in endpoints:
                component = self.components.get(ref)
                if component is None:
                    errors.append(f"net {net_name} references missing component {ref}")
                    continue
                if port not in component.ports:
                    errors.append(f"net {net_name} references missing port {ref}.{port}")
                    continue
                key = (ref, port)
                previous = endpoint_owner.get(key)
                if previous and previous != net_name:
                    errors.append(f"endpoint {ref}.{port} is in {previous} and {net_name}")
                endpoint_owner[key] = net_name

        required_nets = {
            "AC_L",
            "AC_L_FUSED",
            "AC_N",
            "PE_CHASSIS",
            "RECT_DC_PLUS",
            "HV_DC_PLUS",
            "HV_DC_MINUS_HOT_GND",
            "SAFE_GND",
            "PB4_PRECHARGE",
            "SAFE_UART_TX",
            "SAFE_UART_RX",
        }
        missing = sorted(required_nets - self.nets.keys())
        if missing:
            errors.append(f"missing required nets: {', '.join(missing)}")

        forbidden_same_nets = [
            ("AC_N", "HV_DC_MINUS_HOT_GND"),
            ("SAFE_GND", "HV_DC_MINUS_HOT_GND"),
            ("SAFE_GND", "AC_N"),
            ("PE_CHASSIS", "HV_DC_MINUS_HOT_GND"),
        ]
        for left, right in forbidden_same_nets:
            if left == right:
                errors.append(f"forbidden merged domains: {left} and {right}")

        def endpoint_net(ref: str, port: str) -> str | None:
            return endpoint_owner.get((ref, port))

        invariants = {
            "bridge_ac1_is_fused_line": endpoint_net("BR1", "AC1") == "AC_L_FUSED",
            "bridge_ac2_is_neutral": endpoint_net("BR1", "AC2") == "AC_N",
            "bridge_minus_is_hot_ground": endpoint_net("BR1", "MINUS") == "HV_DC_MINUS_HOT_GND",
            "bridge_plus_is_rectified_plus": endpoint_net("BR1", "PLUS") == "RECT_DC_PLUS",
            "precharge_is_pb4": endpoint_net("U_BP", "PB4") == "PB4_PRECHARGE",
            "steval_j2_21_is_nc": endpoint_net("U_BP", "PB1") is None
            and endpoint_net("J_STEVAL_J2", "P21") is None,
            "unoq_power_uses_vin": endpoint_net("U_UNOQ", "VIN") == "SAFE_VIN_7_24V",
            "unoq_5v_not_backfed": endpoint_net("U_UNOQ", "5V_USB") is None,
            "unoq_3v3_is_output_only": endpoint_net("U_UNOQ", "OUT_3V3") == "UNOQ_3V3_OUT",
            "bluepill_5v_not_driven": endpoint_net("U_BP", "5V") is None,
            "bluepill_3v3_driven": endpoint_net("U_BP", "3V3") == "HOT_3V3",
            "hot_15v_sources_are_selected": endpoint_net("PS1", "VOUT") == "ONBOARD_HOT_15V"
            and endpoint_net("J_HOT15_EXT", "PLUS") == "EXTERNAL_HOT_15V"
            and endpoint_net("JP_HOT15_SRC", "COMMON") == "HOT_15V",
            "fan_uses_standard_4wire_power": endpoint_net("J_FAN", "V12") == "HOT_12V"
            and endpoint_net("J_FAN", "PWM") == "FAN_PWM_OC",
            "safe_ground_isolated": endpoint_net("U_UART_ISO", "GND_SAFE") == "SAFE_GND"
            and endpoint_net("U_UART_ISO", "GND_HOT") == "HV_DC_MINUS_HOT_GND",
            "saleae_outputs_explicitly_enabled": endpoint_net("U_LA1", "EN_SAFE") == "SAFE_3V3"
            and endpoint_net("U_LA2", "EN_SAFE") == "SAFE_3V3",
        }
        for name, ok in invariants.items():
            if not ok:
                errors.append(f"invariant failed: {name}")

        j2_ground_pins = (2, 4, 6, 8, 10, 12, 16, 18, 20, 22, 24, 30, 32)
        missing_j2_grounds = [
            pin
            for pin in j2_ground_pins
            if endpoint_net("J_STEVAL_J2", f"P{pin}") != "HV_DC_MINUS_HOT_GND"
        ]
        if missing_j2_grounds:
            errors.append(f"unconnected STEVAL J2 grounds: {missing_j2_grounds}")

        safe_refs = {ref for ref, comp in self.components.items() if comp.domain == "SAFE"}
        hot_refs = {ref for ref, comp in self.components.items() if comp.domain in {"HOT", "HV"}}
        barrier_refs = {ref for ref, comp in self.components.items() if comp.domain == "BARRIER"}
        domain_crossings: list[str] = []
        for net_name, endpoints in self.nets.items():
            refs = {ref for ref, _ in endpoints}
            has_safe = bool(refs & safe_refs)
            has_hot = bool(refs & hot_refs)
            if has_safe and has_hot and not (refs & barrier_refs):
                domain_crossings.append(net_name)
        if domain_crossings:
            errors.append(f"unisolated SAFE/HOT crossings: {sorted(domain_crossings)}")

        intentional_nc = {
            ("U_BP", "5V"),
            ("U_BP", "PB1"),
            ("U_UNOQ", "5V_USB"),
            ("J_STEVAL_J2", "P21"),
            ("J_STEVAL_J2", "P34"),
        }
        unconnected = {
            (component.ref, port)
            for component in self.components.values()
            for port in component.ports
            if (component.ref, port) not in endpoint_owner
        }
        unexpected_unconnected = sorted(unconnected - intentional_nc)
        missing_intentional_nc = sorted(intentional_nc - unconnected)
        if unexpected_unconnected:
            errors.append(f"unexpected unconnected ports: {unexpected_unconnected}")
        if missing_intentional_nc:
            errors.append(f"ports expected NC are connected: {missing_intentional_nc}")

        if "F1_VALUE_BY_LOAD" not in self.components["F1"].value:
            warnings.append("F1 should remain explicitly load-dependent until motor current is known")

        return {
            "pass": not errors,
            "errors": errors,
            "warnings": warnings,
            "invariants": invariants,
            "component_count": len(self.components),
            "net_count": len(self.nets),
            "connected_endpoint_count": len(endpoint_owner),
            "intentional_nc": [f"{ref}.{port}" for ref, port in sorted(intentional_nc)],
        }


def comp(
    ref: str,
    value: str,
    ports: Iterable[str],
    footprint: str,
    domain: str,
    note: str = "",
    populate: str = "YES",
) -> Component:
    return Component(ref, value, tuple(ports), footprint, domain, note, populate)


def build_model() -> ElectricalModel:
    m = ElectricalModel()

    # Mains, rectifier, precharge, and HV bus.
    m.add(comp("J_AC_IN", "230VAC INPUT", ("L", "N", "PE"), "TerminalBlock_1x03_P7.62mm", "HV"))
    m.add(comp("F1", "F1_VALUE_BY_LOAD slow-blow 250VAC", ("1", "2"), "Fuse_5x20mm", "HV"))
    m.add(comp("MOV1", "S14K300", ("1", "2"), "MOV_D14mm", "HV", "Must be after F1"))
    m.add(comp("BR1", "KBPC5010", ("AC1", "AC2", "PLUS", "MINUS"), "KBPC", "HV", "Verify body marks + - ~ ~"))
    m.add(comp("RPRE1", "20R 25W pulse-rated", ("1", "2"), "Chassis_Resistor_25W", "HV"))
    m.add(comp("RPRE2", "20R 25W pulse-rated", ("1", "2"), "Chassis_Resistor_25W", "HV"))
    m.add(comp("K1", "TE Mini K HV 2-1904058-5, 12V coil, 400VDC/20A", ("COM", "NO", "COIL_PLUS", "COIL_LOW"), "TE_2-1904058-5", "HV"))
    m.add(comp("Q1", "AO3400A (AOS)", ("G", "D", "S"), "SOT-23", "HOT", "Pin 1 G, pin 2 S, pin 3 D"))
    m.add(comp("R_Q1_GATE", "100R", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_Q1_PD", "100K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("D_K1", "SS14", ("A", "K"), "SMA", "HOT", "Cathode to HOT_12V"))
    m.add(comp("C_HV", "220uF 450V, optional if STEVAL C1 fitted", ("PLUS", "MINUS"), "Electrolytic_SnapIn", "HV", populate="VERIFY"))
    for index in range(1, 5):
        m.add(comp(f"RB{index}", "100K 0.5W HV-rated", ("1", "2"), "R_Axial_10mm", "HV"))
    m.add(comp("J_J7", "TO STEVAL J7", ("PLUS", "MINUS"), "TerminalBlock_1x02_P10.16mm", "HV"))
    m.add(comp("J_PE", "PE / CHASSIS / MOTOR FRAME", ("PE",), "Ring_Lug_M4", "HV"))

    # Hot-side power. Its ground is intentionally the negative DC bus.
    m.add(comp("PS1", "HLK-20M15", ("AC1", "AC2", "VOUT", "GND_OUT"), "HLK-20M15", "BARRIER", "Output is HOT, not SELV"))
    m.add(comp("J_HOT15_EXT", "ISOLATED 15V BENCH INPUT - HV OFF", ("PLUS", "RETURN"), "TerminalBlock_1x02_P5.08mm", "HOT"))
    m.add(comp("JP_HOT15_SRC", "ONBOARD/EXTERNAL 15V SELECT", ("COMMON", "ONBOARD", "EXTERNAL"), "Jumper_1x03_P2.54mm", "HOT", "Fit exactly one source position"))
    m.add(comp("U_BUCK12", "15V to 12V, >=2A", ("IN", "GND", "OUT"), "Buck_Module", "HOT"))
    m.add(comp("U_BUCK5", "15V to 5V, >=1A", ("IN", "GND", "OUT"), "Buck_Module", "HOT"))
    m.add(comp("U_BUCK3V3", "15V to 3.3V, >=1A", ("IN", "GND", "OUT"), "Buck_Module", "HOT"))
    m.add(comp("J_STEVAL_J4", "STEVAL J4 AUX", ("PLUS", "RETURN"), "TerminalBlock_1x02_P5.08mm", "HOT"))

    # Controller and STEVAL connector.
    bp_ports = (
        "3V3", "5V", "GND", "PA0", "PA1", "PA2", "PA3", "PA4", "PA5", "PA6", "PA7",
        "PA8", "PA9", "PA10", "PA11", "PA13", "PA14", "PB0", "PB1", "PB3", "PB4", "PB5",
        "PB9", "PB10", "PB11", "PB12", "PB13", "PB14", "PB15", "NRST",
    )
    m.add(comp("U_BP", "Blue Pill STM32F103C8T6", bp_ports, "BluePill_2x20", "HOT", "5V pin intentionally NC"))
    m.add(comp("J_STEVAL_J2", "STEVAL-IPM15B J2", tuple(f"P{i}" for i in range(1, 35)), "IDC_2x17_P2.54mm", "HOT"))

    pwm_map = (
        ("R_PWM_UH", "PA8", 3, "PWM_UH"),
        ("R_PWM_UL", "PB13", 5, "PWM_UL"),
        ("R_PWM_VH", "PA9", 7, "PWM_VH"),
        ("R_PWM_VL", "PB14", 9, "PWM_VL"),
        ("R_PWM_WH", "PA10", 11, "PWM_WH"),
        ("R_PWM_WL", "PB15", 13, "PWM_WL"),
    )
    for ref, _, _, _ in pwm_map:
        m.add(comp(ref, "33R", ("1", "2"), "R_0603", "HOT"))
        m.add(comp(f"{ref}_PD", "47K", ("1", "2"), "R_0603", "HOT", "Default LOW during reset"))

    analog_map = (
        ("R_ADC_VBUS", "PA5", 14, "ADC_VBUS"),
        ("R_ADC_IA", "PA0", 15, "ADC_IA"),
        ("R_ADC_IB", "PA1", 17, "ADC_IB"),
        ("R_ADC_IC", "PA4", 19, "ADC_IC"),
        ("R_ADC_TEMP", "PB0", 26, "ADC_TEMP"),
        ("R_ADC_PHASE_A", "PA6", 31, "ADC_PHASE_A"),
        ("R_ADC_PHASE_B", "PA7", 33, "ADC_PHASE_B"),
    )
    for ref, _, _, _ in analog_map:
        m.add(comp(ref, "100R", ("1", "2"), "R_0603", "HOT"))

    for ref in ("R_PFC", "R_BRAKE"):
        m.add(comp(ref, "100R", ("1", "2"), "R_0603", "HOT"))
        m.add(comp(f"{ref}_PD", "47K", ("1", "2"), "R_0603", "HOT", "Default LOW during reset"))

    # Safe-side HMI and selectable PC-direct UART.
    uno_ports = ("VIN", "GND", "OUT_3V3", "5V_USB", "TX_D1", "RX_D0")
    m.add(comp("U_UNOQ", "Arduino UNO Q", uno_ports, "UNO_Q_HEADERS", "SAFE", "Power only through VIN 7-24V or USB-C"))
    m.add(comp("J_SAFE_DC_IN", "UNO Q SAFE 7-24V", ("VIN", "GND"), "TerminalBlock_1x02_P5.08mm", "SAFE"))
    m.add(comp("J_PC_UART", "USB-UART SAFE SIDE, 3.3V LOGIC", ("TX", "RX", "GND"), "Header_1x03_P2.54mm", "SAFE", "Do not connect adapter power pin"))
    m.add(comp("JP_UART_TX", "UNOQ/PC TX SELECT", ("COMMON", "UNO", "PC"), "Jumper_1x03", "SAFE"))
    m.add(comp("JP_UART_RX", "UNOQ/PC RX SELECT", ("COMMON", "UNO", "PC"), "Jumper_1x03", "SAFE"))
    m.add(comp("JP_SAFE_3V3", "UNOQ/EXT 3V3 SELECT", ("COMMON", "UNO", "EXT"), "Jumper_1x03", "SAFE"))
    m.add(comp("J_SAFE_3V3", "SAFE 3.3V INPUT", ("V3V3", "GND"), "Header_1x02_P2.54mm", "SAFE"))
    m.add(comp("J_SAFE_5V", "SAFE 5V FOR E-STOP LOOP", ("V5", "GND"), "Header_1x02_P2.54mm", "SAFE"))

    iso_uart_ports = ("VCC_SAFE", "GND_SAFE", "TX_SAFE_IN", "RX_SAFE_OUT", "VCC_HOT", "GND_HOT", "RX_HOT_OUT", "TX_HOT_IN")
    m.add(comp("U_UART_ISO", "ISO7721DWR reinforced 1/1 UART isolator", iso_uart_ports, "SOIC-16W", "BARRIER"))
    for ref, domain in (("C_UART_SAFE", "SAFE"), ("C_UART_HOT", "HOT")):
        m.add(comp(ref, "100nF", ("1", "2"), "C_0603", domain))
    m.add(comp("R_UART_TX_PU", "47K", ("1", "2"), "R_0603", "SAFE", "UART idle HIGH if selector is open"))

    # Isolated Saleae monitor: eight hot-to-safe channels.
    iso_la_ports = ("VCC_HOT", "GND_HOT", "HI1", "HI2", "HI3", "HI4", "VCC_SAFE", "GND_SAFE", "EN_SAFE", "SO1", "SO2", "SO3", "SO4")
    m.add(comp("U_LA1", "ISO7740FDWR reinforced 4/0 monitor", iso_la_ports, "SOIC-16W", "BARRIER"))
    m.add(comp("U_LA2", "ISO7740FDWR reinforced 4/0 monitor", iso_la_ports, "SOIC-16W", "BARRIER"))
    m.add(comp("J_SALEAE", "SAFE ISOLATED SALEAE", tuple([f"CH{i}" for i in range(8)] + ["GND"]), "Header_1x09_P2.54mm", "SAFE"))
    for ref, domain in (("C_LA1_SAFE", "SAFE"), ("C_LA1_HOT", "HOT"), ("C_LA2_SAFE", "SAFE"), ("C_LA2_HOT", "HOT")):
        m.add(comp(ref, "100nF", ("1", "2"), "C_0603", domain))

    # Fail-safe external E-stop loop. Loss of SAFE_5V or broken loop forces stop.
    m.add(comp("J_ESTOP", "NC PWM-INHIBIT LOOP / E-STOP AUX CONTACT", ("OUT", "RETURN"), "TerminalBlock_1x02_P5.08mm", "SAFE", "Not a substitute for a mains safety contactor"))
    m.add(comp("R_ESTOP_LED", "680R", ("1", "2"), "R_0603", "SAFE"))
    m.add(comp("U_ESTOP_OPTO", "LTV-817", ("LED_A", "LED_K", "C", "E"), "DIP-4_W7.62mm", "BARRIER"))
    m.add(comp("R_ESTOP_PULL", "10K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("U_ESTOP_INV", "SN74LVC1G14DBVR", ("VCC", "GND", "A", "Y"), "SOT-23-5_DBV", "HOT"))
    m.add(comp("U_ESTOP_AND", "SN74LVC1G08DBVR", ("VCC", "GND", "A", "B", "Y"), "SOT-23-5_DBV", "HOT"))
    m.add(comp("R_ESTOP_OUT", "220R", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_ESTOP_PD", "47K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_PB12_PD", "47K", ("1", "2"), "R_0603", "HOT", "RUN command defaults LOW during MCU reset"))
    m.add(comp("C_ESTOP_INV", "100nF", ("1", "2"), "C_0603", "HOT"))
    m.add(comp("C_ESTOP_AND", "100nF", ("1", "2"), "C_0603", "HOT"))

    # Standard four-wire PWM fan. A three-wire fan on pins 1..3 runs full speed.
    m.add(comp("Q_FAN_N", "MMBT2222A-7-F (Diodes Inc.)", ("B", "C", "E"), "SOT-23", "HOT", "Pin 1 B, pin 2 E, pin 3 C"))
    m.add(comp("R_FAN_BASE", "1K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_FAN_BPD", "47K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_TACH_SER", "1K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("R_TACH_PU", "10K", ("1", "2"), "R_0603", "HOT"))
    m.add(comp("C_FAN_BULK", "100uF 25V", ("PLUS", "MINUS"), "Electrolytic_Radial", "HOT", "Place at fan header"))
    m.add(comp("C_FAN_HF", "100nF 25V", ("1", "2"), "C_1206", "HOT", "Place at fan header"))
    m.add(comp("J_FAN", "4-PIN PWM FAN; 3-PIN = FULL SPEED", ("GND", "V12", "TACH", "PWM"), "Fan_Header_1x04_P2.54mm", "HOT", "Pin order: GND, +12V, TACH, PWM"))

    # Encoder and hot-side debug.
    m.add(comp("J_AS5600", "AS5600 I2C", ("SCL", "SDA", "VCC", "GND"), "Header_1x04_P2.54mm", "HOT", "Inside insulated HV enclosure"))
    m.add(comp("R_SCL_PU", "4.7K DNP if module fitted", ("1", "2"), "R_0603", "HOT", populate="DNP"))
    m.add(comp("R_SDA_PU", "4.7K DNP if module fitted", ("1", "2"), "R_0603", "HOT", populate="DNP"))
    m.add(comp("J_SWD", "HOT SWD - HV OFF ONLY", ("VREF", "SWDIO", "SWCLK", "GND", "NRST"), "Header_1x05_P2.54mm", "HOT"))

    # HV and power nets.
    m.connect("AC_L", ("J_AC_IN", "L"), ("F1", "1"))
    m.connect("AC_L_FUSED", ("F1", "2"), ("MOV1", "1"), ("BR1", "AC1"), ("PS1", "AC1"))
    m.connect("AC_N", ("J_AC_IN", "N"), ("MOV1", "2"), ("BR1", "AC2"), ("PS1", "AC2"))
    m.connect("PE_CHASSIS", ("J_AC_IN", "PE"), ("J_PE", "PE"))
    m.connect("RECT_DC_PLUS", ("BR1", "PLUS"), ("RPRE1", "1"), ("K1", "COM"))
    m.connect("PRECHARGE_MID", ("RPRE1", "2"), ("RPRE2", "1"))
    m.connect("HV_DC_PLUS", ("RPRE2", "2"), ("K1", "NO"), ("C_HV", "PLUS"), ("RB1", "1"), ("J_J7", "PLUS"))
    m.connect("BLEEDER_1", ("RB1", "2"), ("RB2", "1"))
    m.connect("BLEEDER_2", ("RB2", "2"), ("RB3", "1"))
    m.connect("BLEEDER_3", ("RB3", "2"), ("RB4", "1"))

    hot_ground_endpoints = [
        ("BR1", "MINUS"), ("C_HV", "MINUS"), ("RB4", "2"), ("J_J7", "MINUS"),
        ("PS1", "GND_OUT"), ("J_HOT15_EXT", "RETURN"),
        ("U_BUCK12", "GND"), ("U_BUCK5", "GND"), ("U_BUCK3V3", "GND"),
        ("J_STEVAL_J4", "RETURN"), ("U_BP", "GND"), ("Q1", "S"), ("R_Q1_PD", "2"),
        ("U_UART_ISO", "GND_HOT"), ("C_UART_HOT", "2"),
        ("U_LA1", "GND_HOT"), ("U_LA2", "GND_HOT"), ("C_LA1_HOT", "2"), ("C_LA2_HOT", "2"),
        ("U_ESTOP_OPTO", "E"), ("U_ESTOP_INV", "GND"), ("U_ESTOP_AND", "GND"),
        ("R_ESTOP_PD", "2"), ("R_PB12_PD", "2"), ("C_ESTOP_INV", "2"), ("C_ESTOP_AND", "2"),
        ("Q_FAN_N", "E"), ("R_FAN_BPD", "2"), ("J_FAN", "GND"),
        ("C_FAN_BULK", "MINUS"), ("C_FAN_HF", "2"), ("J_AS5600", "GND"), ("J_SWD", "GND"),
    ]
    for pin in (2, 4, 6, 8, 10, 12, 16, 18, 20, 22, 24, 30, 32):
        hot_ground_endpoints.append(("J_STEVAL_J2", f"P{pin}"))
    for ref, _, _, _ in pwm_map:
        hot_ground_endpoints.append((f"{ref}_PD", "2"))
    for ref in ("R_PFC", "R_BRAKE"):
        hot_ground_endpoints.append((f"{ref}_PD", "2"))
    m.connect("HV_DC_MINUS_HOT_GND", *hot_ground_endpoints)

    m.connect("ONBOARD_HOT_15V", ("PS1", "VOUT"), ("JP_HOT15_SRC", "ONBOARD"))
    m.connect("EXTERNAL_HOT_15V", ("J_HOT15_EXT", "PLUS"), ("JP_HOT15_SRC", "EXTERNAL"))
    m.connect("HOT_15V", ("JP_HOT15_SRC", "COMMON"), ("U_BUCK12", "IN"), ("U_BUCK5", "IN"), ("U_BUCK3V3", "IN"), ("J_STEVAL_J4", "PLUS"))
    m.connect("HOT_12V", ("U_BUCK12", "OUT"), ("K1", "COIL_PLUS"), ("D_K1", "K"), ("J_FAN", "V12"), ("C_FAN_BULK", "PLUS"), ("C_FAN_HF", "1"))
    m.connect("HOT_5V", ("U_BUCK5", "OUT"), ("J_STEVAL_J2", "P25"))
    hot_3v3_eps = [
        ("U_BUCK3V3", "OUT"), ("U_BP", "3V3"), ("J_STEVAL_J2", "P28"), ("J_STEVAL_J2", "P29"),
        ("U_UART_ISO", "VCC_HOT"), ("C_UART_HOT", "1"),
        ("U_LA1", "VCC_HOT"), ("U_LA2", "VCC_HOT"), ("C_LA1_HOT", "1"), ("C_LA2_HOT", "1"),
        ("R_ESTOP_PULL", "1"), ("U_ESTOP_INV", "VCC"), ("U_ESTOP_AND", "VCC"),
        ("C_ESTOP_INV", "1"), ("C_ESTOP_AND", "1"), ("R_TACH_PU", "1"),
        ("J_AS5600", "VCC"), ("R_SCL_PU", "1"), ("R_SDA_PU", "1"), ("J_SWD", "VREF"),
    ]
    m.connect("HOT_3V3", *hot_3v3_eps)

    # Precharge relay driver.
    m.connect("PB4_PRECHARGE", ("U_BP", "PB4"), ("R_Q1_GATE", "1"), ("U_LA2", "HI4"))
    m.connect("Q1_GATE", ("R_Q1_GATE", "2"), ("Q1", "G"), ("R_Q1_PD", "1"))
    m.connect("K1_COIL_LOW", ("K1", "COIL_LOW"), ("Q1", "D"), ("D_K1", "A"))

    # PWM with series resistors and isolated monitor taps at the STEVAL side.
    for ref, bp_pin, j2_pin, signal in pwm_map:
        m.connect(f"BP_{bp_pin}_RAW", ("U_BP", bp_pin), (ref, "1"))
        la_ref, la_port = {
            "PWM_UH": ("U_LA1", "HI1"),
            "PWM_UL": ("U_LA1", "HI2"),
            "PWM_VH": ("U_LA1", "HI3"),
            "PWM_VL": ("U_LA1", "HI4"),
            "PWM_WH": ("U_LA2", "HI1"),
            "PWM_WL": ("U_LA2", "HI2"),
        }[signal]
        m.connect(signal, (ref, "2"), ("J_STEVAL_J2", f"P{j2_pin}"), (la_ref, la_port), (f"{ref}_PD", "1"))

    # ADC feedback lines.
    for ref, bp_pin, j2_pin, signal in analog_map:
        m.connect(f"STEVAL_{signal}", ("J_STEVAL_J2", f"P{j2_pin}"), (ref, "1"))
        m.connect(signal, (ref, "2"), ("U_BP", bp_pin))

    m.connect("PB5_PFC_SYNC", ("U_BP", "PB5"), ("R_PFC", "1"))
    m.connect("PFC_TO_STEVAL", ("R_PFC", "2"), ("J_STEVAL_J2", "P27"), ("R_PFC_PD", "1"))
    m.connect("PB9_BRAKE_PWM", ("U_BP", "PB9"), ("R_BRAKE", "1"))
    m.connect("BRAKE_TO_STEVAL", ("R_BRAKE", "2"), ("J_STEVAL_J2", "P23"), ("R_BRAKE_PD", "1"))

    # Safe-side power and selectable command source.
    safe_ground_eps = [
        ("U_UNOQ", "GND"), ("J_SAFE_DC_IN", "GND"), ("J_PC_UART", "GND"),
        ("J_SAFE_3V3", "GND"), ("J_SAFE_5V", "GND"), ("U_UART_ISO", "GND_SAFE"),
        ("C_UART_SAFE", "2"), ("U_LA1", "GND_SAFE"), ("U_LA2", "GND_SAFE"),
        ("C_LA1_SAFE", "2"), ("C_LA2_SAFE", "2"), ("J_SALEAE", "GND"),
        ("U_ESTOP_OPTO", "LED_K"),
    ]
    m.connect("SAFE_GND", *safe_ground_eps)
    m.connect("SAFE_VIN_7_24V", ("J_SAFE_DC_IN", "VIN"), ("U_UNOQ", "VIN"))
    m.connect("UNOQ_3V3_OUT", ("U_UNOQ", "OUT_3V3"), ("JP_SAFE_3V3", "UNO"))
    m.connect("EXT_SAFE_3V3", ("J_SAFE_3V3", "V3V3"), ("JP_SAFE_3V3", "EXT"))
    safe_3v3_eps = [
        ("JP_SAFE_3V3", "COMMON"), ("U_UART_ISO", "VCC_SAFE"), ("C_UART_SAFE", "1"),
        ("U_LA1", "VCC_SAFE"), ("U_LA2", "VCC_SAFE"), ("C_LA1_SAFE", "1"), ("C_LA2_SAFE", "1"),
        ("U_LA1", "EN_SAFE"), ("U_LA2", "EN_SAFE"),
        ("R_UART_TX_PU", "1"),
    ]
    m.connect("SAFE_3V3", *safe_3v3_eps)
    m.connect("UNOQ_TX", ("U_UNOQ", "TX_D1"), ("JP_UART_TX", "UNO"))
    m.connect("PC_TX", ("J_PC_UART", "TX"), ("JP_UART_TX", "PC"))
    m.connect("SAFE_UART_TX", ("JP_UART_TX", "COMMON"), ("U_UART_ISO", "TX_SAFE_IN"), ("R_UART_TX_PU", "2"))
    m.connect("UNOQ_RX", ("U_UNOQ", "RX_D0"), ("JP_UART_RX", "UNO"))
    m.connect("PC_RX", ("J_PC_UART", "RX"), ("JP_UART_RX", "PC"))
    m.connect("SAFE_UART_RX", ("JP_UART_RX", "COMMON"), ("U_UART_ISO", "RX_SAFE_OUT"))
    m.connect("BP_RX_PA3", ("U_UART_ISO", "RX_HOT_OUT"), ("U_BP", "PA3"))
    m.connect("BP_TX_PA2", ("U_BP", "PA2"), ("U_UART_ISO", "TX_HOT_IN"))

    # Isolated Saleae outputs.
    for channel, iso_ref, iso_port in (
        (0, "U_LA1", "SO1"), (1, "U_LA1", "SO2"), (2, "U_LA1", "SO3"), (3, "U_LA1", "SO4"),
        (4, "U_LA2", "SO1"), (5, "U_LA2", "SO2"), (6, "U_LA2", "SO3"), (7, "U_LA2", "SO4"),
    ):
        m.connect(f"SAFE_LA_CH{channel}", (iso_ref, iso_port), ("J_SALEAE", f"CH{channel}"))

    # Fail-safe E-stop: PB12 high and loop healthy are both required to release shutdown.
    m.connect("SAFE_5V", ("J_SAFE_5V", "V5"), ("J_ESTOP", "OUT"))
    m.connect("ESTOP_LOOP_RETURN", ("J_ESTOP", "RETURN"), ("R_ESTOP_LED", "1"))
    m.connect("ESTOP_LED_A", ("R_ESTOP_LED", "2"), ("U_ESTOP_OPTO", "LED_A"))
    m.connect("ESTOP_N", ("R_ESTOP_PULL", "2"), ("U_ESTOP_OPTO", "C"), ("U_ESTOP_INV", "A"))
    m.connect("ESTOP_OK", ("U_ESTOP_INV", "Y"), ("U_ESTOP_AND", "B"))
    m.connect("PB12_RUN", ("U_BP", "PB12"), ("U_ESTOP_AND", "A"), ("U_LA2", "HI3"), ("R_PB12_PD", "1"))
    m.connect("ESTOP_GATE_OUT", ("U_ESTOP_AND", "Y"), ("R_ESTOP_OUT", "1"))
    m.connect("EM_STOP_TO_STEVAL", ("R_ESTOP_OUT", "2"), ("R_ESTOP_PD", "1"), ("J_STEVAL_J2", "P1"))

    # Four-wire fan control. NPN open collector inverts PB3; timer polarity compensates.
    m.connect("PB3_FAN_PWM", ("U_BP", "PB3"), ("R_FAN_BASE", "1"))
    m.connect("FAN_NPN_BASE", ("R_FAN_BASE", "2"), ("Q_FAN_N", "B"), ("R_FAN_BPD", "1"))
    m.connect("FAN_PWM_OC", ("Q_FAN_N", "C"), ("J_FAN", "PWM"))
    m.connect("FAN_TACH_RAW", ("J_FAN", "TACH"), ("R_TACH_SER", "1"), ("R_TACH_PU", "2"))
    m.connect("PA11_FAN_TACH", ("R_TACH_SER", "2"), ("U_BP", "PA11"))

    # Encoder and debug.
    m.connect("PB10_AS5600_SCL", ("U_BP", "PB10"), ("J_AS5600", "SCL"), ("R_SCL_PU", "2"))
    m.connect("PB11_AS5600_SDA", ("U_BP", "PB11"), ("J_AS5600", "SDA"), ("R_SDA_PU", "2"))
    m.connect("PA13_SWDIO", ("U_BP", "PA13"), ("J_SWD", "SWDIO"))
    m.connect("PA14_SWCLK", ("U_BP", "PA14"), ("J_SWD", "SWCLK"))
    m.connect("NRST", ("U_BP", "NRST"), ("J_SWD", "NRST"))

    return m


class DualPage:
    def __init__(self, pdf: canvas.Canvas, svg_path: Path, width: float, height: float):
        self.pdf = pdf
        self.width = width
        self.height = height
        self.svg_path = svg_path
        self.svg: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]

    def _sy(self, y: float) -> float:
        return self.height - y

    @staticmethod
    def _color(value: str) -> colors.Color:
        return colors.HexColor(value)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = "#172126", width: float = 1.5, dash: tuple[int, ...] | None = None) -> None:
        self.pdf.setStrokeColor(self._color(color))
        self.pdf.setLineWidth(width)
        self.pdf.setDash(dash or [])
        self.pdf.line(x1, y1, x2, y2)
        dash_attr = f' stroke-dasharray="{",".join(map(str, dash))}"' if dash else ""
        self.svg.append(f'<line x1="{x1:.2f}" y1="{self._sy(y1):.2f}" x2="{x2:.2f}" y2="{self._sy(y2):.2f}" stroke="{color}" stroke-width="{width}"{dash_attr}/>')

    def rect(self, x: float, y: float, w: float, h: float, stroke: str = "#172126", fill: str = "#ffffff", width: float = 1.5, radius: float = 0) -> None:
        self.pdf.setStrokeColor(self._color(stroke))
        self.pdf.setFillColor(self._color(fill))
        self.pdf.setLineWidth(width)
        if radius:
            self.pdf.roundRect(x, y, w, h, radius, stroke=1, fill=1)
        else:
            self.pdf.rect(x, y, w, h, stroke=1, fill=1)
        self.svg.append(f'<rect x="{x:.2f}" y="{self._sy(y + h):.2f}" width="{w:.2f}" height="{h:.2f}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def circle(self, x: float, y: float, r: float = 3, stroke: str = "#172126", fill: str = "#172126") -> None:
        self.pdf.setStrokeColor(self._color(stroke))
        self.pdf.setFillColor(self._color(fill))
        self.pdf.circle(x, y, r, stroke=1, fill=1)
        self.svg.append(f'<circle cx="{x:.2f}" cy="{self._sy(y):.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}"/>')

    def text(self, x: float, y: float, value: str, size: float = 10, color: str = "#172126", bold: bool = False, anchor: str = "start") -> None:
        font = "Arial-Bold" if bold else "Arial"
        self.pdf.setFont(font, size)
        self.pdf.setFillColor(self._color(color))
        if anchor == "middle":
            self.pdf.drawCentredString(x, y, value)
        elif anchor == "end":
            self.pdf.drawRightString(x, y, value)
        else:
            self.pdf.drawString(x, y, value)
        svg_anchor = {"start": "start", "middle": "middle", "end": "end"}[anchor]
        weight = "700" if bold else "400"
        self.svg.append(f'<text x="{x:.2f}" y="{self._sy(y):.2f}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{svg_anchor}" fill="{color}">{escape(value)}</text>')

    def multiline(self, x: float, y: float, lines: Iterable[str], size: float = 9, leading: float | None = None, color: str = "#172126", bold_first: bool = False) -> float:
        step = leading or size * 1.35
        current = y
        for index, value in enumerate(lines):
            self.text(x, current, value, size=size, color=color, bold=bold_first and index == 0)
            current -= step
        return current

    def box(self, x: float, y: float, w: float, h: float, title: str, lines: Iterable[str], fill: str = "#f5f8f7", stroke: str = "#35524a", title_color: str = "#153b32") -> None:
        self.rect(x, y, w, h, stroke=stroke, fill=fill, width=1.8, radius=6)
        self.text(x + 10, y + h - 18, title, size=11, color=title_color, bold=True)
        self.multiline(x + 10, y + h - 36, lines, size=8.4, leading=11.5, color="#24332f")

    def arrow(self, x1: float, y1: float, x2: float, y2: float, color: str = "#1f6252", width: float = 2) -> None:
        self.line(x1, y1, x2, y2, color=color, width=width)
        angle = math.atan2(y2 - y1, x2 - x1)
        for delta in (2.55, -2.55):
            self.line(x2, y2, x2 + 9 * math.cos(angle + delta), y2 + 9 * math.sin(angle + delta), color=color, width=width)

    def title(self, page_no: int, title: str, subtitle: str) -> None:
        self.text(36, self.height - 38, f"MIC_AI REV {REVISION}", size=18, color="#163c32", bold=True)
        self.text(235, self.height - 37, title, size=17, color="#172126", bold=True)
        self.text(36, self.height - 58, subtitle, size=9, color="#4b5f59")
        self.line(36, self.height - 68, self.width - 36, self.height - 68, color="#286f5d", width=2)
        self.text(self.width - 36, 20, f"Лист {page_no}/{TOTAL_PAGES}   {REVISION_DATE}", size=8, color="#5b6965", anchor="end")

    def finish(self) -> None:
        self.svg.append("</svg>")
        self.svg_path.write_text("\n".join(self.svg), encoding="utf-8")
        self.pdf.showPage()


def draw_architecture(p: DualPage) -> None:
    p.title(1, "Архитектура и домены земли", "Каноническая схема: SAFE_GND никогда напрямую не соединяется с HV_DC-/HOT_GND")
    p.rect(30, 80, 325, 650, stroke="#276e5c", fill="#eef8f4", width=2, radius=10)
    p.rect(383, 80, 220, 650, stroke="#d78823", fill="#fff7e8", width=2, radius=10)
    p.rect(632, 80, 525, 650, stroke="#a32b28", fill="#fff0ef", width=2, radius=10)
    p.text(48, 705, "SAFE DOMAIN", 16, "#195747", True)
    p.text(401, 705, "ISOLATION BARRIER", 14, "#9a5a0d", True)
    p.text(650, 705, "HOT / HV DOMAIN", 16, "#8d211f", True)

    p.box(58, 570, 265, 100, "UNO Q / ПК", ["Питание UNO Q: VIN 7-24V или USB-C", "3.3V и 5V на UNO Q не подпитывать", "UART source: UNO Q либо PC USB-UART"], fill="#ffffff")
    p.box(58, 420, 265, 100, "Saleae Logic", ["Только SAFE_GND", "CH0..CH7 после ISO7740F", "Изоляционная задержка не более десятков нс"], fill="#ffffff")
    p.box(58, 270, 265, 100, "Аппаратный PWM inhibit", ["Нормально-замкнутый изолированный контур", "Обрыв питания/провода = PWM STOP", "Настоящий E-STOP также отключает сетевой контактор"], fill="#ffffff")
    p.box(58, 120, 265, 100, "SAFE питание", ["SAFE_GND отдельно от PE и HOT_GND", "SAFE_3V3: UNO Q OUT либо внешний источник", "SAFE_5V питает только E-STOP loop"], fill="#ffffff")

    p.box(413, 555, 160, 110, "U_UART_ISO", ["ISO7721DWR", "UART 1 канал туда", "1 канал обратно", "8 mm creepage package"], fill="#fffdf8", stroke="#be761b")
    p.box(413, 390, 160, 120, "U_LA1 + U_LA2", ["2 x ISO7740FDWR", "8 hot-to-safe channels", "PWM/EM_STOP/PB4", "default LOW"], fill="#fffdf8", stroke="#be761b")
    p.box(413, 245, 160, 95, "U_ESTOP_OPTO", ["LTV-817", "Безопасный loop", "74LVC1G14 + AND"], fill="#fffdf8", stroke="#be761b")
    p.line(603, 100, 603, 720, color="#d78823", width=3, dash=(8, 6))
    p.text(603, 90, "НЕТ медного соединения земель", 9, "#9a5a0d", True, "middle")

    p.box(665, 565, 215, 105, "Blue Pill", ["Питание только HOT_3V3", "USART2 PA2/PA3", "TIM1 PWM + safety", "HOT_GND = HV_DC-"], fill="#fffafa", stroke="#a32b28")
    p.box(920, 565, 205, 105, "STEVAL-IPM15B", ["J2 signals + J4 15V", "J7: 125..400VDC", "J2 GND = J7 DC-", "Внутри закрытого корпуса"], fill="#fffafa", stroke="#a32b28")
    p.box(665, 410, 215, 105, "AS5600", ["PB10 SCL / PB11 SDA", "HOT_3V3 / HOT_GND", "Кабель и модуль недоступны", "при включенной HV"], fill="#fffafa", stroke="#a32b28")
    p.box(920, 410, 205, 105, "4-pin PWM fan", ["HOT_12V постоянно", "PB3 -> NPN open collector", "PA11 TACH", "3-pin: только полная скорость"], fill="#fffafa", stroke="#a32b28")
    p.box(665, 245, 460, 110, "Силовое питание", ["230VAC -> F1 -> MOV -> KBPC5010 -> precharge -> HV_DC+", "HV_DC- = HOT_GND только внутри опасного домена", "PE идет только на корпус/раму/двигатель, не на HV_DC-", "HLK-20M15 питает горячие 15V/12V/5V/3.3V"], fill="#fffafa", stroke="#a32b28")
    p.box(665, 115, 460, 80, "Запрещено при поданной HV", ["USB Blue Pill, обычный ST-Link, прямой Saleae, заземленный осциллограф", "Любая пайка и перестановка проводов - только после разряда DC-шины"], fill="#ffe1df", stroke="#a32b28")

    p.arrow(323, 620, 413, 610)
    p.arrow(573, 610, 665, 620)
    p.arrow(665, 595, 573, 440, color="#7b5620")
    p.arrow(413, 440, 323, 470, color="#7b5620")
    p.arrow(323, 320, 413, 290)
    p.arrow(573, 290, 665, 600)
    p.arrow(880, 615, 920, 615, color="#9a2522")
    p.arrow(770, 565, 770, 515, color="#9a2522")
    p.arrow(1022, 565, 1022, 515, color="#9a2522")
    p.finish()


def draw_power(p: DualPage) -> None:
    p.title(2, "230VAC, мост, предзаряд и питание", "Проверять по именам выводов + / - / ~ / ~; номера footprint не считать источником истины")
    p.box(45, 620, 90, 80, "J_AC_IN", ["L", "N", "PE"], fill="#fff9f8", stroke="#9f2d29")
    p.box(170, 640, 100, 60, "F1", ["slow-blow", "BY LOAD"], fill="#fff9f8", stroke="#9f2d29")
    p.box(315, 535, 120, 65, "MOV1", ["S14K300", "после F1"], fill="#fff9f8", stroke="#9f2d29")
    p.box(480, 620, 130, 80, "BR1", ["KBPC5010", "AC1 AC2 + -"], fill="#fff9f8", stroke="#9f2d29")
    p.box(690, 665, 170, 55, "RPRE1 + RPRE2", ["20R + 20R; 25W pulse"], fill="#fff9f8", stroke="#9f2d29")
    p.box(690, 575, 170, 55, "K1 bypass", ["TE 2-1904058-5; 400VDC"], fill="#fff9f8", stroke="#9f2d29")
    p.box(995, 610, 100, 90, "J_J7", ["DC+", "DC-"], fill="#fff9f8", stroke="#9f2d29")

    p.arrow(135, 680, 170, 680, color="#a32b28")
    p.arrow(270, 680, 480, 680, color="#a32b28")
    p.text(285, 687, "AC_L_FUSED", 8, "#7e1f1c", True)
    p.arrow(135, 642, 480, 642, color="#a32b28")
    p.text(315, 649, "AC_N", 8, "#7e1f1c", True)
    p.line(300, 680, 300, 580, color="#a32b28", width=1.8)
    p.line(300, 580, 315, 580, color="#a32b28", width=1.8)
    p.line(435, 555, 455, 555, color="#a32b28", width=1.8)
    p.line(455, 555, 455, 642, color="#a32b28", width=1.8)
    p.circle(300, 680, 2.5, fill="#a32b28", stroke="#a32b28")
    p.circle(455, 642, 2.5, fill="#a32b28", stroke="#a32b28")

    p.line(610, 680, 650, 680, color="#a32b28", width=2)
    p.circle(650, 680, 3, fill="#a32b28", stroke="#a32b28")
    p.arrow(650, 680, 690, 692, color="#a32b28")
    p.arrow(650, 680, 690, 602, color="#a32b28")
    p.line(860, 692, 925, 680, color="#a32b28", width=2)
    p.line(860, 602, 925, 680, color="#a32b28", width=2)
    p.circle(925, 680, 3, fill="#a32b28", stroke="#a32b28")
    p.arrow(925, 680, 995, 680, color="#a32b28")
    p.line(610, 642, 630, 642, color="#7e1f1c", width=2)
    p.line(630, 642, 630, 548, color="#7e1f1c", width=2)
    p.line(630, 548, 960, 548, color="#7e1f1c", width=2)
    p.line(960, 548, 960, 635, color="#7e1f1c", width=2)
    p.arrow(960, 635, 995, 635, color="#7e1f1c")
    p.text(704, 646, "K1 подключён ПАРАЛЛЕЛЬНО 40R", 9, "#7e1f1c", True)
    p.text(650, 555, "BR1.MINUS = HV_DC-/HOT_GND", 8.5, "#7e1f1c", True)

    p.box(45, 430, 330, 100, "K1 coil driver", ["HOT_12V -> K1 coil -> Q1 drain", "Q1 AO3400A: source -> HOT_GND", "PB4 -> 100R -> gate; 100K pulldown", "SS14: cathode to HOT_12V"], fill="#f7fbf9")
    p.box(410, 430, 330, 100, "DC bus support", ["C_HV 220uF/450V if STEVAL C1 absent", "RB1..RB4: 4 x 100K 0.5W HV-rated", "Bleeder is not an ADC divider", "Test points remain shrouded"], fill="#f7fbf9")
    p.box(775, 430, 350, 100, "Relay rules", ["K1 closes only after Vbus precharge check", "K1 opens only with PWM off and no bus current", "Observe TE contact pinout", "SRD-12VDC-SL-C forbidden at 325VDC"], fill="#ffeceb", stroke="#a32b28")

    p.box(45, 235, 190, 120, "PS1 onboard", ["HLK-20M15", "AC_L_FUSED + AC_N", "Output -> source selector", "Secondary tied to HOT_GND"], fill="#fff7e8", stroke="#b06b16")
    p.box(255, 235, 190, 120, "External 15V / JP", ["Isolated bench source", "HV/J7 OFF only", "JP: ONBOARD or EXTERNAL", "Never bridge both positions"], fill="#fff7e8", stroke="#b06b16")
    p.box(465, 235, 190, 120, "U_BUCK12", ["15V -> 12V", "K1 coil", "4-pin fan", "Total PS1 budget applies"], fill="#fff7e8", stroke="#b06b16")
    p.box(675, 235, 190, 120, "U_BUCK5", ["15V -> 5V", "STEVAL J2-25", "Blue Pill 5V = NC", "HOT_GND"], fill="#fff7e8", stroke="#b06b16")
    p.box(885, 235, 240, 120, "U_BUCK3V3", ["15V -> 3.3V", "Blue Pill 3V3", "STEVAL J2-28/29", "HOT isolators"], fill="#fff7e8", stroke="#b06b16")
    p.text(45, 208, "HOT_15V существует только после JP_HOT15_SRC; внешний БП отключить перед подачей сети/HV.", 9, "#8a5315", True)

    p.rect(45, 92, 1080, 75, stroke="#a32b28", fill="#ffe4e2", width=2, radius=6)
    p.text(60, 142, "ПЕРЕД 230VAC", 12, "#8f211e", True)
    p.text(190, 142, "Проверить омметром: AC_L-AC_N не КЗ; BR1 AC1/AC2 не соединены с MINUS; SAFE_GND изолирован от HOT_GND.", 9, "#612321")
    p.text(60, 120, "F1 выбирается только после известного тока двигателя и сечения проводов. Не увеличивать номинал для маскировки ошибки.", 9, "#612321")
    p.text(60, 100, "PCB/layout требует отдельного DRC по creepage/clearance, прорезей и ширины HV дорожек. Эта принципиальная схема не заменяет layout review.", 9, "#612321")
    p.finish()


def draw_j2_mapping(p: DualPage) -> None:
    p.title(3, "Blue Pill - STEVAL-IPM15B J2", "Все сигналы этого листа относятся к HOT_GND = J7 DC-; J2-21 и J2-34 намеренно не подключены")
    headers = ["J2", "Сигнал STEVAL", "Blue Pill / питание", "Примечание"]
    rows = [
        ("1", "EM_STOP", "PB12 через hardware interlock + 220R", "LOW = shutdown"),
        ("3", "PWM-1H", "PA8 TIM1_CH1 через 33R", "Saleae isolated CH0"),
        ("5", "PWM-1L", "PB13 TIM1_CH1N через 33R", "Saleae isolated CH1"),
        ("7", "PWM-2H", "PA9 TIM1_CH2 через 33R", "Saleae isolated CH2"),
        ("9", "PWM-2L", "PB14 TIM1_CH2N через 33R", "Saleae isolated CH3"),
        ("11", "PWM-3H", "PA10 TIM1_CH3 через 33R", "Saleae isolated CH4"),
        ("13", "PWM-3L", "PB15 TIM1_CH3N через 33R", "Saleae isolated CH5"),
        ("14", "HV bus voltage", "PA5 ADC1_IN5 через 100R", "0..3.3V from STEVAL"),
        ("15", "current phase A", "PA0 ADC1_IN0 через 100R", "ADC"),
        ("17", "current phase B", "PA1 ADC1_IN1 через 100R", "ADC"),
        ("19", "current phase C", "PA4 ADC1_IN4 через 100R", "ADC"),
        ("21", "NTC bypass relay", "NC", "Сеть не используется на STEVAL-IPM15B"),
        ("23", "dissipative brake PWM", "PB9 TIM4_CH4 через 100R", "Default OFF"),
        ("25", "+V power", "HOT_5V", "Не GPIO"),
        ("26", "heat sink temperature", "PB0 ADC1_IN8 через 100R", "SW3 = TSO 1-2"),
        ("27", "PFC sync", "PB5 через 100R", "GPIO output"),
        ("28", "VDD_m", "HOT_3V3", "Power/reference"),
        ("29", "PWM VREF", "HOT_3V3", "PWM reference"),
        ("31", "measure phase A", "PA6 ADC1_IN6 через 100R", "Real sample"),
        ("33", "measure phase B", "PA7 ADC1_IN7 через 100R", "Real sample"),
        ("34", "measure phase C", "NC", "Virtual C computed from A/B"),
        ("2,4,6,8,10,12", "GND", "HV_DC-/HOT_GND", "Connect all"),
        ("16,18,20,22,24", "GND", "HV_DC-/HOT_GND", "Connect all"),
        ("30,32", "GND", "HV_DC-/HOT_GND", "Connect all"),
    ]
    x0, y_top = 45, 735
    col_w = [95, 250, 350, 385]
    row_h = 24
    x = x0
    for text, width in zip(headers, col_w):
        p.rect(x, y_top - row_h, width, row_h, stroke="#315b50", fill="#dceee8", width=1)
        p.text(x + 6, y_top - 17, text, 9, "#183f35", True)
        x += width
    y = y_top - row_h
    for index, row in enumerate(rows):
        y -= row_h
        fill = "#ffffff" if index % 2 == 0 else "#f4f8f6"
        x = x0
        for value, width in zip(row, col_w):
            p.rect(x, y, width, row_h, stroke="#91a39e", fill=fill, width=0.6)
            color = "#8c231f" if value in {"NC", "HV_DC-/HOT_GND"} else "#172126"
            p.text(x + 6, y + 7, value, 8.2, color, bold=value in {"NC", "HV_DC-/HOT_GND"})
            x += width

    p.rect(45, 88, 1080, 48, stroke="#a32b28", fill="#ffe8e6", width=1.5, radius=5)
    p.text(58, 115, "Важно:", 10, "#8f211e", True)
    p.text(115, 115, "PB4 управляет внешним K1 precharge. PB1 и STEVAL J2-21 оставлены NC.", 9, "#612321")
    p.text(58, 96, "Blue Pill питается через HOT_3V3; его 5V pin остается NC. J4 RETURN - это HOT_GND, а не отрицательные -15V.", 9, "#612321")
    p.finish()


def draw_interfaces(p: DualPage) -> None:
    p.title(4, "Изолированные интерфейсы и аппаратный запрет PWM", "UART/monitor barrier рассчитан на гальваническое разделение SAFE и HOT доменов")
    p.box(45, 580, 260, 105, "UART source select", ["JP_UART_TX / JP_UART_RX", "Позиция UNO Q: D1 TX / D0 RX", "Позиция PC: USB-UART 3.3V logic", "Power pin USB-UART = NC"], fill="#eef8f4")
    p.box(395, 575, 240, 115, "U_UART_ISO", ["ISO7721DWR wide-body", "SAFE TX -> HOT PA3 RX", "HOT PA2 TX -> SAFE RX", "100nF с обеих сторон"], fill="#fff7e8", stroke="#b36b16")
    p.box(725, 580, 400, 105, "Blue Pill USART2", ["PA3 = RX commands", "PA2 = TX telemetry", "115200 8N1", "CRC/timeout remain active across isolator"], fill="#fff0ef", stroke="#a32b28")
    p.arrow(305, 632, 395, 632)
    p.arrow(635, 632, 725, 632)

    p.box(45, 390, 260, 120, "Safe Saleae", ["J_SALEAE CH0..CH7 + SAFE_GND", "CH0..5 complementary PWM", "CH6 PB12 command", "CH7 PB4 precharge command"], fill="#eef8f4")
    p.box(395, 385, 240, 130, "2 x ISO7740FDWR", ["CH0..CH3 via U_LA1", "CH4..CH7 via U_LA2", "EN2 (pin 10) -> SAFE_3V3", "100Mbps / default LOW", "2000ns deadtime remains measurable"], fill="#fff7e8", stroke="#b36b16")
    p.box(725, 390, 400, 120, "Hot monitor taps", ["CH0 PWM_UH after 33R", "CH1 PWM_UL after 33R", "CH2 PWM_VH / CH3 PWM_VL", "CH4 PWM_WH / CH5 PWM_WL", "CH6 PB12_RUN / CH7 PB4_PRECHARGE"], fill="#fff0ef", stroke="#a32b28")
    p.arrow(725, 450, 635, 450, color="#7d5b22")
    p.arrow(395, 450, 305, 450, color="#7d5b22")

    p.box(45, 165, 260, 150, "Safe NC PWM-inhibit loop", ["SAFE_5V -> NC switch -> 680R", "-> LTV-817 LED -> SAFE_GND", "Обрыв loop или SAFE_5V", "аппаратно запрещает PWM RUN", "E-STOP также размыкает внешний контактор"], fill="#eef8f4")
    p.box(395, 160, 240, 160, "Barrier + hot logic", ["LTV-817 collector + 10K pull-up", "74LVC1G14: loop OK", "74LVC1G08: PB12 AND loop OK", "220R to STEVAL J2-1", "47K pulldown = shutdown by default"], fill="#fff7e8", stroke="#b36b16")
    p.box(725, 175, 400, 130, "Hardware interlock truth table", ["PB12 LOW -> J2-1 LOW -> PWM STOP", "NC loop open -> J2-1 LOW -> PWM STOP", "Hot logic power lost -> output pulldown -> STOP", "RUN only when PB12 HIGH and loop closed", "Software cannot override an open loop"], fill="#ffe4e2", stroke="#a32b28")
    p.arrow(305, 240, 395, 240)
    p.arrow(635, 240, 725, 240)

    p.text(45, 115, "SAFE_3V3 выбирается джампером: UNO Q OUT_3V3 либо внешний safe 3.3V. Это выход UNO Q, не вход питания платы.", 9, "#28463e", True)
    p.text(45, 95, "Wide-body isolators и прорезь/keepout под barrier обязательны на PCB; дорожки или полигоны под корпусами изоляторов запрещены.", 9, "#8f211e", True)
    p.finish()


def draw_aux(p: DualPage) -> None:
    p.title(5, "Вентилятор, AS5600, SWD и сборочные проверки", "Стандартный fan header: 1 GND, 2 +12V, 3 TACH, 4 PWM open-collector")
    p.box(45, 565, 300, 125, "Fan power", ["HOT_15V -> buck -> HOT_12V", "+12V и GND подаются постоянно", "100uF + 100nF у разъема", "3-pin fan на контактах 1..3", "работает только на полной скорости"], fill="#fff7e8", stroke="#b36b16")
    p.box(405, 565, 310, 125, "4-pin PWM control", ["PB3 -> 1K -> MMBT2222A base", "47K base pulldown", "Collector -> FAN PWM; emitter -> HOT_GND", "25kHz; timer polarity active-low", "Loss of MCU drive -> fan full speed"], fill="#fff7e8", stroke="#b36b16")
    p.box(775, 565, 350, 125, "Fan tach", ["TACH -> 1K -> PA11", "10K pull-up to HOT_3V3", "Не использовать Blue Pill USB при PA11", "Проверить pin order и ток вентилятора", "Вентилятор/кабель относятся к HOT domain"], fill="#fff7e8", stroke="#b36b16")

    p.box(45, 375, 500, 125, "AS5600", ["PB10 -> SCL", "PB11 -> SDA", "HOT_3V3 -> VCC; HOT_GND -> GND", "4.7K pull-ups DNP if module already has pull-ups", "AS5600 and cable stay inside insulated HV enclosure"], fill="#fff0ef", stroke="#a32b28")
    p.box(625, 375, 500, 125, "SWD", ["VREF HOT_3V3 / PA13 SWDIO / PA14 SWCLK", "HOT_GND / NRST", "HV/J7 disconnected and bus discharged before use", "Do not power target from ST-Link", "Unplug ST-Link before applying HV"], fill="#ffe4e2", stroke="#a32b28")

    checks_left = [
        "1. Омметр: SAFE_GND - HOT_GND = разрыв.",
        "2. Омметр: AC_N - HV_DC- = разрыв при снятом BR1.",
        "3. Проверить BR1 по маркировке + / - / ~ / ~.",
        "4. Проверить K1: PB4, не PB1.",
        "5. Проверить все J2 GND pins.",
        "6. Проверить UNO Q: только VIN или USB-C.",
    ]
    checks_right = [
        "7. Выбрать один HOT_15V source; подать low voltage без J7.",
        "8. Проверить E-STOP truth table.",
        "9. Проверить UART и isolated Saleae static LOW.",
        "10. Проверить precharge relay при HV OFF.",
        "11. Проверить PWM overlap при EM_STOP active.",
        "12. E-STOP должен также снимать питание внешним контактором.",
    ]
    p.box(45, 135, 520, 180, "Предпусковая проверка A", checks_left, fill="#f4f8f6")
    p.box(605, 135, 520, 180, "Предпусковая проверка B", checks_right, fill="#f4f8f6")
    p.rect(45, 82, 1080, 36, stroke="#a32b28", fill="#ffe4e2", width=1.5, radius=5)
    p.text(585, 94, "Эта ревизия исправляет принципиальную схему. PCB/макет на 230VAC нельзя включать без отдельной проверки зазоров и механической защиты.", 9, "#7e1f1c", True, "middle")
    p.finish()


def draw_pinmap(p: DualPage) -> None:
    p.title(6, "Контроль физических выводов", "Номера указаны для выбранных корпусов; ориентацию всегда проверять по метке pin 1 на корпусе")

    p.box(45, 520, 335, 180, "U_UART_ISO: ISO7721DWR", [
        "1,7 GND1 -> SAFE_GND; 3 VCC1 -> SAFE_3V3",
        "4 OUTA -> SAFE RX; 5 INB <- SAFE TX",
        "9,16 GND2 -> HOT_GND; 14 VCC2 -> HOT_3V3",
        "12 OUTB -> PA3 RX; 13 INA <- PA2 TX",
        "2,6,8,10,11,15 = NC",
        "Корпус DW-16 wide-body, вид сверху",
    ], fill="#fff7e8", stroke="#b36b16")

    p.box(420, 500, 350, 200, "U_LA1/U_LA2: ISO7740FDWR", [
        "1 VCC1 -> HOT_3V3; 2,8 GND1 -> HOT_GND",
        "3 INA / 4 INB / 5 INC / 6 IND <- HOT signals",
        "7 = NC",
        "9,15 GND2 -> SAFE_GND; 16 VCC2 -> SAFE_3V3",
        "10 EN2 -> SAFE_3V3 (выходы разрешены)",
        "14 OUTA / 13 OUTB / 12 OUTC / 11 OUTD -> Saleae",
        "Суффикс F: при потере входа выход LOW",
    ], fill="#fff7e8", stroke="#b36b16")

    p.box(810, 500, 315, 200, "Аппаратный PWM inhibit", [
        "LTV-817: 1 LED_A, 2 LED_K, 3 E, 4 C",
        "SN74LVC1G14DBVR: 1 NC, 2 A, 3 GND, 4 Y, 5 VCC",
        "SN74LVC1G08DBVR: 1 A, 2 B, 3 GND, 4 Y, 5 VCC",
        "DBV = SOT-23-5, вид сверху",
        "J2-1 имеет 47K pulldown: питание пропало -> STOP",
    ], fill="#fff7e8", stroke="#b36b16")

    p.box(45, 285, 335, 170, "Драйвер K1", [
        "Q1 AO3400A: 1 G, 2 S, 3 D",
        "D_K1 SS14: полоса = K -> HOT_12V",
        "K1 TE 2-1904058-5: 12V, coil 50R",
        "K1 contact: 400VDC / 20A",
        "Посадочное место K1 брать только из TE CAD",
        "Катушка не содержит встроенного резистора",
    ], fill="#fff0ef", stroke="#a32b28")

    p.box(420, 285, 350, 170, "Вентилятор", [
        "Q_FAN_N MMBT2222A-7-F: 1 B, 2 E, 3 C",
        "J_FAN: 1 GND, 2 +12V, 3 TACH, 4 PWM",
        "PWM = open collector, 25kHz",
        "PA11 принимает TACH через 1K",
        "3-pin fan: только pins 1..3, без регулирования",
    ], fill="#fff7e8", stroke="#b36b16")

    p.box(810, 285, 315, 170, "Силовые маркировки", [
        "BR1: использовать только marks ~, ~, +, - на корпусе",
        "J7: PLUS -> DC+, MINUS -> DC- / HOT_GND",
        "SS14: полоса на корпусе обозначает катод",
        "PE никогда не соединять с HOT_GND на этой плате",
        "SAFE_GND никогда не соединять с HOT_GND",
    ], fill="#fff0ef", stroke="#a32b28")

    p.rect(45, 105, 1080, 125, stroke="#a32b28", fill="#ffe4e2", width=2, radius=6)
    p.text(60, 204, "ОБЯЗАТЕЛЬНО ПЕРЕД ПАЙКОЙ", 12, "#8f211e", True)
    p.multiline(60, 182, [
        "1. Сверить фактический MPN каждой микросхемы с MIC_AI_REV2_PINMAP.csv; заменять производителя без повторной проверки pinout нельзя.",
        "2. Для K1 импортировать официальный TE CAD/footprint 2-1904058-5 и вручную сопоставить две силовые площадки и две площадки катушки.",
        "3. После разводки выполнить ERC/DRC, проверку creepage/clearance и прозвонку SAFE_GND - HOT_GND - PE - AC_N как четырех разных сетей.",
        "4. Номинал F1 остаётся F1_VALUE_BY_LOAD до расчёта по двигателю, проводам и допустимому току входа.",
    ], size=9, leading=21, color="#612321")
    p.finish()


def register_fonts() -> None:
    regular = Path("C:/Windows/Fonts/arial.ttf")
    bold = Path("C:/Windows/Fonts/arialbd.ttf")
    if not regular.exists() or not bold.exists():
        raise FileNotFoundError("Arial fonts are required for Cyrillic PDF output")
    pdfmetrics.registerFont(TTFont("Arial", str(regular)))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(bold)))


def write_pdf_and_svg() -> list[Path]:
    register_fonts()
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A3)
    pdf = canvas.Canvas(str(PDF_PATH), pagesize=(width, height), pageCompression=1)
    pdf.setTitle("MIC_AI REV2 Schematic")
    pdf.setAuthor("Codex / 11lisov11")
    pages = [draw_architecture, draw_power, draw_j2_mapping, draw_interfaces, draw_aux, draw_pinmap]
    svg_paths: list[Path] = []
    for index, draw in enumerate(pages, start=1):
        svg_path = SVG_DIR / f"page_{index:02d}.svg"
        page = DualPage(pdf, svg_path, width, height)
        draw(page)
        svg_paths.append(svg_path)
    pdf.save()
    return svg_paths


def edif_id(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not result or result[0].isdigit():
        result = f"N_{result}"
    return result


def write_edif(model: ElectricalModel) -> None:
    lines = [
        f'(edif MIC_AI_REV2',
        '  (edifVersion 2 0 0)',
        '  (edifLevel 0)',
        '  (keywordMap (keywordLevel 0))',
        '  (status (written',
        f'    (timestamp 2026 7 17 0 0 0)',
        f'    (program "Codex MIC_AI generator" (version "{REVISION}"))))',
        '  (library MICAI_LIB',
        '    (edifLevel 0)',
        '    (technology (numberDefinition))',
    ]
    for component in model.components.values():
        cell = f"CELL_{edif_id(component.ref)}"
        lines.extend([
            f'    (cell {cell}',
            '      (cellType generic)',
            '      (view schematic',
            '        (viewType netlist)',
            '        (interface',
        ])
        for port in component.ports:
            lines.append(f'          (port {edif_id(port)} (direction inout))')
        lines.extend([
            '        )',
            '      )',
            '    )',
        ])

    lines.extend([
        '    (cell TOP',
        '      (cellType generic)',
        '      (view schematic',
        '        (viewType netlist)',
        '        (interface)',
        '        (contents',
    ])
    for component in model.components.values():
        lines.extend([
            f'          (instance {edif_id(component.ref)}',
            f'            (viewRef schematic (cellRef CELL_{edif_id(component.ref)} (libraryRef MICAI_LIB)))',
            f'            (property VALUE (string "{component.value}"))',
            f'            (property FOOTPRINT (string "{component.footprint}"))',
            f'            (property DOMAIN (string "{component.domain}"))',
            f'            (property POPULATE (string "{component.populate}"))',
            '          )',
        ])
    for net_name, endpoints in model.nets.items():
        lines.append(f'          (net {edif_id(net_name)}')
        lines.append('            (joined')
        for ref, port in endpoints:
            lines.append(f'              (portRef {edif_id(port)} (instanceRef {edif_id(ref)}))')
        lines.extend(['            )', '          )'])
    lines.extend([
        '        )',
        '      )',
        '    )',
        '  )',
        '  (design MIC_AI_REV2_DESIGN',
        '    (cellRef TOP (libraryRef MICAI_LIB))',
        '  )',
        ')',
    ])
    EDIF_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_pinmap(model: ElectricalModel) -> list[dict[str, str]]:
    endpoint_net = {
        (ref, port): net_name
        for net_name, endpoints in model.nets.items()
        for ref, port in endpoints
    }
    rows: list[dict[str, str]] = []

    def add(
        ref: str,
        logical_port: str,
        physical_pin: str,
        pin_name: str,
        verification: str,
        source: str,
        note: str = "",
    ) -> None:
        component = model.components[ref]
        if logical_port and logical_port not in component.ports:
            raise ValueError(f"pinmap references missing logical port {ref}.{logical_port}")
        rows.append({
            "Ref": ref,
            "MPN": component.value,
            "LogicalPort": logical_port or "PHYSICAL_NC",
            "PhysicalPin": physical_pin,
            "PinName": pin_name,
            "Net": endpoint_net.get((ref, logical_port), "NC"),
            "Verification": verification,
            "Source": source,
            "Note": note,
        })

    ti_iso7721 = "TI ISO7721 Rev.G, Figure 5-2/Table 5-1"
    for port, pin, name in (
        ("GND_SAFE", "1,7", "GND1"),
        ("VCC_SAFE", "3", "VCC1"),
        ("RX_SAFE_OUT", "4", "OUTA"),
        ("TX_SAFE_IN", "5", "INB"),
        ("GND_HOT", "9,16", "GND2"),
        ("RX_HOT_OUT", "12", "OUTB"),
        ("TX_HOT_IN", "13", "INA"),
        ("VCC_HOT", "14", "VCC2"),
    ):
        add("U_UART_ISO", port, pin, name, "DATASHEET_VERIFIED", ti_iso7721)
    add("U_UART_ISO", "", "2,6,8,10,11,15", "NC", "DATASHEET_VERIFIED", ti_iso7721)

    ti_iso7740 = "TI ISO7740 Rev.J, Figure 4-1/Table 4-1"
    iso7740_map = (
        ("VCC_HOT", "1", "VCC1"),
        ("GND_HOT", "2,8", "GND1"),
        ("HI1", "3", "INA"),
        ("HI2", "4", "INB"),
        ("HI3", "5", "INC"),
        ("HI4", "6", "IND"),
        ("GND_SAFE", "9,15", "GND2"),
        ("EN_SAFE", "10", "EN2"),
        ("SO4", "11", "OUTD"),
        ("SO3", "12", "OUTC"),
        ("SO2", "13", "OUTB"),
        ("SO1", "14", "OUTA"),
        ("VCC_SAFE", "16", "VCC2"),
    )
    for ref in ("U_LA1", "U_LA2"):
        for port, pin, name in iso7740_map:
            add(ref, port, pin, name, "DATASHEET_VERIFIED", ti_iso7740)
        add(ref, "", "7", "NC", "DATASHEET_VERIFIED", ti_iso7740)

    for port, pin, name in (
        ("LED_A", "1", "ANODE"),
        ("LED_K", "2", "CATHODE"),
        ("E", "3", "EMITTER"),
        ("C", "4", "COLLECTOR"),
    ):
        add("U_ESTOP_OPTO", port, pin, name, "DATASHEET_VERIFIED", "Lite-On LTV-817 Rev.Q")

    ti_inv = "TI SN74LVC1G14 Rev.AA, DBV pin table"
    for port, pin in (("A", "2"), ("GND", "3"), ("Y", "4"), ("VCC", "5")):
        add("U_ESTOP_INV", port, pin, port, "DATASHEET_VERIFIED", ti_inv)
    add("U_ESTOP_INV", "", "1", "NC", "DATASHEET_VERIFIED", ti_inv, "Solder pad; no electrical connection required")

    ti_and = "TI SN74LVC1G08 Rev.Z, DBV pin table"
    for port, pin in (("A", "1"), ("B", "2"), ("GND", "3"), ("Y", "4"), ("VCC", "5")):
        add("U_ESTOP_AND", port, pin, port, "DATASHEET_VERIFIED", ti_and)

    for port, pin in (("G", "1"), ("S", "2"), ("D", "3")):
        add("Q1", port, pin, port, "DATASHEET_VERIFIED", "AOS AO3400A Rev.3.1")
    for port, pin in (("B", "1"), ("E", "2"), ("C", "3")):
        add("Q_FAN_N", port, pin, port, "DATASHEET_VERIFIED", "Diodes MMBT2222A Rev.18-2")

    add("D_K1", "K", "BANDED_END", "CATHODE", "BODY_MARK_VERIFIED", "SS14 body marking")
    add("D_K1", "A", "UNBANDED_END", "ANODE", "BODY_MARK_VERIFIED", "SS14 body marking")

    te_source = "TE 2-1904058-5 official product/CAD"
    for port, pad, name in (
        ("COM", "TE_CONTACT_A", "POWER_CONTACT_A"),
        ("NO", "TE_CONTACT_B", "POWER_CONTACT_B"),
        ("COIL_PLUS", "TE_COIL_A", "COIL_A"),
        ("COIL_LOW", "TE_COIL_B", "COIL_B"),
    ):
        add("K1", port, pad, name, "TE_CAD_FOOTPRINT_REQUIRED", te_source, "Lock official TE footprint before PCB release")

    for port, mark in (("AC1", "~1"), ("AC2", "~2"), ("PLUS", "+"), ("MINUS", "-")):
        add("BR1", port, mark, mark, "BODY_MARK_VERIFIED", "KBPC5010 body markings", "Do not infer from footprint numbering")

    for port, pin in (("GND", "1"), ("V12", "2"), ("TACH", "3"), ("PWM", "4")):
        add("J_FAN", port, pin, port, "STANDARD_HEADER_ORDER", "Intel/Noctua 4-wire fan convention")

    critical_refs = {
        "U_UART_ISO", "U_LA1", "U_LA2", "U_ESTOP_OPTO", "U_ESTOP_INV",
        "U_ESTOP_AND", "Q1", "Q_FAN_N", "D_K1", "K1", "BR1", "J_FAN",
    }
    covered = {
        (row["Ref"], row["LogicalPort"])
        for row in rows
        if row["LogicalPort"] != "PHYSICAL_NC"
    }
    missing = sorted(
        (ref, port)
        for ref in critical_refs
        for port in model.components[ref].ports
        if (ref, port) not in covered
    )
    if missing:
        raise ValueError(f"critical physical pinmap is incomplete: {missing}")
    return rows


def write_csvs(model: ElectricalModel) -> list[dict[str, str]]:
    with BOM_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Ref", "Value", "Footprint", "Domain", "Populate", "Note"])
        for component in sorted(model.components.values(), key=lambda item: item.ref):
            writer.writerow([component.ref, component.value, component.footprint, component.domain, component.populate, component.note])

    with CONNECTIONS_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Net", "Ref", "Pin", "Domain", "Component"])
        for net_name in sorted(model.nets):
            for ref, port in model.nets[net_name]:
                component = model.components[ref]
                writer.writerow([net_name, ref, port, component.domain, component.value])

    pinmap = build_pinmap(model)
    with PINMAP_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        fieldnames = ["Ref", "MPN", "LogicalPort", "PhysicalPin", "PinName", "Net", "Verification", "Source", "Note"]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pinmap)
    return pinmap


def write_assembly() -> None:
    text = f"""# MIC_AI REV {REVISION} - схема сборки

Канонический PDF: `../../output/pdf/MIC_AI_REV2_SCHEMATIC.pdf`.

Редактируемые/производные файлы:

- `MIC_AI_REV2_NETLIST.edif` - импорт netlist в EasyEDA;
- `MIC_AI_REV2_BOM.csv` - перечень элементов;
- `MIC_AI_REV2_CONNECTIONS.csv` - каждая электрическая сеть и вывод;
- `MIC_AI_REV2_PINMAP.csv` - физические выводы критичных корпусов и их сети;
- `svg/page_01.svg` ... `svg/page_06.svg` - векторные листы;
- `manifest.json` - результат автоматической проверки инвариантов.

## Главная архитектура

- `HV_DC_MINUS_HOT_GND` является отрицательной DC-шиной и горячей землей STEVAL/Blue Pill.
- `SAFE_GND` принадлежит UNO Q, ПК, Saleae и изолированному контуру аппаратного запрета PWM.
- Между `SAFE_GND` и `HV_DC_MINUS_HOT_GND` нет прямого соединения.
- UART проходит через `ISO7721DWR`.
- Saleae CH0..CH7 проходит через два `ISO7740FDWR`.
- ST-Link подключается только при отключенной HV/J7 и разряженной шине.

## Обязательные отличия от старой схемы

1. У KBPC5010 четыре отдельные сети: два `AC~`, `PLUS`, `MINUS`.
2. MOV установлен после F1.
3. Внешний precharge K1 управляется `PB4`; `PB1` и STEVAL J2-21 оставлены NC.
4. K1 - TE Mini K HV `2-1904058-5`, а не SRD-12VDC-SL-C.
5. UNO Q питается через `VIN 7-24V` или USB-C. Его 3.3V и 5V не являются входами питания в этой схеме.
6. Blue Pill питается только через внешний `HOT_3V3`; pin 5V не подключен.
7. Все GND-контакты STEVAL J2 подключены к горячей земле.
8. Стандартный 4-pin fan получает постоянные `HOT_12V` и `HOT_GND`; PB3 управляет PWM-входом через открытый коллектор MMBT2222A на 25 кГц.
9. 3-pin fan можно подключить к контактам GND/+12V/TACH, но регулировки скорости тогда нет: он работает постоянно на полной скорости.
10. J4 negative называется `RETURN/HOT_GND`, а не `-15V`.
11. `JP_HOT15_SRC` выбирает ровно один источник: бортовой HLK-20M15 или внешний изолированный 15 В для стендовой проверки без HV.

## Неопределенный параметр

Номинал F1 нельзя корректно выбрать без шильдика двигателя, максимального входного тока и сечения проводов. В BOM он намеренно оставлен `F1_VALUE_BY_LOAD`. Нельзя увеличивать предохранитель, чтобы скрыть ошибку сборки.

## Исходные документы

- ST UM2014, STEVAL-IPM15B: `../../um2014-1500-w-motor-control-power-board-based-on-stgib15ch60tsl-sllimm-2nd-series-ipm-stmicroelectronics.pdf`.
- TE Mini K HV `2-1904058-5`: https://www.te.com/en/product-2-1904058-5.html
- TI ISO7721: https://www.ti.com/product/ISO7721
- TI ISO7740: https://www.ti.com/product/ISO7740
- Arduino UNO Q datasheet: https://docs.arduino.cc/resources/datasheets/ABX00162-datasheet.pdf
- 4-pin fan PWM/RPM interface reference: https://www.noctua.at/cn/support/faqs/microcontroller-guide-pwm-setup-and-rpm-monitoring

## Порядок проверки

1. Не подключая 230VAC, прозвонить разделение SAFE/HOT/PE/AC_N.
2. Выбрать `EXTERNAL` на `JP_HOT15_SRC`, подать изолированные 15 В без J7/HV и проверить аппаратный запрет PWM.
3. Проверить UART через изолятор.
4. Проверить static LOW и PWM через изолированный Saleae.
5. Проверить K1 при отключенной HV.
6. Провести отдельный PCB/layout review по creepage, clearance, ширине дорожек и защитному корпусу.
7. Только после этого рассматривать подачу 230VAC.
"""
    ASSEMBLY_PATH.write_text(text, encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = build_model()
    audit = model.validate()
    if not audit["pass"]:
        raise RuntimeError(json.dumps(audit, ensure_ascii=False, indent=2))

    svg_paths = write_pdf_and_svg()
    write_edif(model)
    pinmap = write_csvs(model)
    write_assembly()

    artifacts = [PDF_PATH, EDIF_PATH, BOM_PATH, CONNECTIONS_PATH, PINMAP_PATH, ASSEMBLY_PATH, *svg_paths]
    manifest = {
        "project": "MIC_AI",
        "revision": REVISION,
        "date": REVISION_DATE,
        "audit": audit,
        "pinmap": {
            "row_count": len(pinmap),
            "critical_component_count": len({row["Ref"] for row in pinmap}),
            "requires_official_footprint": ["K1"],
        },
        "canonical_pdf": str(PDF_PATH),
        "artifacts": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in artifacts
        ],
        "unresolved": [
            "F1 value requires motor nameplate current, intended maximum power, conductor size, and protection coordination.",
            "PCB layout still requires creepage/clearance, thermal, and mechanical safety review.",
            "The required safety category and external mains contactor must be selected for the final machine/application.",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="Validate the electrical model without writing artifacts.")
    args = parser.parse_args()

    model = build_model()
    audit = model.validate()
    if args.check_only:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0 if audit["pass"] else 1

    manifest = generate()
    print(json.dumps({
        "pass": manifest["audit"]["pass"],
        "revision": manifest["revision"],
        "canonical_pdf": manifest["canonical_pdf"],
        "component_count": manifest["audit"]["component_count"],
        "net_count": manifest["audit"]["net_count"],
        "artifact_count": len(manifest["artifacts"]),
        "unresolved": manifest["unresolved"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
