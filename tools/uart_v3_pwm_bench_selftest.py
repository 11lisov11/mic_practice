"""Offline bench gates and actual cleanup control flow under RPC failure."""
import ast
import json
from pathlib import Path
import tempfile
import tkinter

from run_uart_v3_pwm_bench import basic, clean_transport, PRODUCTION
from web_hmi_command_guard_selftest import safe_status


def main():
    cases = 0
    s = safe_status(fw_build=PRODUCTION[0], mc_fw_build=PRODUCTION[1],
                    vdc=0.0,bp_vdc=0.0,bp_vbus_raw=0,mc_age_ms=25,
                    mc_diag_valid=1,bp_vbus_valid=1,uno_tx_short_writes=0,
                    mc_bad_cnt=0,mc_uart_error_flags=0,mc_last_uart_error_flags=0,
                    bp_transport_fault=0,mc_bad_integrity=0,mc_bad_sequence=0)
    basic(s,PRODUCTION); cases+=1
    baseline={"mc_bad_integrity":0,"mc_bad_sequence":0}
    assert clean_transport(s,baseline); cases+=1
    for key,value in (("vdc",2.01),("vdc",float("nan")),("bp_vdc",float("inf")),
                      ("bp_vbus_raw",21),("mc_age_ms",300),("bp_temp_age_ms",-1),
                      ("mc_diag_valid",0),("precharge",1),("uno_tx_short_writes",1),
                      ("mc_fw_build",2026101099)):
        try:basic(dict(s,**{key:value}),PRODUCTION)
        except (RuntimeError,ValueError,TypeError):cases+=1
        else:raise AssertionError("unsafe bench state accepted")
    for key in ("mc_bad_cnt","mc_uart_error_flags","mc_last_uart_error_flags",
                "bp_transport_fault","mc_bad_integrity","mc_bad_sequence"):
        assert not clean_transport(dict(s,**{key:1}),baseline);cases+=1
    source=Path(__file__).with_name("run_uart_v3_pwm_bench.py")
    tree=ast.parse(source.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    program_uno=next(n for n in fn.body if isinstance(n,ast.FunctionDef) and n.name=="program_uno")
    assert sum(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
               and n.func.id=="run_logged" for n in ast.walk(program_uno))==1
    assert "flash_verify_unoq_sketch.cfg" in ast.unparse(program_uno)
    cases+=2
    recipe=source.with_name("flash_verify_unoq_sketch.cfg").read_text()
    for image in ("${filename0}","${filename1} 0x08100000 bin"):
        assert recipe.index("flash write_image erase "+image) < recipe.rindex("flash verify_image "+image)
        cases+=1
    assert recipe.index("shutdown error") < recipe.index("mww 0x40036400 0xCAFFEEEE")
    cases+=1
    for scenario in ("unchanged", "changed", "write_error", "verify_error"):
        tcl=tkinter.Tcl()
        tcl.eval(r'''
            set filename0 loader
            set filename1 sketch
            set events {}
            set mismatch [dict create loader 0 sketch 0]
            proc reset_config {args} {}
            proc init {} {}
            proc reset {} {lappend ::events reset}
            proc halt {} {}
            proc echo {args} {}
            proc sleep {args} {}
            proc mww {args} {lappend ::events boot}
            proc shutdown {args} {set ::exit_status $args}
            proc flash {op args} {
                global events mismatch scenario
                lappend events [list flash $op {*}$args]
                if {$op eq "verify_image"} {
                    if {[dict get $mismatch [lindex $args 0]]} {error "injected mismatch"}
                } elseif {$op eq "write_image"} {
                    set target [lindex $args 1]
                    if {$scenario eq "write_error"} {error "injected write error"}
                    if {$scenario ne "verify_error"} {dict set mismatch $target 0}
                }
            }
        ''')
        tcl.setvar("scenario",scenario)
        if scenario != "unchanged":
            tcl.eval("set mismatch [dict create loader 1 sketch 1]")
        tcl.eval(recipe)
        successful=scenario in ("unchanged","changed")
        assert (tcl.getvar("exit_status")=="") == successful
        assert bool(int(tcl.eval("expr {[lsearch -exact $events boot] >= 0}"))) == successful
        if successful:
            assert int(tcl.eval("llength [lsearch -all -exact $events reset]"))==2
        else:
            assert int(tcl.eval("llength [lsearch -all -exact $events reset]"))==1
        cases+=3
    cleanup=next(n.finalbody for n in fn.body if isinstance(n,ast.Try) and n.finalbody)
    code=compile(ast.fix_missing_locations(ast.Module(body=cleanup,type_ignores=[])),str(source),"exec")

    class BrokenRpc:
        def fail_safe_stop(self):return None
        def status(self):raise RuntimeError("injected RPC loss")
        def close(self):pass

    with tempfile.TemporaryDirectory() as folder:
        calls=[]
        def program(image,label):calls.append(label)
        def boundary(*args):raise RuntimeError("RPC still lost after byte verification")
        rep={"pass":False,"restored":False}
        env=dict(changed=True,h=BrokenRpc(),rep=rep,PRODUCTION=PRODUCTION,FIXTURE=(2026101100,2026101099),
                 pb=Path(folder),nb="image.bin",pu=Path(folder)/"uno.bin",out=Path(folder),
                 program_nuc=program,program_uno=program,boundary=boundary,
                 clean_transport=clean_transport,reply_baseline=baseline,json=json,time=None)
        exec(code,env)
        assert calls==["restore_nucleo","restore_uno"],calls
        assert "profile_restore_error" in rep and "restore_error" in rep
        cases+=2
    print(json.dumps({"pass":True,"cases":cases,"hardware_commands":0,
                      "rpc_failure_cannot_skip_flash_restore":True}))


if __name__=="__main__":main()
