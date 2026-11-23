"""One5s diagnostic, requiring physical Saleae capture before the mailbox write."""
import argparse,json,sys
from pathlib import Path
import run_no_switch_diag as run
import logic_edges_diag_io as io
DEVICE='A7D1BB81883C0092'

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--confirm-j1-j4-off-meter-below20-nucleo-usb',action='store_true')
 p.add_argument('--confirm-sd-pa6-pd2-jumper-and-probes',action='store_true')
 p.add_argument('--request-once',action='store_true')
 p.add_argument('--device',default=DEVICE);p.add_argument('--outdir',type=Path,required=True)
 a=p.parse_args()
 if not a.confirm_j1_j4_off_meter_below20_nucleo_usb or not a.confirm_sd_pa6_pd2_jumper_and_probes:
  p.error('OFF/discharged setup plus PA6-to-PD2 jumper/probe mapping must be confirmed')
 symbols=json.loads((io.PACKAGE/'verification/symbols.json').read_text(encoding='utf-8'))
 capture=None;manager=None
 out=a.outdir.resolve()
 class CapturingProbe(io.Probe):
  def request(self,addr,cancel=False):
   nonlocal capture
   if not cancel:
    er=io.decode_edges(self.read(symbols['mic_logic_edge_report']['address'],48,'edge_preflight'))
    (out/'edge_before.json').write_text(json.dumps(er,indent=2)+'\n',encoding='utf-8')
    if er['flags']!=0:raise RuntimeError('Auxiliary edge request already consumed; no write')
    # A failed capture setup must never be followed by a diagnostic request.
    capture=manager.start_capture(device_id=a.device,
     device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(8)),digital_sample_rate=24_000_000,glitch_filters=[]),
     capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=10)))
   return super().request(addr,cancel)
 run.PACKAGE=io.PACKAGE;run.Probe=CapturingProbe;run.decode=io.decode;run.eligible=io.eligible;run.read_report=io.read_report
 argv=sys.argv
 try:
  if a.request_once:
   from runtime_python import ensure_modules_or_reexec
   ensure_modules_or_reexec(['saleae'],'MIC_LOGIC_EDGES_REEXEC')
   from saleae import automation
   manager=automation.Manager.connect(port=10430,connect_timeout_seconds=3)
   devices=[d for d in manager.get_devices() if d.device_id==a.device and not d.is_simulation]
   if len(devices)!=1:raise RuntimeError('Expected physical Saleae not found; no request sent')
  sys.argv=['run_logic_edges_diag','--confirm-j1-j4-off-meter-below20-nucleo-usb','--outdir',str(out)]+(['--request-once'] if a.request_once else [])
  code=run.main()
  if capture is not None and (out/'report.json').exists():
   capture.wait() # Also covers an ambiguous write: no SWD read during5s.
   # Read only AFTER the complete5s interval. Keep the previous first-fault
   # and release records archived by the underlying runner without clearing.
   pr=io.Probe(out/'edge_logs');pr.logs.mkdir(exist_ok=True)
   raw=pr.read(symbols['mic_logic_edge_report']['address'],48,'edge_after')
   (out/'edge_after.bin').write_bytes(raw)
   (out/'edge_after.json').write_text(json.dumps(io.decode_edges(raw),indent=2)+'\n',encoding='utf-8')
  return code
 finally:
  sys.argv=argv
  try:
   if capture is not None:
    # Even an ambiguous mailbox response retains its waveform; never retry.
    capture.wait();capture.save_capture(str(out/'logic_edges.sal'))
    csv=out/'csv';csv.mkdir(exist_ok=True)
    capture.export_raw_data_csv(directory=str(csv),digital_channels=list(range(8)))
    from analyze_logic_edges_diag import analyze
    result=analyze(csv/'digital.csv')
    (out/'waveform.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
  finally:
   if capture is not None:capture.close()
   if manager is not None:manager.close()
if __name__=='__main__':raise SystemExit(main())
