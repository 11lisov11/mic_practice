"""Compile actual CLEAR path, ST ACK API, TX DMA and OFF scheduling. PC only."""
import ast,json,shutil,subprocess
import prepare_clear_recovery as p
import test_foc_runtime_fix as common
from test_foc_update_latency_fix import function


def branch(source):
    start=source.index('  if (uno_clear_frame_is_safe(frame)) {')
    opening=source.index('{',start);depth=1;end=opening+1
    while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


def main():
    out=p.OUT/'verification';out.mkdir(exist_ok=True);common.p=p
    sources={name:p.read(folder/'nucleo/Src/main.c') for name,folder in [('baseline',p.BASE),('candidate',p.OUT)]}
    fixture=p.read(p.SOURCE/'handler_fixture.cpp')
    ack=function(p.read(p.OUT/'nucleo/Src/mc_interface.c'),'MCI_FaultAcknowledged')
    outputs={}
    names=('uno_tx_clear_ready','uno_mcsdk_fault_present','uno_stop_motor','uno_rearm_break_irq',
        'uno_latch_fault','uno_capture_diagnostics','uno_latch_fault_reason','uno_clear_diagnostics',
        'uno_clear_frame_is_safe')
    for name,s in sources.items():
        funcs='\n'.join(function(s,n) for n in names)
        if name=='candidate':funcs+='\n'+'\n'.join(function(s,n) for n in ('mic_clear_diag_begin','mic_clear_diag_finish'))
        definitions='static uint8_t mic_clear_diag_packet[UV3_FRAME];static uint8_t mic_clear_diag_ready;\n' if name=='candidate' else ''
        code=fixture.replace('// ACTUAL_MCI_ACK',ack).replace('// ACTUAL_FUNCTIONS',definitions+funcs).replace('// ACTUAL_CLEAR_BRANCH',branch(s))
        code='#define CANDIDATE '+str(int(name=='candidate'))+'\n'+code
        outputs[name]=common.compile_run(out,'clear_'+name,code).strip()
    raw=bytes.fromhex(outputs['candidate']);assert len(raw)==43
    (out/'CLEAR_record_example.bin').write_bytes(raw)
    # Exercise the actual embedded DMA driver including2048 full CRC frames.
    src=sources['candidate'];a=src.index('/* USART1 TX owns DMA1 channel 1');b=src.index('\nstatic bool uno_rx_push',a)
    p.write(out/'driver.inc',src[a:b].strip()+'\n')
    from uart_tx_dma_selftest import body
    hal=p.read(p.OUT/'nucleo/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_uart.c')
    p.write(out/'old_hal_transmit.inc',body(hal,'HAL_UART_Transmit')+'\n')
    dma=p.read(p.ROOT/'tools/uart_tx_dma/driver_test.cpp')
    dma='#define DMA_CCR_TCIE 2U\n#define MIC_FOC_IRQ_SCOPE_NAMED(a,b) ((void)0)\n'+dma
    # Model the release's DMA-TC interrupt which alone arms UART-TC. The older
    # fixture predates this existing IRQ-budget fix; no candidate driver edit.
    dma=dma.replace('if(channel.CNDTR==0){usart.ISR|=UART_FLAG_TC;',
        'if(channel.CNDTR==0){dma.ISR|=2U;DMA1_Channel1_IRQHandler();usart.ISR|=UART_FLAG_TC;')
    dma=dma.replace('mic_uart_tx.early_tc==1','mic_uart_tx.early_tc==0')
    dma=dma.replace('if(mode){usart.ISR|=64;uno_tx_tc_isr();}',
        'if(mode){usart.ISR|=64;uno_tx_tc_isr();DMA1_Channel1_IRQHandler();}')
    extra='''
 reset();auto active_clear=frame(70);uno_tx_submit(active_clear.data(),0);settle();
 for(unsigned i=0;i<39;++i)dma_byte();
 const auto clear_remaining=channel.CNDTR;const auto clear_head=mic_uart_tx.head;
 check(uno_tx_clear_ready(),"healthy active CRC tail must not block CLEAR");
 check(channel.CNDTR==clear_remaining && mic_uart_tx.head==clear_head,"CLEAR never aborts DMA or rewrites queue");
 drain();equals({active_clear});
'''
    dma=dma.replace('int main(){','int main(){\n'+extra)
    dma_result=json.loads(common.compile_run(out,'clear_actual_DMA',dma))
    # Decode the native-produced record with the exact new HMI function.
    tree=ast.parse(p.read(p.OUT/'web_hmi/server.py'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('current_crc32c','clear_recovery_status')]
    ns={};exec(compile(ast.Module(body=nodes,type_ignores=[]),'release_HMI','exec'),ns)
    decode=ns['clear_recovery_status'];kv=dict(bp_fw_build=str(p.NEW[1]),mc_clear_recovery_hex=raw.hex())
    good=decode(kv)['clear_recovery'];assert good['available'] and good['result']=='ACK_ACCEPTED' and good['tx_pending']==1
    assert not good['protection_readiness_confirmed']
    for bit in range(43*8):
        bad=bytearray(raw);bad[bit//8]^=1<<(bit%8)
        assert not decode(dict(kv,mc_clear_recovery_hex=bad.hex()))['clear_recovery']['available']
    assert not decode(dict(kv,bp_fw_build='2026111604'))['clear_recovery']['available']
    # Preserve all guards/control/ADC/IRQ and the first/repeat Break record writers.
    old=sources['baseline'].replace('2026111603',str(p.NEW[0])).replace('2026111604',str(p.NEW[1]));new=sources['candidate']
    unchanged=('MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','uno_rearm_break_irq','uno_stop_motor',
        'mic_repeat_capture_arm','mic_repeat_break_irq','mic_bkin_prepare_record','uno_send_reply',
        'uno_tx_submit','uno_tx_tc_isr','uno_tx_watchdog','uno_clear_frame_is_safe','uno_transport_result')
    for name in unchanged:assert function(old,name)==function(new,name),name
    # Outside the CLEAR branch the command handler is exactly unchanged.
    assert function(old,'uno_handle_valid_frame').replace(branch(old),'CLEAR_BLOCK')==function(new,'uno_handle_valid_frame').replace(branch(new),'CLEAR_BLOCK')
    for rel in ('nucleo/Src/multi_native.c','nucleo/Src/current_shunt.c','nucleo/Src/mc_interface.c',
        'nucleo/Src/mc_tasks.c','nucleo/Src/stm32g4xx_mc_it.c','nucleo/Inc/foc_experiment.h','nucleo/Inc/motor_control.h'):
        assert p.read(p.BASE/rel).replace('2026111603',str(p.NEW[0])).replace('2026111604',str(p.NEW[1]))==p.read(p.OUT/rel),rel
    for rel,h in json.loads(p.read(p.OUT/'preserved_capture_hashes.json')).items():assert p.sha(p.ROOT/rel)==h,rel
    report=dict(passed=True,baseline_reproduction=outputs['baseline'],actual_CLEAR_branch=True,actual_ST_MCI_ACK=True,
        actual_DMA_driver=dma_result,guard_functions_unchanged=list(unchanged),HMI_CRC_bit_injections=344,
        first_attempt_record_immutable=True,MCSDK_rejected_ACK_keeps_latch=True,async_ACK_not_claimed_ready=True,
        hardware_commands=0,START=0,CLEAR=0,RESET=0,thresholds_changed=False,target_verified=False)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
