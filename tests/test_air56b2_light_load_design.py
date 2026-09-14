"""Check the prospective matrix without running or inspecting motor outcomes."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("low_load_design",ROOT/"tools/run_air56b2_light_load.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_complete_fixed_matrix():
    protocol,jobs = runner.design("light_load")
    assert len(jobs)==128
    assert len({(j[0],j[3],j[6],j[7]) for j in jobs})==128
    assert len(protocol["cases"])==8
    assert protocol["seeds"]==[92067,92068]
    assert all(j[4] is False and j[5]==12. and j[7]==2 and j[8:10]==(.1,.1) for j in jobs)
    assert {j[3] for j in jobs}==set(runner.METHODS)
    assert all(c["controller"]==protocol["cases"][0]["controller"] for c in protocol["cases"])
    assert protocol["exploratory_extension"]


def test_refinement_is_prespecified_not_selected_by_gain():
    protocol,jobs = runner.design("light_load_refinement")
    assert len(jobs)==24
    assert {j[0] for j in jobs}=={"s92067_motor0_k0"}
    assert {j[6] for j in jobs}=={.7}
    assert {j[7] for j in jobs}=={2,4,8}
    assert len({(j[3],j[7]) for j in jobs})==24
    assert len(protocol["cases"])==1


def test_rejects_unknown_stage():
    with pytest.raises(ValueError,match="unknown stage"):
        runner.design("best_case")
