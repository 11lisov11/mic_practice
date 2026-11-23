"""Prepare versioned working and detached-test pairs from the audited 1205/1204 source."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

from prepare_ipm_break_wifi import source_hashes
from prepare_mcsdk_logic_bench import FIXTURE_STATE, BENCH_BUS_READY, replace_once, function_span
from prepare_local_stop_pwm_fixture import fixture_server

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'artifacts/live_bench_20261012/local_button'
AUDIT=ROOT/'artifacts/live_bench_20261014/pwm_filter_audit_r6'
HMI=ROOT/'artifacts/live_bench_20261014/passive_decoder/candidate_r1/web_hmi/server.py'
PROD_PAIR=(2026101405,2026101404)
FIXTURE_PAIR=(2026101498,2026101499)
VF='MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/acim_vf_control.c'
PWM='MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c'
FINITE_HELPER='''/* Integer classification survives the project's -Ofast finite-math assumptions. */
static bool mic_float_isfinite(float value)
{
  uint32_t bits;
  memcpy(&bits, &value, sizeof(bits));
  return (bits & 0x7f800000U) != 0x7f800000U;
}
'''


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,text):path.write_text(text,encoding='utf-8',newline='\n')


def change(path,old,new):write(path,replace_once(path.read_text(encoding='utf-8-sig'),old,new))


def prepare(out):
    n=HERE/'candidate_r5/nucleo';u=HERE/'uno_peer_r2/UNOQ_MOTOR'
    before_n,before_u=source_hashes(n),source_hashes(u)
    if before_n!=json.loads((HERE/'candidate_r5/manifest.json').read_text())['candidate_sha256']:
        raise RuntimeError('Frozen Nucleo source changed')
    if before_u!=json.loads((HERE/'uno_peer_r2/manifest.json').read_text())['source_sha256']:
        raise RuntimeError('Frozen Uno source changed')
    audit=json.loads((AUDIT/'report.json').read_text());proof=json.loads((AUDIT/'verification.json').read_text())
    if not audit['pass'] or not proof['pass']:raise RuntimeError('Audited fixes not qualified offline')
    for path,digest in proof['evidence_sha256'].items():
        if sha(AUDIT/path)!=digest:raise RuntimeError('Audited evidence changed: '+path)
    if sha(HMI)!='992b3c20c8573681f195de3a208a461359c22673b83e3f2d578f87e16ce212d1':
        raise RuntimeError('Installed HMI source changed')
    out.mkdir(parents=True,exist_ok=False)
    prod=out/'production';fixture=out/'fixture'
    shutil.copytree(n,prod/'nucleo',ignore=shutil.ignore_patterns('Debug','Release','.metadata'))
    shutil.copytree(u,prod/'UNOQ_MOTOR')
    for relative in audit['candidate_modified_files']:
        shutil.copy2(AUDIT/'candidate_unflashed'/relative,prod/'nucleo'/relative)
    for relative in (PWM,VF):
        path=prod/'nucleo'/relative
        text=path.read_text(encoding='utf-8-sig')
        text=replace_once(text,'#include <math.h>','#include <string.h>\n'+FINITE_HELPER)
        text=text.replace('!isfinite(', '!mic_float_isfinite(')
        write(path,text)
    change(prod/'nucleo/Src/main.c','MIC_NUCLEO_FW_BUILD_ID 2026101204UL','MIC_NUCLEO_FW_BUILD_ID 2026101404UL')
    change(prod/'nucleo/Inc/break_wire.h','BW_NUCLEO_BUILD 2026101204UL','BW_NUCLEO_BUILD 2026101404UL')
    change(prod/'UNOQ_MOTOR/UNOQ_MOTOR.ino','FW_BUILD_ID = 2026101205U','FW_BUILD_ID = 2026101405U')
    change(prod/'UNOQ_MOTOR/break_wire.h','BW_NUCLEO_BUILD 2026101204UL','BW_NUCLEO_BUILD 2026101404UL')
    change(prod/'UNOQ_MOTOR/nucleo_fault_diagnostics.h','build == 2026101204U;',
        'build == 2026101204U || build == 2026101404U;')
    web=HMI.read_text(encoding='utf-8')
    web=replace_once(web,'peer not in (2026101102, 2026101204)',
        'peer not in (2026101102, 2026101204, 2026101404, 2026101499)')
    node=next(n for n in ast.parse(web).body if isinstance(n,ast.FunctionDef) and n.name=='hv_arm_precheck')
    lines=web.splitlines(keepends=True);old_function=''.join(lines[node.lineno-1:node.end_lineno])
    new_function=replace_once(old_function,'    calibration_ready = VBUS_HV_CALIBRATION_VALID if vbus_calibrated is None else bool(vbus_calibrated)',
        '    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) in (2026101404, 2026101499):\n'
        '        return False, "PWM/filter update awaits new calibration and physical qualification"\n'
        '    calibration_ready = VBUS_HV_CALIBRATION_VALID if vbus_calibrated is None else bool(vbus_calibrated)')
    web=replace_once(web,old_function,new_function)
    (prod/'web_hmi').mkdir();write(prod/'web_hmi/server.py',web)
    # Do not extend the old calibration identity whitelist: the IIR DC bias changed.
    shutil.copytree(prod/'nucleo',fixture/'nucleo')
    shutil.copytree(prod/'UNOQ_MOTOR',fixture/'UNOQ_MOTOR')
    main=fixture/'nucleo/Src/main.c'
    change(main,'MIC_NUCLEO_FW_BUILD_ID 2026101404UL','MIC_NUCLEO_FW_BUILD_ID 2026101499UL')
    change(main,'static void uno_link_init(void);','static void uno_link_init(void);\nbool mic_logic_bench_bus_ready(void);')
    text=main.read_text();a,b=function_span(text,'uno_update_softstart_state');write(main,text[:a]+BENCH_BUS_READY+text[b:])
    change(main,'      ((uint32_t)MOTOR_MAX_SPEED_RPM * (uint32_t)POLE_PAIR_NUM * 1000U) / 60U;',
        '      5000U; /* Detached fixture: no command above 5 Hz. */')
    tasks=fixture/'nucleo/Src/mc_tasks.c'
    state=FIXTURE_STATE.replace('>= 15000U','>= 3000U').replace('15 s','3 s')
    change(tasks,'__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)',state+'\n__weak void TSK_SafetyTask_PWMOFF(uint8_t bMotor)')
    anchor='CodeReturn |= errMask[bMotor] & RVBS_CalcAvVbus(&BusVoltageSensor_M1, rawValueM1);'
    change(tasks,anchor,anchor+'\n    CodeReturn = mic_logic_bench_observe_bus(rawValueM1, CodeReturn);')
    change(fixture/'nucleo'/VF,'uint16_t hVbus_V = VBS_GetAvBusVoltage_V(pBVS);',
        '/* DETACHED FIXTURE ONLY: ADC telemetry remains real; not a motor image. */\n'
        '  (void)pBVS;\n  uint16_t hVbus_V = 310U;')
    change(fixture/'nucleo/Inc/break_wire.h','BW_NUCLEO_BUILD 2026101404UL','BW_NUCLEO_BUILD 2026101499UL')
    change(fixture/'UNOQ_MOTOR/UNOQ_MOTOR.ino','FW_BUILD_ID = 2026101405U','FW_BUILD_ID = 2026101498U')
    change(fixture/'UNOQ_MOTOR/break_wire.h','BW_NUCLEO_BUILD 2026101404UL','BW_NUCLEO_BUILD 2026101499UL')
    change(fixture/'UNOQ_MOTOR/nucleo_fault_diagnostics.h','build == 2026101404U;',
        'build == 2026101404U || build == 2026101499U;')
    fweb=fixture_server(web).replace('(2026101298, 2026101299)','(2026101498, 2026101499)')
    (fixture/'web_hmi').mkdir();write(fixture/'web_hmi/server.py',fweb)
    for package,pair in ((prod,PROD_PAIR),(fixture,FIXTURE_PAIR)):
        if (package/'nucleo/Inc/break_wire.h').read_bytes()!=(package/'UNOQ_MOTOR/break_wire.h').read_bytes():
            raise RuntimeError('Wire peers differ')
        report=dict(schema='mic_ai.pwm_filter_pair.v1',pair=list(pair),
            nucleo_source_sha256=source_hashes(package/'nucleo'),uno_source_sha256=source_hashes(package/'UNOQ_MOTOR'),
            hmi_sha256=sha(package/'web_hmi/server.py'),detached_fixture=(package==fixture),
            hardware_commands=0,installed=False,hv_release_approved=False,
            original_vbus_calibration_transfer_allowed=False,patch_evidence_sha256=sha(AUDIT/'verification.json'))
        (package/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    if source_hashes(n)!=before_n or source_hashes(u)!=before_u:raise RuntimeError('Baseline modified')
    summary=dict(production_pair=PROD_PAIR,fixture_pair=FIXTURE_PAIR,hardware_commands=0,
        source_baselines_unchanged=True,hv_release_approved=False)
    (out/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',required=True,type=Path)
    a=p.parse_args();print(json.dumps(prepare(a.outdir.resolve()),indent=2))
