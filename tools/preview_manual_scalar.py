"""Local browser fixture for manual UI; no physical board or network RPC access."""
import copy,json,sys,time
from pathlib import Path
from ipm_break_wifi_selftest import load_module
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261015/manual_scalar_working_pair_r1'
OUT=ROOT/'output/playwright/manual_scalar_20261015'
OUT.mkdir(parents=True,exist_ok=True)
mod=load_module(PACKAGE/'web_hmi/server.py')
data=json.loads((ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/working_bus_on_1791997952551152700/first_status.json').read_text())
data.update(fw_build=2026101501,mc_fw_build=2026101502,bp_fw_build=2026101502,
 manual_scalar_capable=1,manual_run_mode=0,accel_hz_per_s=5.,decel_hz_per_s=1.,downmode_coast=0,
 mc_frequency_reference_hz=0.,mc_frequency_reference_valid=1,mc_decel_bus_hold=0,
 state='SAFE',state_code=0,pwm=0,estop=0,bp_fault=0,bp_status=1,bp_softstart_ready=1,
 bp_age_ms=20,bp_rsp_age_ms=20,mc_age_ms=20,mc_rsp_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20,
 vdc=324.,bp_vdc=324.,bp_vbus_raw=3240,freq_cmd=5.,freq=0.,link=True,
 mc_fault_reason=0,mc_fault_current_mask=0,mc_fault_occurred_mask=0)
class RPC:
 def __init__(self):self.data=copy.deepcopy(data);self.commands=[];self.stamp=time.monotonic()
 def get(self):
  now=time.monotonic();dt=now-self.stamp;self.stamp=now
  if self.data['pwm']:
   delta=self.data['freq_cmd']-self.data['freq'];rate=self.data['accel_hz_per_s'] if delta>=0 else self.data['decel_hz_per_s']
   self.data['freq']+=min(abs(delta),rate*dt)*(1 if delta>=0 else -1)
  self.data['mc_frequency_reference_hz']=self.data['freq']
  self.data['ts']=int(time.time()*1000)
  result=copy.deepcopy(self.data)
  for key,value in list(result.items()):
   if key.startswith('bp_'):result['mc_'+key[3:]]=value
  return True,mod.with_motor_controller_aliases(result),''
 def cmd(self,command):
  self.commands.append({'command':command,'time':time.time()})
  if command=='START':self.data.update(state='VF_RUN',state_code=1,pwm=1,bp_status=0x23)
  elif command in ('STOP','ESTOP'):self.data.update(state='SAFE',state_code=0,pwm=0,bp_status=1,freq=0.)
  elif command.startswith('SET FREQ '):self.data['freq_cmd']=float(command.split()[-1])
  elif command.startswith('SET ACCEL '):self.data['accel_hz_per_s']=float(command.split()[-1])
  elif command.startswith('SET DECEL '):self.data['decel_hz_per_s']=float(command.split()[-1])
  elif command.startswith('SET DOWNMODE '):self.data['downmode_coast']=int(command.endswith('COAST'))
  elif command.startswith('SET RUNMODE '):self.data['manual_run_mode']=int(command.endswith('MANUAL'))
  (OUT/'mock_commands.json').write_text(json.dumps(self.commands,indent=2)+'\n')
  return True,''
rpc=RPC();key=OUT/'fixture_token';key.write_text('offline-browser-fixture-only')
store=mod.VbusCalibrationStore(str(ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1/vbus_recalibration_preparation/original_vbus_calibration.json'))
app=mod.AppState(rpc,mod.LogStore(65536,None,65536),0,
 command_guard=mod.CommandGuardConfig(max_vdc=400,allow_hv=True,local_bench_gate=True),
 hv_arm=mod.HvArmState(mod.HvArmConfig(enabled=True,min_vdc=250,max_vdc=360)),
 start_runlimit_sec=15,control_access=mod.ControlAccessConfig(str(key)),vbus_calibration=store)
http=mod.ThreadingHTTPServer(('127.0.0.1',18765),mod.Handler);http.app=app
print('LOCAL MOCK ONLY http://127.0.0.1:18765',flush=True)
try:http.serve_forever()
except KeyboardInterrupt:pass
finally:http.server_close()
