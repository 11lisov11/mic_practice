"""Bounded zero-bus Saleae tests derived from current MCSDK; always restore 707."""
import argparse
import json
from pathlib import Path
import time

from saleae import automation
from prepare_mcsdk_logic_bench import BENCH_BUILD
from run_mcsdk_logic_bench import compare_code_sections, waveform, off_tail, PROGRAMMER, SERIAL, DEVICE
from run_wifi_nucleo_pwm_bench import WifiHmi, wait_status, verify_unpowered_preflash, read_control_token, run_logged, sha256, capture, analyze_static
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import outputs_off, operator_keepalive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--production',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--confirm-zero-bus-j4-off',action='store_true')
    args=p.parse_args()
    if not args.confirm_zero_bus_j4_off:
        p.error('physically unpowered power stage and J4 required')
    root=Path(__file__).resolve().parents[1]
    out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    logs=out/'logs'; logs.mkdir()
    production=args.production.resolve(); production_bin=production.with_suffix('.bin')
    bench_build=args.fixture.resolve()/'project/STM32CubeIDE/Debug'
    bench=bench_build/production.name
    real_build=root/'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/STM32CubeIDE/Debug'
    manifest=json.loads(production.with_suffix('.build-manifest.json').read_text(encoding='utf-8-sig'))
    if manifest['firmware_build_id']!=2026100707: raise RuntimeError('wrong restore build')
    hashes={e['file']:e['sha256'].lower() for e in manifest['artifacts']}
    for image in (production,production_bin):
        if sha256(image)!=hashes[image.name]: raise RuntimeError('restore image hash mismatch')
    report={'pass':False,'restored':False,'commands':[],
            'scope':'current production-derived zero-bus fixture, not energized inverter acceptance',
            'production_active_pwm_tested':False,'uno_build':2026100707,'nucleo_restore_build':2026100707,
            'fixture_build':BENCH_BUILD,'images':{'production':sha256(production),'fixture':sha256(bench)},'cases':{}}
    token=read_control_token('adb','3880458060','/home/arduino/.config/mic-ai/control_token')
    h=WifiHmi('http://192.168.1.138:8080',token,report['commands'],via_wsl=True)
    modified=False

    def cli(extra,name):
        run_logged([PROGRAMMER,'-c','port=SWD','mode=UR','reset=HWrst','sn='+SERIAL,*extra],logs/name,timeout=60)

    def clean():
        h.fail_safe_stop()
        wait_status(h,lambda s: outputs_off(s) and s.get('mc_fw_build')==BENCH_BUILD
                    and s.get('bp_softstart_ready')==1 and s.get('vdc')==0,15,'fresh fixture zero bus')
        h.command('CLEAR')
        return wait_status(h,lambda s:outputs_off(s) and s.get('bp_fault')==0 and s.get('estop')==0
                           and s.get('bp_bad_cnt')==0 and s.get('bp_bad')==0,8,'fault-free fixture')

    try:
        report['before']=h.status(); verify_unpowered_preflash(report['before'])
        if report['before']['fw_build']!=2026100707 or report['before']['mc_fw_build']!=2026100707:
            raise RuntimeError('installed pair does not match current sources')
        report['code_equivalence']=compare_code_sections(real_build,bench_build,out/'code_equivalence')
        if not report['code_equivalence']['pass']: raise RuntimeError('PWM code not equivalent')
        with automation.Manager.connect(port=10430) as manager:
            if not any(d.device_id==DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError('physical analyzer absent')
            report['before_capture']=analyze_static(capture(manager,DEVICE,out/'before',.1,24_000_000),settle_s=.002,sample_rate_hz=24_000_000)
            if not report['before_capture']['pass']: raise RuntimeError('outputs not LOW before fixture')
            verify_unpowered_preflash(h.status())
            modified=True
            cli(['-w',str(bench),'-v','-rst'],'flash_fixture.log')
            clean(); h.post('/api/arm-profile',{'profile':'lv'},'zero-bus LV profile')
            with operator_keepalive(h) as heartbeat:
                clean(); h.command('MODE VF'); h.command('SET FREQ 5')
                h.post('/api/hv-arm',{'action':'arm','confirm':'ARM LV HV OFF'},'high-resolution zero-bus ARM')
                h.post('/api/start-sequence',{},'Wi-Fi high-resolution START')
                wait_status(h,lambda s:s.get('pwm')==1 and s.get('bp_status',0)&0x20,2,'high-resolution PWM')
                high_csv=capture(manager,DEVICE,out/'high_resolution',.12,24_000_000)
                report['high_resolution']=waveform(high_csv,24_000_000,16000,1.35e-6)
                h.fail_safe_stop()
                if not report['high_resolution']['pass']: raise RuntimeError('24 MHz carrier/deadtime failed')
                for label,freq in (('STOP',5),('ESTOP',20),('FREQ_ZERO',5),('RUNLIMIT',5)):
                    clean(); h.command('MODE VF'); h.command(f'SET FREQ {freq}')
                    h.post('/api/hv-arm',{'action':'arm','confirm':'ARM LV HV OFF'},'zero-bus ARM')
                    capture(manager,DEVICE,out/(label+'_flush'),.05,24_000_000)
                    folder=out/label; folder.mkdir()
                    entry={'commanded_frequency_hz':freq,'steady_frequency_proven':False,'sample_rate_hz':4_000_000}
                    report['cases'][label]=entry
                    with manager.start_capture(device_id=DEVICE,
                            device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(7)),digital_sample_rate=4_000_000),
                            capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=4))) as session:
                        time.sleep(.25)
                        h.post('/api/start-sequence',{},'Wi-Fi START '+label)
                        entry['active_status']=wait_status(h,lambda s:s.get('pwm')==1 and s.get('bp_status',0)&0x20,2,'fixture PWM active')
                        time.sleep(.4)
                        if label in ('STOP','ESTOP'):
                            h.post('/api/stop-sequence',{'emergency':label=='ESTOP'},'Wi-Fi '+label)
                        elif label=='FREQ_ZERO': h.command('SET FREQ 0')
                        else: h.command('SET RUNLIMIT 0.1')
                        entry['off_status']=wait_status(h,outputs_off,3,'six outputs commanded off')
                        if label=='FREQ_ZERO' and entry['off_status'].get('bp_fault')!=0:
                            raise RuntimeError('zero setpoint caused fault instead of STOP')
                        session.wait(); session.save_capture(str(folder/'capture.sal'))
                        session.export_raw_data_csv(directory=str(folder/'csv'),digital_channels=list(range(7)))
                    csv=folder/'csv/digital.csv'
                    entry['waveform']=waveform(csv,4_000_000,16000,1.35e-6,settled=False)
                    entry['off_tail']=off_tail(csv,4_000_000)
                    entry['pass']=entry['waveform']['pass'] and entry['off_tail']['pass']
                    if not entry['pass']: raise RuntimeError('physical PWM/stop check failed: '+label)
                    if heartbeat['errors']: raise RuntimeError('Wi-Fi heartbeat failed')
            report['pass']=report['high_resolution']['pass'] and all(e['pass'] for e in report['cases'].values()) and len(report['cases'])==4
    except BaseException as exc:
        report['error']=str(exc)
    finally:
        report['final_stop']=h.fail_safe_stop()[0]
        try:
            if modified:
                # Reset even after an aborted capture, then return the HMI profile
                # while the fixture can acknowledge its zero-bus fault state.
                cli(['-rst'],'reset_fixture.log'); clean()
                h.post('/api/arm-profile',{'profile':'hv'},'restore HV profile')
        except Exception as exc: report['profile_restore_error']=str(exc)
        try:
            if modified:
                cli(['-w',str(production),'-v','-rst'],'restore_production.log')
                readback=out/'production_readback.bin'
                cli(['-u','0x08000000',str(production_bin.stat().st_size),str(readback)],'readback.log')
                report['restored']=readback.read_bytes()==production_bin.read_bytes()
                cli(['-rst'],'production_reset.log')
            else: report['restored']=True
            report['final_status']=wait_status(h,lambda s:s.get('fw_build')==2026100707 and s.get('mc_fw_build')==2026100707
                 and outputs_off(s) and s.get('vdc')==0,25,'production pair restored SAFE')
            report['pass']=report['pass'] and report['restored'] and report['final_status'].get('hmi_arm_profile')=='hv'
            (out/'wifi_logs.txt').write_text(get_wifi_logs(h,token),encoding='utf-8')
        except Exception as exc:
            report['restore_error']=str(exc); report['restored']=False; report['pass']=False
        h.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','restored','error','restore_error','profile_restore_error')},indent=2))
    return 0 if report['pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
