import inspect
import math

from config.env import MotorParams
from estimation.sensorless_flux_slip_observer import SensorlessFluxSlipConfig, SensorlessFluxSlipObserver
from models.induction_motor_current_flux_rk4 import CurrentFluxInductionMotorRk4, CurrentFluxMotorParams


def _motor() -> CurrentFluxMotorParams:
    return CurrentFluxMotorParams.from_motor_params(
        MotorParams(
            Rs=5.39,
            Rr=14.22,
            Ls_sigma=0.00249,
            Lr_sigma=0.00194,
            Lm=0.482,
            J=8e-5,
            B=1.5e-4,
            p=1,
            I_n=1.24,
        ),
        current_limit_a=12.0,
    )


def test_independent_plant_is_finite_under_zero_voltage() -> None:
    plant = CurrentFluxInductionMotorRk4(_motor())
    for _ in range(100):
        output = plant.step(0.0, 0.0, 0.0, 1e-4)
    assert output.current_abs_a == 0.0
    assert output.state.omega_m_rad_s == 0.0
    assert output.torque_nm == 0.0


def test_sensorless_observer_signature_has_no_speed_angle_or_true_flux_input() -> None:
    signature = inspect.signature(SensorlessFluxSlipObserver.step)
    assert set(signature.parameters) == {
        "self",
        "v_alpha_v",
        "v_beta_v",
        "i_s_alpha_a",
        "i_s_beta_a",
        "dt_s",
    }


def test_sensorless_observer_builds_flux_from_voltage_and_current_only() -> None:
    motor = _motor()
    observer = SensorlessFluxSlipObserver(
        SensorlessFluxSlipConfig(
            rs_ohm=motor.rs_ohm,
            rr_ohm=motor.rr_ohm,
            ls_h=motor.ls_h,
            lr_h=motor.lr_h,
            lm_h=motor.lm_h,
            pole_pairs=motor.pole_pairs,
        )
    )
    update = None
    for index in range(2000):
        theta = 2.0 * math.pi * 20.0 * index * 1e-4
        update = observer.step(
            v_alpha_v=50.0 * math.cos(theta),
            v_beta_v=50.0 * math.sin(theta),
            i_s_alpha_a=0.2 * math.cos(theta - 0.5),
            i_s_beta_a=0.2 * math.sin(theta - 0.5),
            dt_s=1e-4,
        )
    assert update is not None
    assert update.input_contract == "applied_voltage_and_measured_stator_current_only"
    assert update.state.valid
    assert math.isfinite(update.state.omega_m_rad_s)
