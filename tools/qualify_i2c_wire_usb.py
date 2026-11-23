"""One OFF/low-bus manual trace, archive, native reset and epoch-retention check.
No motor command, CLEAR, peripheral-register write or flash operation.
"""
import argparse,json,struct,subprocess,time
from pathlib import Path
import install_i2c_wire_capture as update
from wifi_stop_tail_probe import parse_registers
from ipm_break_wifi_selftest import load_module
from passive_i2c_wire_guard import precheck as passive_precheck
p=update.p;io=update.install.io
GNU=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin')

def symbols():
    elf=p.OUT/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
    wanted=('wire','wire_ring','mic_i2c_wire_request','mic_bkin_ring','mic_bkin_record','mic_bkin_record_ready')
    result={}
    for line in subprocess.check_output([str(GNU/'arm-none-eabi-nm.exe'),'-S','--defined-only',str(elf)],text=True).splitlines():
        x=line.split()
        if len(x)==4 and x[3] in wanted:result[x[3]]=dict(address=int(x[0],16),bytes=int(x[1],16))
    assert set(result)==set(wanted) and result['wire']['bytes']==60 and result['wire_ring']['bytes']==8192
    return result

def main():
    global p
    ap=argparse.ArgumentParser();ap.add_argument('--confirm-j1-off-below20-both-usb',action='store_true')
    ap.add_argument('--epoch-fixed',action='store_true')
    ap.add_argument('--outdir',type=Path,required=True);a=ap.parse_args()
    if a.epoch_fixed:
        import prepare_i2c_wire_epoch_fix as fixed
        p=fixed
        guard=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
          '((2026101805,2026101804),(2026101807,2026101806))','((2026102813,2026102812),)')
        exec(guard,update.install.__dict__)
    if not a.confirm_j1_off_below20_both_usb:ap.error('Existing mains-off/discharged USB confirmation required')
    out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=False);(out/'logs').mkdir()
    io.URL='http://127.0.0.1:18080';sy=symbols()
    p.write(out/'symbols.json',json.dumps(sy,indent=2)+'\n')
    result=dict(passed=False,motor_commands=0,clear_commands=0,flash_commands=0,mailbox_writes=0,reset_commands=0,
        physical_bus_off_operator_confirmed=True,analog_or_external_timing_qualified=False,
        used_tool_sha256=p.sha(Path(__file__)))
    n=0
    def call(args,label):
        nonlocal n
        n+=1
        return io.run([str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL,*args],f'{n:03}_{label}',out/'logs',result,30)
    def read(address,size,label):
        allowed=(0x20000000<=address and address+size<=0x20008000) or (address,size) in ((0x40020408,16),(0x40020444,16),(0x40000800,48),(0x40012c44,4))
        assert allowed and address%4==size%4==0
        values=parse_registers(call(['-r32',hex(address),str(size)],label))
        assert all(address+i in values for i in range(0,size,4))
        return b''.join(struct.pack('<I',values[address+i]) for i in range(0,size,4))
    def live(label,require_sensor=True):
        s=io.live_status();p.write(out/(label+'.json'),json.dumps(s,indent=2)+'\n')
        okay,why=passive_precheck(s,p.NEW);assert okay,why
        assert (s['fw_build'],s['mc_fw_build'])==p.NEW
        q=s['mc_sd_live'];assert q['available'] and q['config_ok'] and q['level']=='HIGH' and q['break_irq_enabled']
        if require_sensor:assert s['enc_ok']==s['enc_bus_ok']==s['enc_diag_cfg_match']==1
        return s
    try:
        before=live('before');assert before['enc_wire_state']==1 and before['enc_wire_valid']==0
        result['before']=before
        # Retained counters may be nonzero after the preceding USB restart;
        # never reset/normalize them. Require an unchanged observed stream.
        watch=('mc_bad_cnt','bp_bad_cnt','mc_uart_error_flags','bp_uart_error_flags','uno_rx_hw_errors','enc_errors')
        for i in range(2):
            time.sleep(.4);sample=live('admission_'+str(i))
            assert all(sample[k]==before[k] for k in watch),'Diagnostics changing before passive capture'
        timer=struct.unpack('<12I',read(0x40000800,48,'TIM4_readonly'))
        dma=struct.unpack('<4I',read(0x40020444,16,'DMA2ch4_readonly'))
        sd=struct.unpack('<4I',read(0x40020408,16,'DMA2ch1_readonly'))
        assert timer[0]&1 and timer[3]&256 and timer[10]==0 and timer[11]==19
        assert dma[0]&1 and dma[0]&14==0 and dma[0]&768==512 and dma[0]&3072==1024
        assert dma[2]==0x48000410 and dma[3]==sy['wire_ring']['address'] and 0<dma[1]<=4096
        assert sd[0]&1 and sd[0]&768==512 and sd[0]&3072==0
        assert sd[2]==0x48000010 and sd[3]==sy['mic_bkin_ring']['address'] and 0<sd[1]<=8192
        assert not(struct.unpack('<I',read(0x40012c44,4,'MOE_readonly'))[0]&32768)
        live('last_pre_request')
        # Only this dedicated SRAM mailbox may be written. Native code repeats
        # OFF/low-bus checks; this request cannot enable PWM or modify I2C.
        call(['-w32',hex(sy['mic_i2c_wire_request']['address']),'0x57495245','-nv'],'one_passive_capture')
        result['mailbox_writes']=1
        deadline=time.monotonic()+15
        while True:
            s=live('captured_status')
            if s.get('enc_wire_valid')==1 and s.get('enc_wire_decode_valid')==1:break
            assert time.monotonic()<deadline,'Manual waveform delivery incomplete'
            time.sleep(.4)
        assert s['enc_wire_record']['manual'] and s['enc_wire_record']['digital_record_valid']
        raw=bytes.fromhex(s['enc_wire_hex']);h=load_module(p.OUT/'web_hmi/server.py')
        native=read(sy['wire']['address'],60,'frozen_wire_state')
        ring=read(sy['wire_ring']['address'],8192,'frozen_wire_ring')
        head=struct.unpack('<12I',native[:48]);end=int.from_bytes(native[56:58],'little')
        assert native[58]==3 and head[7]==4096 and head[11]==5
        words=struct.unpack('<4096H',ring)
        reconstructed=native[:48]+bytes(sum(((words[(end+j*4+k)&4095]>>8)&3)<<(k*2) for k in range(4)) for j in range(1024))
        assert reconstructed==raw and h.crc32c(raw)==int.from_bytes(native[52:56],'little')
        (out/'frozen_ring.bin').write_bytes(ring);(out/'native_wire_state.bin').write_bytes(native);(out/'wire.bin').write_bytes(raw)
        p.write(out/'manual_waveform.json',json.dumps(s['enc_wire_record'],indent=2)+'\n')
        # Freeze/retain SD and I2C records in a host archive before the one reset.
        (out/'native_sd_record.bin').write_bytes(read(sy['mic_bkin_record']['address'],320,'SD_record_before_reset'))
        live('before_rearm_reset')
        call(['-rst'],'one_native_reset_after_archive');result['reset_commands']=1
        deadline=time.monotonic()+20;observations=[]
        while True:
            try:s=live('after_reset_status',False)
            except (AssertionError,KeyError,RuntimeError) as exc:
                assert time.monotonic()<deadline,'No fresh safe post-reset telemetry: '+str(exc)
                time.sleep(.4);continue
            observations.append(s)
            if s['enc_wire_state']==1 and s['enc_wire_valid']==0 and s['enc_wire_hex']=='-' and s['enc_peer_epoch']>before['enc_peer_epoch']:break
            assert time.monotonic()<deadline,'Peer epoch did not invalidate old wire record'
            time.sleep(.4)
        assert s['enc_previous_records_retained']==1
        assert s['enc_previous_epoch']==before['enc_peer_epoch']
        assert int(s['enc_previous_record_crcs'].split(',')[4],16)==h.crc32c(raw)
        p.write(out/'reset_observations.json',json.dumps(observations,indent=2)+'\n')
        # Full retained previous waveform is read through status by CRC, and
        # the exact original raw bytes are already archived above.
        result.update(passed=True,TIM4_readonly=list(timer),DMA2ch4_readonly=list(dma),SD_DMA2ch1_readonly=list(sd),
          manual_trace_uart_matches_frozen_native_ring=True,record_bytes=len(raw),record_crc32c=f'{h.crc32c(raw):08x}',
          full_record_rpc_delivered=True,after_reset=s,previous_epoch_retention_verified=True,
          capture_rearmed=True,sd_records_archived_before_reset=True,sensor_errors_before=before['enc_errors'],sensor_errors_after=s['enc_errors'])
    except Exception as exc:result['error']=str(exc) or type(exc).__name__
    p.write(out/'report.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after_reset','commands')}))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
