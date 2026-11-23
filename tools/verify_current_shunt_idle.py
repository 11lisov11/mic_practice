"""Read-only verification of the real shunt ADC/zero/UART/UI, no START/ARM/CLEAR."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import install_current_shunt_monitor as install
from install_sd_break_filter_usb_pair import tunneled
from unoq_wifi_hmi_deploy import ssh_base


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--duration',type=float,default=8)
    p.add_argument('--require-sd-armed',action='store_true')
    args=p.parse_args();c=args.candidate.resolve();out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    m=json.loads((c/'manifest.json').read_text());pair=tuple(m['pair_compatibility_ids'])
    r=dict(passed=False,read_only=True,motor_commands=0,clear_commands=0,reset_commands=0,flash_commands=0,
           samples=[],physical_current_scale_verified=False,motor_current_measurement_verified=False)
    install.io.URL='http://127.0.0.1:18080'
    try:
        adb=['adb','-s',install.io.UNO_SERIAL]
        for local,remote in ((18080,8080),(12222,2222)):
            subprocess.run(adb+['forward',f'tcp:{local}',f'tcp:{remote}'],capture_output=True,check=True)
        started=time.monotonic()
        assert 0<args.duration<=120
        if m.get('zero_raw_span_advisory_only'):
            from current_zero_quality import ready as new_zero_ready
            wait_until=time.monotonic()+12
            r['warmup_samples']=[]
            while True:
                s=install.io.live_status();r['warmup_samples'].append(s)
                assert (s['fw_build'],s['mc_fw_build'])==pair and s['state']=='SAFE' and s['pwm']==0
                if new_zero_ready(s):break
                if s.get('mc_current_flags',0)&16 or time.monotonic()>=wait_until:
                    raise RuntimeError('New zero contract/history not ready: '+s.get('mc_current_status',''))
                time.sleep(.3)
        while len(r['samples'])<16 or time.monotonic()-started<args.duration:
            s=install.io.live_status();r['samples'].append(s)
            assert (s['fw_build'],s['mc_fw_build'])==pair
            assert s['state']=='SAFE' and s['pwm']==0 and s['hmi_hv_armed']==0
            assert 0<=s['mc_age_ms']<300 and 0<=s['vdc']<=20
            assert 0<=s['mc_current_age_ms']<750 and 0<=s['mc_current_detail_age_ms']<1500
            assert s['mc_current_zero_ready']==1, s.get('mc_current_status','Autonull not ready')
            assert s['mc_current_telemetry_valid']==0 and s['mc_current_rms_a'] is None, 'Idle is not a motor RMS measurement'
            assert s['mc_current_scale_qualified']==0
            assert all(v==256 for v in s['mc_current_zero_samples'])
            assert all(1600<=v<=2500 for v in s['mc_current_offsets_adc'])
            if m.get('zero_uses_multiple_blocks'):
                assert 0<=s['mc_current_quality_age_ms']<1500, 'Stale zero quality'
                assert s['mc_current_zero_stable']==3 and 3<=s['mc_current_zero_attempts']<=8
                assert len(s['mc_current_zero_spans'])==4
                if m.get('zero_raw_span_advisory_only'):
                    assert new_zero_ready(s),'New mean-uncertainty/history contract failed'
                else:
                    assert all(0<=v<=40 for v in s['mc_current_zero_spans'])
            if args.require_sd_armed:
                sd=s['mc_sd_live']
                assert sd['available'] and sd['config_ok'] and 0<=sd['age_ms']<300
                assert sd['level']=='HIGH' and sd['break_irq_enabled'] and sd['capture_running'] and not sd['first_record_ready'], 'SD capture not free and armed'
            time.sleep(.35)
        first,last=r['samples'][0],r['samples'][-1]
        assert last['mc_current_good']>first['mc_current_good'] and last['mc_good']>first['mc_good']
        for key in ('mc_current_bad','mc_bad_cnt','mc_bad_sequence','mc_uart_error_flags'):
            assert last[key]==first[key], 'Counter changed during idle: '+key
        # Resolve the actual state address from this exact target link map.
        text=(c/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.map').read_text()
        symbol=re.search(r'\.bss.state\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+\./Application/User/current_shunt.o',text)
        address,size=(int(symbol[i],16) for i in (1,2))
        assert 176<=size<=1024 and size%4==0
        read=subprocess.run([str(install.io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG',
            'sn='+install.io.STLINK_SERIAL,'-r32',hex(address),hex(size)],capture_output=True,text=True,timeout=15)
        log=read.stdout+read.stderr;(out/'adc_state_hotplug.log').write_text(log)
        assert read.returncode==0
        raw=bytearray()
        for line in log.splitlines():
            match=re.match(r'0x[0-9A-Fa-f]+ : ((?:[0-9A-Fa-f]{8}\s*)+)$',line)
            if match:
                for word in match[1].split():raw.extend(int(word,16).to_bytes(4,'little'))
        assert len(raw)==size
        u16=lambda offset:[int.from_bytes(raw[i:i+2],'little') for i in range(offset,offset+8,2)]
        lows,highs=u16(24),u16(32)
        spans=[b-a for a,b in zip(lows,highs)]
        if not m.get('zero_raw_span_advisory_only'):
            assert max(spans)<=40, 'Actual zero span outside unchanged acceptance'
        if m.get('zero_uses_multiple_blocks'):
            assert spans==last['mc_current_zero_spans'], 'D7 and direct memory zero quality differ'
            r.update(zero_attempts=last['mc_current_zero_attempts'],zero_stable_blocks=last['mc_current_zero_stable'],
                     zero_quality_direct_memory_match=True)
        if args.require_sd_armed:r['sd_capture_free_and_armed']=True
        r.update(adc_zero_lows=lows,adc_zero_highs=highs,adc_zero_spans=spans,
                 offsets=u16(40),raw_adc=u16(48),current_packet_progress=last['mc_current_good']-first['mc_current_good'])
        r['observed_duration_s']=time.monotonic()-started
        ssh=tunneled(ssh_base)('192.168.1.138',2222,'arduino',install.ROOT/'.unoq_ssh/id_ed25519',install.ROOT/'.unoq_ssh/known_hosts')
        paths=['/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py',
               '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/static/app.js',
               '/home/arduino/.config/mic-ai/vbus_calibration.json']
        hashes=subprocess.run(ssh+['sha256sum '+' '.join(paths)],capture_output=True,text=True,timeout=20)
        (out/'live_hmi_calibration_hashes.log').write_text(hashes.stdout+hashes.stderr)
        assert hashes.returncode==0
        actual=[line.split()[0] for line in hashes.stdout.splitlines()]
        assert actual[:2]==[install.io.sha(c/'web_hmi/server.py'),install.io.sha(c/'web_hmi/static/app.js')]
        assert actual[2]=='a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17'
        r.update(passed=True,live_pair=list(pair),adc_zero_verified=True,calibration_unchanged=True,
                 hmi_files_match=True,final_status=last)
    except Exception as exc:r['error']=str(exc)
    (out/'report.json').write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:r.get(k) for k in ('passed','live_pair','offsets','adc_zero_spans','calibration_unchanged','error')},ensure_ascii=True))
    return 0 if r['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
