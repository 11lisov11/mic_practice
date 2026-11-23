"""Read-only USB/GET/SWD inventory after user connected both boards; no flashing."""
import json,subprocess,urllib.request
import prepare_clear_recovery as p
from probe_native_programming_state import probe
from install_bkin_boot_armed_pair import PROGRAMMER,STLINK_SERIAL


def main():
    out=p.OUT/'USB_recheck_after_shared_bank_r1';out.mkdir(exist_ok=False)
    report=dict(START=0,CLEAR=0,ARM=0,RESET=0,flash=0,halt=0,
        operator_state='Both boards PCUSB; J1 last confirmed OFF; J4 left ON',shared_powerbank_user_confirmed=True)
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token=p.read(p.ROOT/'.unoq_ssh/control_token').strip()
    try:
        q=urllib.request.Request('http://127.0.0.1:18080/api/status',headers={'X-UNOQ-Control-Token':token})
        with op.open(q,timeout=8) as f:raw=f.read()
        (out/'status.json').write_bytes(raw);r=json.loads(raw);s=r.get('data') or {}
        report['status']=dict(ok=r.get('ok'),values={k:s.get(k) for k in ('fw_build','mc_fw_build','state','pwm','vdc',
            'run_id','mc_fault','mc_transport_fault','mc_current_zero_ready','algorithm_fast_cycles')},SD=s.get('mc_sd_live'))
    except Exception as e:report['status_error']=str(e)
    try:
        result=probe(p.OUT,out/'native',confirmation_description='User connected both boards to PC; J1 last confirmed OFF; passive reads only')
        report['native']=result
        cmd=[str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+STLINK_SERIAL,'-u','0x20000000','32768',str(out/'native_RAM.bin')]
        r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
        p.write(out/'RAM_read.log',r.stdout+r.stderr);r.check_returncode()
        report['RAM_saved']=True
    except Exception as e:report['native_error']=str(e)
    p.write(out/'report.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=report.get('status'),status_error=report.get('status_error'),
        native_passed=report.get('native',{}).get('passed'),native_error=report.get('native_error'),RAM_saved=report.get('RAM_saved'),flash=0,RESET=0),ensure_ascii=True))


if __name__=='__main__':main()
