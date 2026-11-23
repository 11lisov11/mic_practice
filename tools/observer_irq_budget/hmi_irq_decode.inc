def irq_breakdown_status(kv,fault):
    words=[int(kv.get('foc_runtime_w'+str(i),0)) for i in range(42,63)]
    if not all(0<=v<=0xffffffff for v in words):raise ValueError('IRQ counter outside uint32')
    names=('DMA2_BKIN','DMA1_UART_TX','USART1_CONTROL','ADC1_2','TIM1_UPDATE',
           'TIM1_BREAK','USART2_MCSDK','SysTick','EXTI_STOP')
    valid=words[20]
    if valid&~511:raise ValueError('IRQ valid mask')
    return {
        'available':bool(valid),
        'scope':'first_fault_inflight_window' if fault and fault.get('observer_inflight') else 'last_completed_observer_window',
        'window_us':((words[19]-words[18])&0xffffffff)/170,
        'valid_mask':valid,
        'handlers':[{'name':name,'valid':bool(valid&(1<<i)),
                     'completed_calls':words[2*i], 'inclusive_body_us':words[2*i+1]/170}
                    for i,name in enumerate(names)],
        'limitation':'Inclusive body times overlap under nesting: do not sum them as CPU utilisation. An in-flight IRQ is not yet counted; early-fault capture may mark an interrupted counter invalid. No safety threshold uses these diagnostics.'}
