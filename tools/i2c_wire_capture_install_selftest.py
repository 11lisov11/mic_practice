"""Programming gate tests against the current actual read-only USB fixture."""
import json
import install_i2c_wire_capture as update

def main():
    s=json.loads(update.p.read(update.p.OUT/'before_install_status.json'))
    assert update.install.precheck(s)[0];checks=1
    for changes in ({'pwm':1},{'hmi_hv_armed':1},{'state':'RUN'},{'bp_status':0x22},
      {'vdc':20.01},{'bp_vdc':21},{'vdc':float('nan')},{'bp_vbus_raw':201},
      {'mc_age_ms':300},{'bp_temp_age_ms':301},{'bp_vbus_valid':0},{'bp_temp_fault':1},
      {'mc_fw_build':0},{'rpc_schema_version':2},{'precharge':1},{'brake':1},
      {'mc_uart_error_flags':4},{'mc_transport_fault':4},{'bp_transport_fault':4}):
        assert not update.install.precheck(dict(s,**changes))[0],changes;checks+=1
    assert update.install.precheck(dict(s,fw_build=update.p.NEW[0],mc_fw_build=update.p.NEW[1]))[0];checks+=1
    scope={};exec(update.install.GUARD,dict(math=__import__('math')),scope)
    assert scope['precheck'](s)[0];checks+=1
    r=dict(passed=True,checks=checks,hardware_commands=0,programming_only=True)
    update.p.write(update.p.OUT/'install_gate_selftest.json',json.dumps(r,indent=2)+'\n')
    print(json.dumps(r))
if __name__=='__main__':main()
