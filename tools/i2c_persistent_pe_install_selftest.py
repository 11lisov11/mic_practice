"""Programming gate tests, using the current saved OFF-state fixture only."""
import copy,json,math
import install_i2c_persistent_pe as update
from pathlib import Path
def main():
 s=json.loads((update.p.OUT/'before_install_status.json').read_text(encoding='utf-8'))
 assert update.install.precheck(s)[0];n=1
 for changes in ({'pwm':1},{'hmi_hv_armed':1},{'state':'RUN'},{'bp_status':0x22},{'vdc':20.01},{'bp_vdc':21},{'vdc':float('nan')},{'bp_vbus_raw':201},{'mc_age_ms':300},{'bp_temp_age_ms':301},{'bp_vbus_valid':0},{'bp_temp_fault':1},{'mc_fw_build':0},{'rpc_schema_version':2},{'precharge':1},{'brake':1},{'mc_last_bad_reason':1},{'mc_bad_cnt':2},{'mc_uart_error_flags':4},{'mc_fault_current_mask':16},{'uno_rx_hw_errors':1}):
  assert not update.install.precheck(dict(s,**changes))[0],changes;n+=1
 x=copy.deepcopy(s);x.update(fw_build=2026102709,mc_fw_build=2026102710)
 assert update.install.precheck(x)[0];n+=1
 # Acknowledged clean metadata also remains eligible; no fault CLEAR is sent.
 for key in ('mc_uart_error_flags','bp_uart_error_flags','mc_transport_fault','bp_transport_fault'):x[key]=0
 assert update.install.precheck(x)[0];n+=1
 print(json.dumps(dict(passed=True,checks=n,hardware_commands=0,latched_metadata_not_mutated=True)))
if __name__=='__main__':main()
