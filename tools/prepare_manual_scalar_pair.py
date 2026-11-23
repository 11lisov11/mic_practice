"""Prepare one permanent manual V/f working bundle; no hardware writes."""
import json
import shutil
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha,write
from manual_scalar_sources import sketch,nucleo,replace,PAIR
from manual_scalar_web import server,html,javascript

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/uart_recovery_working_pair_r2'
OUT=ROOT/'artifacts/live_bench_20261015/manual_scalar_working_pair_r1'

def prepare():
    old=json.loads((BASE/'manifest.json').read_text())
    assert old['installed'] and old['pair']==[2026101415,2026101414]
    for tree,key in [('nucleo','nucleo_source_sha256'),('UNOQ_MOTOR','uno_source_sha256')]:
        assert source_hashes(BASE/tree)==old[key]
    assert sha(BASE/'web_hmi/server.py')==old['hmi_sha256']
    if (OUT/'manifest.json').exists():assert not json.loads((OUT/'manifest.json').read_text())['installed']
    OUT.mkdir(exist_ok=True,parents=True)
    for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,dirs_exist_ok=True,ignore=shutil.ignore_patterns('Debug','Release','__pycache__','.metadata'))
    write(OUT/'nucleo/Src/main.c',nucleo((BASE/'nucleo/Src/main.c').read_text()))
    write(OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino',sketch((BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()))
    for tree in ('nucleo/Inc','UNOQ_MOTOR'):
        shutil.copyfile(ROOT/'tools/manual_scalar_control.h',OUT/tree/'manual_scalar_control.h')
        f=OUT/tree/'break_wire.h';write(f,replace(f.read_text(),'BW_NUCLEO_BUILD 2026101414UL','BW_NUCLEO_BUILD 2026101502UL'))
    f=OUT/'UNOQ_MOTOR/nucleo_fault_diagnostics.h';s=f.read_text()
    s=replace(s,'build == 2026101414U;','build == 2026101414U || build == 2026101502U;')
    s=replace(s,'  // Caller has already checked', '''  if (reply && mcsdk && build==2026101502U && (reply[11]&0xFEU)==0xA0U) {
    d.valid=true;d.last_bad_valid=true;
    d.current_faults=(uint16_t)(reply[15] | ((uint16_t)reply[16]<<8));
    d.occurred_faults=(uint16_t)(reply[27] | ((uint16_t)reply[28]<<8));
    d.sequence=reply[30];d.tx_status=reply[22]&0x0FU;d.last_bad_reason=reply[22]>>4;
    return d;
  }
  // Caller has already checked''')
    write(f,s)
    write(OUT/'web_hmi/server.py',server((BASE/'web_hmi/server.py').read_text()))
    static=OUT/'web_hmi/static';static.mkdir(exist_ok=True)
    archived=OUT/'base_static';archived.mkdir(exist_ok=True)
    op=build_opener(ProxyHandler({}))
    for route,name in (('/','index.html'),('/app.js','app.js'),('/style.css','style.css')):
        source=archived/name
        if not source.exists():
            with op.open('http://192.168.1.138:8080'+route,timeout=8) as response:source.write_bytes(response.read())
        text=source.read_text(encoding='utf-8')
        if name=='index.html':text=html(text)
        if name=='app.js':text=javascript(text)
        if name=='style.css':text+='\n[hidden]{display:none!important;} .manual-config {display:grid;gap:10px;padding:14px 0;} .manual-config label{display:flex;gap:10px;align-items:center;justify-content:space-between;} .manual-config input[type=number],.manual-config select{max-width:220px;background:#131922;color:#eef0f4;border:1px solid #39404b;border-radius:8px;padding:8px;} .manual-settings{display:grid;gap:10px;border-top:1px solid #303844;padding-top:10px;} .manual-settings summary{cursor:pointer;color:#b9c2ce;}\n'
        write(static/name,text)
    css=static/'style.css';write(css,css.read_text()+ '\n.io-block[hidden]{display:none!important;}\n')
    hashes=source_hashes(OUT/'nucleo')
    changed=[path for path,h in hashes.items() if old['nucleo_source_sha256'].get(path)!=h]
    assert sorted(changed)==['Inc/break_wire.h','Inc/manual_scalar_control.h','Src/main.c'],changed
    assert sha(OUT/'nucleo/Inc/uart_v3_transport.h')==sha(BASE/'nucleo/Inc/uart_v3_transport.h')
    mf=dict(old,pair=list(PAIR),predecessor_pair=old['pair'],predecessor_candidate=str(BASE),
        nucleo_source_sha256=hashes,uno_source_sha256=source_hashes(OUT/'UNOQ_MOTOR'),
        hmi_sha256=sha(OUT/'web_hmi/server.py'),hmi_static_sha256={f:sha(static/f) for f in ('index.html','app.js','style.css')},
        source_only=True,installed=False,qualification_pending=True,manual_scalar=True,
        continuous_operator_control=True,frequency_range_hz=[0,50],accel_range_hz_per_s=[.1,50],
        decel_range_hz_per_s=[.1,5],stop_mode='coast',default_downshift_mode='voltage-aware ramp',
        brake_resistor_used=False,calibration_points_preserved=True,hardware_commands=0,
        measurement_and_pwm_sources_unchanged=True,no_fixture_firmware=True)
    write(OUT/'manifest.json',json.dumps(mf,indent=2)+'\n')
    print(json.dumps({'prepared':True,'pair':list(PAIR),'installed':False,'hardware_commands':0,'candidate':str(OUT)}))

if __name__=='__main__':prepare()
