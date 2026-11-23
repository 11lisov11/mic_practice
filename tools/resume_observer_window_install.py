"""Complete one1611/1612 install after HEX padding audit, never rewrite native."""
import inspect,json,shlex,subprocess,time,uuid
from pathlib import Path
import install_observer_current_window as install
from probe_native_programming_state import programmed_hex_image
p=install.p;io=install.io
def main():
    out=p.OUT/'hardware_install_r1'
    r=json.loads(p.read(out/'report.json'))
    assert r['nucleo_flash_commands']==1 and r['uno_flash_commands']==0
    assert r['previous_native_image_verified']
    backup=out/'report_failed_padding.json'
    if not backup.exists():backup.write_bytes((out/'report.json').read_bytes())
    raw_bin=p.OUT/'release/nucleo_2026111612_observer_mean16.bin'
    hexfile=p.OUT/'release/nucleo_2026111612_observer_mean16.hex'
    image,holes=programmed_hex_image(hexfile,raw_bin.read_bytes())
    assert holes==[112172,112173,112174,112175],holes
    actual=(out/'native_flash_2026111612_readback.bin').read_bytes()
    assert image==actual,'HEX-derived full readback mismatch'
    expected=p.OUT/'release/nucleo_2026111612_expected_readback.bin'
    original=out/'expected_readback_zero_padding_original.bin'
    if not original.exists():original.write_bytes(expected.read_bytes())
    expected.write_bytes(image)
    assets=json.loads(p.read(p.OUT/'installation_assets.json'))
    assets[expected.relative_to(p.OUT).as_posix()]=p.sha(expected)
    p.write(p.OUT/'installation_assets.json',json.dumps(assets,indent=2)+'\n')
    p.write(out/'HEX_padding_audit.json',json.dumps(dict(passed=True,holes=holes,
        reference_derived_from='sealed IntelHEX, not readback bytes',
        every_HEX_programmed_byte_matches=True,erased_holes_FF=True,
        expected_sha256=p.sha(expected),additional_native_flash_commands=0),indent=2)+'\n')
    install.package_check()
    r.pop('error',None);r.update(native_readback_verified=True,native_flash_sha256=p.sha(expected),
        HEX_padding_audit=True,additional_nucleo_flash_commands=0)
    def save():p.write(out/'report.json',json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    def run(command,label,timeout=60):
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
        p.write(out/(label+'.log'),result.stdout+result.stderr)
        r.setdefault('commands',[]).append(dict(label=label,exit_code=result.returncode));save()
        result.check_returncode();return result.stdout
    io.URL='http://127.0.0.1:18080';io.ssh_base=install.tunneled(install.ssh_base)
    ssh=io.ssh_base('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    scp=install.tunneled(install.scp_base)('192.168.1.138',2222,'arduino',p.ROOT/'.unoq_ssh/id_ed25519',p.ROOT/'.unoq_ssh/known_hosts')
    uno_port,_=io.board_ports()
    swd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL]
    def registers(label):
        text=run(swd+['-r32','0x48000000','40','-r32','0x48000400','40','-r32','0x40012c00','104'],label,20)
        regs=install.parse_registers(text)
        assert regs[0x40012c44]&4096 and not regs[0x40012c44]&32768
        return regs
    registers('registers_before_resume')
    # Recheck live programming conditions in the expected intermediate pair.
    install.safe(io.live_status(),(2026111609,2026111612))
    config=out/'deploy_config.json';helper=out/'deploy_hmi.py'
    cfg=json.loads(p.read(config));prefix=cfg['files'][0]['remote'][:-len('server.py')]
    assert prefix.startswith('/tmp/mic_window1612_') and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_/' for c in prefix)
    router_closed=False
    source=inspect.getsource(install.main)
    tail=source[source.index('  def route(action):'):source.index(' print(json.dumps({k:r.get(k)')]
    # Reuse the checked upload/readback/HMI deployment and safe final checks.
    scope=dict(install.__dict__,p=p,io=io,NEW=p.NEW,out=out,r=r,save=save,run=run,
        ssh=ssh,scp=scp,uno_port=uno_port,swd=swd,registers=registers,prefix=prefix,helper=helper,
        cal='/home/arduino/.config/mic-ai/vbus_calibration.json',
        router_closed=router_closed)
    text='try:\n'+''.join(line[1:]+'\n' for line in tail.splitlines())
    # The original tail contains the except/finally of its surrounding try.
    exec(compile(text,__file__,'exec'),scope)
    print(json.dumps({k:r.get(k) for k in ('passed','native_readback_verified','uno_readback_verified','calibration_unchanged','error')}))
    return 0 if r['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
