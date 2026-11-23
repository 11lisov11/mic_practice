"""Atomic Linux-only update on the stopped USB bench; never writes either MCU."""
import ast,hashlib,json,subprocess,time,importlib.util
import prepare_rpc_hmi_admission as p


def main():
    out=p.OUT/'install_r1';out.mkdir(exist_ok=False)
    assert json.loads((p.OUT/'verification/report.json').read_text())['passed']
    proof=json.loads((p.BASE/'native_idle_recheck_r1/report.json').read_text())
    assert proof['passed'] and all(not x['moe'] and x['bus_volts']<20 and x['bdtr']&4096 for x in proof['rows'])
    adb=['adb','-s','3880458060']
    def run(args,label,timeout=20):
        r=subprocess.run(adb+args,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
        (out/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode();return r.stdout.strip()
    # Direct test is GET-only and must have restored the main port first.
    direct=json.loads((p.BASE/'direct_serial_r1/report.json').read_text())
    assert direct['main_open'][3] is True and direct['START']==direct['CLEAR']==0
    lines=(p.BASE/'direct_serial_r1/GETs.jsonl').read_text().splitlines()
    last=json.loads(lines[-1])['response'][3]
    spec=importlib.util.spec_from_file_location('rpc_candidate',p.OUT/'web_hmi/server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    status=m.RpcBridge._parse_status_string(last)
    assert status['state']=='SAFE' and status['pwm']==0 and 0<status['vdc']<20
    assert (status['fw_build'],status['mc_fw_build'])==(2026111609,2026111606)
    (out/'last_direct_status.json').write_text(json.dumps(status,indent=2),encoding='utf8')
    cal='/home/arduino/.config/mic-ai/vbus_calibration.json'
    cal_hash=run(['shell','sha256sum',cal],'calibration_before').split()[0]
    root='/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py'
    run(['pull',root,str(out/'server_before.py')],'backup_current_server')
    assert hashlib.sha256((out/'server_before.py').read_bytes()).hexdigest()==hashlib.sha256((p.BASE/'web_hmi/server.py').read_bytes()).hexdigest()
    staged='/tmp/mic_rpc_hmi_admission_server.py';run(['push',str(p.OUT/'web_hmi/server.py'),staged],'stage_server')
    digest=hashlib.sha256((p.OUT/'web_hmi/server.py').read_bytes()).hexdigest()
    cfg=dict(offline_programming_only=True,native_BKE=True,native_MOE=False,calibration_sha256=cal_hash,
        prospective_identity=status,files=[dict(remote=staged,destination='server.py',sha256=digest)])
    config=out/'deploy_config.json';config.write_text(json.dumps(cfg))
    run(['push',str(config),'/tmp/mic_rpc_hmi_admission_config.json'],'stage_config')
    tree=ast.parse((p.ROOT/'tools/finish_rollback_3014_hmi.py').read_text(encoding='utf8'))
    remote=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='REMOTE' for x in n.targets))
    remote=remote.replace("'rollback_3014_'","'rpc_hmi_admission_'").replace('CONFIG',repr('/tmp/mic_rpc_hmi_admission_config.json'))
    script=out/'deploy.py';script.write_text(remote)
    run(['push',str(script),'/tmp/mic_rpc_hmi_admission_deploy.py'],'stage_deploy')
    result=json.loads(run(['shell','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/.venv/bin/python','/tmp/mic_rpc_hmi_admission_deploy.py'],'deploy'))
    after=run(['shell','sha256sum',cal],'calibration_after').split()[0];assert after==cal_hash
    run(['pull',root,str(out/'server_readback.py')],'readback_server')
    assert (out/'server_readback.py').read_bytes()==(p.OUT/'web_hmi/server.py').read_bytes()
    report=dict(installed=True,Linux_server_readback_verified=True,calibration_unchanged=True,
        calibration_sha256=cal_hash,START=0,CLEAR=0,ARM=0,flash=0,MCU_reset=0,
        protections_unchanged=True,server_sha256=digest,deployment=result,runtime_verified=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=json.loads((p.OUT/'manifest.json').read_text());manifest.update(installed=True,readback_verified=True)
    (p.OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
