"""Exercise actual TX driver, old HAL failure, UART protections and BKIN recorder."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r1'
BASE=ROOT/'artifacts/live_bench_20261018/sd_live_diagnostics_r1'

def read(p):return p.read_text(encoding='utf-8-sig')
def body(source,name):
    m=re.search(r'(?m)^(?:static )?(?:void|bool|uint\d+_t|int\d+_t|HAL_StatusTypeDef)\s+'+re.escape(name)+r'\([^;]*?\)\s*\{',source)
    assert m,name
    depth=1;end=m.end()
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[m.start():end]

def main():
    global C
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,default=C)
    args=p.parse_args();C=args.candidate.resolve()
    pair=json.loads((C/'manifest.json').read_text(encoding='utf-8'))['pair_compatibility_ids']
    work=C/'selftest';work.mkdir(exist_ok=True);checks=[]
    def check(value,name):
        checks.append(dict(name=name,pass_=bool(value)))
        if not value:raise AssertionError(name)
    def run(cmd,label):
        p=subprocess.run(cmd,cwd=work,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (work/(label+'.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if p.returncode:raise RuntimeError(label+': '+(p.stderr or p.stdout)[-2500:])
        return p.stdout
    source=read(C/'nucleo/Src/main.c');old=read(BASE/'nucleo/Src/main.c')
    a=source.index('/* USART1 TX owns DMA1 channel 1');b=source.index('\nstatic bool uno_rx_push',a)
    driver=source[a:b].strip()+'\n'
    check(driver==read(ROOT/'tools/uart_tx_dma/driver.inc'),'test compiles exact embedded DMA driver')
    (work/'driver.inc').write_text(driver,encoding='utf-8')
    hal=read(BASE/'nucleo/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_uart.c')
    (work/'old_hal_transmit.inc').write_text(body(hal,'HAL_UART_Transmit')+'\n',encoding='utf-8')
    cpp=work/'driver_test.cpp';cpp.write_text(read(ROOT/'tools/uart_tx_dma/driver_test.cpp'),encoding='utf-8')
    exe=work/'tx_driver.exe'
    flags=['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror']
    run(flags+['-I',str(C/'nucleo/Inc'),str(cpp),'-o',str(exe)],'tx_compile')
    tx=json.loads(run([str(exe)],'tx_run'))
    check(tx['pass'] and tx['old_prefix_bytes']==39 and tx['dma_stress_frames']==2048,'old truncation reproduced and actual DMA sender stress passes')
    # Negative controls: removing the non-abort rule, TC length check,
    # CRC-tail ownership or PWM shutdown must fail real driver tests.
    mutations=[('abort_on_timeout','++mic_uart_tx.timeouts;failure=HAL_TIMEOUT;','++mic_uart_tx.timeouts;failure=HAL_TIMEOUT;DMA1_Channel1->CCR &= ~DMA_CCR_EN;'),
        ('early_tc_advance','if(DMA1_Channel1->CNDTR!=0U) {','if(false) {'),
        ('missing_crc_tail','DMA1_Channel1->CNDTR=UV3_FRAME;','DMA1_Channel1->CNDTR=UV3_FRAME-4;'),
        ('no_DMA_error_stop','LL_TIM_DisableAllOutputs(TIM1);','/* removed */'),
        ('raised_TX_deadline','>UNO_REPLY_TIMEOUT_MS)', '>50U)'),
        ('clock_before_lock','  int failure=HAL_OK;\n  uno_tx_lock();','  const uint32_t stale_clock=HAL_GetTick();\n  int failure=HAL_OK;\n  uno_tx_lock();')]
    for name,a,b in mutations:
        assert driver.count(a)==1,name
        folder=work/name;folder.mkdir(exist_ok=True)
        mutant_driver=driver.replace(a,b)
        if name=='clock_before_lock':mutant_driver=mutant_driver.replace('const uint32_t now_ms=HAL_GetTick();','const uint32_t now_ms=stale_clock;')
        (folder/'driver.inc').write_text(mutant_driver,encoding='utf-8')
        (folder/'old_hal_transmit.inc').write_text(body(hal,'HAL_UART_Transmit')+'\n',encoding='utf-8')
        mutant=folder/'driver_test.cpp';mutant.write_text(read(cpp),encoding='utf-8')
        binary=folder/'mutant.exe'
        run(flags+['-I',str(C/'nucleo/Inc'),str(mutant),'-o',str(binary)],name+'_compile')
        p=subprocess.run([str(binary)],cwd=folder,capture_output=True,text=True)
        (folder/'run.log').write_text(p.stdout+p.stderr,encoding='utf-8')
        check(p.returncode!=0 and 'FAIL ' in p.stderr,'negative control detected '+name)
    # Same command parser/receiver test, including 5/15/300-ms guards and D3.
    contract=work/'uart_contract.exe'
    run(flags+['-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(ROOT/'tools/uart_resync_fix/contract_test.cpp'),'-o',str(contract)],'uart_compile')
    uart=json.loads(run([str(contract)],'uart_run'));check(uart['pass'],'UART CRC/replay/hard-error/300-ms watchdog contracts retained')
    a=source.index('static bool mic_bkin_dma_initialized;');b=source.index('\n\nstatic void mic_bkin_wave_packet',a)
    (work/'firmware.inc').write_text(source[a:b],encoding='utf-8')
    (work/'sim.c').write_text(read(ROOT/'tools/bkin_fast_capture/sim.c'),encoding='utf-8')
    sim=work/'bkin.exe'
    run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR'),str(work/'sim.c'),'-o',str(sim)],'bkin_compile')
    bkin=json.loads(run([str(sim)],'bkin_run'));check(bkin['pass'] and bkin['host_cases']==450,'450 actual BKIN capture/receiver cases retained')
    # Compare every protection and GPIO setup source, allowing only identities
    # and explicitly listed TX integration functions to change.
    for tree in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR'):
        for p in (BASE/tree).rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(BASE)
            if rel.as_posix()=='nucleo/Src/main.c':continue
            expected=read(p).replace('2026101809',str(pair[0])).replace('2026101808',str(pair[1]))
            check(read(C/rel)==expected,'unchanged '+str(rel))
    functions=set(re.findall(r'(?m)^static (?:void|bool|uint\d+_t) (uno_\w+)\([^;]*?\)\s*\{',old))
    for name in functions-{'uno_send_reply','uno_handle_valid_frame','uno_link_poll'}:
        check(body(old,name)==body(source,name),'unchanged motor/receive function '+name)
    check(body(source,'USART1_IRQHandler').replace('  uno_tx_tc_isr();\n','')==body(old,'USART1_IRQHandler'),'RX ISR unchanged before appended TX completion service')
    check('UNO_REPLY_TIMEOUT_MS = 5U' in source and 'HAL_UART_Transmit(&huart1' not in source,'same TX deadline without blocking partial-frame sender')
    check('if(!uno_tx_clear_ready())' in body(source,'uno_handle_valid_frame'),'CLEAR refuses active or failed TX')
    poll=body(source,'uno_link_poll')
    check('uno_tx_watchdog' in poll and 'uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_TX)' in poll,'TX watchdog reaches real motor STOP/fault latch')
    # New identity accepts both existing and new SD records; calibration stays.
    spec=importlib.util.spec_from_file_location('tx_dma_hmi',C/'web_hmi/server.py')
    hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
    check(hmi.manual_scalar_supported(dict(fw_build=pair[0],mc_fw_build=pair[1],manual_scalar_capable=1)),
          'manual scalar accepts generated exact pair')
    check(not hmi.manual_scalar_supported(dict(fw_build=pair[0],mc_fw_build=pair[1],manual_scalar_capable=0)),
          'manual scalar still requires MCU capability')
    check(not hmi.manual_scalar_supported(dict(fw_build=pair[0],mc_fw_build=0,manual_scalar_capable=1)),
          'manual scalar rejects mismatched pair')
    for build in (2026101808,pair[1]):
        sd=hmi.sd_live_status(dict(mc_fw_build=build,mc_age_ms=20,bp_temp_flags=189))
        check(sd['available'] and sd['level']=='HIGH' and sd['config_ok'],'live SD for peer '+str(build))
    raw=(work/'fatal.bin').read_bytes()
    check(hmi.uart_reject_status(dict(mc_fw_build=pair[1],mc_uart_reject_hex=raw.hex()))['available'],'new D3 decoded independently')
    oldcal=dict(fw_build=2026101809,mc_fw_build=2026101808,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    check(hmi._vbus_calibration_identity_matches(oldcal,dict(oldcal,fw_build=pair[0],mc_fw_build=pair[1])),'calibration identity preserved')
    run(['node','--check',str(C/'web_hmi/static/app.js')],'browser_syntax')
    report=dict(pass_=True,checks=len(checks),details=checks,tx=tx,uart=uart,bkin=bkin,
        mutation_controls=len(mutations),hardware_commands=0,active_motor_test=False,
        limitations=['A synthetic main-thread stall reproduces the observed old HAL prefix; actual scheduling delay at the earlier event was not measured',
            'DMA configuration and behavior require readback/idle and powered-load checks after installation'])
    report['pass']=report.pop('pass_');(work/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('pass','checks','tx','uart','bkin','mutation_controls','hardware_commands')}))

if __name__=='__main__':main()
