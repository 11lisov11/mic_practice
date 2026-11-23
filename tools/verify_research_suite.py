"""Offline gates for firmware, capability proof, current path and simple UI."""
import json,shutil,subprocess,sys
from pathlib import Path
import prepare_research_suite as p

def main():
 v=p.OUT/'verification';v.mkdir(exist_ok=False)
 report=dict(passed=False,hardware_commands=0,actuating_algorithms=['VF_FIXED'],other_actuators_implemented=False,checks={})
 def run(args,name):
  q=subprocess.run(args,cwd=p.ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
  p.write(v/(name+'.log'),q.stdout+q.stderr);report['checks'][name]=q.returncode==0;q.check_returncode()
 run([sys.executable,str(p.ROOT/'tools/test_research_suite.py')],'research_suite_regression')
 run([sys.executable,str(p.ROOT/'tools/test_current_only.py')],'current_dataset_regression')
 run([shutil.which('node'),'--check',str(p.OUT/'web_hmi/static/app.js')],'javascript_syntax')
 # The older DOM harness expects the renderer at EOF. Extract that unchanged
 # shipped function before the new capability/UI footer, not a rewritten copy.
 app=p.read(p.OUT/'web_hmi/static/app.js');a=app.index('function updateShuntCurrentPanel(data)');b=app.index('// Capability catalog only:',a)
 renderer=v/'shunt_renderer.js';p.write(renderer,app[a:b])
 run([shutil.which('node'),str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(renderer)],'current_renderer')
 import current_adc_apex_fix_selftest as irq
 from collect_current_peak import decoder
 irq.p.OUT=p.OUT
 def decode(candidate):
  module=decoder(candidate);f=module.decode_adc_peak_hex
  module.decode_adc_peak_hex=lambda value,expected_build=p.NEW[1]:f(value,expected_build)
  return module
 irq.decoder=decode;irq.main()
 adc=json.loads(p.read(p.OUT/'apex_selftest_r1/report.json'));assert adc['passed']
 report['checks']['actual_adc_irq_raw_capture_replay']=True;report['actual_adc_conditions']=adc['checks']
 b=p.OUT/'nucleo/STM32CubeIDE/Debug'
 for f in b.iterdir():
  if f.suffix in ('.elf','.hex','.bin','.map') or f.name.endswith(('.build-manifest.json','.build.log')):
   dest=p.OUT/'build/nucleo'/f.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
 run([sys.executable,str(p.ROOT/'tools/research_suite_runner.py'),'--outdir',str(v/'full_requested_plan')],'full_requested_plan')
 full=json.loads(p.read(v/'full_requested_plan/plan.json'));assert not full['executable']
 run([sys.executable,str(p.ROOT/'tools/research_suite_runner.py'),'--algorithms','VF_FIXED','--outdir',str(v/'scalar_plan')],'scalar_plan')
 assert json.loads(p.read(v/'scalar_plan/plan.json'))['executable']
 # Inventory the actual model sources, retaining deployment limits explicitly.
 inventory=[]
 for name in ('safe_neural_horizon_pwm.py','info_optimal_coded_pwm.py','active_belief_rotor_observer.py','antiuchebnik_inverter_observer.py'):
  path=Path('C:/mic_theory/control')/name
  if path.exists():inventory.append(dict(source=str(path),sha256=p.sha(path),deployment='research_python_only_not_firmware'))
 p.write(p.OUT/'model_inventory.json',json.dumps(inventory,indent=2))
 report.update(passed=True,ui_preview_is_synthetic=True,powered_trial_performed=False,
    as5600_enabled=False,physical_amp_scale_qualified=False,rotor_speed_labels_available=False)
 p.write(v/'report.json',json.dumps(report,indent=2))
 m=json.loads(p.read(p.OUT/'manifest.json'));m.update(built=True,selftest_pass=True,uart_diagnostic_extension=True,control_uart_format_changed=False,
    simple_web_ui=True,program_autostart=False)
 for key,folders in [('source_sha256',('nucleo','UNOQ_MOTOR','libraries','web_hmi')),
                     ('build_sha256',('build',)),('verification_sha256',('verification','apex_selftest_r1'))]:
  m[key]={str(f.relative_to(p.OUT)).replace('\\','/'):p.sha(f) for folder in folders for f in sorted((p.OUT/folder).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(p.OUT/folder).parts)}
 p.write(p.OUT/'manifest.json',json.dumps(m,indent=2))
 from install_research_suite import verify_package
 verify_package();print(json.dumps(report))

if __name__=='__main__':main()
