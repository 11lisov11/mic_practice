import json
import prepare_i2c_wire_epoch_fix as p
from passive_i2c_wire_guard import precheck
def main():
    s=json.loads(p.read(p.OUT/'manual_usb_capture_r1/before.json'))
    assert precheck(s,p.NEW)[0];checks=1
    for change in ({'state':'RUN'},{'pwm':1},{'hmi_hv_armed':1},{'bp_status':0x22},
      {'vdc':20},{'bp_vdc':float('nan')},{'bp_vbus_raw':200},{'mc_age_ms':300},
      {'bp_temp_age_ms':300},{'bp_vbus_valid':0},{'bp_temp_fault':1},{'mc_diag_valid':0},
      {'mc_uart_error_flags':1},{'uno_rx_hw_flags':8},{'precharge':1},{'brake':1},
      {'mc_fw_build':0},{'rpc_schema_version':2}):
        assert not precheck(dict(s,**change),p.NEW)[0],change;checks+=1
    result=dict(passed=True,checks=checks,hardware_commands=0,
      retained_timeout_CRC_metadata_not_modified=True,only_passive_capture=True,programming_and_motor_gates_unchanged=True)
    p.write(p.OUT/'passive_capture_gate_selftest.json',json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
