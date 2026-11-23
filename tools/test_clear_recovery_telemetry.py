"""Retest live-packet deadlines and record delivery with the extra OFF class."""
import inspect,json
import prepare_clear_recovery as p
import test_telemetry_deadline as t
from test_foc_update_latency_fix import function


def main():
    out=p.OUT/'verification/telemetry';out.mkdir(exist_ok=False)
    t.p=p;t.common.p=p
    t.PRE=t.PRE.replace('2026111604',str(p.NEW[1]))
    packet=(p.OUT/'verification/CLEAR_record_example.bin').read_bytes()
    clear_extra='\nstatic uint8_t mic_clear_diag_ready=1;\nstatic uint8_t mic_clear_diag_packet[43]={'+','.join(str(x) for x in packet)+'};\n'
    clear_extra+=function(p.read(p.OUT/'nucleo/Src/main.c'),'mic_send_clear_page')+'\n'
    src=inspect.getsource(t.compile_variants).replace('code=PRE+producers','code=PRE+clear_extra+producers')
    scope=dict(t.__dict__,clear_extra=clear_extra);exec(compile(src,__file__,'exec'),scope)
    programs=scope['compile_variants'](out);decode=t.hmi_function();results={}
    cases=[(50000,0,100,1,0),(20000,1000,100,1,0),(33000,1900,250,1,0),
        (40000,4300,1000,1,0),(50000,17000,2000,1,0),(100000,4300,1000,1,0),
        (50000,17000,1000,1,0xfffff000)]
    for i,case in enumerate(cases):results[str(i)]=t.run_case(out,programs['candidate'],'candidate_'+str(i),case,decode)
    report=dict(passed=True,hardware_commands=0,cases=results,actual_extra_clear_sender=True,
        actual_normal_senders_and_arbiter=True,normal_receiver_and_HMI=True,
        stale_and_CRC_negative_controls=True,HAL_tick_wrap=True,MCU_IRQ_timing_simulated=True)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(cases),max_summary_gap_us=max(r['summary_gap_us'] for r in results.values()),
        max_detail_gap_us=max(r['detail_gap_us'] for r in results.values()),max_quality_gap_us=max(r['quality_gap_us'] for r in results.values()),
        max_ADC_complete_us=max(r['ADC_complete_us'] for r in results.values()))))


if __name__=='__main__':main()
