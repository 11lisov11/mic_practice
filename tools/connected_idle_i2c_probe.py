"""Read-only connection comparison. Does not reset, clear, flash or request PWM."""
import argparse,json,time
from pathlib import Path
from saleae import automation
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,BUILD
import full_mcsdk_edges_host as host
host.PACKAGE=OUT;host.BUILD=BUILD
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--j1-physically-unplugged',action='store_true');ap.add_argument('--supply15',choices=('off','on'),required=True);ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not a.j1_physically_unplugged:ap.error('Physical J1 disconnection required for this USB-connected observation')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=host.Probe(out/'logs')
 m=json.loads(p.read(OUT/'manifest.json'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 sy=json.loads(p.read(OUT/'verification/symbols.json'));before=host.read(pr,sy,out,'before');host.archive(pr,sy,out,'before')
 assert before['pin']['build']==BUILD and not(before['pin']['BDTR']&0x8000) and not(before['full']['TIM8_BDTR']&0x8000) and before['full']['bus_v']<20
 with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
  assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
  with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=6))) as cap:
   cap.wait();cap.save_capture(str(out/'connected_idle.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
 after=host.read(pr,sy,out,'after');host.archive(pr,sy,out,'after')
 assert not(after['pin']['BDTR']&0x8000) and not(after['full']['TIM8_BDTR']&0x8000)
 from analyze_pin_pwm_i2c import analyze
 wave=analyze(out/'csv/digital.csv');p.write(out/'waveform.json',json.dumps(wave,indent=2)+'\n')
 delta={k:after['pin']['encoder'][k]-before['pin']['encoder'][k] for k in ('reads','errors','NACK','BUSY','deadline','ARLO','BERR_clears','forced_resets','normal_parks')}
 r=dict(observation_saved=True,build=BUILD,supply15=a.supply15,flash_commands=0,reset_commands=0,CLEAR_commands=0,PWM_requests=0,
  encoder_delta_host_interval=delta,delta_includes_debug_snapshot_interval=True,physical_PWM_edges=wave['PWM_rising_edges'],I2C_complete_reads=wave['AS5600_valid_reads'],
  target_NACK=wave['AS5600_target_NACK'],partial_frames=wave['partial_frames'],bus_v=after['full']['bus_v'],
  active_MCSDK_fault=after['full']['active_fault'],occurred_MCSDK_fault=after['full']['occurred_fault'],pin_reason=after['pin']['reason'],
  UART_RX_bad=after['full']['rx_bad'],UART_guard=after['full']['uart_guard'],all_MOE_off=True,
  I2C_healthy_delta=delta['reads']>500 and delta['errors']==0 and not wave['AS5600_target_NACK'])
 p.write(out/'report.json',json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
