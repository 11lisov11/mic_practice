"""Render saved DMA evidence only; no connection or motor-control operations."""
import importlib.util
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('pulse_evidence_decoder',ROOT/'artifacts/live_bench_20261018/bkin_full_pulse_r1/web_hmi/server.py')
hmi=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hmi;spec.loader.exec_module(hmi)
status=json.loads((HERE/'final_status.json').read_text(encoding='utf-8'))
d=hmi.bkin_wave_status(status)
api=json.loads((HERE/'bkin_trace.json').read_text(encoding='utf-8'))['data']
for key in ('schema','pulse_width_us','runs','pulse_complete','dma_error','sampling_overrun'):
    assert d[key]==api[key],key
assert d['pulse_complete'] and d['post_complete'] and d['pulse_width_us']==18696
(HERE/'decoded_wave.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
fig,axes=plt.subplots(3,1,figsize=(10,7),gridspec_kw={'height_ratios':[2,1,1]})
x=[];y=[]
for run in d['runs']:
    x.extend([run['from_us'],run['to_us']]);y.extend([run['level'],run['level']])
for ax in axes:
    ax.plot(x,y,color='#007a8a',lw=2)
    ax.set_ylim(-.2,1.4);ax.set_yticks([0,1],['LOW','HIGH'])
    ax.grid(alpha=.2);ax.axvline(0,color='#d17300',ls=':',lw=1,label='Break IRQ reference')
    ax.set_ylabel('PA6 / SD')
axes[0].set_xlim(-100,18820)
axes[0].annotate('LOW = 18.696 ms (18,696 samples)',xy=(9347,0),xytext=(9347,.6),ha='center',fontsize=12,
    arrowprops={'arrowstyle':'->','color':'#333333'})
axes[0].set_title('J4-only, J1 OFF, PWM OFF: complete captured PA6 pulse',loc='left',fontweight='bold')
axes[1].set_xlim(-12,12);axes[1].set_title('Falling edge: sample position -1 us',loc='left')
axes[2].set_xlim(18683,18707);axes[2].set_title('Recovery edge: sample position +18,695 us',loc='left')
axes[-1].set_xlabel('Time relative to Break IRQ reference (us); sampling step 1 us')
fig.text(.1,.012,'No clipping, timeout, DMA error, or sampling overrun. Only digital PA6 measured; physical fault source unconfirmed.',fontsize=9)
fig.tight_layout(rect=(0,.035,1,1));fig.savefig(HERE/'bkin_full_pulse.png',dpi=160);plt.close(fig)
print(json.dumps({'validated_saved_record':True,'pulse_width_us':d['pulse_width_us'],'plot':str(HERE/'bkin_full_pulse.png')}))
