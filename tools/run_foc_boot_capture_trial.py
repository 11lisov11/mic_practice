"""One authorized 3013/3014 FOC5Hz/5s trial, unchanged guards and boot evidence."""
import hashlib
import json
from pathlib import Path
import sys
import run_foc_runtime_trial as trial
import prepare_boot_reset_capture as package
from configure_multi_algorithm import crc32c

trial.PAIR=package.NEW
trial.__doc__=__doc__


def decode_boot(s,pair,*,require_fresh=True):
    assert (s.get('fw_build'),s.get('mc_fw_build'))==pair,'Unexpected firmware pair'
    p=bytes.fromhex(s.get('mc_boot_packet_hex',''))
    assert len(p)==43 and p[:6]==bytes.fromhex('55aae9010100') and p[38]==0
    assert crc32c(p[:39])==int.from_bytes(p[39:43],'little'),'Boot wire CRC invalid'
    u=lambda offset:int.from_bytes(p[offset:offset+4],'little')
    assert u(6)==pair[1]
    words=[0x31525442,pair[1],u(10),u(14),u(18),u(22),u(26)]
    assert u(10)>0 and not u(22)&~15
    assert crc32c(b''.join(w.to_bytes(4,'little') for w in words))==u(30),'Early record CRC invalid'
    b=s.get('native_boot') or {}
    assert b.get('available') and (b.get('fresh') or not require_fresh) and b.get('current_flags_cleared')
    assert b.get('early_record_crc')==u(30) and b.get('csr_raw')==u(14)
    assert b.get('retained_sequence')==u(10)
    linux=s.get('linux_boot_id')
    assert isinstance(linux,str) and len(linux)==36,'Missing Linux boot identity'
    return dict(identity=[pair[1],u(10),u(14),u(18),u(22),u(26),u(30)],
        Linux_boot_id=linux,native_tick_ms=u(34),record=b,packet_hex=p.hex())


def audit_saved_trial(out):
    """Read saved files only. Never START/STOP/CLEAR/RESET or retry a run."""
    path=out/'report.json';report=json.loads(path.read_text(encoding='utf-8'))
    audit=dict(passed=False,hardware_commands=0,source='saved_trial_files')
    try:
        before=json.loads((out/'before_CLEAR.json').read_text(encoding='utf-8'))
        after=json.loads((out/'final_status.json').read_text(encoding='utf-8'))
        a=decode_boot(before,package.NEW);b=decode_boot(after,package.NEW)
        audit.update(before=a,after=b,native_identity_unchanged=a['identity']==b['identity'],
            Linux_identity_unchanged=a['Linux_boot_id']==b['Linux_boot_id'])
        assert audit['native_identity_unchanged'],'Native boot changed during trial'
        assert audit['Linux_identity_unchanged'],'Linux boot changed during trial'
        assert b['native_tick_ms']>=a['native_tick_ms'],'Native uptime decreased'
        if report.get('start_commands'):
            raw=(out/'ADC_peak.bin').read_bytes()
            assert len(raw)==1024 and raw[:4]==b'APC1' and int.from_bytes(raw[8:12],'little')==package.NEW[1]
            assert crc32c(raw[:60]+bytes(4)+raw[64:])==int.from_bytes(raw[60:64],'little')
            audit['ADC_raw_sha256']=hashlib.sha256(raw).hexdigest()
            audit['ADC_firmware_and_CRC_verified']=True
        audit['passed']=True
    except Exception as error:
        audit['error']=str(error);report['passed']=False
    report['boot_evidence_audit']=audit
    (out/'boot_evidence_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()
            if p.is_file() and p.name!='saved_files_sha256.json'}
    (out/'saved_files_sha256.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return bool(report.get('passed'))


def main():
    rc=trial.main()
    out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
    verified=audit_saved_trial(out)
    print(json.dumps(dict(saved_boot_audit_passed=json.loads((out/'boot_evidence_audit.json').read_text(encoding='utf-8'))['passed'],
        motor_commands_added_by_audit=0,passed=rc==0 and verified)))
    return 0 if rc==0 and verified else 1


if __name__=='__main__':raise SystemExit(main())
