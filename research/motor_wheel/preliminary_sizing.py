"""Offline road-load sizing and an optimistic three-phase inverter screen.

No hardware, network, FEA, motor identification, or measured performance is used.
Run from any working directory; only --output-dir requests file writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

G = 9.80665


def number(value: object, name: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name}: expected finite value >= {minimum}")
    return result


def positive(value: object, name: str) -> float:
    result = number(value, name)
    if result == 0.0:
        raise ValueError(f"{name}: expected positive value")
    return result


def fraction(value: object, name: str) -> float:
    result = positive(value, name)
    if result > 1.0:
        raise ValueError(f"{name}: expected value <= 1")
    return result


def road_load(vehicle: dict, speed_kmh: float, grade_pct: float,
              acceleration_m_s2: float = 0.0) -> dict:
    mass = positive(vehicle["gross_mass_kg"], "gross_mass_kg")
    radius = positive(vehicle["loaded_wheel_diameter_m"], "wheel_diameter") / 2
    speed = number(speed_kmh, "speed_kmh") / 3.6
    slope = number(grade_pct, "grade_pct") / 100
    acceleration = number(acceleration_m_s2, "acceleration_m_s2")
    angle = math.atan(slope)
    relative_air_speed = speed + number(vehicle["headwind_m_s"], "headwind")
    rolling = mass * G * math.cos(angle) * number(vehicle["rolling_coefficient"], "Crr")
    gravity = mass * G * math.sin(angle)
    aerodynamic = (0.5 * positive(vehicle["air_density_kg_m3"], "rho")
                   * number(vehicle["drag_area_m2"], "CdA") * relative_air_speed ** 2)
    inertial = mass * acceleration
    force = rolling + gravity + aerodynamic + inertial
    omega = speed / radius
    return {
        "speed_kmh": float(speed_kmh), "grade_pct": float(grade_pct),
        "acceleration_m_s2": acceleration,
        "wheel_rpm": omega * 60 / (2 * math.pi),
        "rolling_force_n": rolling, "grade_force_n": gravity,
        "aerodynamic_force_n": aerodynamic, "translational_inertial_force_n": inertial,
        "wheel_force_n": force, "wheel_torque_nm": force * radius,
        "wheel_mechanical_power_w": force * speed,
        "rotating_inertia_included": False,
    }


def electrical_screen(dc_v: float, shaft_w: float, screen: dict, energy: dict) -> dict:
    dc_v = positive(dc_v, "dc_v")
    shaft_w = number(shaft_w, "shaft_w")
    utilization = fraction(screen["three_phase_linear_svpwm_voltage_utilization"], "utilization")
    eta_motor = fraction(energy["motor_efficiency_assumption"], "eta_motor")
    eta_inverter = fraction(energy["inverter_efficiency_assumption"], "eta_inverter")
    power_factor = fraction(screen["motor_power_factor_assumption"], "power_factor")
    line_rms_v = utilization * dc_v / math.sqrt(2)
    # Fundamental current at the assumed maximum available output voltage.
    # This is an optimistic screen, not the current of a designed low-speed motor.
    rms_a = shaft_w / (eta_motor * math.sqrt(3) * line_rms_v * power_factor)
    peak_a = math.sqrt(2) * rms_a
    return {
        "dc_bus_v": dc_v, "shaft_power_target_w": shaft_w,
        "available_line_line_fundamental_rms_v": line_rms_v,
        "optimistic_line_current_rms_a": rms_a,
        "fundamental_sinusoidal_peak_a_excluding_pwm_ripple": peak_a,
        "battery_current_a": (shaft_w / (eta_motor * eta_inverter)
                              + number(energy["auxiliary_power_w"], "auxiliary_power_w")) / dc_v,
        "within_board_nominal_rms_current": rms_a <= positive(screen["nominal_output_current_rms_a"], "board_rms"),
        "within_proposed_software_peak": peak_a <= positive(screen["proposed_software_sinusoidal_peak_limit_a"], "software_peak"),
        "below_datasheet_ocp_peak_excluding_ripple": peak_a < positive(screen["datasheet_ocp_peak_a"], "ocp_peak"),
        "is_motor_or_short_term_rating_validation": False,
    }


def calculate(config: dict) -> dict:
    if config.get("schema") != "mic_ai.motor_wheel.sizing_inputs.v1":
        raise ValueError("Unsupported input schema")
    energy, envelope = config["energy"], config["target_envelope"]
    eta_motor = fraction(energy["motor_efficiency_assumption"], "eta_motor")
    eta_inverter = fraction(energy["inverter_efficiency_assumption"], "eta_inverter")
    usable_wh = (positive(energy["battery_nominal_voltage_v"], "battery_nominal_voltage_v")
                 * positive(energy["battery_capacity_ah"], "battery_capacity_ah")
                 * fraction(energy["usable_energy_fraction"], "usable_energy_fraction"))
    rows = [road_load(config["vehicle"], speed, grade)
            for grade in config["grades_pct"] for speed in config["steady_speeds_kmh"]]
    rows.extend(road_load(config["vehicle"], **case) for case in config["acceleration_cases"])
    for row in rows:
        shaft_w = row["wheel_mechanical_power_w"]
        row["battery_power_assumption_w"] = shaft_w / (eta_motor * eta_inverter) + number(energy["auxiliary_power_w"], "auxiliary_power_w")
        row["within_requested_continuous_envelope"] = (
            shaft_w <= positive(envelope["continuous_shaft_power_w"], "continuous_power")
            and row["wheel_torque_nm"] <= positive(envelope["continuous_torque_nm"], "continuous_torque"))
        row["within_tentative_peak_envelope"] = (
            shaft_w <= positive(envelope["tentative_peak_shaft_power_w"], "peak_power")
            and row["wheel_torque_nm"] <= positive(envelope["tentative_peak_torque_nm"], "peak_torque"))
        # An acceleration sample is not a trip-energy or achievable-range model.
        if row["acceleration_m_s2"] == 0 and row["speed_kmh"] > 0:
            row["conditional_wh_per_km"] = row["battery_power_assumption_w"] / row["speed_kmh"]
            row["conditional_steady_range_km"] = usable_wh / row["conditional_wh_per_km"]
            row["range_is_achievability_claim"] = False
    screens = [electrical_screen(dc, power, config["inverter_screen"], energy)
               for dc in config["inverter_screen"]["bus_voltages_v"]
               for power in config["inverter_screen"]["shaft_power_targets_w"]]
    sensitivity = []
    for eta in energy["motor_efficiency_sensitivity"]:
        for grade in (0.0, 5.0):
            row = road_load(config["vehicle"], 25.0 if grade == 0 else 10.0, grade)
            battery_w = row["wheel_mechanical_power_w"] / (fraction(eta, "sensitivity_eta") * eta_inverter) + number(energy["auxiliary_power_w"], "auxiliary_power_w")
            sensitivity.append({"motor_efficiency_assumption": eta, "grade_pct": grade,
                                "speed_kmh": row["speed_kmh"], "battery_power_w": battery_w,
                                "conditional_steady_range_km": usable_wh * row["speed_kmh"] / battery_w})
    frequency = []
    for pairs in config["pole_pair_candidates"]:
        if isinstance(pairs, bool) or not isinstance(pairs, int) or pairs <= 0:
            raise ValueError("pole_pair_candidates must be positive integers")
        rpm = road_load(config["vehicle"], 25.0, 0.0)["wheel_rpm"]
        frequency.append({"pole_pairs": pairs, "wheel_rpm": rpm,
                          "rotor_electrical_frequency_hz": pairs * rpm / 60,
                          "stator_frequency_requires_additional_slip_hz": True})
    digest = hashlib.sha256(json.dumps(config, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"schema": "mic_ai.motor_wheel.preliminary_sizing.v1",
            "input_sha256": digest, "inputs": config, "usable_battery_energy_assumption_wh": usable_wh,
            "road_cases": rows, "inverter_screen": screens,
            "efficiency_sensitivity": sensitivity, "pole_pair_screen": frequency,
            "fea_completed": False, "motor_identified": False, "hardware_validated": False}


def markdown(report: dict) -> str:
    lines = ["# Предварительный расчёт асинхронного мотор колеса", "",
             "Расчёт по заданным допущениям. Геометрия двигателя, его параметры и характеристики не измерены. Проверка по току оптимистическая и не подтверждает работоспособность двигателя или платы.", "",
             f"Контрольная сумма входных данных: `{report['input_sha256']}`.", "",
             "## Тяга и мощность", "",
             "| Скорость км/ч | Уклон % | Ускорение м/с² | Обороты об/мин | Момент Н·м | Мощность колеса Вт | Оценка от батареи Вт | В целевой длительной характеристике |",
             "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in report["road_cases"]:
        lines.append(f"| {r['speed_kmh']:.0f} | {r['grade_pct']:.0f} | {r['acceleration_m_s2']:.1f} | {r['wheel_rpm']:.1f} | {r['wheel_torque_nm']:.2f} | {r['wheel_mechanical_power_w']:.1f} | {r['battery_power_assumption_w']:.1f} | {'Да' if r['within_requested_continuous_envelope'] else 'Нет'} |")
    lines += ["", "Инерция вращающихся деталей в ускорение не включена. Диаметр 0,508 м, масса 120 кг, сопротивление качению 0,015 и CdA 0,6 м² являются допущениями. Мощность от батареи включает предположенные КПД двигателя 0,75, инвертора 0,95 и 15 Вт вспомогательной нагрузки.", "",
              "## Предварительная проверка трёхфазной платы", "",
              "| Шина В | Цель на колесе Вт | Доступное U между фазами RMS В | Минимальный оценочный ток RMS А | Пик синусоиды без пульсаций А | В номинале 15 А RMS | В предложенном пике 25 А |",
              "|---:|---:|---:|---:|---:|---|---|"]
    for r in report["inverter_screen"]:
        lines.append(f"| {r['dc_bus_v']:.0f} | {r['shaft_power_target_w']:.0f} | {r['available_line_line_fundamental_rms_v']:.2f} | {r['optimistic_line_current_rms_a']:.2f} | {r['fundamental_sinusoidal_peak_a_excluding_pwm_ripple']:.2f} | {'Да' if r['within_board_nominal_rms_current'] else 'Нет'} | {'Да' if r['within_proposed_software_peak'] else 'Нет'} |")
    lines += ["", "Предположены cos φ = 0,8 и использование 90% линейного диапазона SVPWM. Реальный ток на малой скорости требует карты двигателя; ток намагничивания, насыщение и пульсации могут ухудшить результат. Порог OCP не является допустимым рабочим током. Положительный результат таблицы не даёт разрешения на пуск.", "",
              "## Чувствительность запаса хода к КПД", "",
              "| Предположенный КПД двигателя | Скорость км/ч | Уклон % | От батареи Вт | Условный пробег км |", "|---:|---:|---:|---:|---:|"]
    for r in report["efficiency_sensitivity"]:
        lines.append(f"| {r['motor_efficiency_assumption']:.2f} | {r['speed_kmh']:.0f} | {r['grade_pct']:.0f} | {r['battery_power_w']:.1f} | {r['conditional_steady_range_km']:.1f} |")
    lines += ["", "Использованы 36 В × 14 А·ч × 0,8 = 403,2 Вт·ч. Это сценарий постоянного движения, без доказательства достижимости режима, остановок, ветра, изменения КПД и просадки батареи. Паспортная энергия не заменяет измеренную разрядную кривую.", "",
              "## Частота и число пар полюсов", ""]
    for r in report["pole_pair_screen"]:
        lines.append(f"- {r['pole_pairs']} пар полюсов: при {r['wheel_rpm']:.1f} об/мин электрическая частота ротора {r['rotor_electrical_frequency_hz']:.2f} Гц; к частоте статора добавляется частота скольжения.")
    lines += ["", "## Границы результата", "", "FEA, тепловой расчёт, прочность, идентификация двигателя, обучение ИИ и аппаратные испытания ещё не выполнены. Файл не содержит интерфейсов оборудования.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path(__file__).with_name("sizing_inputs.json"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    report = calculate(json.loads(args.inputs.read_text(encoding="utf-8")))
    if args.output_dir is None:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "preliminary_sizing.json"
        report_path = args.output_dir / "REPORT_RU.md"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        report_path.write_text(markdown(report), encoding="utf-8")
        print(json_path.resolve())
        print(report_path.resolve())


if __name__ == "__main__":
    main()
