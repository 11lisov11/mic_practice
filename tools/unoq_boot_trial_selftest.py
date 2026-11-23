"""Offline mutation and lifecycle checks for the explicit 1108 short-trial grant."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import time

from prepare_unoq_boot_trial import HMI, server
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status


def proof(mod):
    now=time.time()
    result=dict(schema=mod.BOOT_TRIAL_SCHEMA,pair=list(mod.BOOT_TRIAL_PAIR),
        images=dict(mod.BOOT_TRIAL_IMAGES),profile='short',
        scope='unchanged_nucleo_pwm_with_supervisory_boot_fix',
        new_pair_active_pwm_measured=False,physical_idle_registers_current=False,
        hv_release_approved=False,current_telemetry_qualified=False,
        max_run_s=3,max_frequency_hz=5,offline_suites=57,sd_sample_v=2.6,
        idle_tx_max_gap_us=53177,evidence_sha256={k:'a'*64 for k in mod.BOOT_TRIAL_EVIDENCE},
        issued_at=now-1,expires_at=now+300)
    for key in ('nucleo_pwm_equivalence_pass','calibration_contract_pass','images_verified',
                'offline_pass','idle_wifi_pass','autonomous_boot_pass','prestart_break_context_pass',
                'sd_sample_operator_reported'):
        result[key]=True
    return result


def status():
    return safe_status(fw_build=2026101108,mc_fw_build=2026101102,mc_diag_valid=1,hmi_hv_armed=0,
        mc_age_ms=20,bp_age_ms=20,bp_good=100,mc_bad_cnt=0,mc_bad_integrity=0,
        mc_bad_sequence=0,mc_uart_error_flags=0,mc_last_uart_error_flags=0,
        uno_tx_short_writes=0,bp_transport_fault=0,mc_last_bad_reason=0,
        bp_bad=0,bp_bad_cnt=0,bp_mcsdk_telemetry=1,bp_vbus_valid=1,bp_softstart_ready=1,
        mode='VF',freq_cmd=5,vdc=320.,bp_vdc=320.,bp_vbus_raw=3200,uno_rx_dropped=0,
        uno_rx_hw_errors=0,uno_rx_hw_flags=0,mc_break_rx_bad=0,mc_fault_reason=0,
        mc_fault_current_mask=0,mc_fault_occurred_mask=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    cases=0
    def check(value,message='check failed'):
        nonlocal cases
        cases+=1
        assert value,message
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/'server.py';f.write_text(server(HMI.read_text()));mod=load_module(f)
        good=proof(mod)
        check(mod.validate_powered_trial_qualification(good)[0])
        for key in good:
            broken=copy.deepcopy(good);del broken[key]
            check(not mod.validate_powered_trial_qualification(broken)[0],key)
        for key,val in dict(pair=[2026101109,2026101102],images={},schema='wrong',
            profile=mod.COAST30_PROFILE,scope='full_release',max_run_s=30,max_frequency_hz=50,
            offline_suites=56,sd_sample_v=2.52,idle_tx_max_gap_us=100000,
            issued_at=float('nan'),expires_at=float('inf'),new_pair_active_pwm_measured=True,
            physical_idle_registers_current=True,hv_release_approved=True,
            current_telemetry_qualified=True,autonomous_boot_pass=1).items():
            check(not mod.validate_powered_trial_qualification({**good,key:val})[0],key)
        for key in good['evidence_sha256']:
            broken=copy.deepcopy(good);del broken['evidence_sha256'][key]
            check(not mod.validate_powered_trial_qualification(broken)[0],key)
        stored=dict(fw_build=2026092901,mc_fw_build=2026100601,rpc_schema_version=3,
                    mc_capabilities=1,mc_mcsdk_telemetry=1)
        current={**stored,'fw_build':2026101108,'mc_fw_build':2026101102}
        check(mod._vbus_calibration_identity_matches(stored,current))
        for key,val in dict(fw_build=2026101109,mc_fw_build=2026101103,rpc_schema_version=4,
                            mc_capabilities=3,mc_mcsdk_telemetry=0).items():
            check(not mod._vbus_calibration_identity_matches(stored,{**current,key:val}),key)
        s=status()
        check(not mod.hv_arm_precheck(s,mod.HvArmConfig(enabled=True),True)[0])
        gate=mod.PoweredTrialGate(300,pair=mod.BOOT_TRIAL_PAIR)
        check((gate.max_run_s,gate.max_freq_hz,gate.stop_after_s)==(3,5,3))
        check(mod.PoweredTrialGate.live_check(s,idle=True,pair=gate.pair)[0])
        for key,val in dict(freq_cmd=6,bp_fault=5,vdc=9.,bp_vdc=9.,mc_age_ms=300,
                uno_rx_dropped=1,uno_rx_hw_errors=1,uno_rx_hw_flags=1,mc_break_rx_bad=1,
                bp_transport_fault=7,bp_softstart_ready=0,estop=1).items():
            check(not mod.PoweredTrialGate.live_check({**s,key:val},idle=True,pair=gate.pair)[0],key)
        for key in ('uno_rx_dropped','uno_rx_hw_errors','uno_rx_hw_flags','mc_break_rx_bad'):
            check(not mod.PoweredTrialGate.live_check({k:v for k,v in s.items() if k!=key},pair=gate.pair)[0])
        try:mod.PoweredTrialGate(300,pair=gate.pair,profile=mod.COAST30_PROFILE)
        except ValueError:check(True)
        else:check(False,'coast30 forbidden')
        check(not mod.hv_arm_precheck(s,mod.HvArmConfig(enabled=True,trial_gate=gate),True)[0])
        gate.begin=time.monotonic()-31;gate.last_seen=time.monotonic()
        gate.first_good=0;gate.last_good=100;gate.samples=20
        check(gate.ready(s,True)[0])
        gate.consume()
        check(not gate.ready(s,True)[0])
        try:gate.consume()
        except RuntimeError:check(True)
        else:check(False,'one-shot replay allowed')
        from install_vbus_hmi_fix_remote import precheck
        check(precheck(dict(s,vdc=9.,bp_vdc=9.,bp_vbus_raw=90),10)[0])
        check(not precheck(dict(s,vdc=9.,bp_vdc=9.,bp_vbus_raw=90),2)[0])
        from unoq_wifi_hmi_deploy import physical_update_confirmation
        for maximum,both,mains,allowed in ((2,False,True,False),(2,True,False,True),
                (10,False,True,True),(10,False,False,False),(15,True,True,False)):
            check(physical_update_confirmation(maximum,both,mains) is allowed)
        # Test actual calibration evaluation without altering its original identity or bytes.
        cal_path=Path(d)/'cal.json'
        record=dict(schema=mod.VbusCalibrationStore.SCHEMA,identity=stored,
                    points={'zero':{'meter_vdc':0,'mc_vdc_mean':0},
                            'high':{'meter_vdc':322.7,'mc_vdc_mean':325}})
        record['integrity_sha256']=mod.VbusCalibrationStore._digest(record)
        cal_path.write_text(json.dumps(record));before=cal_path.read_bytes()
        cal=mod.VbusCalibrationStore(str(cal_path))
        check(cal.is_valid(dict(s,rpc_schema_version=3)))
        check(cal_path.read_bytes()==before)
        # Preparation is non-actuating, including the specifically bounded auxiliary bias.
        class Rpc:
            def __init__(self,data):self.data=data;self.commands=[]
            def get(self):return True,self.data,None
            def cmd(self,cmd):self.commands.append(cmd);return True,None
        class Logs:
            def add(self,line):pass
        for volts,expected in ((0,True),(9,True),(10,True),(10.01,False),(320,False)):
            data=dict(s,vdc=volts,bp_vdc=volts,bp_vbus_raw=round(volts*10),rpc_schema_version=3)
            rpc=Rpc(data)
            app=mod.AppState(rpc,Logs(),status_log_interval=1,
                             hv_arm=mod.HvArmState(mod.HvArmConfig(enabled=True)),
                             vbus_calibration=cal,control_access=mod.ControlAccessConfig(token_file='test-only'))
            ok,_=app.prepare_powered_trial(good,'PREPARE UARTV3 TRIAL 3S')
            check(ok is expected,repr((volts,ok)))
            check(not rpc.commands,'preparation emitted a control command')
    report=dict(pass_=True,cases=cases,hardware_commands=0,general_hv_release=False,
                new_pair_active_pwm_measured=False,physical_idle_registers_current=False)
    report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
