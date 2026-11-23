"""Streaming digital evidence: real PWM edges inside the marker, no analog claim."""
import csv,json,statistics
from pathlib import Path
def analyze(path):
 counts=[0]*3;periods=[[] for _ in range(3)];last_rise=[None]*3
 marker=[];sd_low=False;outside=False;previous=None;previous_t=None;end=None
 rows=0;nonzero_i2c_edges=0
 with Path(path).open(newline='') as f:
  it=csv.reader(f);header=next(it);norm=[''.join(c.lower() for c in x if c.isalnum()) for x in header]
  cols=[norm.index('channel'+str(c)) for c in range(8)]
  for row in it:
   if not row:continue
   t=float(row[0]);v=[int(row[c]) for c in cols];rows+=1
   if any(x not in (0,1) for x in v) or (previous_t is not None and t<previous_t):raise ValueError('Invalid digital CSV')
   if not v[5] or not v[6]:sd_low=True
   if not v[7] and any(v[:3]):outside=True
   if previous is not None:
    if v[7]!=previous[7]:marker.append((t,v[7]))
    if v[3]!=previous[3] or v[4]!=previous[4]:nonzero_i2c_edges+=1
    for ch in range(3):
     if v[7] and v[ch] and not previous[ch]:
      counts[ch]+=1
      if last_rise[ch] is not None:periods[ch].append(t-last_rise[ch])
      last_rise[ch]=t
   previous=v;previous_t=t;end=t
 if rows<2 or end is None:raise ValueError('Truncated capture')
 bounded=len(marker)==2 and marker[0][1]==1 and marker[1][1]==0
 duration=marker[1][0]-marker[0][0] if bounded else None
 hz=[1/statistics.median(x) if x else None for x in periods]
 expected=170000000/(2*5312)
 ok=(bounded and 2.99<=duration<=3.01 and not outside and not sd_low and nonzero_i2c_edges>100
     and all(47000<=c<=49000 for c in counts) and all(x is not None and abs(x-expected)<expected*.02 for x in hz))
 return dict(physical_edges_verified=ok,marker_transitions=marker,edge_window_s=duration,rising_edges=counts,
  median_carrier_hz=hz,PWM_outside_marker=outside,SD_low_observed=sd_low,I2C_edge_count=nonzero_i2c_edges,
  adc_phase_synchronization_proven=False,I2C_protocol_decoded=False,analog_signal_integrity_proven=False,
  motor_current_qualified=False,powered_inverter_cause_proven=False)
if __name__=='__main__':
 import sys
 print(json.dumps(analyze(sys.argv[1]),indent=2))
