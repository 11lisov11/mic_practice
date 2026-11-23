"""Exercise installed recorder with changing adjacent GPIO bits and saved LOW runs.

Mocks register/DMA delivery, not electrical GPIO or individual DMA bus latency.
Never accesses a controller, resets it, or starts a motor.
"""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'artifacts/live_bench_20261018/uart_tx_dma_fix_r2'
OUT=ROOT/'artifacts/live_bench_20261018/sd_short_pulse_audit_r1'


def main():
    OUT.mkdir(exist_ok=False)
    src=(C/'nucleo/Src/main.c').read_text(encoding='utf-8-sig')
    a=src.index('static bool mic_bkin_dma_initialized;')
    b=src.index('\n\nstatic void mic_bkin_wave_packet',a)
    exact=src[a:b]
    (OUT/'firmware.inc').write_text(exact,encoding='utf-8')
    sim=(ROOT/'tools/bkin_fast_capture/sim.c').read_text()
    prefix=sim[:sim.index('static void dump(')]
    w=json.loads((ROOT/'artifacts/live_bench_20261018/uart_tx_dma_to_50_r2/decoded_wave.json').read_text())
    expected=','.join('{%d,%d}'%(x['level'],x['samples']) for x in w['runs'])
    code=prefix+'''
static void wordstep(unsigned count,unsigned word) {
  if(mic_bkin_capture_state!=MIC_BKIN_RUNNING)return;
  mic_bkin_ring[(count-1)&8191]=(uint16_t)word;
  channel.CNDTR=8192-(count&8191);sim_tick=count/5000;
  if(!(count&4095)) {dma.ISR|=(count&4096)?4:2;DMA2_Channel1_IRQHandler();dma.ISR&=~dma.IFCR;dma.IFCR=0;}
}
static uint32_t random_word=0x7131;
static unsigned next_word(void) {random_word=1664525U*random_word+1013904223U;return random_word;}
static const bp_run observed[]={'''+expected+'''};
int main(void) {
  for(unsigned phase=0;phase<8192;phase++) {
    reset();unsigned trigger=16384+phase;
    for(unsigned i=1;i<trigger+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      /* PA6 is always HIGH, every other stored input can change. */
      wordstep(i,next_word()|64U);
      if(i==trigger)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(mic_bkin_pulse.runs==1 && mic_bkin_pulse.run[0].level==1);
    assert(mic_bkin_pulse.flags==(BP_FROZEN|BP_POST_DONE|BP_NO_LOW));
    assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);++cases;
  }
  for(unsigned phase=0;phase<8192;phase+=127) {
    reset();unsigned trigger=20000+phase,origin=trigger-2048+1;
    unsigned j=0,run=0,remaining=observed[0].count;
    for(unsigned i=1;i<trigger+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      unsigned high=1;
      if(i>=origin && j<2369) {
        high=observed[run].level;++j;
        if(!--remaining && run+1<sizeof(observed)/sizeof(*observed))remaining=observed[++run].count;
      }
      wordstep(i,(next_word()&~64U)|(high?64U:0));
      if(i==trigger)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(mic_bkin_pulse.samples==2369 && mic_bkin_pulse.flags==519);
    assert(mic_bkin_pulse.runs==sizeof(observed)/sizeof(*observed));
    assert(!memcmp(mic_bkin_pulse.run,observed,sizeof(observed)));
    assert(bp_width(&mic_bkin_pulse)==2);++cases;
  }
  const unsigned widths[]={120,350};
  for(unsigned w=0;w<2;w++)for(unsigned phase=0;phase<8192;phase+=127) {
    reset();unsigned start=20000+phase;
    for(unsigned i=1;i<start+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      unsigned high=!(i>=start && i<start+widths[w]);
      wordstep(i,(next_word()&~64U)|(high?64U:0));
      if(i==start+2)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(bp_width(&mic_bkin_pulse)==widths[w]);
    assert(!(mic_bkin_pulse.flags&(BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW)));++cases;
  }
  printf("{\\"pass\\":true,\\"cases\\":%u,\\"constant_high_phases\\":8192,\\"observed_wave_replays\\":65,\\"long_pulse_replays\\":130}\\n",cases);
  return 0;
}
'''
    (OUT/'audit.c').write_text(code,encoding='utf-8')
    flags=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function',
           '-I',str(C/'nucleo/Inc'),'-I',str(C/'UNOQ_MOTOR')]
    def compile_and_run(folder):
        p=subprocess.run(flags+[str(folder/'audit.c'),'-o',str(folder/'audit.exe')],cwd=folder,capture_output=True,text=True)
        (folder/'compile.log').write_text(p.stdout+p.stderr)
        if p.returncode:raise RuntimeError('C audit compile failed: '+p.stderr[-1800:])
        p=subprocess.run([str(folder/'audit.exe')],cwd=folder,capture_output=True,text=True,timeout=45)
        (folder/'run.log').write_text(p.stdout+p.stderr)
        return p
    result=compile_and_run(OUT)
    if result.returncode:raise RuntimeError('Recorder audit failed: '+result.stderr[-1800:])
    measured=json.loads(result.stdout)
    mutant=OUT/'wrong_gpio_bit';mutant.mkdir()
    (mutant/'audit.c').write_text(code)
    (mutant/'firmware.inc').write_text(exact.replace('&GPIO_PIN_6','&128U'))
    bad=compile_and_run(mutant)
    assert bad.returncode!=0 and 'Assertion' in bad.stderr
    report=dict(pass_=True,recorder=measured,wrong_bit_negative_control_detected=True,
        exact_installed_recorder_source=True,hardware_commands=0,
        conclusion='Changing adjacent GPIO bits does not create LOW on PA6 in actual C processing; recorded runs replay identically, and 24/70-us synthetic pulses do not compress to 0.4 us.',
        limitations=['Mocked DMA is supplied correct input words; this does not qualify real DMA service timing or prove analog GPIO integrity.',
                     'No hardware fault source has been uniquely identified.'])
    report['pass']=report.pop('pass_')
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
