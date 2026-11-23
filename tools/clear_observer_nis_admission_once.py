"""Send one operator-authorized CLEAR on 2101/2102 with J1 OFF and USB attached."""
import json
import subprocess
import time
import urllib.error
import urllib.request

import build_observer_nis_admission_release as release
from clear_recovery_idle_once import disarmed
from install_bkin_boot_armed_pair import PROGRAMMER, STLINK_SERIAL, UNO_SERIAL, board_ports
from probe_low_bus_usb import off
from rpc_counter_guard import RpcCounterGuard
from run_foc_boot_capture_trial import decode_boot
from wifi_stop_tail_probe import parse_registers


OUT = release.OUT/'one_CLEAR_USB_r1'
UART = ('mc_transport_fault','bp_transport_fault','mc_uart_error_flags',
        'mc_last_uart_error_flags','mc_bad_cnt','mc_bad_integrity','mc_bad_sequence',
        'uno_rx_hw_errors','uno_rx_dropped')
FIELDS = (*UART,'mc_fault','bp_fault','mc_fault_current_mask','mc_fault_occurred_mask',
          'estop','algorithm_fault','mc_current_zero_ready','bp_vdc','pwm','run_id')


def direct_state(label):
    command = [str(PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+STLINK_SERIAL,
               '-r32','0x40012C0C','8','-r32','0x40012C44','4','-r32','0x48000010','4']
    read = subprocess.run(command, capture_output=True, text=True, timeout=20, errors='replace')
    release.write(OUT/f'SWD_{label}.log', read.stdout+read.stderr)
    read.check_returncode()
    regs = parse_registers(read.stdout)
    bdtr = regs[0x40012c44]
    return {'BKE':bool(bdtr&4096),'MOE':bool(bdtr&32768),
        'BIE':bool(regs[0x40012c0c]&128),'TIM1_SR':regs[0x40012c10],
        'PA6_HIGH':bool(regs[0x48000010]&64)}


def run():
    accepted = release.read_json(release.OUT/'installation_acceptance.json')
    assert accepted['pair']==list(release.NEW) and accepted['installed']
    assert accepted['native_readback_verified'] and accepted['uno_readback_verified']
    preserved = release.read_json(release.OUT/'preserved_inputs_sha256.json')
    for folder in ('hardware_install_r1','post_install_idle_r1','post_install_link_observation_r1'):
        for path in (release.OUT/folder).rglob('*'):
            if path.is_file():
                preserved[path.relative_to(release.ROOT).as_posix()] = release.digest(path)
    release.verify_inventory(preserved, release.ROOT)
    ports = board_ports()
    subprocess.run(['adb','-s',UNO_SERIAL,'get-state'],check=True,capture_output=True,timeout=8)
    OUT.mkdir()  # A second invocation cannot enter the command path.
    report = {'CLEAR':0,'START':0,'ARM':0,'RESET':0,'flash':0,'thresholds_changed':False,
              'operator_confirmed_J1_OFF':True,'ports':ports,'passed':False}
    path = OUT/'report.json'
    def checkpoint():
        release.write(path, json.dumps(report,indent=2)+'\n')

    token = release.read(release.ROOT/'.unoq_ssh/control_token').strip()
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(route, *, clear=False):
        assert not clear or route=='/api/cmd' and report['CLEAR']==1
        req = urllib.request.Request('http://127.0.0.1:18080'+route,
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},
            data=b'{"cmd":"CLEAR"}' if clear else None, method='POST' if clear else 'GET')
        with op.open(req,timeout=8) as response:
            return json.load(response)

    def get(route):
        payload = request(route)
        assert payload['ok'], payload.get('error')
        return payload['data']

    def status():
        state = get('/api/status')
        off(state,release.NEW)
        assert disarmed(state) and state.get('rpc_route_failures')==0
        return state

    guard = RpcCounterGuard(lambda s,**kw:decode_boot(s,release.NEW,**kw))
    checkpoint()
    try:
        release.save(OUT/'preserved_before_sha256.json',preserved)
        native = direct_state('before')
        assert native['BKE'] and not native['MOE'] and native['PA6_HIGH']
        report['native_before']=native
        before = status()
        assert before.get('clear_recovery',{}).get('available') is False
        assert before['mc_sd_live']['level']=='HIGH' and before['mc_sd_live']['config_ok']
        assert before['mc_transport_fault']==4 and before['mc_uart_error_flags']==2
        release.save(OUT/'before.json',before)
        for name,route in (('SD_before','/api/break-snapshot'),('SD_trace_before','/api/bkin-trace'),
                           ('UART_reject_before','/api/uart-reject')):
            release.save(OUT/f'{name}.json',get(route))
        wave = before.get('mc_break_wave_hex','-')
        if wave not in ('','-'):
            (OUT/'SD_first.bin').write_bytes(bytes.fromhex(wave))
        uart_hex = before.get('mc_uart_reject_hex','-')
        if uart_hex not in ('','-'):
            (OUT/'UART_reject.bin').write_bytes(bytes.fromhex(uart_hex))
        assert before['mc_adc_peak_complete']==before['mc_observer_trace_complete']==0

        preclear = []
        for _ in range(8):
            s=status(); preclear.append(s)
            assert all(s[k]==before[k] for k in UART), 'UART state changed during observation'
            assert s['mc_sd_live']['level']=='HIGH' and s.get('mc_break_wave_hex','-')==wave
            assert guard.observe(s),guard.failure
            if guard.ready:
                break
            time.sleep(.3)
        release.save(OUT/'before_samples.json',preclear)
        assert guard.ready and not preclear[-1]['clear_recovery'].get('available')
        report['before']={k:preclear[-1].get(k) for k in FIELDS}
        report['CLEAR']=1
        checkpoint()  # Durable intent. A timeout never issues another POST.
        try:
            reply=request('/api/cmd',clear=True)
            release.save(OUT/'CLEAR_response.json',reply)
            report['CLEAR_HTTP_acknowledged']=reply.get('ok') is True
        except (OSError,ValueError) as error:
            report['CLEAR_response_error']=repr(error)
        checkpoint()

        samples=[]
        with (OUT/'after_samples.jsonl').open('x',encoding='utf8') as stream:
            for _ in range(16):
                s=status();samples.append(s)
                stream.write(json.dumps(s)+'\n');stream.flush()
                assert s.get('mc_break_wave_hex','-')==wave, 'Saved SD snapshot changed'
                guard.observe(s)  # Observe even if the reply shows a protection remains latched.
                time.sleep(.35)
        last=samples[-1]
        release.save(OUT/'after.json',last)
        for name,route in (('SD_after','/api/break-snapshot'),('SD_trace_after','/api/bkin-trace'),
                           ('repeat_Break_after','/api/repeat-break')):
            release.save(OUT/f'{name}.json',get(route))
        state=direct_state('after'); stable=samples[-4:]
        transport=all(all(s[k]==0 for k in UART) for s in stable)
        diag=last.get('clear_recovery',{})
        break_ok=(state['BKE'] and not state['MOE'] and state['BIE'] and state['PA6_HIGH']
                  and all(s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['break_irq_enabled']
                          and s['mc_sd_live']['config_ok'] for s in stable))
        report.update(native_after=state,UART_latch_cleared=transport,Break_ready=break_ok,
            clear_recovery=diag,qualified_for_start=False,
            after={k:last.get(k) for k in FIELDS},post_samples=len(samples),
            first_SD_retained=True,RPC_stable=guard.ready,
            passed=transport and break_ok and guard.ready and diag.get('result_code')==1)
    except Exception as error:
        report['error']=repr(error)
    finally:
        release.verify_inventory(preserved,release.ROOT)
        report['preserved_files_verified']=len(preserved)
        report['RPC_guard']=guard.snapshot()
        checkpoint()
        release.save(OUT/'sha256.json',{file.name:release.digest(file) for file in OUT.iterdir() if file.is_file()})
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(run())
