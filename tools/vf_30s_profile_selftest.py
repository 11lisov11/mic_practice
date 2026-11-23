"""Validate offline profile planning and conditional energy bounds, never operate a stand."""
import json
from prepare_vf_30s_profile import plan, regeneration_bound


def main():
    cases=0
    for maximum in (5,10,20,30,50):
        profile=plan(maximum)
        assert profile["duration_s"]==30 and profile["independent_safety_limit_s"]==33
        assert profile["phases"][1]["target_hz"]==.1 and profile["phases"][-1]["command"]=="STOP"
        assert profile["phases"][1]["at_s"]+max(3,(maximum-.1)/5)<=28.001
        cases+=3
    for maximum in (0,4,51,True,float("nan"),float("inf"),"50"):
        try:plan(maximum)
        except ValueError:cases+=1
        else:raise AssertionError("unreviewed maximum accepted")
    no_cap=regeneration_bound(None)
    coast=plan(50,"coast")
    assert len(coast["phases"])==2 and coast["phases"][1]["at_s"]==30;cases+=1
    assert coast["stop_mode"]=="coast" and coast["phases"][1]["command"]=="STOP";cases+=1
    try:plan(50,"reverse")
    except ValueError:cases+=1
    else:raise AssertionError("unknown stop mode accepted")
    assert no_cap["projected_vdc"] is None and no_cap["identified_inertia"] is False; cases+=1
    worst=regeneration_bound(690)
    lower=regeneration_bound(690,maximum_hz=20)
    assert 403<worst["projected_vdc"]<405 and worst["conditional_envelope_below_ceiling"] is False; cases+=1
    assert 338<lower["projected_vdc"]<340 and lower["conditional_envelope_below_ceiling"] is True; cases+=1
    assert worst["kinetic_energy_j"]>lower["kinetic_energy_j"] and lower["attached_load_inertia_included"] is False; cases+=1
    for capacitance in (0,-1,float("nan"),float("inf")):
        try:regeneration_bound(capacitance)
        except ValueError:cases+=1
        else:raise AssertionError("invalid capacitance accepted")
    for vdc in (0,360,400,float("nan")):
        try:regeneration_bound(690,initial_vdc=vdc)
        except ValueError:cases+=1
        else:raise AssertionError("invalid initial voltage accepted")
    print(json.dumps(dict(pass_=True,cases=cases,hardware_commands=0)))


if __name__=="__main__":main()
