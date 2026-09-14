import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location("active_audit", ROOT/"tools/analyze_air56b2_active_probe.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def study():
    base = dict(case="motor0", duration_s=3., total_simulation_s=4., speed_fraction=.7,
        disturbance=False, noise_seed=730, dt_s=.1, plant_substeps=2, observer="current",
        method="fixed", supervisor=None,
        trace_columns=["time_s", "true_interval_terminal_power_w", "phase"],
        trace=[[1.,100.,"fixed"],[2.,100.,"fixed"],[3.,100.,"fixed"]])
    row = copy.deepcopy(base)
    row.update(method="active_cost", supervisor=dict(cycles=[], open_episode=None,
        episodes=[dict(start_s=.5,end_s=3.,kind="verification_hold_return",predicted_cost_j=1.,
                       interrupted=True,recovery_window_observed=True,missing_measurement_s=.1)]),
        trace=[[1.,102.,"candidateverify"],[2.,200.,"committed"],[3.,103.,"rejected"]])
    return dict(rows=[base,row])


def test_journal_audit_includes_failed_final_return_but_separates_holding():
    data = audit.audit_episodes(study())
    assert len(data) == 1
    assert data[0]["sampled_nonholding_cost_j"] == 5.
    assert data[0]["underpredicted"]
    assert data[0]["interrupted"]
    assert data[0]["missing_measurement_s"] == .1


def test_unclosed_episode_is_right_censored_not_zero_cost_success():
    data = study()
    s = data["rows"][-1]["supervisor"]
    s["open_episode"] = dict(kind="query_return",start_s=2.,recovery_window_observed=False)
    result = audit.audit_episodes(data)[-1]
    assert result["status"] == "right_censored"
    assert result["underpredicted"] is None
    assert result["sampled_nonholding_cost_j"] == 3.


def test_mismatched_grid_never_interpolated_as_if_same_experiment():
    data = study()
    data["rows"][-1]["trace"][0][0] += .1
    assert audit.audit_episodes(data)[0]["status"] == "unmatched_grid"


def test_changed_result_artifact_rejected(tmp_path):
    import json
    (tmp_path/"manifest.json").write_text(json.dumps(dict(outputs={"study.json":"wrong"})))
    (tmp_path/"study.json").write_text("{}")
    with pytest.raises(ValueError,match="artifact changed"):
        audit.load_study(tmp_path)
