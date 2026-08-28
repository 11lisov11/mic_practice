from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from config.env import MotorParams, create_default_env


"""AIR56B2 FOC/PPO research profile with explicit parameter provenance.

Only the motor nameplate is authoritative hardware data. Electrical and
mechanical model constants are the deterministic central sample of the
nameplate-constrained F1 ensemble. Controller gains are mapped from the
selected encoder-observer FOC simulation candidate. Neither source is a
substitute for hardware identification or commissioning.
"""

PROFILE_SCHEMA = "air56b2-foc-ppo-profile-v1"
SOURCE_KIND = "official_nameplate_plus_simulation_prior"
PHYSICAL_CONNECTION = "D"
MODEL_CONNECTION = "power_invariant_star_equivalent"
HARDWARE_IDENTIFIED = False
HARDWARE_RELEASE_READY = False
PARAMETER_SAMPLE_INDEX = 128

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENSEMBLE_PATH = REPOSITORY_ROOT / "artifacts" / "air56b2_nameplate_ensemble.json"
ENCODER_FOC_TUNING_PATH = REPOSITORY_ROOT / "artifacts" / "air56b2_encoder_foc_tuning.json"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required AIR56B2 artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_provenance() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ensemble = _read_json(ENSEMBLE_PATH)
    if ensemble.get("schema") != "air56b2-nameplate-ensemble-v2":
        raise ValueError("Unsupported AIR56B2 ensemble schema")
    if int(ensemble.get("master_seed", -1)) != 560225:
        raise ValueError("Unexpected AIR56B2 ensemble seed")
    if int(ensemble.get("sample_count", -1)) != 256:
        raise ValueError("AIR56B2 ensemble must contain 256 samples")
    if bool(ensemble.get("hardware_identified", True)):
        raise ValueError("Simulation-prior profile must not claim hardware identification")

    sample = next(
        (row for row in ensemble.get("samples", []) if int(row.get("index", -1)) == PARAMETER_SAMPLE_INDEX),
        None,
    )
    if sample is None:
        raise ValueError(f"AIR56B2 ensemble sample {PARAMETER_SAMPLE_INDEX} is missing")

    tuning = _read_json(ENCODER_FOC_TUNING_PATH)
    if tuning.get("schema") != "air56b2-encoder-foc-tuning-v1":
        raise ValueError("Unsupported AIR56B2 encoder FOC tuning schema")
    if tuning.get("status") != "PASS":
        raise ValueError("AIR56B2 encoder FOC tuning did not pass its simulation gates")
    if bool(tuning.get("hardware_identified", True)) or bool(tuning.get("hardware_claim", True)):
        raise ValueError("FOC tuning artifact must remain simulation-only")
    return ensemble, sample, tuning


_ensemble, _sample, _tuning = _load_provenance()
_nameplate = _ensemble["nameplate"]
_derived = _ensemble["derived"]
_motor_data = _sample["motor"]
_foc_tuning = _tuning["selected"]["config"]

NAMEPLATE_AIR56B2_025KW_DELTA = {
    "P_n": float(_nameplate["output_power_w"]),
    "U_ll": float(_nameplate["line_voltage_v"]),
    "I_n": float(_nameplate["line_current_a"]),
    "cos_phi_n": float(_nameplate["power_factor"]),
    "eta_n": float(_nameplate["efficiency"]),
    "f_n": float(_nameplate["frequency_hz"]),
    "p": int(_nameplate["pole_pairs"]),
    "n_rated": float(_nameplate["rated_speed_rpm"]),
    "connection": str(_nameplate["connection"]),
}

RATED_TORQUE_NM = float(_derived["rated_torque_nm"])
OMEGA_BASE_RAD_S = float(_derived["rated_omega_rad_s"])
PARAMETER_SAMPLE_SEED = int(_sample["seed"])
FOC_TUNING_CANDIDATE_INDEX = int(_tuning["selected"]["candidate_index"])

_motor = MotorParams(
    Rs=float(_motor_data["Rs"]),
    Rr=float(_motor_data["Rr"]),
    Ls_sigma=float(_motor_data["Ls_sigma"]),
    Lr_sigma=float(_motor_data["Lr_sigma"]),
    Lm=float(_motor_data["Lm"]),
    J=float(_motor_data["J"]),
    B=float(_motor_data["B"]),
    p=int(_motor_data["p"]),
    I_n=float(_motor_data["I_n"]),
    psi_sat=float(_motor_data["psi_sat"]),
    sat_exp=float(_motor_data["sat_exp"]),
    lm_min_scale=float(_motor_data["lm_min_scale"]),
)

