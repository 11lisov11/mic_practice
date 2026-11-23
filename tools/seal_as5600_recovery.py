"""Seal errata/recovery candidate, preserving installed2517 and its evidence."""
import json
import prepare_as5600_recovery as p
import prepare_current_shunt_monitor as u
def main():
    out=p.OUT;m=json.loads(u.read(out/'manifest.json'));assert not m['installed']
    for rel,digest in m['source_sha256'].items():assert u.sha(out/rel)==digest,rel
    assert json.loads(u.read(out/'offline-checks.json'))['passed']
    b=json.loads(u.read(out/'build/uno/unoq_mcsdk_scalar.build-manifest.json'));assert b['firmware_build_id']==2026102518
    for a in b['artifacts']:assert u.sha(out/'build/uno'/a['file'])==a['sha256'].lower()
    assert json.loads(u.read(out/'build/uno/llext-check.json'))['pass']
    evidence=dict(
        errata='https://www.st.com/resource/en/errata_sheet/es0499-stm32u575xx-and-stm32u585xx-device-errata-stmicroelectronics.pdf',
        errata_revision='ES0499 Rev12,June2026,section2.20.2 applies to U585 revisionU(0x3007)',
        ll_reset='https://dev.st.com/stm32cube-docs/stm32u5-hal2/2.0.0-beta.1.1/docs/drivers/ll_drivers/i2c/api/ll_i2c_exported_functions.html',
        sensor='https://cdn.sparkfun.com/assets/f/a/b/b/a/AS5600_Datasheet.pdf',
        confirmed_software_defect='2517 aborted and reset on sole BERR; ST says clear BERR and continue controller transfer. This can induce secondary BUSY but its exact contribution on the bench is unproven.',
        other_hardening='Wait boundedly for automatic NACK STOP/ARLO bus release before reset;PE readback+2us. NACK/ARLO/OVR/deadline remain failures;all data discarded. No bus-clear clocks or same-sample retry.',
        filter='Mode5 ANF+DNF, PCLK mux verified, actual kernel rate required20..160MHz; standard timing recalculated with conservative edge assumptions. Mode4 provides unfiltered timing comparison in same image.',
        not_proven=['Primary physical cause of original PWM errors','That all NACK/ARLO disappear','Actual bus rise/fall times or independent sensor accuracy'],
        installed_unchanged=True,motor_start_commands=0,clear_commands=0)
    u.write(out/'cause_evidence.json',json.dumps(evidence,indent=2)+'\n')
    names=('offline-checks.json','cause_evidence.json','host-contract-checks.json')
    assert json.loads(u.read(out/'host-contract-checks.json'))['passed']
    m.update(built=True,selftest_pass=True,
        build_sha256={str(x.relative_to(out)).replace('\\','/'):u.sha(x) for x in (out/'build/uno').iterdir() if x.is_file()},
        verification_sha256={name:u.sha(out/name) for name in names},
        flash_artifact_sha256=u.sha(out/'build/uno'/b['flash_artifact']),
        programming_state_required='J1OFF, independent meter<20V, Uno USB toPC. Nucleo may stay on powerbank,15V may stay ON; motor/wiring unchanged.')
    u.write(out/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(passed=True,installed=False,sha256=m['flash_artifact_sha256'])))
if __name__=='__main__':main()
