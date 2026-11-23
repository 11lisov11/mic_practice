"""Assess sensor reliability separately from successful motor START/STOP."""
import argparse,json,statistics
from pathlib import Path

def assess(folder):
 r=json.loads((folder/'report.json').read_text(encoding='utf-8-sig'))
 ext=folder/'release_capture_result.json'
 end=json.loads(ext.read_text(encoding='utf-8-sig')).get('final',{}) if ext.exists() else {}
 end=end or r.get('final_status',{})
 before=r.get('before',{})
 samples=[x['status'] for x in r.get('samples',[]) if x.get('status',{}).get('pwm')==1]
 error_delta=end.get('enc_errors',-1)-before.get('enc_errors',0)
 bus_clean=(bool(samples) and error_delta==0 and all(s.get('enc_bus_ok')==1 and s.get('enc_errors')==before.get('enc_errors') and 0<=s.get('enc_age_ms',9999)<100 for s in samples))
 field_good=bool(samples) and all(type(s.get('enc_status')) is int and s['enc_status']&0x38==0x20 for s in samples)
 angle_good=field_good and all(s.get('enc_ok')==1 for s in samples)
 speed_good=bool(samples) and all(s.get('enc_speed_ok')==1 for s in samples)
 speeds=[s['enc_rpm'] for s in samples if type(s.get('enc_rpm')) in (float,int) and s.get('enc_speed_ok')==1]
 uart_clean=all(end.get(k)==0 for k in ('mc_bad_cnt','mc_uart_error_flags','mc_transport_fault'))
 timed_stop=(r.get('outputs_off_confirmed') is True and r.get('completion',{}).get('run_limit_ms')==5000 and r.get('completion',{}).get('run_reason')==1 and 5000<=r.get('completion',{}).get('run_elapsed_ms',-1)<=5100)
 sensor_pass=(r.get('passed') is True and len(samples)>=2 and bus_clean and angle_good and speed_good and uart_clean and timed_stop)
 return dict(schema='mic_ai.as5600_dir_comparison.v1',motor_trial_passed=r.get('passed') is True,outputs_off_confirmed=r.get('outputs_off_confirmed') is True,
  MCU_five_second_stop_confirmed=timed_stop,AS5600_under_PWM_passed=sensor_pass,AS5600_errors_delta=error_delta,active_samples=len(samples),
  I2C_clean_during_recorded_PWM_samples=bus_clean,magnetic_flags_valid_during_PWM=field_good,angle_valid_during_PWM=angle_good,speed_valid_during_PWM=speed_good,
  sensor_RPM_min=min(speeds) if speeds else None,sensor_RPM_median=statistics.median(speeds) if speeds else None,sensor_RPM_max=max(speeds) if speeds else None,
  I2C_fault_categories={k:end.get(k) for k in ('enc_health_nack','enc_health_busy','enc_health_deadline','enc_health_arlo','enc_health_berr_clears')},
  UART_clean=uart_clean,old_SD_waveform_preserved=before.get('mc_break_wave_hex')==end.get('mc_break_wave_hex'),
  compared_previous_configuration_errors=249,DIR_alone_proven_cause=False,
  limitations=['One5Hz trial cannot qualify every speed or FOC','DIR bias,TP23 removal and mechanical sensor positioning changed since comparison baseline','Digital sensor replies do not establish analog signal integrity'])

def main():
 ap=argparse.ArgumentParser();ap.add_argument('trial',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 result=assess(a.trial);a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
