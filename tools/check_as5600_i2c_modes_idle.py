"""Compare sensor transports with PWM OFF and J1 OFF; never send drive commands."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def guard(s, uno_build=2026102513):
    return (uno_build in (2026102513,2026102515)
            and s.get('fw_build') == uno_build and s.get('mc_fw_build') == 2026102510
            and s.get('state') == 'SAFE' and s.get('pwm') == 0
            and s.get('hmi_hv_armed') == 0 and s.get('bp_mcsdk_telemetry') == 1
            and s.get('bp_vbus_valid') == 1
            and type(s.get('vdc')) in (int, float) and 0 <= s['vdc'] <= 20
            and type(s.get('bp_age_ms')) in (int, float) and 0 <= s['bp_age_ms'] < 300
            and s.get('bp_status', 0x20) & 0x20 == 0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-off-meter-below-20v', action='store_true')
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--seconds-per-mode', type=int, choices=range(3, 31), default=5)
    p.add_argument('--uno-build', type=int, choices=(2026102513,2026102515), default=2026102513)
    a = p.parse_args()
    plan = ((0,'HW100'),(3,'LEGACY'),(1,'SW100')) if a.uno_build == 2026102515 else ((0,'HW100'),(1,'SW100'),(2,'SW25'))
    restore = ('LEGACY',3) if a.uno_build == 2026102515 else ('HW100',0)
    if not a.confirm_j1_off_meter_below_20v:
        p.error('J1 off, DMM below20V required; this script is not a powered run')
    out = a.outdir.resolve(); out.mkdir(parents=True, exist_ok=False)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = (ROOT / '.unoq_ssh/control_token').read_text().strip()
    base = 'http://127.0.0.1:18080'
    r = dict(passed=False, motor_commands=0, clear_commands=0, firmware_writes=0,
             commands=[], modes=[], transport='USB offline diagnostic; not WiFi powered qualification')

    def status():
        with opener.open(base + '/api/status', timeout=8) as resp:
            p = json.load(resp)
        assert p.get('ok') is True and isinstance(p.get('data'), dict), 'No live status'
        s = p['data']; assert guard(s,a.uno_build), 'Offline programming/PWM OFF state changed'
        with (out / 'status.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(dict(host_monotonic_s=time.monotonic(), status=s)) + '\n')
        return s

    def command(mode):
        assert mode in dict((name,mode) for mode,name in plan)
        status()  # Fresh independent OFF check before every mode request.
        record = dict(command='ENC BUS ' + mode, sent=False)
        r['commands'].append(record)
        (out / 'report.json').write_text(json.dumps(r, indent=2) + '\n')
        request = urllib.request.Request(base + '/api/cmd', method='POST',
                    data=json.dumps({'cmd': record['command']}).encode(),
                    headers={'Content-Type': 'application/json', 'X-UNOQ-Control-Token': token})
        record['sent'] = True
        with opener.open(request, timeout=8) as resp:
            result = json.load(resp)
        assert result.get('ok') is True, 'Mode rejected: ' + str(result)
        record['accepted'] = True

    def stable_mode(mode):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            s = status()
            if s.get('enc_diag_mode') == mode and s.get('enc_diag_epoch', 0) > 0:
                return s
            time.sleep(.2)
        raise RuntimeError('Requested mode did not become active')

    try:
        r['before'] = status()
        for mode, name in plan:
            command(name)
            first = stable_mode(mode); samples = [first]
            until = time.monotonic() + a.seconds_per_mode
            while time.monotonic() < until:
                time.sleep(.4); samples.append(status())
            last = samples[-1]
            assert all(s['enc_diag_mode'] == mode and s['enc_init_error'] == 0 for s in samples)
            if a.uno_build == 2026102515:
                assert all(s['enc_diag_thread_priority'] == (14 if mode == 3 else 4)
                           and s['enc_diag_cfg_match'] == 1 for s in samples)
                assert all((s['enc_diag_cfg_before'] & 15) == (10 if mode in (0,3) else 5)
                           and ((s['enc_diag_cfg_before'] >> 4) & 3) == 3 for s in samples)
                if mode == 1:
                    assert all(s['enc_diag_tx_bits'] == 8
                               and s['enc_diag_tx_byte'] == s['enc_diag_tx_echo'] == 0x6d for s in samples)
            reads = last['enc_reads'] - first['enc_reads']
            errors = last['enc_errors'] - first['enc_errors']
            r['modes'].append(dict(name=name, epoch=first['enc_diag_epoch'],
                 successful_reads=reads, errors=errors,
                 observed_statuses=sorted({s['enc_status'] for s in samples}),
                 current_causes=sorted({s['enc_diag_cause'] for s in samples}),
                 last_error_causes=sorted({s['enc_diag_last_cause'] for s in samples}),
                 duration_us_max=max(s['enc_diag_us'] for s in samples),
                 thread_priority=last.get('enc_diag_thread_priority'),
                 pin_config=last.get('enc_diag_cfg_before'),
                 pin_config_match=last.get('enc_diag_cfg_match'),
                 tx_byte=last.get('enc_diag_tx_byte'),tx_echo=last.get('enc_diag_tx_echo'),
                 init_error=last['enc_init_error'],
                 idle_transfer_pass=reads > 0 and errors == 0))
        r['passed'] = all(m['idle_transfer_pass'] for m in r['modes'])
    except Exception as e:
        r['error'] = str(e)
    finally:
        try:
            command(restore[0]); r['after'] = stable_mode(restore[1])
            r['native_default_restored'] = True
            r['selected_final_mode'] = restore[0]
            # A first capture may arrive during the test: preserve and report it.
            old = r.get('before', {}).get('mc_break_wave_hex', '-')
            new = r['after'].get('mc_break_wave_hex', '-')
            r['sd_wave_unchanged'] = old == new
            r['sd_before_sha256'] = hashlib.sha256(bytes.fromhex(old)).hexdigest() if old != '-' else None
            r['sd_after_sha256'] = hashlib.sha256(bytes.fromhex(new)).hexdigest() if new != '-' else None
        except Exception as e:
            r['passed'] = False; r['restore_error'] = str(e)
        (out / 'report.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k:r.get(k) for k in ('passed', 'modes', 'native_default_restored', 'error', 'restore_error')}))
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
