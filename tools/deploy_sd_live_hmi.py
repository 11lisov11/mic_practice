"""Apply verified SD display correction over Wi-Fi, without MCU access or actuation."""
import argparse
import json
from pathlib import Path
import shlex
import uuid
import install_sd_live_diagnostics_pair as candidate
from unoq_wifi_hmi_deploy import ssh_base, scp_base


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-j1-off',action='store_true',required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    candidate.verify_package()
    io=candidate.base.io
    root=candidate.ROOT
    out=args.outdir.resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=dict(pass_=False,motor_commands=0,clear_commands=0,reset_commands=0,
        mcu_flash_commands=0,calibration_writes=0,j1_off_user_confirmed=True,j4_unchanged=True)

    def run(cmd,label,timeout=60):return io.run(cmd,label,out,report,timeout)

    try:
        before=io.live_status()
        report['before']=before
        assert (before['fw_build'],before['mc_fw_build'])==candidate.OLD
        okay,reason=candidate.precheck(before)
        if not okay:raise RuntimeError(reason)
        report['calibration_before']=io.calibration_hash(out,report)
        ssh=ssh_base('192.168.1.138',2222,'arduino',root/'.unoq_ssh/id_ed25519',root/'.unoq_ssh/known_hosts')
        scp=scp_base('192.168.1.138',2222,'arduino',root/'.unoq_ssh/id_ed25519',root/'.unoq_ssh/known_hosts')
        local=out/'remote_hmi_installer.py'
        local.write_text(candidate.make_remote_installer(),encoding='utf-8')
        prefix='/tmp/mic_sd_live_'+uuid.uuid4().hex
        files=[(candidate.C/'web_hmi/server.py',prefix+'_server.py'),
               (candidate.C/'web_hmi/static/app.js',prefix+'_app.js'),(local,prefix+'_installer.py')]
        for source,target in files:
            run(scp+[str(source),'arduino@192.168.1.138:'+target],'stage_'+source.name)
        cmd=['python3',files[2][1],'--candidate',files[0][1],'--sha256',io.sha(files[0][0]),
             '--app-js',files[1][1],'--app-js-sha256',io.sha(files[1][0]),'--max-vdc','20','--confirm-mains-off']
        run(ssh+[shlex.join(cmd+['--check-only'])],'hmi_precheck')
        run(ssh+[shlex.join(cmd)],'install_hmi',65)
        report['after']=io.live_status()
        after=report['after']
        if (after['fw_build'],after['mc_fw_build'])!=candidate.OLD:raise RuntimeError('MCU identities changed')
        okay,reason=candidate.precheck(after)
        if not okay:raise RuntimeError(reason)
        sd=after.get('mc_sd_live',{})
        if sd.get('available') is not False or sd.get('reason')!='unsupported_peer':
            raise RuntimeError('older MCU must explicitly report unknown current SD')
        report['calibration_after']=io.calibration_hash(out,report)
        if report['calibration_after']!=report['calibration_before']:raise RuntimeError('calibration changed')
        report['calibration_unchanged']=True
        report['pass_']=True
    except Exception as exc:
        report['error']=str(exc)
    report['pass']=report.pop('pass_')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','mcu_flash_commands','motor_commands','calibration_unchanged','error')}))
    return 0 if report['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
