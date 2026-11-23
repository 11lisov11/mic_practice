"""Offline regression for scoped key-pinned Wi-Fi HMI deployment; no stand access."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from unoq_wifi_hmi_deploy import app_candidate_path,safe_for_update,ssh_base,scp_base,matching_host
from web_hmi_command_guard_selftest import safe_status


def main():
    with TemporaryDirectory() as temporary:
        root=Path(temporary);default_app=root/"web_hmi/static/app.js"
        default_app.parent.mkdir(parents=True);default_app.write_text("// app")
        candidate=root/"candidate.js";candidate.write_text("// candidate")
        assert app_candidate_path(root,False) is None
        assert app_candidate_path(root,True)==default_app.resolve()
        assert app_candidate_path(root,True,candidate)==candidate.resolve()
        try:app_candidate_path(root,False,candidate)
        except ValueError:pass
        else:raise AssertionError("explicit app without install flag accepted")
    s=safe_status(fw_build=2026101008,mc_fw_build=2026101006,hmi_hv_armed=0,
        bp_mcsdk_telemetry=1,bp_vbus_valid=1,bp_vbus_raw=0,mc_age_ms=20,bp_temp_age_ms=20,
        mc_bad_cnt=0,mc_bad_integrity=0,mc_bad_sequence=0,mc_uart_error_flags=0,
        mc_last_uart_error_flags=0,uno_tx_short_writes=0,bp_transport_fault=0)
    assert safe_for_update(s,2)[0];cases=1
    assert safe_for_update(dict(s,fw_build=2026101507,mc_fw_build=2026101506),2)[0];cases+=1
    assert safe_for_update(dict(s,mc_bad_integrity=1),2)[0];cases+=1
    assert not safe_for_update(dict(s,mc_bad_integrity=-1),2)[0];cases+=1
    assert safe_for_update(dict(s,bp_fault=5),2)[0];cases+=1
    assert not safe_for_update(dict(s,vdc=7,bp_vdc=7,bp_vbus_raw=70),2)[0];cases+=1
    assert safe_for_update(dict(s,vdc=7,bp_vdc=7,bp_vbus_raw=70),10)[0];cases+=1
    for key,value in (("state","VF_RUN"),("pwm",1),("estop",1),("hmi_hv_armed",1),
        ("precharge",1),("bp_ext",1),("bp_fault",1),("mc_bad_cnt",1),
        ("mc_bad_sequence",1),("mc_uart_error_flags",4),("mc_last_uart_error_flags",4),
        ("uno_tx_short_writes",1),("bp_transport_fault",5),("mc_age_ms",300),
        ("bp_temp_age_ms",float("nan")),("bp_vbus_raw",101),("vdc",325),
        ("fw_build",2026101099),("rpc_schema_version",4)):
        assert not safe_for_update(dict(s,**{key:value}),10)[0],key;cases+=1
    for key in ("mc_bad_cnt","mc_age_ms","bp_vbus_raw","bp_temp_valid","rpc_schema_version"):
        missing=dict(s);missing.pop(key)
        assert not safe_for_update(missing,2)[0],key;cases+=1
    for limit in (0,15,100,True,float("nan"),float("inf")):
        assert not safe_for_update(s,limit)[0];cases+=1
    lso = dict(s, fw_build=2026112305, mc_fw_build=2026112306, vdc=9, bp_vdc=9,
               bp_vbus_raw=90, bp_softstart_ready=0, research_native_valid=1, research_native_caps=2)
    assert safe_for_update(lso,10,lso_verified_idle=True)[0]
    assert not safe_for_update(lso,10)[0]
    assert not safe_for_update(lso,2,lso_verified_idle=True)[0]
    cases+=3
    for key,value in (("fw_build",2026112303),("bp_softstart_ready",1),("research_native_valid",0),
                      ("research_native_caps",15),("bp_vdc",11),("hmi_hv_armed",1),("bp_status",0x20)):
        assert not safe_for_update(dict(lso,**{key:value}),10,lso_verified_idle=True)[0],key;cases+=1
    for command in (ssh_base("192.168.1.138",2222,"arduino",Path("key"),Path("pin")),
                    scp_base("192.168.1.138",2222,"arduino",Path("key"),Path("pin"))):
        assert "StrictHostKeyChecking=yes" in command and "UserKnownHostsFile=pin" in command
        assert "IdentitiesOnly=yes" in command and "BatchMode=yes" in command
        assert "UpdateHostKeys=no" in command and not any("accept-new" in value for value in command)
        cases+=3
    assert matching_host("http://192.168.1.138:8080")=="192.168.1.138";cases+=1
    for url,override in (("http://192.168.1.138:8080","192.168.1.139"),
                         ("http://user:password@192.168.1.138:8080",""),("file:///tmp/x","")):
        try:matching_host(url,override)
        except ValueError:cases+=1
        else:raise AssertionError("unguarded/different SSH target accepted")
    print(json.dumps(dict(pass_=True,cases=cases,hardware_commands=0)))


if __name__=="__main__":main()
