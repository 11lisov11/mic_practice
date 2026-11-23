"""Archive the original calibration and check readiness for a fresh meter zero point."""
import argparse,json
from pathlib import Path
from ipm_break_wifi_selftest import load_module
import pwm_filter_hardware_session as bench

def main(folder):
    s=bench.Session(folder);assert s.state.get('restored') and s.state.get('idle_30s_pass')
    status=s.idle(False);assert status['vdc']==0 and status['bp_vbus_raw']==0
    s.hashes('recalibration_preparation_current_files')
    out=folder/'vbus_recalibration_preparation';out.mkdir(exist_ok=False)
    remote='/home/arduino/.config/mic-ai/vbus_calibration.json.before_fw1411_fw1410_20261014'
    s.remote(f'''from pathlib import Path
import hashlib,shutil
source=Path('/home/arduino/.config/mic-ai/vbus_calibration.json');backup=Path({remote!r})
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source)=={bench.CAL_SHA!r}
if backup.exists():assert sha(backup)=={bench.CAL_SHA!r}
else:shutil.copy2(source,backup)
assert sha(backup)==sha(source)
print('Original calibration copied byte-for-byte; current calibration unchanged')
''','archive_calibration_before_new_measurements')
    s.run(s.scp+['arduino@192.168.1.138:'+remote,out/'original_vbus_calibration.json'],'download_calibration_archive',timeout=40)
    assert bench.sha(out/'original_vbus_calibration.json')==bench.CAL_SHA
    module=load_module(bench.PACKAGE/'production/web_hmi/server.py')
    ready,reason=module.vbus_capture_precheck(status,0.0);assert ready,reason
    report=dict(zero_capture_controller_precheck_pass=True,zero_meter_value_is_only_placeholder=True,
       actual_zero_reference_meter_reading_received=False,measurement_not_yet_recorded=True,
       installed_pair=list(bench.PROD),original_calibration_sha256=bench.CAL_SHA,
       original_calibration_archived=True,original_calibration_file_unchanged=True,
       identity=module._vbus_calibration_identity(status),calibration_valid_for_current_pair=False,
       firmware_writes=0,arm_commands=0,start_commands=0,hv_release_approved=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',required=True,type=Path);a=p.parse_args();main(a.session.resolve())
