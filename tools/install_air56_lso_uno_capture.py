"""Install sealed 2301/2302 and the matching HMI while physically J1 OFF."""
import argparse
import json
import shlex
import struct
import subprocess
import time
import uuid

import install_bkin_boot_armed_pair as io
from install_air56_lso_timing_aspep import (
    FLASH, RAM, SWD, images, inspect_layout, parse_registers, programmed_hex_image, read_dwt,
)
from install_sd_break_filter_usb_pair import tunneled
from prepare_air56_lso_uno_capture import LSO, NEW, OUT, ROOT, SUPERVISOR, release
from unoq_wifi_hmi_deploy import ssh_base, scp_base

REMOTE_ROOT = '/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi'
CAL = '/home/arduino/.config/mic-ai/vbus_calibration.json'
ADB = ['adb', '-s', io.UNO_SERIAL]
OPENOCD = ['/opt/openocd/bin/openocd', '-s', '/opt/openocd', '-s',
           '/opt/openocd/share/openocd/scripts', '-f', '/opt/openocd/openocd_gpiod.cfg']

DEPLOY = '''import hashlib,importlib.util,json,os,pathlib,signal,subprocess,sys
cfg=json.loads(pathlib.Path(sys.argv[1]).read_text())
root=pathlib.Path(cfg['root'])
cal=pathlib.Path(cfg['cal'])
sha=lambda b:hashlib.sha256(b).hexdigest()
original=cal.read_bytes()
assert sha(original)==cfg['cal_sha']
source=pathlib.Path(cfg['candidate'])
data=source.read_bytes()
assert sha(data)==cfg['server_sha']
compile(data,str(source),'exec')
spec=importlib.util.spec_from_file_location('lso_candidate',source)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
cal_ok=module.VbusCalibrationStore(str(cal)).is_valid(cfg['prospective_identity'])
if sys.argv[2]=='check':
    print(json.dumps(dict(server_verified=True,calibration_valid_for_pair=cal_ok)))
    raise SystemExit(0)
target=root/'server.py'
old=target.read_bytes()
assert sha(old)==cfg['old_server_sha']
pid=int(subprocess.check_output(['systemctl','show','-p','MainPID','--value','unoq-hmi.service'],text=True))
restart=subprocess.check_output(['systemctl','show','-p','Restart','--value','unoq-hmi.service'],text=True).strip()
proc=pathlib.Path('/proc')/str(pid)
assert pid>1 and restart=='always' and proc.stat().st_uid==os.geteuid()
assert (proc/'cwd').resolve()==root and 'server.py' in (proc/'cmdline').read_bytes().decode().split(chr(0))
backup=root/'backups'/cfg['backup']
backup.mkdir()
(backup/'server.py').write_bytes(old)
pending=root/('.server.py.'+cfg['backup'])
pending.write_bytes(data)
pending.chmod(target.stat().st_mode&0o777)
os.replace(pending,target)
assert target.read_bytes()==data and cal.read_bytes()==original
os.kill(pid,signal.SIGTERM)
print(json.dumps(dict(deployed=True,backup=str(backup),server_sha256=sha(data),
    calibration_unchanged=True,calibration_valid_for_pair=cal_ok)))
'''


