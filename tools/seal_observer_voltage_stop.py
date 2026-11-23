"""Seal tested offline voltage/reply candidate; never access boards."""
import inspect
import json
import seal_observer_input_epoch as old
import prepare_observer_voltage_stop as p


def main():
 assert json.loads(p.read(p.OUT/'verification/HMI_record_validation.json'))['passed']
 src=inspect.getsource(old.main)
 src=src.replace("'recorded_run_analysis.json'","'recorded_842ms_analysis.json'")
 src=src.replace('_observer_input.hex','_observer_voltage_stop.hex').replace('_observer_trace.elf-zsk.bin','_observer_voltage_stop.elf-zsk.bin')
 scope=dict(old.__dict__,p=p)
 exec(compile(src,__file__,'exec'),scope);scope['main']()
 m=json.loads(p.read(p.OUT/'manifest.json'))
 m.update(stop_path_reproduced=True,applied_voltage_source_corrected=True,
  accepted_reply_lifecycle_corrected=True,local_stop_provenance_available=True,
  NIS_residual_and_variance_available=True,physical_NIS_root_cause_proven=False,
  verification_reports={rel:p.sha(p.OUT/rel) for rel in ('verification/report.json','verification/HMI_record_validation.json','model_verification/model_report.json','recorded_842ms_analysis.json')})
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')


if __name__=='__main__':main()
