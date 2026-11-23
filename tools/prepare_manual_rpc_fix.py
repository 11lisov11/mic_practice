"""Preserve the installed motor image; correct the actual Uno RouterBridge status path."""
import json
import shutil
from pathlib import Path
from prepare_ipm_break_wifi import source_hashes
from prepare_pwm_filter_pair import sha, write
from manual_scalar_sources import replace

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/live_bench_20261015/manual_scalar_working_pair_r1'
OUT = ROOT / 'artifacts/live_bench_20261015/manual_scalar_working_pair_r2'

def prepare():
    old = json.loads((BASE / 'manifest.json').read_text())
    assert old['installed'] and old['pair'] == [2026101501, 2026101502]
    assert not (OUT / 'manifest.json').exists(), 'Do not overwrite a prepared or installed bundle'
    OUT.mkdir(parents=True, exist_ok=True)
    for tree in ('nucleo', 'UNOQ_MOTOR', 'web_hmi'):
        shutil.copytree(BASE / tree, OUT / tree, ignore=shutil.ignore_patterns('__pycache__'))
    f = OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    s = replace(f.read_text(), 'FW_BUILD_ID = 2026101501U', 'FW_BUILD_ID = 2026101503U')
    helper = '''static String manual_status_fields(uint32_t bp_age) {
  String s;
  s.reserve(256);
  s += " manual_scalar_capable=1";
  s += " manual_run_mode="; s += String(g_manual_scalar_mode ? 1 : 0);
  s += " accel_hz_per_s="; s += format_fixed(g_manual_accel_centi*0.01f, 2);
  s += " decel_hz_per_s="; s += format_fixed(g_manual_decel_centi*0.01f, 2);
  s += " downmode_coast="; s += String(g_manual_coast_down ? 1 : 0);
  s += " mc_frequency_reference_hz="; s += format_fixed(g_manual_reference_hz, 2);
  s += " mc_frequency_reference_valid="; s += String(g_manual_reference_valid && bp_age < 300U ? 1 : 0);
  s += " mc_decel_bus_hold="; s += String(g_manual_bus_hold ? 1 : 0);
  return s;
}

'''
    s = replace(s, 'static String rpc_get() {', helper + 'static String rpc_get() {')
    s = replace(s, '  const unsigned int timing_done_key = irq_lock();',
                '  s += manual_status_fields(bp_age);\n  const unsigned int timing_done_key = irq_lock();')
    write(f, s)
    f = OUT / 'web_hmi/server.py'
    s = f.read_text()
    s = replace(s, '(2026101501, 2026101502),', '(2026101501, 2026101502),\n        (2026101503, 2026101502),')
    s = replace(s, '"fw_build", -1) != 2026101501:', '"fw_build", -1) != 2026101503:')
    s = replace(s, '"fw_build",0)==2026101501', '"fw_build",0)==2026101503')
    helper = '''def manual_status_reference(data):
    if (manual_scalar_supported(data) and _as_int(data,"mc_frequency_reference_valid",0)==1
            and 0 <= _as_int(data,"bp_age_ms",999999) < 300):
        data["local_ramp_reference_hz"]=data["freq"]
        data["freq"]=data["mc_frequency_reference_hz"]
        data["speed"]=data["freq"]*60.0  # electrical reference, not measured rotor RPM
    return data

'''
    s = replace(s, 'class HvArmState:', helper + 'class HvArmState:')
    start = s.index('    def _parse_status_string(')
    end = s.index('\n\nclass AppState:', start)
    block = s[start:end]
    block = replace(block, 'return with_motor_controller_aliases({', 'return with_motor_controller_aliases(manual_status_reference({')
    block = replace(block, '                "ts": int(_now_ts() * 1000.0),', '''                **{key: int(kv[key]) for key in ("manual_scalar_capable", "manual_run_mode",
                    "downmode_coast", "mc_frequency_reference_valid", "mc_decel_bus_hold") if key in kv},
                **{key: float(kv[key]) for key in ("accel_hz_per_s", "decel_hz_per_s",
                    "mc_frequency_reference_hz") if key in kv},
                "ts": int(_now_ts() * 1000.0),''')
    block = replace(block, '            })\n        except Exception:', '            }))\n        except Exception:')
    s = s[:start] + block + s[end:]
    compile(s, str(f), 'exec')
    write(f, s)
    mf = dict(old, pair=[2026101503,2026101502], predecessor_pair=old['pair'],
        predecessor_candidate=str(BASE), installed=False, source_only=True, qualification_pending=True,
        uno_source_sha256=source_hashes(OUT/'UNOQ_MOTOR'), hmi_sha256=sha(f),
        reuse_identical_nucleo_image=True, routerbridge_manual_status_fixed=True)
    assert source_hashes(OUT/'nucleo') == old['nucleo_source_sha256']
    # Static assets are unchanged; their existing real-browser qualification remains applicable.
    shutil.copyfile(BASE/'browser_qualification.json', OUT/'browser_qualification.json')
    write(OUT/'manifest.json',json.dumps(mf,indent=2)+'\n')
    print(json.dumps({'prepared':str(OUT),'pair':mf['pair'],'nucleo_rewrite_needed':False}))

if __name__=='__main__': prepare()
