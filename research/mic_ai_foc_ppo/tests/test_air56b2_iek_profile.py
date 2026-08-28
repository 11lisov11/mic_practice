import math

from config.env_air56b2_iek_025kw_delta import (
    ENV,
    MODEL_INPUT_AIR56B2_STAR_EQUIVALENT,
    NAMEPLATE_AIR56B2_025KW_DELTA,
    PHYSICAL_CONNECTION,
    SOURCE_KIND,
)


def test_air56b2_nameplate_and_inverter_scaling() -> None:
    assert SOURCE_KIND == "official_catalog_nameplate_with_unmeasured_model_parameters"
    assert PHYSICAL_CONNECTION == "D"
    assert NAMEPLATE_AIR56B2_025KW_DELTA["connection"] == "D"
    assert NAMEPLATE_AIR56B2_025KW_DELTA["P_n"] == 250.0
    assert NAMEPLATE_AIR56B2_025KW_DELTA["U_ll"] == 220.0
    assert NAMEPLATE_AIR56B2_025KW_DELTA["I_n"] == 1.24
    assert NAMEPLATE_AIR56B2_025KW_DELTA["p"] == 1
    assert NAMEPLATE_AIR56B2_025KW_DELTA["n_rated"] == 2720.0

    assert MODEL_INPUT_AIR56B2_STAR_EQUIVALENT["connection"] == "Y"
    phase_voltage = 220.0 / math.sqrt(3.0)
    assert math.isclose(ENV.scalar_vf.u_phase_nom or 0.0, phase_voltage)
    assert math.isclose(ENV.scalar_vf.k_vf, phase_voltage / 50.0)
    assert ENV.motor.p == 1
    assert ENV.inverter.Vdc == 325.0
    assert ENV.inverter.Vdc >= math.sqrt(2.0) * NAMEPLATE_AIR56B2_025KW_DELTA["U_ll"]
    assert ENV.sim.mode == "scalar"
    assert ENV.sim.load_torque == 0.0
