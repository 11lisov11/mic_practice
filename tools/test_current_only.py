"""Regression tests for measurement integrity, firmware removal and offline learning."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import current_only_lab as lab
import prepare_current_only as package
from audit_production_pwm_filters import function


def valid_status(tick=200):
    return dict(fw_build=lab.PAIR[0],mc_fw_build=lab.PAIR[1],research_profile='air56b2_current_only',
                mc_age_ms=10,mc_current_age_ms=10,mc_current_telemetry_valid=1,
                mc_current_zero_ready=1,mc_current_frozen=0,pwm=1,enc_source='disabled',
                mc_current_rms_a=[.5,.6,.7],mc_current_peak_a=[.9,1.,1.1],
                mc_current_instant_a=[-.1,.2,-.1],mc_current_coverage_pct=99,
                mc_current_window_ms=200,mc_current_window_tick_ms=tick,
                mc_frequency_reference_valid=1,mc_frequency_reference_hz=10.,freq_cmd=10.,
                vdc=320.,mc_fault_current_mask=0,mc_fault_occurred_mask=0,estop=0,
                run_id=1,run_start_ms=1000)


class CurrentOnly(unittest.TestCase):
    def test_missing_stale_partial_frozen_fault_never_training_zero(self):
        self.assertTrue(lab.sample(valid_status(),'x')['valid_for_learning'])
        for changes in ({'mc_current_rms_a':None},{'mc_current_age_ms':750},
                        {'mc_age_ms':300},{'mc_current_frozen':1},
                        {'mc_current_coverage_pct':94},{'mc_fault_current_mask':64},
                        {'mc_current_rms_a':[float('nan'),0,0]}, {'mc_fw_build':1},
                        {'enc_source':'nucleo_g431_i2c1'}, {'pwm':0}):
            with self.subTest(changes=changes):
                s=valid_status();s.update(changes)
                r=lab.sample(s,'x')
                self.assertFalse(r['valid_for_learning'])
                self.assertIsNone(r['rotor_speed_rpm'])

    def test_nucleo_control_and_protection_unchanged(self):
        old=(package.MC_BASE/'nucleo/Src/main.c').read_text(encoding='utf-8')
        new=(package.OUT/'nucleo/Src/main.c').read_text(encoding='utf-8')
        names=re.findall(r'^(?:static\s+)?(?:void|bool|uint\w+|HAL_StatusTypeDef)\s+(\w+)\([^;]*?\)\s*\{',old,re.M)
        checked=[]
        for name in names:
            if name=='main' or name.startswith('mic_send_encoder') or name in ('mic_send_i2c_wire_page','mic_send_bus_clear'):continue
            a=function(old,name).replace(str(package.OLD[1]),str(package.NEW[1]))
            self.assertEqual(a,function(new,name),name)
            checked.append(name)
        self.assertGreater(len(checked),25)
        self.assertIn('uno_link_poll',checked)
        self.assertIn('mic_send_current_page',checked)
        for filename in ('Src/current_shunt.c','Inc/current_core.h','Src/stm32g4xx_it.c','Src/mc_tasks.c'):
            self.assertEqual((package.MC_BASE/'nucleo'/filename).read_bytes(),(package.OUT/'nucleo'/filename).read_bytes())
        self.assertNotIn('mic_encoder_',new)
        self.assertNotIn('mic_i2c_wire_',new)
        self.assertNotIn('off_low_bus',new)
        for filename in ('nucleo_encoder.c','nucleo_i2c_wire.c'):
            content=(package.OUT/'nucleo/Src'/filename).read_text()
            self.assertNotIn('#include',content)
            self.assertNotIn('void ',content)

    def test_hmi_current_contract_and_unavailable_speed(self):
        spec=importlib.util.spec_from_file_location('co_hmi',package.OUT/'web_hmi/server.py')
        hmi=importlib.util.module_from_spec(spec);spec.loader.exec_module(hmi)
        s=valid_status();s.update(enc_ok=1,enc_rpm=1234)
        s=hmi.with_current_only_profile(s)
        self.assertEqual(s['enc_source'],'disabled')
        self.assertIsNone(s['enc_rpm'])
        self.assertIsNone(s['speed_measured_rpm'])
        self.assertFalse(s['ai_control_enabled'])
        # Reconstruct native frame from the archived measured OFF packet: CRC must
        # be checked for the new peer; old identity/CRC cannot be accepted by accident.
        baseline=json.loads((package.ROOT/'tmp/current_only_baseline_status_20261029.json').read_text())['data']
        for key in ('mc_current_packet_hex','mc_current_detail_hex','mc_current_quality_hex','mc_zero_history_hex'):
            raw=baseline.get(key)
            if not raw or raw=='-':continue
            data=bytearray.fromhex(raw)
            for offset in range(0,len(data),43):
                data[offset+6:offset+10]=package.NEW[1].to_bytes(4,'little')
                data[offset+39:offset+43]=hmi.current_crc32c(data[offset:offset+39]).to_bytes(4,'little')
            baseline[key]=data.hex()
        baseline.update(fw_build=package.NEW[0],mc_fw_build=package.NEW[1])
        result=hmi.with_shunt_currents(baseline)
        self.assertEqual(result['mc_current_zero_ready'],1)
        self.assertEqual(result['mc_current_telemetry_valid'],0) # OFF is not zero current.
        self.assertIsNone(result['mc_current_rms_a'])
        result=hmi.with_zero_history(result)
        self.assertEqual(result['mc_zero_history_valid'],1)

    def test_learning_uses_run_holdout_and_current_target(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix='current_only_synthetic_') as temp:
            paths=[]
            for run in range(3):
                folder=Path(temp)/str(run);folder.mkdir()
                rows=[]
                for n in range(65):
                    s=valid_status((n+1)*200)
                    s.update(run_id=run+1,run_start_ms=1000+run*20000)
                    s['mc_current_rms_a']=[.5+.002*n+.01*run]*3
                    rows.append(lab.sample(s,str(run)))
                path=folder/'windows.jsonl'
                path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
                lab.dump(folder/'manifest.json',dict(schema=lab.SCHEMA,completed=True,load_condition='unloaded',run_id=str(run),
                    windows_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),synthetic=True))
                paths.append(path)
            lab.train(argparse.Namespace(inputs=paths,outdir=Path(temp)/'model',epochs=25))
            result=json.loads((Path(temp)/'model/report.json').read_text())
            self.assertEqual(result['train_runs'],['0','1'])
            self.assertEqual(result['holdout_runs'],['2'])
            self.assertFalse(result['rotor_speed_model'])
            self.assertFalse(result['ai_control_enabled'])
            self.assertEqual(result['train_windows'],128)
            with self.assertRaises(ValueError):lab.load_examples(paths+paths[:1])


if __name__=='__main__':unittest.main()
