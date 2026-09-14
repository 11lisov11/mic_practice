import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location("accepted_refinement",ROOT/"tools/run_air56b2_accepted_refinement.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def row(case,**changes):
    return dict(case=case,speed_fraction=.7,method="energy_value",eligible=True,
                ever_committed=True,duration_s=12.,disturbance=False,**changes)


def test_selection_not_based_on_largest_or_positive_saving():
    negative = row("a",loss_saving_j=-1.)
    positive = row("b",loss_saving_j=100.)
    assert runner.select_case(dict(pairs=[positive,negative])) is negative


def test_ineligible_or_uncommitted_case_not_substituted():
    a = row("a")
    a["eligible"] = False
    b = row("b")
    b["ever_committed"] = False
    assert runner.select_case(dict(pairs=[a,b])) is None


def test_first_speed_breaks_tie_not_saving():
    a = row("a",loss_saving_j=1.)
    b = row("a",loss_saving_j=100.)
    a["speed_fraction"] = .3
    assert runner.select_case(dict(pairs=[b,a])) is a


def test_disturbed_or_short_case_not_used_for_steady_12s_refinement():
    a = row("a")
    b = row("b")
    a["disturbance"] = True
    b["duration_s"] = 6.
    assert runner.select_case(dict(pairs=[a,b])) is None