def install(*, out=OUT, pair=NEW, previous_native=LSO,
            previous_uno=SUPERVISOR/'release/uno_2026112201_if_foc.elf-zsk.bin',
            previous_uno_build=2026112201, verification='uno_capture_PC.json',
            verify_uart_startup=False):
    sha = release.base.sha
    approved = release.base.read_json(out/verification)
    protected = release.base.read_json(out/'preserved_inputs_sha256.json')
    assert approved['passed'] and approved['pair'] == list(pair)
    assert (approved['DWT_limit'], approved['ADC_age_limit_us']) == (4000, 2000)
    assert not approved['hardware_commands']
    release.base.verify_inventory(approved['images_sha256'], out/'image')
    release.base.verify_inventory(protected, ROOT)
    server = out/'web_hmi/server.py'
    assert sha(server) == approved['web_hmi_sha256']
    old_elf, old_hex, old_bin = images(previous_native)
    new_elf, new_hex, new_bin = images(out)
    expected, _ = programmed_hex_image(new_hex, new_bin.read_bytes())
    old, _ = programmed_hex_image(old_hex, old_bin.read_bytes())
    uno = out/'image/UNOQ-LSO_CAPTURE.elf-zsk.bin'
    attempts = sorted(out.glob('hardware_install_r[0-9]*'))
    assert not any((path/'flash_intent.json').exists() for path in attempts), 'Review issued flash first'
    folder = out/f'hardware_install_r{len(attempts)+1}'
    folder.mkdir()
    report = dict(pair=pair, passed=False, START=0, CLEAR=0, ARM=0, uno_flash=0, nucleo_flash=0)
    label = f'lso_{pair[1]%10000:04d}_' + uuid.uuid4().hex
    prefix = '/tmp/' + label + '_'
    ssh, scp = (tunneled(factory)('192.168.1.138', 2222, 'arduino',
                 ROOT/'.unoq_ssh/id_ed25519', ROOT/'.unoq_ssh/known_hosts')
                 for factory in (ssh_base, scp_base))

    def save():
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')

    def run(args, name, timeout=25):
        p = subprocess.run(args,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=timeout)
        (folder/(name+'.log')).write_text(p.stdout+p.stderr,encoding='utf8')
        p.check_returncode()
        return p.stdout

    def remote(code,name,timeout=25):
        return run(ssh+[code],name,timeout)

    def read(address,size,name):
        path = folder/(name+'.bin')
        run(SWD+['-u',hex(address),str(size),str(path)],name)
        data=path.read_bytes()
        assert len(data)==size
        return data

    def safety(elf, name):
        sym,layout=inspect_layout(elf)
        vbs,tick=sym['BusVoltageSensor_M1'],sym['uwTick']
        reg=parse_registers(run(SWD+['-r32',hex(vbs),'12','-r32',hex(tick),'4',
          '-r32','0x40012c0c','12','-r32','0x40012c44','4','-r32','0x48000010','4'],name))
        raw=struct.pack('<3I',*(reg[vbs+i] for i in (0,4,8)))
        scale=struct.unpack_from('<H',raw,layout['ConversionFactor'])[0]
        bus=struct.unpack_from('<H',raw,layout['AvBusVoltage_d'])[0]*scale/65536
        bdtr=reg[0x40012c44]
        assert scale==416 and 0<=bus<20 and bdtr & 0x1000 and not bdtr & 0xc000
        return dict(tick=reg[tick],bus_V=bus,MOE=False,AOE=False,BKE=True,
            BIE=bool(reg[0x40012c0c]&128),SD_HIGH=bool(reg[0x48000010]&64),
            BKF=(bdtr>>16)&15),sym

    def dump_uno(areas,name):
        common=(ROOT/'tools/unoq_idle_rpc_RAM_readonly.cfg').read_text(encoding='utf8')
        functions='\n'.join(f'dump_image {prefix}{n}.bin {hex(address)} {hex(length)}' for n,address,length in areas)
        cfg=folder/(name+'.cfg')
        cfg.write_text(common.replace('dump_image /tmp/unoq_idle_rpc_RAM.bin 0x20000000 0xC0000',functions),encoding='utf8')
        run(ADB+['push',str(cfg),prefix+cfg.name],name+'_stage')
        run(ADB+['shell',*OPENOCD,'-f',prefix+cfg.name],name,120)
        log=(folder/(name+'.log')).read_text(encoding='utf8')
        assert 'CORE_AFTER: running' in log
        for n,_,length in areas:
            destination=folder/(n+'.bin')
            run(ADB+['pull',prefix+n+'.bin',str(destination)],n+'_pull',45)
            assert destination.stat().st_size==length

    def route(action):
        code="""import socket,msgpack
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(5);s.connect('/var/run/arduino-router.sock')
s.sendall(msgpack.packb([0,1,'$/serial/ACTION',['/dev/ttyHS1']],use_bin_type=True))
u=msgpack.Unpacker(raw=False)
while True:
 b=s.recv(65536);assert b;u.feed(b)
 for r in u:
  if r[0]==1 and r[1]==1:
   assert r[2] is None and r[3] is True,r
   print('route ACTION OK');raise SystemExit(0)
""".replace('ACTION',action)
        remote(REMOTE_ROOT+'/.venv/bin/python -c '+shlex.quote(code),'router_'+action)

    route_closed=False
    try:
        assert run(ADB+['get-state'],'adb_state').strip()=='device'
        for local,target in ((18080,8080),(12222,2222)):
            run(ADB+['forward',f'tcp:{local}',f'tcp:{target}'],f'forward_{local}')
        io.URL='http://127.0.0.1:18080'
        uno_port,_=io.board_ports()
        cached=io.live_status()
        assert cached['fw_build']==previous_uno_build and cached['state']=='SAFE' and cached['pwm']==0
        assert not cached['hmi_hv_armed'] and not cached['bp_status']&0x22
        (folder/'before_cached_status.json').write_text(json.dumps(cached,indent=2),encoding='utf8')
        report['before_SWD'],_=safety(old_elf,'before_SWD')
        native=read(FLASH,0x20000,'previous_nucleo_full_flash')
        assert native[:len(old)]==old
        read(RAM,0x8000,'previous_nucleo_RAM')
        dump_uno([('previous_uno_RAM',0x20000000,0xc0000),
                  ('previous_uno_sketch',0x08100000,previous_uno.stat().st_size)],'before_uno')
        assert (folder/'previous_uno_sketch.bin').read_bytes()==previous_uno.read_bytes()
        report['saved_previous_native_and_uno_memory']=True
        old_server=remote('sha256sum '+REMOTE_ROOT+'/server.py','previous_server').split()[0]
        # Stage only the reviewed backend changes. Keep the installed static frontend.
        candidate=prefix+'server.py'
        run(scp+[str(server),'arduino@192.168.1.138:'+candidate],'stage_server')
        assert remote('sha256sum '+candidate,'staged_server').split()[0]==sha(server)
        cal_sha=remote('sha256sum '+CAL,'cal_before').split()[0]
        cfg=dict(root=REMOTE_ROOT,cal=CAL,cal_sha=cal_sha,candidate=candidate,
              server_sha=sha(server),old_server_sha=old_server,backup=label,
              prospective_identity=dict(cached,fw_build=pair[0],mc_fw_build=pair[1]))
        for name,data in (('deploy.json',json.dumps(cfg)),('deploy.py',DEPLOY)):
            local=folder/name
            local.write_text(data,encoding='utf8')
            run(scp+[str(local),'arduino@192.168.1.138:'+prefix+name], 'stage_'+name)
        deploy='python3 '+prefix+'deploy.py '+prefix+'deploy.json'
        report['web_preflight']=json.loads(remote(deploy+' check','web_candidate_check'))
        final_old,_=safety(old_elf,'before_programming_SWD')
        assert final_old['tick']!=report['before_SWD']['tick']
        route('close')
        route_closed=True
        upload=['arduino-cli','upload','-p',uno_port,'-b','arduino:zephyr:unoq','-i',str(uno),
              '--upload-property','upload.artifacts.sketch='+str(uno),
              '--upload-property','upload.port.properties.serialNumber='+io.UNO_SERIAL,
              '--upload-property','build.variant.path='+str(ROOT/'tools'),'--upload-property']
        (folder/'flash_intent.json').write_text(json.dumps(dict(pair=pair,physical_j1_off=True)),encoding='utf8')
        report['uno_flash']=1
        save()
        run(upload+['openocd_cfg=flash_verify_unoq_history_hold.cfg'],'program_uno_once',100)
        assert 'VERIFIED AND HELD' in (folder/'program_uno_once.log').read_text(encoding='utf8')
        report['nucleo_flash']=1
        save()
        run([str(io.PROGRAMMER),'-c','port=SWD','mode=UR','sn='+io.STLINK_SERIAL,
             '-w',str(new_hex),'-v','-rst'],'program_nucleo_once',75)
        native_name=f'nucleo_{pair[1]%10000:04d}_flash_readback'
        native=read(FLASH,len(expected),native_name)
        assert native==expected
        report['nucleo_hex_readback_sha256']=sha(folder/(native_name+'.bin'))
        report['after_SWD'],symbols=safety(new_elf,'after_SWD')
        ccm_start,ccm_end,ccm_flash=(symbols[k] for k in ('_sccmram','_eccmram','_siccmram'))
        ccm=read(ccm_start,ccm_end-ccm_start,'ccm_runtime')
        assert ccm==expected[ccm_flash-FLASH:ccm_flash-FLASH+len(ccm)]
        report['DWT']=read_dwt(read,symbols)
        save()
        run(upload+['openocd_cfg=verify_restart_unoq_sketch.cfg'],'verify_restart_uno',100)
        assert 'UNO Q verification PASSED' in (folder/'verify_restart_uno.log').read_text(encoding='utf8')
        uno_name=f'uno_{pair[0]%10000:04d}_flash_readback'
        dump_uno([(uno_name,0x08100000,uno.stat().st_size)],'after_uno')
        assert (folder/(uno_name+'.bin')).read_bytes()==uno.read_bytes()
        report['uno_flash_readback_sha256']=sha(folder/(uno_name+'.bin'))
        route('open')
        route_closed=False
        report['hmi']=json.loads(remote(deploy+' apply','deploy_web'))
        assert remote('sha256sum '+CAL,'cal_after').split()[0]==cal_sha
        end=time.monotonic()+(40 if verify_uart_startup else 22)
        uart_samples=[]
        while time.monotonic()<end:
            try:
                state=io.live_status()
                (folder/'after_status.json').write_text(json.dumps(state,indent=2),encoding='utf8')
                assert (state.get('fw_build'),state.get('mc_fw_build'))==pair
                assert state['state']=='SAFE' and state['pwm']==0 and not state['bp_status']&0x22
                assert state['bp_vbus_valid'] == 1 and 0<=state['bp_vdc']<20 and 0<=state['mc_age_ms']<300
                assert state['research_native_caps']==2 and state['research_native_valid']==1
                assert state['foc_timing_cases']==64
                if verify_uart_startup:
                    diagnostic=state.get('mc_uart_startup') or {}
                    assert diagnostic.get('available') and diagnostic.get('qualified'), 'new UART diagnostic absent or not qualified'
                    assert diagnostic.get('clean_off_frames')==3 and not diagnostic.get('fault_latched'), diagnostic
                    assert state['bp_status']&1 and state['mc_transport_fault']==state['mc_bad']==state['mc_uart_error_flags']==0
                    assert state['mc_sd_live']['level']=='HIGH' and state['mc_sd_live']['break_irq_enabled']
                    uart_samples.append({k:state[k] for k in ('mc_good','mc_age_ms','mc_uart_startup',
                                         'rpc_response_timeouts','rpc_send_timeouts')})
                    (folder/'cold_uart_samples.json').write_text(json.dumps(uart_samples,indent=2),encoding='utf8')
                    if len(uart_samples)<5:
                        time.sleep(.25)
                        continue
                    assert uart_samples[-1]['mc_good']>uart_samples[0]['mc_good']
                    assert all(uart_samples[-1][k]==uart_samples[0][k] for k in ('rpc_response_timeouts','rpc_send_timeouts'))
                    report['cold_uart']=dict(qualified=True, clean_off_frames=3, samples=len(uart_samples),
                                           new_uart_frames=uart_samples[-1]['mc_good']-uart_samples[0]['mc_good'],
                                           max_age_ms=max(row['mc_age_ms'] for row in uart_samples),
                                           diagnostic=diagnostic)
                report['uno_live']=True
                break
            except (OSError,AssertionError,RuntimeError,KeyError,ValueError) as ex:
                uart_samples.clear()
                report['runtime_pending']=repr(ex)
                time.sleep(1)
        report['final_SWD'],_=safety(new_elf,'final_SWD')
        report['passed']=report['DWT']['passed'] and report.get('uno_live',False)
    except Exception as ex:
        report['error']=repr(ex)
    finally:
        if route_closed:
            try:
                route('open')
            except Exception as ex:
                report['router_reopen_error']=repr(ex)
        release.base.verify_inventory(protected,ROOT)
        report['preserved_files_verified']=len(protected)
        save()
    print(folder)
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-j1-off-both-usb',action='store_true',required=True)
    parser.parse_args()
    raise SystemExit(install())
