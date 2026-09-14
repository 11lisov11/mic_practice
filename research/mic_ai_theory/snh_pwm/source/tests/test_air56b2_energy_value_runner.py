from concurrent.futures import Future
from dataclasses import dataclass
import json
import sys

import pytest

from tools import run_air56b2_energy_value as runner


@dataclass
class Parameter:
    value: float = 1.


class InlineExecutor:
    def __init__(self,**kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self,*args):
        pass

    def submit(self,fn,*args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def fake_row(job):
    name,plant,control,method,disturbance,duration,speed,n,initial,final,step = job
    return dict(case=name,method=method,duration_s=duration,total_simulation_s=duration+1,
        speed_fraction=speed,disturbance=disturbance,noise_seed=730,dt_s=1e-4,
        plant_substeps=n,observer="current",initial_load_fraction=initial,
        final_load_fraction=final,load_step_s=step,status="PASS",probe_complete=True,
        probe_reason="scheduled_return",checks=dict(complete=True),
        completed_steps=round((duration+1)/1e-4),final_id_a=.83,
        evaluation_final_state=[.1,0.,.09,0.,.08,0.,100.],
        supervisor=dict(ever_committed=False),
        energy=dict(shaft_work_j=100.,stored_change_j=2.,input_j=150.,loss_j=48.))


def setup(monkeypatch,tmp_path,job=fake_row):
    out = tmp_path/"new"
    monkeypatch.setattr(sys,"argv",["study","--stage","development","--out",str(out)])
    monkeypatch.setattr(runner,"build_cases",lambda count,seed:[("motor0_k0",Parameter(),Parameter())])
    monkeypatch.setattr(runner,"source_hashes",lambda:{})
    monkeypatch.setattr(runner,"ProcessPoolExecutor",InlineExecutor)
    monkeypatch.setattr(runner,"run_job",job)
    return out


def test_each_trial_is_checkpointed_and_complete_matrix_published(monkeypatch,tmp_path):
    out = setup(monkeypatch,tmp_path)
    runner.main()
    records = [json.loads(line) for line in (out/"trials.jsonl").read_text().splitlines()]
    study = json.loads((out/"study.json").read_text())
    assert len(records)==len(study["rows"])==32
    assert all(r["kind"]=="trial" for r in records)
    manifest = json.loads((out/"manifest.json").read_text())
    assert "trials.jsonl" in manifest["outputs"]


def test_failed_job_retained_other_jobs_finish_and_no_success_published(monkeypatch,tmp_path):
    def job(j):
        if j[3]=="energy_value":
            raise RuntimeError("synthetic worker failure")
        return fake_row(j)
    out = setup(monkeypatch,tmp_path,job)
    with pytest.raises(RuntimeError,match="failed jobs"):
        runner.main()
    assert not (out/"study.json").exists() and not (out/"manifest.json").exists()
    records = [json.loads(line) for line in (out/"trials.jsonl").read_text().splitlines()]
    assert len(records)==32
    assert sum(r["kind"]=="error" for r in records)==4
    assert len(json.loads((out/"errors.json").read_text()))==4


def test_output_directory_never_overwritten(monkeypatch,tmp_path):
    out = setup(monkeypatch,tmp_path)
    out.mkdir()
    sentinel = out/"keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(SystemExit):
        runner.main()
    assert sentinel.read_text()=="keep"
