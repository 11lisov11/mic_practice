"""One verified install while retaining a continuous physical I2C startup capture."""
import argparse,json,subprocess,sys
from pathlib import Path
from saleae import automation
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--isolation-confirmed',action='store_true');a=ap.parse_args()
 if not a.isolation_confirmed:ap.error('Existing isolated J1/J4OFF and ribbon-disconnected state required')
 out=OUT/'startup_capture_r1';out.mkdir(exist_ok=False)
 with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
  assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
  with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=12))) as cap:
   try:
    q=subprocess.run([sys.executable,'-u',str(p.ROOT/'tools/full_edges_busy_wait_host.py'),'install','--isolation-confirmed','--outdir',str(OUT/'install_r1')],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    p.write(out/'install_console.log',q.stdout+q.stderr)
   finally:
    cap.wait();cap.save_capture(str(out/'startup_install.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
 r=json.loads(p.read(OUT/'install_r1/report.json'));assert not q.returncode and r['passed'] and r['readback_verified']
 print(json.dumps(dict(installed=True,readback_verified=True,flash_commands=r['flash_commands'],fixture_requests=r['fixture_requests'],startup_capture_seconds=12,boot_encoder=r['boot']['pin']['encoder'])))
if __name__=='__main__':main()
