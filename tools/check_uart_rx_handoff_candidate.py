"""Exercise actual candidate adapter plus real recorded HMI diagnostics."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import prepare_uart_rx_handoff as p
from current_zero_quality import ready


def main():
    out=p.OUT;checks=[];v=out/'verification'
    audit=p.BASE/'rx_handoff_audit_r1'
    folder=v/'rx';folder.mkdir(exist_ok=True)
    (folder/'adapter.h').write_bytes((out/'UNOQ_MOTOR/nucleo_buffered_serial.h').read_bytes())
    source=(audit/'probe.cpp').read_text()
    source=source.replace('if(same&&uv3_crc_ok(got))++exact;',
        'assert(serial.stats().rescued==1);if(same&&uv3_crc_ok(got))++exact;')
    probe=folder/'probe.cpp';probe.write_text(source)
    exe=folder/'probe.exe'
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',
        '-I',str(audit/'mock'),'-I',str(folder),'-I',str(out/'UNOQ_MOTOR'),
        str(probe),'-o',str(exe)],check=True)
    rx=json.loads(subprocess.check_output([str(exe)],text=True))
    assert rx['exact_crc_valid']==43 and rx['one_byte_erased']==0 and rx['overflow_checks']==1
    checks.append('Actual candidate: late arrival at all43 positions preserves byte order/CRC and rescued count; overflow still counted')
    for f in (p.BASE/'UNOQ_MOTOR').iterdir():
        if f.is_file() and f.name not in ('nucleo_buffered_serial.h','UNOQ_MOTOR.ino'):
            assert f.read_bytes()==(out/'UNOQ_MOTOR'/f.name).read_bytes(),f.name
    old=(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8')
    new=(out/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8')
    normalized=new.replace('FW_BUILD_ID = 2026102603U;','FW_BUILD_ID = 2026102601U;')
    normalized=normalized.replace('\n  s += " uno_rx_rescued="; s += String((unsigned long)rx_stats.rescued);','')
    assert old==normalized
    assert not any('ZephyrSerial::read' in f.read_text(encoding='utf-8',errors='replace')
        for f in (out/'UNOQ_MOTOR').iterdir() if f.is_file() and f.suffix in ('.cpp','.ino'))
    checks.append('All motor/STOP/deadline/SD/PWM/ADC/protocol source unchanged; only adapter, identity and read-only counter differ')
    header=(out/'UNOQ_MOTOR/nucleo_buffered_serial.h').read_text()
    assert header.count('ZephyrSerial::IrqHandler();')==1
    wire=json.loads(subprocess.check_output([str(p.BASE/'verification/encoder_selftest.exe')],text=True))
    assert wire['passed'];checks.append('Encoder driver and wire guards: '+str(wire['checks'])+' checks')
    spec=importlib.util.spec_from_file_location('rxhandoff_hmi',out/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    s=json.loads((p.BASE/'runtime_idle_r1/status_after.json').read_text());s['fw_build']=p.NEW[0]
    assert ready(h.with_zero_history(h.with_shunt_currents(copy.deepcopy(s))))
    assert not ready(dict(s,mc_current_flags=16))
    corrupt=copy.deepcopy(s);z=bytearray.fromhex(s['mc_zero_history_hex']);z[16]^=1;corrupt['mc_zero_history_hex']=z.hex()
    assert h.with_zero_history(corrupt)['mc_zero_history_valid']==0
    assert h.with_zero_history(dict(s,fw_build=2026102699))['mc_zero_history_valid']==0
    stored=dict(fw_build=p.OLD[0],mc_fw_build=p.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=p.NEW[0]))
    assert h.manual_scalar_supported(dict(s,manual_scalar_capable=1))
    done=dict(s,run_id=1,run_reason=1,run_start_ms=1000,run_stop_ms=6000,run_elapsed_ms=5000,run_limit_ms=5000)
    assert h.bounded_run_complete(done,dict(run_id=0),5)
    assert not h.bounded_run_complete(dict(done,mc_fault=1),dict(run_id=0),5)
    parsed=h.RpcBridge._parse_status_string('DATA state=SAFE mode=VF pwm=0 uno_rx_rescued=17')
    assert parsed['uno_rx_rescued']==17
    checks.append('Real recorded zero history, calibration compatibility, manual scalar and MCU5s STOP guards preserved; corrupt and unknown data rejected; rescued field parsed')
    ui=json.loads(subprocess.check_output(['node',str(p.ROOT/'tools/current_shunt_ui_selftest.js'),str(out/'web_hmi/static/app.js')],text=True))
    assert ui['passed']
    report=dict(passed=True,hardware_commands=0,checks=checks,rx=rx,driver_checks=wire['checks'],hardware_validated=False)
    (v/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    m=json.loads((out/'manifest.json').read_text());m['selftest_pass']=True
    (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
