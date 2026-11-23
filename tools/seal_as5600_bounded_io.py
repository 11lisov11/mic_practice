"""Seal tested Uno2516 package without touching any connected board."""
import json
import ast
import prepare_as5600_bounded_io as p
import prepare_current_shunt_monitor as u

def main():
    out=p.OUT;m=json.loads(u.read(out/'manifest.json'))
    assert not m['installed'] and m['pair_compatibility_ids']==[2026102516,2026102510]
    m['source_sha256']={rel:digest for rel,digest in m['source_sha256'].items()
        if '__pycache__' not in rel.split('/') and not rel.endswith('.pyc')}
    for rel,digest in m['source_sha256'].items():assert u.sha(out/rel)==digest,rel
    assert json.loads(u.read(out/'offline-checks.json'))['passed']
    assert json.loads(u.read(out/'runner-selftest.json'))['passed']
    b=json.loads(u.read(out/'build/uno/unoq_mcsdk_scalar.build-manifest.json'))
    assert b['firmware_build_id']==2026102516
    for a in b['artifacts']:assert u.sha(out/'build/uno'/a['file'])==a['sha256'].lower()
    assert json.loads(u.read(out/'build/uno/llext-check.json'))['pass']
    ast.parse(u.read(out/'web_hmi/server.py'))
    provenance=dict(
        zephyr_v420_driver='https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/v4.2.0/drivers/i2c/i2c_ll_stm32_v2.c',
        zephyr_findings='500ms semaphore wait; NACK/ARLO/ERR/timeout combined into EIO. Source is upstreamv4.2.0, not a bit-identical reconstruction of installed vendor kernel.',
        device_read_protocol='https://cdn.sparkfun.com/assets/f/a/b/b/a/AS5600_Datasheet.pdf',
        protocol='Only volatile register-pointer0x0B then3-byte read at address0x36; no OTP/configuration writes.',
        observed='legacy_powered_5hz_r1:5errors,163successful reads in active snapshots,553464us maximum, unchanged PB10/PB11 config.',
        proven_software_defects=['Original host5s timer began after HTTP START response, delayed5.167s.',
            'MCU finite run completion latched ESTOP instead of normal STOP.',
            'Generic native I2C EIO and potentially long transfer give insufficient cause/freshness diagnostics.'],
        not_proven=['Root physical/electrical source of AS5600 errors','Guaranteed elimination of NACK under PWM',
            'Actual IGBT PWM-off exactly5000ms; new marks describe Uno dispatch and UART adds latency'],
        test_scope='Host fault injection and recorded telemetry; no powered test of2516 yet')
    u.write(out/'provenance.json',json.dumps(provenance,indent=2)+'\n')
    verification=['offline-checks.json','runner-selftest.json','recorded_replay.json','provenance.json']
    m.update(built=True,selftest_pass=True,hardware_validated=False,
        build_sha256={str(x.relative_to(out)).replace('\\','/'):u.sha(x) for x in (out/'build/uno').iterdir() if x.is_file()},
        verification_sha256={x:u.sha(out/x) for x in verification},
        tool_sha256={str(x.relative_to(p.ROOT)).replace('\\','/'):u.sha(x) for x in [
            p.ROOT/'tools/run_as5600_bounded_5hz.py',p.ROOT/'tools/install_as5600_bounded_io.py',
            p.ROOT/'tools/current_zero_quality.py',*p.RES.iterdir()] if x.is_file()},
        flash_artifact_sha256=u.sha(out/'build/uno'/b['flash_artifact']),
        programming_state_required='J1 OFF, independent DMM<20V, Uno USB to PC. Nucleo stays on powerbank;15V may remain. No START/CLEAR.',
        hardware_commands_this_preparation=0)
    u.write(out/'manifest.json',json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(passed=True,installed=False,hardware_validated=False,sha256=m['flash_artifact_sha256'])))

if __name__=='__main__':main()
