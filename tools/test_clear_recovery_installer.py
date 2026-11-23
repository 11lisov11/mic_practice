"""Offline installer guards and actual OFF-qualification predicates; no hardware."""
import ast,copy,json,socket
from unittest.mock import patch
import prepare_clear_recovery as p
import install_clear_recovery as installer


def assignment(tree,key):
    return next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='report'
            and isinstance(t.slice,ast.Constant) and t.slice.value==key for t in n.targets))


def main():
    out=p.OUT/'installation_preparation_r1';out.mkdir(exist_ok=False)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline preparation forbids network')):
        installer.package_check()
        s=json.loads(p.read(p.BASE/'post_install_idle_r1/final_status.json'))['data']
        installer.safe(s,installer.OLD)
        failures=[]
        bad_values=dict(vdc=20.01,bp_vdc=20.01,state='RUN',pwm=1,hmi_hv_armed=1,
            bp_status=0x22,mc_age_ms=300,mc_uart_error_flags=2,mc_last_uart_error_flags=2,
            mc_bad_integrity=1,mc_bad_sequence=1,precharge=1,pfc=1,brake=1,bp_ext=1,
            fw_build=2026111601,mc_fw_build=2026111602,rpc_schema_version=2,
            mc_capabilities=0,bp_mcsdk_telemetry=0)
        for key,value in bad_values.items():
            bad=copy.deepcopy(s);bad[key]=value
            try:installer.safe(bad,installer.OLD)
            except AssertionError:failures.append(key)
            else:raise AssertionError('Unsafe installation accepted: '+key)
        source=p.read(p.ROOT/'tools/verify_clear_recovery_idle.py');tree=ast.parse(source)
        predicate=compile(ast.Expression(assignment(tree,'CPU_qualified')),'actual_OFF_predicate','eval')
        row=dict(fe_complete=1,fe_case=64,fe_fault=0,fast_cycles=4000,observer_cycles=85000,
                 OFF_source=1,observer_steps=64,meter_errors=0)
        assert eval(predicate,dict(ram_rows=[row,dict(row)]))
        for key,value in dict(fast_cycles=4001,observer_cycles=85001,fe_complete=0,fe_case=63,
                fe_fault=1,OFF_source=0,observer_steps=63,meter_errors=1).items():
            bad=dict(row);bad[key]=value
            assert not eval(predicate,dict(ram_rows=[row,bad])),key
        passed=compile(ast.Expression(assignment(tree,'passed')),'actual_pass_predicate','eval')
        good=dict(CPU_qualified=True,fresh_link=True,new_rejected_frames=False,
                  ordinary_telemetry_fresh=True,UART_clean=True,RPC_stable=True)
        assert eval(passed,dict(report=good))
        for key in ('CPU_qualified','fresh_link','ordinary_telemetry_fresh','UART_clean','RPC_stable'):
            bad=dict(good);bad[key]=False;assert not eval(passed,dict(report=bad)),key
        text=p.read(p.ROOT/'tools/install_clear_recovery.py')
        assert all(x not in text+source for x in ('/api/start-sequence','/api/cmd','/api/hv-arm'))
        assert "clear_record_empty=val('mic_clear_diag_ready','<B')==0" in source
        assert "assert not row['fe_trial_done'] and trace_empty and row['clear_record_empty']" in source
        assert 'report[\'RPC_stable\']=rpc.ready and rpc.failure is None' in source
    scripts=('prepare_clear_recovery_installer.py','install_clear_recovery.py','verify_clear_recovery_idle.py',
             'record_clear_recovery_installation.py','test_clear_recovery_installer.py')
    for f in scripts:compile(p.read(p.ROOT/'tools'/f),f,'exec')
    report=dict(passed=True,unsafe_states_rejected=failures,OFF_CPU_negative_cases=8,
        OFF_CPU_boundary4000_accepted=True,OFF_CPU4001_rejected=True,ordinary_freshness_UART_RPC_required=True,
        post_programming_CLEAR_record_must_be_empty=True,script_hashes={f:p.sha(p.ROOT/'tools'/f) for f in scripts},
        hardware_commands=0,START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        package_pair=list(p.NEW),preserved_files_verified=len(json.loads(p.read(p.OUT/'preserved_capture_hashes.json'))))
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
