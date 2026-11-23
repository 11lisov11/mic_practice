"""Summarize and plot a saved staged V/f run without device access."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir',type=Path,required=True)
    p.add_argument('--operator-confirms-smooth-speed-changes',action='store_true')
    args=p.parse_args();out=args.outdir.resolve(strict=True)
    report=json.loads((out/'report.json').read_text(encoding='utf-8'))
    rows=sorted(json.loads((out/'samples.json').read_text(encoding='utf-8')),key=lambda x:x['host_monotonic_s'])
    active=[x for x in rows if x['status'].get('pwm')==1]
    if not active:raise RuntimeError('No active telemetry samples')
    slots=json.loads((out/'after_break_snapshot.json').read_text(encoding='utf-8'))['data']['mc_break_snapshots']
    if args.operator_confirms_smooth_speed_changes:
        report.update(physical_rotation_confirmed=True,speed_changes_confirmed=True,
            operator_observation='User confirmed smooth rotation and both visible speed changes in this run.')
    targets=report['requested_targets_hz']
    if report['pass']:
        assert [x['target_hz'] for x in report['settled_steps']]==targets
        assert all(x['status']['mc_frequency_reference_valid']==1 for x in active)
    s0,s1=report['before'],report['final_status']
    fatal=('mc_bad_cnt','mc_bad_integrity','mc_bad_sequence','mc_uart_error_flags','mc_transport_fault','uno_rx_dropped')
    summary={'pass':report['pass'],'targets_requested_hz':targets,
        'targets_settled_hz':[x['target_hz'] for x in report['settled_steps']],
        'active_bus_min_v':min(x['status']['vdc'] for x in active),
        'active_bus_max_v':max(x['status']['vdc'] for x in active),
        'active_temperature_min_c':min(x['status']['bp_temp_c'] for x in active),
        'active_temperature_max_c':max(x['status']['bp_temp_c'] for x in active),
        'uno_noise_advisory_before':s0['uno_rx_hw_errors'],'uno_noise_advisory_after':s1['uno_rx_hw_errors'],
        'new_uno_noise_advisories':s1['uno_rx_hw_errors']-s0['uno_rx_hw_errors'],
        'fatal_telemetry_max':{k:max(x['status'].get(k,0) for x in active) for k in fatal},
        'all_samples_diagnostics_max':{k:max(x['status'].get(k,0) for x in rows) for k in fatal},
        'break_recorded':any(x.get('captured') for x in slots),
        'active_observed_span_s':active[-1]['host_monotonic_s']-active[0]['host_monotonic_s'],
        'active_samples':len(active),'outputs_off_confirmed':report['outputs_off_confirmed'],
        'physical_rotation_confirmed':report['physical_rotation_confirmed'],
        'speed_changes_confirmed':report['speed_changes_confirmed'],
        'decel_bus_hold_samples':sum(x['status'].get('mc_decel_bus_hold',0) for x in active)}
    report['telemetry_summary']=summary
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    t=[x['host_monotonic_s']-report['start_monotonic_s'] for x in rows]
    fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True)
    axes[0].plot(t,[x['status']['mc_frequency_reference_hz'] if x['status'].get('mc_frequency_reference_valid')==1 else None for x in rows],'.-',color='#008b87',label='Valid controller field reference')
    axes[0].step(t,[x['status']['freq_cmd'] for x in rows],where='post',color='#555555',ls='--',label='Command')
    axes[0].set_ylabel('Field frequency (Hz)');axes[0].legend(loc='best')
    axes[1].plot(t,[x['status']['vdc'] for x in rows],'.-',color='#a75c00');axes[1].set_ylabel('DC bus (V)')
    axes[2].step(t,[x['status']['uno_rx_hw_errors'] for x in rows],where='post',label='Cumulative Uno NOISE advisory',color='#a75c00')
    axes[2].step(t,[x['status']['mc_bad_cnt'] for x in rows],where='post',label='Nucleo command rejection count',color='#a33333')
    axes[2].plot(t,[x['status']['mc_bad_integrity'] for x in rows],label='Uno reply integrity rejections',color='#555555',ls='--')
    axes[2].set_ylabel('Diagnostic count');axes[2].legend(loc='best')
    fault=next((x for x in rows if x['status'].get('bp_fault',0)!=0),None)
    for ax in axes:
        ax.grid(alpha=.2)
        if fault:ax.axvline(fault['host_monotonic_s']-report['start_monotonic_s'],color='#a33333',ls=':',lw=1)
    axes[-1].set_xlabel('Host HTTP response time relative to START request (s)')
    desc=' -> '.join(str(x) for x in targets)
    if len(targets)>5:desc=f'{targets[0]} to {targets[-1]} Hz, staged'
    fig.suptitle('Online V/f '+desc+' Hz: '+('targets reached' if report['pass'] else 'incomplete')+', STOP '+('confirmed' if report['outputs_off_confirmed'] else 'unconfirmed'),fontweight='bold')
    fig.text(.08,.014,'Controller reference is not measured rotor speed. All cumulative NOISE advisories remain visible.',fontsize=8)
    fig.tight_layout(rect=(0,.045,1,.96));fig.savefig(out/'run_summary.png',dpi=150);plt.close(fig)
    print(json.dumps(summary))
if __name__=='__main__':main()
