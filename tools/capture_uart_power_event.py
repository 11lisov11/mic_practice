"""No PWM: archive, one admitted reset, manually bracket an auxiliary15V event."""
import argparse,json,subprocess,sys,time
from pathlib import Path
from saleae import automation
import prepare_no_switch_diag as p
from prepare_full_edges_busy_wait import OUT,BUILD
import full_mcsdk_edges_host as host
host.PACKAGE=OUT;host.BUILD=BUILD
def stable_reset_admission(a,b):
 def okay(x):return not(x['pin']['BDTR']&0x8000) and not(x['full']['TIM8_BDTR']&0x8000) and x['full']['backend_flags']==0 and x['full']['active_fault']==4 and x['full']['bus_v']<20 and x['pin']['GPIOA_IDR']&64 and x['pin']['encoder']['valid_flags']&3==3 and x['tx']['timeouts']==x['tx']['dma_errors']==x['tx']['full_errors']==0
 return okay(a) and okay(b) and a['full']['rx_bad']==b['full']['rx_bad'] and b['full']['native_commands_all']>a['full']['native_commands_all'] and a['pin']['encoder']['errors']==b['pin']['encoder']['errors']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--j1-unplugged-15v-stable-d4-rx',action='store_true');ap.add_argument('--allow-one-recorded-reset',action='store_true');ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
 if not(a.j1_unplugged_15v_stable_d4_rx and a.allow_one_recorded_reset):ap.error('Physical J1 removal,15V stable,D4RX and one archive/reset required')
 out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir();pr=host.Probe(out/'logs')
 m=json.loads(p.read(OUT/'manifest.json'));assert m['built'] and m['offline_verified']
 for rel,h in m['sealed_sha256'].items():assert p.sha(OUT/rel)==h,rel
 sy=json.loads(p.read(OUT/'verification/symbols.json'));before=host.read(pr,sy,out,'before_reset');host.archive(pr,sy,out,'before_reset')
 time.sleep(.5);fresh=host.read(pr,sy,out,'fresh_before_reset');assert stable_reset_admission(before,fresh),'No reset: protections/current link not stable'
 q=subprocess.run([sys.executable,str(p.ROOT/'tools/read_edges_uart_context.py'),'--outdir',str(out/'before_uart_context')],capture_output=True,text=True,timeout=30);p.write(out/'logs/archive_uart.log',q.stdout+q.stderr);assert not q.returncode
 pr.call(['-rst'],'one_reset_after_archiving');time.sleep(3)
 boot=host.read(pr,sy,out,'boot');host.archive(pr,sy,out,'boot')
 assert boot['pin']['state']==boot['pin']['reason']==boot['pin']['attempted']==0 and boot['full']['rx_bad']==0 and boot['full']['active_fault']==boot['full']['occurred_fault']==4 and boot['pin']['GPIOA_IDR']&64
 with automation.Manager.connect(port=10430,connect_timeout_seconds=3) as manager:
  assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
  with manager.start_capture(device_id='A7D1BB81883C0092',device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=8_000_000,glitch_filters=[]),capture_configuration=automation.CaptureConfiguration(buffer_size_megabytes=512,capture_mode=automation.ManualCaptureMode(trim_data_seconds=40))) as cap:
   p.write(out/'ready.json',json.dumps(dict(capture_ready=True,channel4='PB7 UART_RX',PWM_requests=0,reset_commands=1,stop_marker='stop.flag'))+'\n');print('CAPTURE_READY: waiting for external15V event; no MCU/SWD access during capture',flush=True)
   started=time.monotonic();marked=False
   try:
    while time.monotonic()-started<120:
     if (out/'stop.flag').exists():marked=True;time.sleep(2);break
     time.sleep(.1)
   finally:
    cap.stop();cap.save_capture(str(out/'uart_power_event.sal'));(out/'csv').mkdir();cap.export_raw_data_csv(directory=str(out/'csv'),digital_channels=list(range(8)))
 after=host.read(pr,sy,out,'after');host.archive(pr,sy,out,'after')
 q=subprocess.run([sys.executable,str(p.ROOT/'tools/read_edges_uart_context.py'),'--outdir',str(out/'after_uart_context')],capture_output=True,text=True,timeout=30);p.write(out/'logs/after_uart.log',q.stdout+q.stderr);assert not q.returncode
 from analyze_uart_rx_capture import analyze as uart_analyze
 from analyze_pin_pwm_i2c import analyze as i2c_analyze
 uart=uart_analyze(out/'csv/digital.csv');i2c=i2c_analyze(out/'csv/digital.csv',pwm_channels=(0,1,2,3))
 p.write(out/'uart_wire.json',json.dumps(uart,indent=2)+'\n');p.write(out/'I2C_SD.json',json.dumps(i2c,indent=2)+'\n')
 result=dict(observation_saved=True,external_event_acknowledged=marked,flash_commands=0,reset_commands=1,PWM_requests=0,CLEAR_commands=0,
  RX_bad_before=boot['full']['rx_bad'],RX_bad_after=after['full']['rx_bad'],I2C_errors_after=after['pin']['encoder']['errors'],
  SD_edges=uart['SD_edges'],wire_valid_UART_frames=uart['valid_frames'],wire_bad_CRC_frames=len(uart['invalid_candidate_frames']),wire_framing_errors=len(uart['framing_errors']),
  I2C_complete_reads=i2c['AS5600_valid_reads'],I2C_target_NACK=i2c['AS5600_target_NACK'],all_MOE_off=not(after['pin']['BDTR']&0x8000),
  first_fault_context='after_uart_context/report.json',no_SWD_during_event=True)
 p.write(out/'report.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
