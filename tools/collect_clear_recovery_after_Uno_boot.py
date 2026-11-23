"""GET-only recovery after user power-cycled Uno, keeping Nucleo/RAM powered."""
import json,pathlib,time,urllib.request
import prepare_clear_recovery as p


def main():
    out=p.OUT/'powered_FOC_NIS_5Hz_r1/after_Uno_coldboot_r1';out.mkdir(exist_ok=False)
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip();op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    report=dict(passed=False,START=0,CLEAR=0,ARM=0,flash=0,RESET=0,SWD=0,
        Uno_power_cycle_user_confirmed=True,Nucleo_power_retained_user_confirmed=True,attempts=[])
    until=time.monotonic()+55
    while time.monotonic()<until:
        try:
            q=urllib.request.Request('http://192.168.1.138:8080/api/status',headers={'X-UNOQ-Control-Token':token})
            with op.open(q,timeout=6) as f:raw=f.read()
            r=json.loads(raw);assert r['ok'],r.get('error');s=r['data']
            name=f'status_{len(report["attempts"]):02d}.json';(out/name).write_bytes(raw)
            report['attempts'].append(dict(ok=True,file=name,pwm=s.get('pwm'),ADC_complete=s.get('mc_adc_peak_complete'),observer_complete=s.get('mc_observer_trace_complete')))
            assert (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW
            assert s.get('pwm')==0 and not s.get('bp_status',0x22)&0x22,'Outputs off not confirmed'
            report['outputs_off_confirmed']=True
            for key,name in (('mc_adc_peak_hex','ADC_peak.bin'),('mc_observer_trace_hex','observer_trace.bin'),('mc_break_wave_hex','SD_after.bin')):
                value=s.get(key,'-')
                if value not in ('','-'):(out/name).write_bytes(bytes.fromhex(value))
            if s.get('mc_adc_peak_complete')==1 and s.get('mc_observer_trace_complete')==1:
                (out/'final_status.json').write_bytes(raw);report.update(passed=True,records_received=True);break
            report['last_status']=name
        except Exception as error:report['attempts'].append(dict(ok=False,error=str(error)))
        p.write(out/'report.json',json.dumps(report,indent=2)+'\n');time.sleep(1)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
