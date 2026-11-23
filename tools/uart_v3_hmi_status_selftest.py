"""Keep v3 diagnostic counters through the real HMI string decoder."""
import json
from pathlib import Path
from web_hmi_command_guard_selftest import load_server_module


def main():
    mod=load_server_module(Path(__file__).resolve().parents[1])
    decode=mod.RpcBridge._parse_status_string
    base="STATE state=SAFE mode=VF pwm=0 fw_build=2026101004 bp_fw_build=2026101003 rpc_schema=3"
    cases=0
    old=decode(base)
    assert old is not None
    for key in ("bp_ne_accepted","bp_ne_observed","bp_ne_flags","bp_transport_fault"):
        assert old[key] is None and old["mc_"+key[3:]] is None
        cases+=1
    for accepted,observed,flags,fault in ((0,0,0,0),(2,3,4,0),(65535,65535,15,7)):
        fields=dict(bp_ne_accepted=accepted,bp_ne_observed=observed,bp_ne_flags=flags,bp_transport_fault=fault)
        result=decode(base+" "+" ".join(f"{k}={v}" for k,v in fields.items()))
        assert result is not None
        for key,value in fields.items():
            assert result[key]==value and result["mc_"+key[3:]]==value
            cases+=1
    for value in ("nan","inf","bad","1.5"):
        assert decode(base+" bp_ne_observed="+value) is None
        cases+=1
    print(json.dumps({"pass":True,"cases":cases,"hardware_commands":0}))


if __name__=="__main__":
    main()
