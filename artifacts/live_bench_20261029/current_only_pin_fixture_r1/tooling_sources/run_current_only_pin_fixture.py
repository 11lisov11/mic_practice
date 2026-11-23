"""One isolated Saleae pulse capture, then unconditional verified production restore."""
import argparse,csv,json,statistics,struct,subprocess,time
from pathlib import Path
from saleae import automation
import prepare_current_only as p
import prepare_current_only_pin_fixture as fixture
from install_current_only import verify_package
from no_switch_diag_snapshot_io import Probe,PROGRAMMER,SERIAL,crc32c
from current_only_lab import get_status

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-j1-j4-off-ribbon-disconnected-bus-below20',action='store_true')
    a=parser.parse_args()
    if not a.confirm_j1_j4_off_ribbon_disconnected_bus_below20:parser.error('Physical isolation confirmation required')
    verify_package();c=fixture.OUT;m=json.loads(p.read(c/'manifest.json'));assert m['built'] and m['offline_verified']
    for rel,h in m['sealed_sha256'].items():assert p.sha(c/rel)==h,rel
    symbols=json.loads(p.read(c/'verification/symbols.json'))
    image=next((c/'nucleo/STM32CubeIDE/Debug').glob('*.hex'));assert p.sha(image)==m['image_sha256']
    restore=next((p.OUT/'build/nucleo').glob('*.hex'))
    out=c/'capture_r1';out.mkdir(exist_ok=False);(out/'logs').mkdir()
    r=dict(passed=False,flash_commands=0,pin_requests=0,motor_commands=0,clear_commands=0,
           isolation_operator_confirmed=True,restored=False)
    pr=Probe(out/'logs');manager=None;capture=None;flashed=False
    def save():p.write(out/'report.json',json.dumps(r,indent=2))
    def flash(path,label):
        q=subprocess.run([str(PROGRAMMER),'-c','port=SWD','mode=UR','sn='+SERIAL,'-w',str(path),'-v','-rst'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        p.write(out/'logs'/(label+'.log'),q.stdout+q.stderr)
        assert q.returncode==0 and 'Download verified successfully' in q.stdout,label
    def report(label):
        for attempt in range(4):
            raw=pr.read(symbols['mic_pin_report']['address'],256,label+str(attempt));(out/(label+str(attempt)+'.bin')).write_bytes(raw)
            w=struct.unpack('<64I',raw)
            if w[0]!=0x314e4950 or w[2]!=fixture.BUILD or w[4]&1 or w[4]!=w[61] or crc32c(raw[20:244])!=w[62]:
                time.sleep(.08);continue
            d=dict(build=w[2],state=w[5],reason=w[6],attempted=w[7],elapsed_ms=w[10]*1000/w[11],
                clock_hz=w[11],updates=w[12],phase=w[16],BDTR=w[17],ARR=w[19],CCR=list(w[20:23]),
                GPIOA_IDR=w[23],local_stop=w[24],CCER=w[53],SMCR=w[58],SysTick_LOAD=w[60])
            p.write(out/(label+'.json'),json.dumps(d,indent=2));return d
        raise RuntimeError('No coherent diagnostic report; no request retry')
    try:
        before=get_status('http://192.168.1.138:8080');p.write(out/'production_before.json',json.dumps(before,ensure_ascii=False,indent=2))
        assert (before['fw_build'],before['mc_fw_build'])==p.NEW and before['state']=='SAFE' and before['pwm']==0 and before['vdc']<20
        manager=automation.Manager.connect(port=10430,connect_timeout_seconds=3)
        assert any(d.device_id=='A7D1BB81883C0092' and not d.is_simulation for d in manager.get_devices())
        flashed=True;r['flash_commands']+=1;save();flash(image,'flash_fixture_verify')
        time.sleep(.3);d=report('fixture_boot');r['boot']=d
        assert d['state']==d['reason']==d['attempted']==0 and d['clock_hz']==170000000
        assert d['BDTR']&0x1000 and not(d['BDTR']&0xc000) and d['CCER']==0x555 and d['ARR']==5312
        assert d['GPIOA_IDR']&64 and d['local_stop']==0 and d['SysTick_LOAD']==169999
        capture=manager.start_capture(device_id='A7D1BB81883C0092',
          device_configuration=automation.LogicDeviceConfiguration(enabled_digital_channels=list(range(7)),digital_sample_rate=12_000_000,glitch_filters=[]),
          capture_configuration=automation.CaptureConfiguration(capture_mode=automation.TimedCaptureMode(duration_seconds=8)))
        time.sleep(.25)
        r['pin_requests']=1;save()
        # The sole SRAM write is the dedicated one-shot request, never a timer register.
        pr.call(['-w32',hex(symbols['mic_pin_request']['address']),'0x50494e35','-nv'],'single_pin_request')
        time.sleep(5.3);d=report('fixture_after');r['after']=d
        assert d['state']==2 and d['reason']==0 and d['attempted']==1 and not(d['BDTR']&0x8000)
        assert 5000<=d['elapsed_ms']<=5000.2
        capture.wait();capture.save_capture(str(out.resolve()/'pwm_5seconds.sal'))
        dest=out/'csv';dest.mkdir();capture.export_raw_data_csv(directory=str(dest.resolve()),digital_channels=list(range(7)))
        r['native_auto_stop_verified']=True;r['capture_saved']=True;r['passed']=True
    except Exception as e:r['error']=type(e).__name__+': '+str(e)
    finally:
        if capture is not None:
            try:
                capture.wait()
                if not r.get('capture_saved'):capture.save_capture(str(out.resolve()/'ambiguous_capture.sal'))
            except Exception as e:r['capture_error']=str(e)
            try:capture.close()
            except Exception as e:r['capture_close_error']=str(e)
        if manager is not None:manager.close()
        if flashed:
            try:
                r['flash_commands']+=1;save();flash(restore,'restore_2902_verify');r['restored']=True;r['restore_sha256']=p.sha(restore)
            except Exception as e:r['restore_error']=str(e);r['passed']=False
        save()
    if r.get('capture_saved'):
        from saleae_pwm_analyze import analyze_csv,load_csv
        analysis=analyze_csv(out/'csv/digital.csv',expect_pwm=True,selected_sample_rate_hz=12_000_000,max_sample_period_ns=100)
        times,values=load_csv(out/'csv/digital.csv',list(range(7)))
        stats={};all_ok=True
        for ch in range(6):
            rises=[t for t,a,b in zip(times[1:],values[ch],values[ch][1:]) if a==0 and b==1]
            falls=[t for t,a,b in zip(times[1:],values[ch],values[ch][1:]) if a==1 and b==0]
            periods=[b-a for a,b in zip(rises,rises[1:])]
            freq=1/statistics.median(periods) if periods else 0
            start=rises[0]+.01 if rises else 0;end=rises[-1]-.01 if rises else 0
            high=total=0.
            for i in range(len(times)-1):
                dt=max(0,min(times[i+1],end)-max(times[i],start));total+=dt;high+=dt*values[ch][i]
            duty=high/total if total else 0;expected=[.25,.75,.5,.5,.75,.25][ch]
            stats[ch]=dict(frequency_hz=freq,duty_cycle=duty,rising_edges=len(rises),active_duration_s=falls[-1]-rises[0] if rises and falls else 0)
            all_ok=all_ok and 15500<freq<16500 and abs(duty-expected)<.02 and len(rises)>70000
        r['channels']=stats;r['sd_high_entire_capture']=all(values[6]);r['waveform_analysis_passed']=analysis['pass'] and all_ok and r['sd_high_entire_capture']
        p.write(out/'waveform_analysis.json',json.dumps(analysis,indent=2));r['passed']=r['passed'] and r['waveform_analysis_passed'];save()
    if r.get('restored'):
        for _ in range(10):
            try:
                s=get_status('http://192.168.1.138:8080')
                if (s.get('fw_build'),s.get('mc_fw_build'))==p.NEW and s.get('state')=='SAFE' and s.get('pwm')==0 and 0<=s.get('mc_age_ms',99999)<300:
                    r['production_live_restored']=True;p.write(out/'production_after.json',json.dumps(s,ensure_ascii=False,indent=2));break
            except Exception as e:r['runtime_last_error']=str(e)
            time.sleep(.5)
        save()
    print(json.dumps({k:r.get(k) for k in ('passed','error','boot','after','channels','native_auto_stop_verified','restored','production_live_restored')},ensure_ascii=True))
    return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
