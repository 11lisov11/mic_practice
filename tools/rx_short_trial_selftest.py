"""Offline checks of the narrow calibration/PWM component transfer; no stand access."""
import copy
import json
from pathlib import Path
import tempfile
import time

from prepare_rx_short_trial import RX, server
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status
from clear_rx_maintenance_timeout import safe as clear_safe


def proof(mod):
    now=time.time()
    return dict(schema=mod.RX_SNAPSHOT_SCHEMA,pair=list(mod.RX_SNAPSHOT_TRIAL_PAIR),
        images=dict(mod.RX_SNAPSHOT_TRIAL_IMAGES),profile='short',
        scope='pwm_component_transfer_with_rx_and_snapshot_delta',
        pwm_evidence_pair=list(mod.UART_V3_TRIAL_PAIR),pwm_evidence_images=dict(mod.UART_V3_TRIAL_IMAGES),
        pwm_core_equivalence_pass=True,break_irq_delta_audited=True,calibration_contract_pass=True,
        images_verified=True,offline_pass=True,idle_wifi_pass=True,physical_idle_pass=True,
        new_pair_active_pwm_measured=False,hv_release_approved=False,current_telemetry_qualified=False,
        max_run_s=3,max_frequency_hz=5,cases={k:True for k in mod.UART_V3_TRIAL_CASES},
        offline_suites=51,evidence_sha256={k:'a'*64 for k in
            ('pwm','physical_idle','delta_audit','uno_install','nucleo_install','offline','idle_wifi')},
        issued_at=now-1,expires_at=now+300)


def main():
    cases=0
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'server.py'; p.write_text(server((RX/'web_hmi/server.py').read_text()))
        mod=load_module(p)
        good=proof(mod)
        assert mod.validate_powered_trial_qualification(good)[0]; cases+=1
        for key in good:
            bad=copy.deepcopy(good); del bad[key]
            assert not mod.validate_powered_trial_qualification(bad)[0],key
            cases+=1
        for key,value in dict(pair=[2026101103,2026101102],images={},profile=mod.COAST30_PROFILE,
            scope='full_new_pair_capture',pwm_evidence_pair=[2026101104,2026101102],
            pwm_evidence_images={},pwm_core_equivalence_pass=1,break_irq_delta_audited=1,
            calibration_contract_pass=1,images_verified=False,offline_pass=1,idle_wifi_pass=1,
            physical_idle_pass=1,new_pair_active_pwm_measured=True,hv_release_approved=True,
            current_telemetry_qualified=True,max_run_s=4,max_frequency_hz=6,offline_suites=50,
            issued_at=float('nan'),expires_at=float('inf')).items():
            assert not mod.validate_powered_trial_qualification({**good,key:value})[0],key
            cases+=1
        for key in good['cases']:
            bad=copy.deepcopy(good); bad['cases'][key]=False
            assert not mod.validate_powered_trial_qualification(bad)[0]; cases+=1
        for key in good['evidence_sha256']:
            bad=copy.deepcopy(good); del bad['evidence_sha256'][key]
            assert not mod.validate_powered_trial_qualification(bad)[0]; cases+=1
        stored=dict(fw_build=2026092901,mc_fw_build=2026100601,rpc_schema_version=3,
                    mc_capabilities=1,mc_mcsdk_telemetry=1)
        current={**stored,'fw_build':2026101104,'mc_fw_build':2026101102}
        assert mod._vbus_calibration_identity_matches(stored,current); cases+=1
        for key,value in dict(fw_build=2026101105,mc_fw_build=2026101103,rpc_schema_version=4,
                mc_capabilities=3,mc_mcsdk_telemetry=0).items():
            assert not mod._vbus_calibration_identity_matches(stored,{**current,key:value}); cases+=1
        s=safe_status(fw_build=2026101104,mc_fw_build=2026101102,mc_diag_valid=1,mc_age_ms=20,
            bp_age_ms=20,bp_good=100,mc_bad_cnt=0,mc_bad_integrity=0,mc_bad_sequence=0,
            mc_uart_error_flags=0,mc_last_uart_error_flags=0,uno_tx_short_writes=0,
            bp_transport_fault=0,mc_last_bad_reason=0,bp_bad=0,bp_bad_cnt=0,bp_mcsdk_telemetry=1,
            bp_vbus_valid=1,bp_softstart_ready=1,mode='VF',freq_cmd=5,vdc=320.,bp_vdc=320.,
            bp_vbus_raw=3200,uno_rx_dropped=0,uno_rx_hw_errors=0,uno_rx_hw_flags=0,mc_break_rx_bad=0)
        assert not mod.hv_arm_precheck(s,mod.HvArmConfig(enabled=True),True)[0]; cases+=1
        gate=mod.PoweredTrialGate(300,pair=mod.RX_SNAPSHOT_TRIAL_PAIR)
        assert gate.max_freq_hz==5 and gate.max_run_s==3 and gate.stop_after_s==3; cases+=1
        assert mod.PoweredTrialGate.live_check(s,pair=gate.pair,idle=True)[0]; cases+=1
        for key,value in dict(uno_rx_dropped=1,uno_rx_hw_errors=1,uno_rx_hw_flags=1,
                mc_break_rx_bad=1,bp_fault=5,freq_cmd=6,vdc=0.,bp_transport_fault=7).items():
            assert not mod.PoweredTrialGate.live_check({**s,key:value},pair=gate.pair,idle=True)[0],key
            cases+=1
        for key in ('uno_rx_dropped','uno_rx_hw_errors','uno_rx_hw_flags','mc_break_rx_bad'):
            assert not mod.PoweredTrialGate.live_check({k:v for k,v in s.items() if k!=key},pair=gate.pair)[0]; cases+=1
        try: mod.PoweredTrialGate(300,pair=gate.pair,profile=mod.COAST30_PROFILE)
        except ValueError: cases+=1
        else: raise AssertionError('New pair must not acquire coast30')
        cfg=mod.HvArmConfig(enabled=True,trial_gate=gate)
        assert not mod.hv_arm_precheck(s,cfg,True)[0]; cases+=1  # Must still observe 30 seconds.
        assert not clear_safe(s); cases+=1  # Cannot acknowledge the timeout on an energized bus.
    print(json.dumps(dict(pass_=True,cases=cases,hardware_commands=0,
        new_pair_active_pwm_measured=False,general_hv_release=False)))


if __name__=='__main__': main()