_base = create_default_env()
_inverter = replace(
    _base.inverter,
    Vdc=325.0,
    f_pwm=10_000.0,
    r_out=0.12,
    dead_time=2e-6,
    v_drop=1.2,
)
_scalar_vf = replace(
    _base.scalar_vf,
    k_vf=(220.0 / math.sqrt(3.0)) / 50.0,
    u_boost=12.0,
    f_min=1.0,
    f_max=50.0,
    u_phase_nom=220.0 / math.sqrt(3.0),
)

# The tuning artifact stores rotor-flux reference. The legacy FOC/PPO stack
# accepts a d-axis current reference, so the initial mapping is psi_r/Lm.
# This mapping is explicitly a simulation initialization, not an identified
# hardware setpoint.
_id_ref = float(_foc_tuning["flux_ref_wb"]) / max(_motor.Lm, 1e-9)
_foc = replace(
    _base.foc,
    kp_id=float(_foc_tuning["current_kp"]),
    ki_id=float(_foc_tuning["current_ki"]),
    kp_iq=float(_foc_tuning["current_kp"]),
    ki_iq=float(_foc_tuning["current_ki"]),
    kp_speed=float(_foc_tuning["speed_kp"]),
    ki_speed=float(_foc_tuning["speed_ki"]),
    id_ref=_id_ref,
    iq_limit=float(_foc_tuning["iq_max_fraction"]) * _motor.I_n,
    v_limit=float(_foc_tuning["voltage_limit_fraction"]) * _inverter.Vdc / math.sqrt(3.0),
    field_weakening_enable=False,
)
_sim = replace(
    _base.sim,
    t_end=1.2,
    dt=float(_foc_tuning["dt_s"]),
    mode="foc",
    scenario_name="speed_step",
    save_prefix="air56b2_foc_ppo_simulation_prior",
    load_torque=0.0,
)

ENV = replace(
    _base,
    motor=_motor,
    inverter=_inverter,
    scalar_vf=_scalar_vf,
    foc=_foc,
    sim=_sim,
    omega_base_rad_s=OMEGA_BASE_RAD_S,
)

# Optional training hints are copied onto ENV by mic_ai.core.env.
ai_omega_ref_pu_range = (0.2, 0.9)
ai_load_torque_range = (0.0, RATED_TORQUE_NM)
ai_profile_contract = "simulation_prior_only_no_hardware_release"

PARAMETER_PROVENANCE = {
    "nameplate": str(ENSEMBLE_PATH),
    "motor_parameter_sample_index": PARAMETER_SAMPLE_INDEX,
    "motor_parameter_sample_seed": PARAMETER_SAMPLE_SEED,
    "foc_tuning": str(ENCODER_FOC_TUNING_PATH),
    "foc_tuning_candidate_index": FOC_TUNING_CANDIDATE_INDEX,
    "hardware_identified": HARDWARE_IDENTIFIED,
    "hardware_release_ready": HARDWARE_RELEASE_READY,
}


def create_env_for_sample(sample_index: int):
    """Return the same profile with another deterministic ensemble sample."""
    selected = next(
        (row for row in _ensemble["samples"] if int(row["index"]) == int(sample_index)),
        None,
    )
    if selected is None:
        raise IndexError(f"AIR56B2 ensemble sample out of range: {sample_index}")
    data = selected["motor"]
    motor = replace(
        _motor,
        Rs=float(data["Rs"]),
        Rr=float(data["Rr"]),
        Ls_sigma=float(data["Ls_sigma"]),
        Lr_sigma=float(data["Lr_sigma"]),
        Lm=float(data["Lm"]),
        J=float(data["J"]),
        B=float(data["B"]),
    )
    foc = replace(_foc, id_ref=float(_foc_tuning["flux_ref_wb"]) / max(motor.Lm, 1e-9))
    return replace(ENV, motor=motor, foc=foc)


__all__ = [
    "ENV",
    "PROFILE_SCHEMA",
    "SOURCE_KIND",
    "PHYSICAL_CONNECTION",
    "MODEL_CONNECTION",
    "HARDWARE_IDENTIFIED",
    "HARDWARE_RELEASE_READY",
    "NAMEPLATE_AIR56B2_025KW_DELTA",
    "RATED_TORQUE_NM",
    "OMEGA_BASE_RAD_S",
    "PARAMETER_SAMPLE_INDEX",
    "PARAMETER_SAMPLE_SEED",
    "FOC_TUNING_CANDIDATE_INDEX",
    "PARAMETER_PROVENANCE",
    "create_env_for_sample",
]
