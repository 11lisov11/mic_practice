"""Correct scheduling of the existing3ms reader; no timeout/guard relaxation."""
import json
import shutil
import prepare_current_shunt_monitor as u
ROOT=u.ROOT
BASE=ROOT/'artifacts/live_bench_20261025/as5600_bounded_io_r1'
OUT=ROOT/'artifacts/live_bench_20261025/as5600_poll_schedule_r1'
RES=ROOT/'tools/as5600_poll_schedule'
FIELDS=('sched_sections','sched_max_hold_us')
def main():
    if (OUT/'manifest.json').exists():
        old=json.loads(u.read(OUT/'manifest.json'));assert not old['built'] and not old['installed']
    m=json.loads(u.read(BASE/'manifest.json'));assert m['installed'] and m['installation_runtime_pair_verified']
    for rel,digest in m['source_sha256'].items():assert u.sha(BASE/rel)==digest,rel
    for tree in ('UNOQ_MOTOR','web_hmi'):
        shutil.copytree(BASE/tree,OUT/tree,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    sk=OUT/'UNOQ_MOTOR';shutil.copyfile(RES/'section.h',sk/'as5600_poll_section.h')
    p=sk/'as5600_teacher.cpp';s=u.read(p)
    s=u.once(s,'#include "as5600_poll_reader.h"','#include "as5600_poll_reader.h"\n#include "as5600_poll_section.h"')
    s=u.once(s,'  uint32_t waits=0;','')
    s=u.once(s,'  void wait_step() {k_busy_wait(1);if((++waits&31U)==0)k_yield();}',
        '  void wait_step() {k_busy_wait(1);}')
    s=u.once(s,'struct PollIo {','struct PollSchedule {\n  static void lock(){k_sched_lock();}\n  static void unlock(){k_sched_unlock();}\n};\nstruct PollIo {')
    s=u.once(s,'  uint32_t resets=0,timeouts=0,nacks=0,last_isr=0;',
        '  uint32_t resets=0,timeouts=0,nacks=0,last_isr=0;\n  uint32_t sections=0,max_hold_us=0;')
    s=u.once(s,'      const auto result=poll.read(bytes); diag=result.transfer; isr=result.error_isr;',
        '      const auto result=encdiag::scheduled_read<PollSchedule>(poll,bytes);\n'
        '      if(sections!=UINT32_MAX)++sections;\n'
        '      if(result.transfer.duration_us>max_hold_us)max_hold_us=result.transfer.duration_us;\n'
        '      diag=result.transfer; isr=result.error_isr;')
    s=u.once(s,'    sample.diag_isr=isr;',
        '    sample.diag_sched_sections=sections;sample.diag_sched_max_hold_us=max_hold_us;\n    sample.diag_isr=isr;')
    u.write(p,s)
    p=sk/'as5600_teacher.h';s=u.read(p)
    s=u.once(s,'  float rpm = 0.0f;','  float rpm = 0.0f;\n'+''.join(f'  uint32_t diag_{f}=0;\n' for f in FIELDS).rstrip());u.write(p,s)
    p=sk/'UNOQ_MOTOR.ino';s=u.read(p)
    s=u.once(s,'FW_BUILD_ID = 2026102516U;','FW_BUILD_ID = 2026102517U;')
    anchor='    s += " enc_diag_mode="; s += String((unsigned long)g_as5600.diag_mode);'
    s=u.once(s,anchor,anchor+'\n'+''.join(f'    s += " enc_diag_{f}="; s += String((unsigned long)g_as5600.diag_{f});\n' for f in FIELDS).rstrip());u.write(p,s)
    p=OUT/'web_hmi/server.py';s=u.read(p)
    # Lists accept both known identities; the completion predicate remains a
    # narrow pair-membership test rather than turning into a truthy tuple.
    s=u.once(s,"if (data.get('fw_build'),data.get('mc_fw_build'))!=(2026102516,2026102510):",
        "if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102516,2026102510),(2026102517,2026102510)):")
    for a,b in [('(2026102516, 2026102510)','(2026102516, 2026102510), (2026102517, 2026102510)'),
                ('(2026102516,2026102510)','(2026102516,2026102510),(2026102517,2026102510)')]:
        # Completion predicate was already expanded explicitly above.
        lines=[]
        for line in s.splitlines(keepends=True):
            if "if (data.get('fw_build'),data.get('mc_fw_build')) not in ((2026102516,2026102510),(2026102517,2026102510)):" not in line:line=line.replace(a,b)
            lines.append(line)
        s=''.join(lines)
    anchor='                "enc_diag_mode": int(float(kv.get("enc_diag_mode", "0"))),'
    s=u.once(s,anchor,anchor+'\n'+''.join(f'                "enc_diag_{f}": int(kv.get("enc_diag_{f}", "0")),\n' for f in FIELDS).rstrip());u.write(p,s)
    (OUT/'build/uno').mkdir(parents=True,exist_ok=True)
    manifest=dict(schema='mic_ai.as5600_poll_schedule.v1',predecessor=str(BASE),pair_compatibility_ids=[2026102517,2026102510],
        built=False,selftest_pass=False,installed=False,hardware_validated=False,uno_only=True,nucleo_firmware_unchanged=True,
        calibration_changed=False,thresholds_changed=False,sd_capture_changed=False,uart_protocol_changed=False,motor_control_changed=False,
        sensor_feedback_control=False,calibration_sha256=m['calibration_sha256'],
        change='No yield within3ms bounded I2C transaction; scheduler RAII scope only around poll.read, all IRQs remain enabled; sleep between reads retained.',
        bound='Normally~0.55ms; stuck-bus CPU wait3ms plus ISR/constant bookkeeping. Does not bound arbitrarily long ISR execution.',
        source_sha256={str(x.relative_to(OUT)).replace('\\','/'):u.sha(x) for tree in ('UNOQ_MOTOR','web_hmi') for x in (OUT/tree).rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc'})
    u.write(OUT/'manifest.json',json.dumps(manifest,indent=2)+'\n');print(OUT)
if __name__=='__main__':main()
