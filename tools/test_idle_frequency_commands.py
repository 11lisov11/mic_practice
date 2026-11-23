"""Check HMI/Uno frequency settings while drive stays disarmed; never START."""
import argparse
import json
from pathlib import Path
import time
import urllib.request
from collect_wifi_telemetry import read_token

ROOT=Path(__file__).resolve().parents[1]
PAIR=(2026102103,2026102104)

def idle(s):
    return ((s.get('fw_build'),s.get('mc_fw_build'))==PAIR and s.get('state')=='SAFE'
        and s.get('pwm')==0 and s.get('hmi_hv_armed')==0 and not s.get('bp_status',0)&0x22
        and 0<=s.get('mc_age_ms',999999)<300
        and all(s.get(k)==0 for k in ('precharge','pfc','brake','mc_transport_fault',
            'bp_transport_fault','mc_uart_error_flags','mc_bad_integrity','mc_bad_sequence')))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=read_token(str(ROOT/'.unoq_ssh/control_token'))
    report=dict(passed=False,start_commands=0,arm_commands=0,clear_commands=0,flash_commands=0,
                scope='Live idle HMI->Uno settings with continuously disabled output; not an active Nucleo frequency/PWM test.',samples=[],commands=[])
    def get():
        with opener.open('http://192.168.1.138:8080/api/status',timeout=5) as response:r=json.load(response)
        assert r['ok'];report['samples'].append(r['data']);return r['data']
    def command(hz):
        # The only mutation in this test is SET FREQ. 0 is the normal STOP endpoint.
        body=json.dumps({'cmd':'SET FREQ '+str(hz)}).encode()
        req=urllib.request.Request('http://192.168.1.138:8080/api/cmd',data=body,
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},method='POST')
        with opener.open(req,timeout=8) as response:r=json.load(response)
        report['commands'].append({'command':'SET FREQ '+str(hz),'ok':r.get('ok')})
        assert r.get('ok'),r.get('error')
    before=None
    try:
        before=get();report['before']=before
        assert idle(before),'Not fresh disarmed exact pair; no setting test'
        assert before.get('freq_cmd')==0,'Preserve existing nonzero user setting'
        for hz in (5,9.9,10,15,20,23,25,50,25,10,5,0):
            assert idle(get()),'Health changed; stop setting test'
            command(hz);time.sleep(.25)
            deadline=time.monotonic()+2
            while True:
                s=get();assert idle(s),'Outputs or transport changed'
                if abs(s.get('freq_cmd',-100)-hz)<.02:break
                if time.monotonic()>deadline:raise RuntimeError('Frequency setting not acknowledged')
                time.sleep(.15)
        report['after']=get()
        assert report['after']['mc_good']>before['mc_good'],'No fresh Nucleo replies'
        assert idle(report['after'])
        report['passed']=True
    except Exception as exc:
        report['error']=str(exc)
        if before is not None and idle(before):
            try:command(0);report['failure_stop_requested']=True
            except Exception as stop_error:report['failure_stop_error']=str(stop_error)
    report['calibration_writes']=0
    report['actual_pwm_waveform_measured']=False
    report['powered_motor_test_performed']=False
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'frequency_settings':[c['command'] for c in report['commands']],
        'start_commands':0,'arm_commands':0,'actual_pwm_waveform_measured':False,'error':report.get('error')}))
    return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
