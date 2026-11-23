"""Schema3 decoder addition; schema2 historic records remain readable."""
import json
import prepare_observer_current_window as p
def main():
    f=p.OUT/'web_hmi/server.py';s=p.read(f)
    a=s.index('def decode_observer_trace_hex(');b=s.index('\ndef with_observer_trace(',a)
    old=s[a:b]
    n=old.replace("if len(raw)!=1832:","if len(raw) not in (1832,1888):")
    n=n.replace("if (magic,schema,fw,size,capacity)!=(0x3144534f,2,expected,136,12) or not 1<=count<=12 or not 0<=oldest<12:",
        "if magic!=0x3144534f or fw!=expected or (schema,size,capacity,stride,len(raw)) not in ((2,136,12,455,1832),(3,152,11,500,1888)) or not 1<=count<=capacity or not 0<=oldest<capacity:")
    n=n.replace(' or stride!=455:',':')
    n=n.replace("u=struct.unpack_from('<8I14f2I6f4I',raw,offset)","u=struct.unpack_from('<8I14f2I6f4I'+('3If' if schema==3 else ''),raw,offset)")
    n=n.replace('        return dict(cycles=', '        result=dict(cycles=')
    anchor='endpoint_arr=u[33]>>16)'
    assert n.count(anchor)==1
    n=n.replace(anchor,anchor+'''
        if schema==3:
            center,first,num,forecast=u[34:38]
            if num!=16 or not math.isfinite(forecast) or not 0<=forecast<=.001:
                raise ValueError('observer averaged window metadata')
            center_age=(center-first)&0xffffffff;end_age=(adc-first)&0xffffffff
            if not (0<center_age<=end_age<340000):
                raise ValueError('observer window clock order')
            result.update(observation_cycles=center,window_first_cycles=first,window_count=num,
                forecast_dt_s=forecast,published_estimate_cycles=bin_tick,
                observer_input_kind='mean16_at_center_RK4_forecast_to_endpoint')
        else:result.update(observer_input_kind='instantaneous_endpoint_current')
        result.update(innovation_kind='sequential_conditional',
            conditional_predicted_current_A=[ia-u[26],ib-u[27]])
        return result''')
    n=n.replace('rows=[sample(64+136*((oldest+i)%12)) for i in range(count)]','rows=[sample(64+size*((oldest+i)%capacity)) for i in range(count)]')
    n=n.replace('first=sample(64+136*12) if loss else None','first=sample(64+size*capacity) if loss else None')
    n=n.replace("limitation='Ток/Id/Iq", "limitation=('Schema3: токи усреднены по16 ADC; EKF корректируется в центре, в регулятор публикуется RK4-прогноз на конец окна. Raw токовая защита не усредняется. Скорость не подтверждена независимым датчиком.' if schema==3 else 'Ток/Id/Iq")
    n=n.replace("измерена.')", "измерена.'))")
    s=s[:a]+n+s[b:];p.write(f,s)
    # Preserve the installed long-RPC-admission fix byte-for-byte outside this decoder.
    baseline=p.read(p.HMI/'web_hmi/server.py').replace('2026111609',str(p.NEW[0])).replace('2026111606',str(p.NEW[1]))
    ba=baseline.index('def decode_observer_trace_hex(');bb=baseline.index('\ndef with_observer_trace(',ba)
    assert s[:a]==baseline[:ba] and s[a+len(n):]==baseline[bb:]
    print('Schema3 added; historic schema2 and HMI RPC patch retained')
if __name__=='__main__':main()
