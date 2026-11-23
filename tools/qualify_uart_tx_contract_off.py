"""Read-only UART/CPU qualification, distinct from motor START readiness.

OFF boot/Break page freshness is reported, never waived for a motor launch.
Fresh ordinary CRC-valid responses plus independent SWD uptime prove the
specific idle UART test, without erasing latches or authorizing a run.
"""
import json,struct,subprocess,time,urllib.request
from elftools.elf.elffile import ELFFile
import prepare_uart_tx_contract_fix as p
import install_bkin_boot_armed_pair as io
from probe_native_programming_state import inspect_layout

def main():
 out=p.OUT/'UART_CPU_OFF_qualification_r1';out.mkdir(exist_ok=False)
 r=dict(passed=False,START=0,CLEAR=0,ARM=0,flash=0,RESET=0,halt=0,OFF_only=True,
  motor_start_qualification=False,full_rate_history_hardware_test=False,under_PWM_test=False)
 def save():p.write(out/'report.json',json.dumps(r,indent=2)+'\n')
 def read(addr,size,label):
  dest=out/(label+'.bin');cmd=[str(io.PROGRAMMER),'-c','port=SWD','mode=HOTPLUG','sn='+io.STLINK_SERIAL,'-u',hex(addr),str(size),str(dest)]
  x=subprocess.run(cmd,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=25)
  p.write(out/(label+'.log'),x.stdout+x.stderr);x.check_returncode();raw=dest.read_bytes();assert len(raw)==size;return raw
 try:
  receipt=json.loads(p.read(p.OUT/'installation_acceptance.json'));assert receipt['installed'] and receipt['native_readback_verified'] and receipt['uno_readback_verified']
  elf=p.OUT/'release/nucleo_2026111806_uart_rx_dma.elf';sy,_=inspect_layout(elf)
  expected=p.OUT/'release/nucleo_2026111806_expected_readback.bin'
  assert read(0x08000000,expected.stat().st_size,'independent_native_flash')==expected.read_bytes()
  def native(label):
   ram=read(0x20000000,32768,label+'_SRAM');bdtr=struct.unpack('<I',read(0x40012c44,4,label+'_BDTR'))[0]
   cr1,_,cr3,brr=struct.unpack('<4I',read(0x40013800,16,label+'_UART'))
   dma=struct.unpack('<4I',read(0x4002001c,16,label+'_DMA'))
   mux=struct.unpack('<I',read(0x40020804,4,label+'_DMAMUX'))[0]
   def v(n,fmt='<I'):return struct.unpack_from(fmt,ram,sy[n]-0x20000000)[0]
   diag=list(struct.unpack_from('<5I2H',ram,sy['mic_uart_rx_dma_diag']-0x20000000))
   row=dict(tick=v('uwTick'),fast_cycles=v('fe_fast_cycles'),observer_cycles=v('fe_observer_cycles'),
    cases=v('fe_case','<B'),complete=v('fe_complete','<B'),fault=v('fe_fault','<B'),running=v('running','<B'),
    BKE=bool(bdtr&4096),MOE=bool(bdtr&32768),UART_CR1=cr1,UART_CR3=cr3,BRR=brr,DMA=dma,DMAMUX=mux,DMA_diagnostics=diag)
   assert row['BKE'] and not row['MOE'] and row['running']==0
   assert row['cases']==64 and row['complete']==1 and row['fault']==0 and 0<row['fast_cycles']<=4000
   assert cr1&(1<<29) and cr1&16 and not cr1&32 and cr3&64 and not cr3&(1<<12) and brr==184
   assert dma[0]==0x20af and dma[1]<=128 and dma[2]==0x40013824 and dma[3]==sy['mic_uart_rx_dma'] and mux&127==24
   assert diag[2:4]==[0,0]
   return row
  first=native('first');r['native_before']=first;save()
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));statuses=[];started=time.monotonic()
  counters=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_last_uart_error_flags',
   'uno_rx_hw_errors','uno_rx_hw_flags','uno_rx_dropped','uno_tx_short_writes','uno_uart_tx_rejected','rpc_response_timeouts','rpc_send_timeouts')
  for i in range(120):
   with opener.open('http://127.0.0.1:18080/api/status',timeout=8) as response:d=json.load(response)
   assert d['ok'];s=d['data'];statuses.append(s)
   with (out/'statuses.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
   assert (s['fw_build'],s['mc_fw_build'])==p.NEW
   assert s['state']=='SAFE' and s['pwm']==s['run_id']==s['hmi_hv_armed']==0 and not s['bp_status']&0x22
   assert 0<=s['mc_age_ms']<300 and s['bp_vbus_valid']==1 and 0<=s['bp_vbus_age_ms']<300 and s['vdc']<20 and s['bp_vdc']<20
   for k in counters:assert s[k]==0,(k,s[k])
   assert s['uno_uart_fifo']==1 and s['mc_transport_fault']==0
   assert s['mc_current_zero_ready']==1 and s['mc_current_zero_stable']==3
   assert s['mc_current_age_ms']<750 and s['mc_current_detail_age_ms']<1500 and s['mc_current_quality_age_ms']<1500
   assert s['algorithm_fast_cycles']==first['fast_cycles'] and s['foc_timing_fault']==0 and s['foc_timing_cases']==64
   assert s['mc_sd_live']['level']=='HIGH' and s['mc_sd_live']['config_ok'] and s['mc_sd_live']['break_irq_enabled']
   if i:
    assert s['linux_boot_id']==statuses[0]['linux_boot_id']
    assert 0<((s['uno_rx_count']-statuses[-2]['uno_rx_count'])&0xffffffff)<1000,'ordinary CRC-valid replies stopped'
   time.sleep(.25)
  last=native('last');assert last['tick']>first['tick'] and last['DMA_diagnostics'][0]>first['DMA_diagnostics'][0]
  # Public RX/TX counters count only real frames, no synthetic motor commands.
  r.update(passed=True,pair=p.NEW,samples=len(statuses),seconds=time.monotonic()-started,
   independent_native_readback_verified=True,native_after=last,fast_cycles=last['fast_cycles'],fast_limit=4000,estimate_age_limit_ms=2,
   UART_nominal_baud=921600,UART_idle_qualified=True,UART_error_counters={k:s[k] for k in counters},
   good_frames_delta=s['mc_good_cnt']-statuses[0]['mc_good_cnt'],accepted_native_replies_delta=s['uno_rx_count']-statuses[0]['uno_rx_count'],
   Uno_FIFO=s['uno_uart_fifo'],Uno_max_RX_batch=s['uno_uart_rx_batch_max'],Uno_max_IRQ_cycles=s['uno_uart_irq_cycles_max'],
   Uno_max_own_lock_cycles=s['uno_uart_lock_cycles_max'],Uno_clock_Hz=160000000,
   zero_ready=True,zero_spans=s['mc_current_zero_spans'],SD=s['mc_sd_live'],
   active_fault_mask=s['mc_fault_current_mask'],retained_fault_mask=s['mc_fault_occurred_mask'],
   native_boot_page_fresh=s['native_boot']['fresh'],repeat_break_page_fresh=s['repeat_break']['fresh'],
   limitation='Idle ordinary full-duplex frames only; not full921600 line saturation, not full history streaming, not PWM. Boot/Break page freshness is reported separately and remains a START gate.')
 except Exception as e:r['error']=repr(e)
 save();print(json.dumps({k:r.get(k) for k in ('passed','error','samples','seconds','fast_cycles','accepted_native_replies_delta','UART_error_counters','native_boot_page_fresh','repeat_break_page_fresh')}))
 return 0 if r['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
