"""Publication-only audit. All study data and generated artifacts stay in memory."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def import_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def analysis():
    return import_tool("publication_review_analysis", "analyze_air56b2_energy_value.py")


@pytest.fixture(scope="module")
def accepted():
    return import_tool("publication_review_accepted", "run_air56b2_accepted_refinement.py")


class MemoryPath:
    def __init__(self, path="/", files=None, directories=None):
        self.path = PurePosixPath(path)
        self.files = {} if files is None else files
        self.directories = set() if directories is None else directories

    def __truediv__(self, name):
        return MemoryPath(self.path / name, self.files, self.directories)

    def __str__(self):
        return str(self.path)

    @property
    def name(self):
        return self.path.name

    def exists(self):
        return self.path in self.files or self.path in self.directories

    def is_file(self):
        return self.path in self.files

    def mkdir(self, parents=False):
        assert not self.exists()
        self.directories.add(self.path)

    def read_bytes(self):
        return self.files[self.path]

    def read_text(self, encoding=None):
        return self.read_bytes().decode(encoding or "utf-8")

    def write_bytes(self, value):
        self.files[self.path] = value
        return len(value)

    def write_text(self, value, encoding=None):
        return self.write_bytes(value.encode(encoding or "utf-8"))

    def iterdir(self):
        return [MemoryPath(p, self.files, self.directories)
                for p in self.files if p.parent == self.path]

    def open(self, mode, encoding=None):
        assert mode == "w"
        path = self

        class Writer(io.StringIO):
            def flush(self):
                path.write_text(self.getvalue(), encoding)

            def close(self):
                if not self.closed:
                    self.flush()
                super().close()

        return Writer()


def row(method, case="fixture_motor0_k0", substeps=2, **changes):
    loss = 50. if method == "fixed" else 45. if method == "energy_value" else 48.
    result = dict(
        case=case, method=method, duration_s=12., total_simulation_s=13.,
        speed_fraction=.7, disturbance=False, noise_seed=730, dt_s=.0001,
        plant_substeps=substeps, observer="current", initial_load_fraction=.25,
        final_load_fraction=.5, load_step_s=2.6, status="PASS", probe_complete=True,
        probe_reason="scheduled_return", completed_steps=130000,
        checks={"complete": True}, final_id_a=.83, peak_current_a=2.,
        evaluation_final_state=[.1, 0., .09, 0., .08, 0., 100.],
        supervisor={"ever_committed": method != "fixed"},
        energy=dict(shaft_work_j=100., stored_change_j=0., input_j=100.+loss, loss_j=loss),
    )
    result.update(changes)
    return result


def study(analysis, rows):
    from tools.run_air56b2_active_probe import aggregate, matched_results

    pairs = matched_results(rows, methods=analysis.METHODS, keys=analysis.KEYS)
    return dict(rows=rows, pairs=pairs,
                summary=aggregate(pairs, methods=analysis.METHODS, keys=analysis.KEYS))


def matrix(analysis, cases=("fixture_motor0_k0",), substeps=(2,)):
    return study(analysis, [row(method, case, n)
                           for case in cases for n in substeps for method in analysis.METHODS])


def protocol(analysis, cases=("fixture_motor0_k0",), substeps=(2,), stage="validation"):
    return dict(
        stage=stage, methods=list(analysis.METHODS),
        cases=[dict(case=c, plant={}, controller={}) for c in cases],
        profiles=[[12., False, .25, .5, 2.6]], speeds=[.7], substeps=list(substeps),
        control_dt_s=.0001, recovery_tail_s=1., noise_seed=730,
    )


def bundle(analysis, root, name, data, proto):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "study.json").write_text(json.dumps(data))
    (folder / "protocol.json").write_text(json.dumps(proto))
    manifest = dict(sources={"fixture_source.py": "frozen"}, outputs={
        filename: analysis.digest(folder / filename)
        for filename in ("study.json", "protocol.json")
    })
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return folder


def test_valid_synthetic_bundle_loads(analysis):
    data = matrix(analysis)
    folder = bundle(analysis, MemoryPath(), "validation", data, protocol(analysis))
    assert analysis.load(folder)[0] == data


def test_hash_mismatch_is_rejected(analysis):
    folder = bundle(analysis, MemoryPath(), "validation", matrix(analysis), protocol(analysis))
    (folder / "study.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact changed"):
        analysis.load(folder)


def test_critical_artifacts_must_be_covered_by_manifest(analysis):
    folder = bundle(analysis, MemoryPath(), "validation", matrix(analysis), protocol(analysis))
    manifest = json.loads((folder / "manifest.json").read_text())
    del manifest["outputs"]["study.json"]
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        analysis.load(folder)


def test_duplicate_jobs_cannot_replace_missing_case_at_equal_row_count(analysis):
    data = matrix(analysis)
    data["rows"] *= 2
    data["pairs"] *= 2
    proto = protocol(analysis, cases=("fixture_motor0_k0", "fixture_motor1_k0"))
    folder = bundle(analysis, MemoryPath(), "validation", data, proto)
    with pytest.raises(ValueError):
        analysis.load(folder)


@pytest.mark.parametrize("field,value", [("case", "unplanned"), ("speed_fraction", .3),
                                         ("plant_substeps", 4), ("noise_seed", 731)])
def test_equal_sized_unplanned_job_set_is_rejected(analysis, field, value):
    data = study(analysis, [row(m, **{field: value}) for m in analysis.METHODS])
    folder = bundle(analysis, MemoryPath(), "validation", data, protocol(analysis))
    with pytest.raises(ValueError):
        analysis.load(folder)


def test_direct_sign_and_pairing_do_not_depend_on_row_order(analysis):
    data = matrix(analysis, cases=("fixture_motor0_k0", "fixture_motor1_k0"))
    for r in data["rows"]:
        if r["case"] == "fixture_motor1_k0" and r["method"] == "energy_value":
            r["energy"]["loss_j"] = 52.
            r["energy"]["input_j"] = 152.
    data = study(analysis, list(reversed(data["rows"])))
    direct = analysis.direct_comparisons(data)
    assert all(p["loss_advantage_j"] == (3. if p["case"] == "fixture_motor0_k0" else -4.)
               for p in direct)


def test_incomplete_horizon_never_generates_direct_saving(analysis):
    rows = matrix(analysis)["rows"]
    ev = next(r for r in rows if r["method"] == "energy_value")
    ev.update(checks={"complete": False}, completed_steps=10, status="FAIL")
    assert all(p["loss_advantage_j"] is None and not p["eligible"]
               for p in analysis.direct_comparisons(study(analysis, rows)))


def test_stale_pair_flags_cannot_turn_a_truncated_row_into_saving(analysis):
    data = matrix(analysis)
    ev = next(r for r in data["rows"] if r["method"] == "energy_value")
    ev.update(checks={"complete": False}, completed_steps=10, status="FAIL")
    try:
        direct = analysis.direct_comparisons(data)
    except ValueError:
        return
    assert all(p["loss_advantage_j"] is None and not p["eligible"] for p in direct)


def test_direct_endpoint_is_checked_between_competitors(analysis):
    data = matrix(analysis)
    for r in data["rows"]:
        if r["method"] == "energy_value":
            r["evaluation_final_state"][-1] += .09
        elif r["method"] == "greedy":
            r["evaluation_final_state"][-1] -= .09
    data = study(analysis, data["rows"])
    comparison = next(p for p in analysis.direct_comparisons(data) if p["comparator"] == "greedy")
    assert comparison["full_horizon"] and not comparison["eligible"]


def test_refinement_preserves_outcome_and_endpoint_failures(analysis):
    data = matrix(analysis, substeps=(2, 4, 8))
    p = next(p for p in data["pairs"] if p["method"] == "energy_value" and p["plant_substeps"] == 8)
    p.update(eligible=False, reason="verification_declined", ever_committed=False)
    result = next(r for r in analysis.refine(data) if r["method"] == "energy_value")
    assert not result["passed"] and not result["same_outcome"] and result["eligible"] == 2


@pytest.mark.parametrize("field,values", [
    ("case", ("fixture_motor0_k0", "fixture_motor1_k0", "fixture_motor2_k0")),
    ("speed_fraction", (.3, .5, .7)),
    ("initial_load_fraction", (.25, .4, .5)),
    ("load_step_s", (2.6, 4.2, 5.)),
    ("dt_s", (.0001, .00005, .000025)),
])
def test_refinement_requires_same_scenario_except_plant_substeps(analysis, field, values):
    rows = []
    for n, value in zip((2, 4, 8), values):
        for method in analysis.METHODS:
            r = row(method, substeps=n, **{field: value})
            r["completed_steps"] = round(r["total_simulation_s"] / r["dt_s"])
            rows.append(r)
    with pytest.raises(ValueError):
        analysis.refine(study(analysis, rows))


def test_refinement_cannot_omit_a_required_substep(analysis):
    with pytest.raises(ValueError, match="2/4/8"):
        analysis.refine(matrix(analysis, substeps=(2, 4)))


def test_accepted_selection_is_lexical_not_largest_saving(analysis, accepted):
    data = matrix(analysis, cases=("fixture_motor1_k0", "fixture_motor0_k0"))
    for r in data["rows"]:
        if r["method"] == "energy_value":
            saving = 999. if r["case"] == "fixture_motor1_k0" else -.01
            r["energy"].update(loss_j=50. - saving, input_j=150. - saving)
    data = study(analysis, data["rows"])
    chosen = accepted.select_case(data)
    assert chosen["case"] == "fixture_motor0_k0"
    assert accepted.select_case(dict(pairs=list(reversed(data["pairs"])))) == chosen


def mock_accepted_run(monkeypatch, accepted, folder, root):
    submitted = []

    class Executor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, function, job):
            # Never call function/run_job or instantiate a physical plant.
            submitted.append(job)
            r = row(job[3], case=job[0], substeps=job[7], speed_fraction=job[6],
                    initial_load_fraction=job[8], final_load_fraction=job[9], load_step_s=job[10])
            return SimpleNamespace(result=lambda: r)

    out = root / "accepted"
    monkeypatch.setattr(accepted.argparse.ArgumentParser, "parse_args",
                        lambda self: SimpleNamespace(validation=folder, out=out, workers=2))
    monkeypatch.setattr(accepted, "source_hashes", lambda: {"fixture_source.py": "frozen"})
    monkeypatch.setattr(accepted, "run_job", lambda job: pytest.fail("physical run_job is forbidden"))
    monkeypatch.setattr(accepted, "ProcessPoolExecutor", Executor)
    monkeypatch.setattr(accepted, "as_completed", lambda fs: reversed(fs))
    monkeypatch.setattr(accepted, "EnergyCoreParams", lambda **kwargs: "plant_stub")
    monkeypatch.setattr(accepted, "AlphaBetaMotorParams", lambda **kwargs: "control_stub")
    monkeypatch.setattr(accepted, "ROOT", root / "repo")
    (accepted.ROOT / "research/AIR56B2_ENERGY_VALUE_ADDITIONAL_REFINEMENT_RU.md").write_text("fixture rule")
    return submitted, out


def test_accepted_runner_constructs_exact_24_jobs_and_retains_parent_hash(analysis, accepted, monkeypatch):
    root = MemoryPath()
    folder = bundle(analysis, root, "validation", matrix(analysis), protocol(analysis))
    jobs, out = mock_accepted_run(monkeypatch, accepted, folder, root)
    accepted.main()
    assert len(jobs) == 24
    assert {(j[3], j[7]) for j in jobs} == {(m, n) for m in analysis.METHODS for n in (2, 4, 8)}
    proto = json.loads((out / "protocol.json").read_text())
    assert proto["conditional_selection"] is True
    assert proto["source_study_sha256"] == analysis.digest(folder / "study.json")
    assert len(json.loads((out / "study.json").read_text())["rows"]) == 24


def test_no_accepted_case_is_explicit_and_does_not_submit_jobs(analysis, accepted, monkeypatch):
    root = MemoryPath()
    data = matrix(analysis)
    for r in data["rows"]:
        r["supervisor"]["ever_committed"] = False
    data = study(analysis, data["rows"])
    folder = bundle(analysis, root, "validation", data, protocol(analysis))
    jobs, out = mock_accepted_run(monkeypatch, accepted, folder, root)
    accepted.main()
    assert jobs == [] and not (out / "study.json").exists()
    assert json.loads((out / "NO_ACCEPTED_CASE.json").read_text())["status"] == "no_eligible_committed_12s_steady_case"


def test_accepted_runner_rejects_incomplete_parent_before_selection(analysis, accepted, monkeypatch):
    root = MemoryPath()
    data = matrix(analysis)
    proto = protocol(analysis, cases=("fixture_motor0_k0", "fixture_motor1_k0"))
    folder = bundle(analysis, root, "validation", data, proto)
    jobs, _ = mock_accepted_run(monkeypatch, accepted, folder, root)
    with pytest.raises(ValueError):
        accepted.main()
    assert jobs == []


def details(analysis, data):
    return dict(direct=analysis.direct_comparisons(data), breakdown=analysis.breakdown(data),
                cycles=[], episodes=[], refinement=[])


def test_report_labels_acceptance_conditioning_separately_from_endpoint_filter(analysis):
    root = MemoryPath()
    data = matrix(analysis, substeps=(2, 4, 8))
    proto = protocol(analysis, substeps=(2, 4, 8), stage="accepted_refinement")
    proto.update(conditional_selection=True, selection_rule="first_eligible_committed_case_then_speed_not_saving")
    analysis.report({"accepted_refinement": (data, proto, {})},
                    {"accepted_refinement": details(analysis, data)}, root)
    rendered = (root / "RESULTS_RU.md").read_text().lower()
    assert ("first_eligible_committed" in rendered or "выбран по" in rendered
            or "отобран по" in rendered or "условный выбор" in rendered), (
        "endpoint-conditioned averages do not disclose acceptance-conditioned case selection"
    )


def test_analysis_rejects_refinement_from_another_parent_study(analysis, monkeypatch):
    root = MemoryPath()
    validation = bundle(analysis, root, "validation", matrix(analysis), protocol(analysis))
    proto = protocol(analysis, substeps=(2, 4, 8), stage="accepted_refinement")
    proto.update(conditional_selection=True, source_study_sha256="wrong_parent_hash")
    refinement = bundle(analysis, root, "accepted", matrix(analysis, substeps=(2, 4, 8)), proto)
    monkeypatch.setattr(analysis.argparse.ArgumentParser, "parse_args", lambda self: SimpleNamespace(
        validation=validation, stress=None, refinement=None, accepted_refinement=refinement))
    monkeypatch.setattr(analysis.paired_audit, "audit_cycles", lambda *a, **k: [])
    monkeypatch.setattr(analysis.paired_audit, "audit_episodes", lambda *a, **k: [])
    monkeypatch.setattr(analysis, "figures", lambda *a: None)
    monkeypatch.setattr(analysis, "archive", lambda folder, *a: (folder / "source_snapshot.zip").write_bytes(b"stub"))
    with pytest.raises(ValueError, match="another parent study"):
        analysis.main()
    assert not (validation / "analysis.json").exists()


def test_wrapper_checks_process_failures_and_conditionally_includes_accepted_study():
    # Static inspection only: never execute the wrapper or its full pytest/matrices.
    source = (ROOT / "tools/run_air56b2_energy_value.ps1").read_text(encoding="utf-8")
    commands = [line.strip() for line in source.splitlines() if line.strip()]
    for index, line in enumerate(commands):
        if line.startswith("& $python"):
            assert "$LASTEXITCODE -ne 0" in commands[index + 1] and "throw" in commands[index + 1]
    assert "@('development','validation','stress','refinement')" in source
    assert "'study.json'" in source and "$additional = @('--accepted-refinement'" in source
    assert "finally { Pop-Location }" in source
