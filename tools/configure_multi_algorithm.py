"""Stopped-only runtime model configuration. Never START, CLEAR, RESET or flash."""
import argparse,hashlib,json,math,struct,time,urllib.request
from pathlib import Path
from current_only_lab import get_status
from prepare_multi_algorithm import ROOT,NEW
FIELDS=('rs','rr','ls','lr','lm','j','b','poles','flux','current_limit','trip_current','current_bw','speed_bw')
def crc32c(data):
    value=0xffffffff
    for byte in data:
        value^=byte
        for _ in range(8):value=(value>>1)^(0x82f63b78 if value&1 else 0)
    return value^0xffffffff
def load(path):
    data=json.loads(path.read_text(encoding='utf-8-sig'));m=data['motor']
    for name in FIELDS:
        if type(m.get(name)) not in (int,float) or not math.isfinite(m[name]):raise ValueError(name+' missing/nonfinite')
    if type(m['poles']) is not int or not 1<=m['poles']<=8:raise ValueError('invalid poles')
    if any(m[k]<=0 for k in FIELDS if k not in ('b','poles')) or m['b']<0:raise ValueError('invalid SI parameters')
    if m['ls']*m['lr']<=1.0001*m['lm']**2 or m['flux']/m['lm']>=.95*m['current_limit']:raise ValueError('invalid inductance/current budget')
    if not 0<m['current_limit']<=1.1 or not m['current_limit']<m['trip_current']<=1.35:raise ValueError('current limits exceed candidate bounds')
    if m['current_bw']>=2000 or m['speed_bw']>=100:raise ValueError('bandwidth exceeds candidate bounds')
    qualification=0
    # A simulation profile cannot accidentally become physical qualification.
    if data.get('purpose')=='identified_physical_motor':
        for bit,key in enumerate(('motor_identification','physical_amp_scale','target_timing')):
            ev=data.get('evidence',{}).get(key)
            if not ev:continue
            p=(path.parent/ev['file']).resolve()
            if hashlib.sha256(p.read_bytes()).hexdigest()!=ev['sha256']:raise ValueError('Evidence hash mismatch: '+key)
            if key=='target_timing':
                t=json.loads(p.read_text());
                if t.get('pair')!=list(NEW) or t.get('physical_target_measured') is not True or not 0<t.get('fast_cycles',0)<5312:
                    raise ValueError('Timing evidence is not measured on this target pair')
            qualification|=1<<bit
    raw=b''.join(struct.pack('<I' if name=='poles' else '<f',m[name]) for name in FIELDS)
    return data,raw,qualification
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True)
    p.add_argument('--url',default='http://192.168.1.138:8080');p.add_argument('--execute-config-only',action='store_true')
    p.add_argument('--token-file',type=Path,default=ROOT/'.unoq_ssh/control_token');a=p.parse_args()
    data,raw,q=load(a.profile);crc=crc32c(raw)
    cmds=['MODEL 1 %d %08x'%(i,struct.unpack_from('<I',raw,4*i)[0]) for i in range(13)]
    cmds.append('MODEL 2 %d %08x'%(q,crc))
    print(json.dumps(dict(qualification=q,profile_crc=crc,commands=len(cmds),start_commands=0,
                         executable_for_powered_foc=q==7,executed=a.execute_config_only)))
    if not a.execute_config_only:return
    token=a.token_file.read_text().strip();opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for cmd in cmds:
        s=get_status(a.url)
        if tuple(s.get(k) for k in ('fw_build','mc_fw_build'))!=NEW or s.get('state')!='SAFE' or s.get('pwm')!=0 or not 0<=s.get('mc_age_ms',9999)<300:
            raise RuntimeError('Configuration requires this exact pair stopped, with fresh native telemetry')
        req=urllib.request.Request(a.url.rstrip('/')+'/api/cmd',data=json.dumps({'cmd':cmd}).encode(),
            headers={'Content-Type':'application/json','X-UNOQ-Control-Token':token},method='POST')
        with opener.open(req,timeout=3) as r:reply=json.load(r)
        if not reply.get('ok'):raise RuntimeError('Native model configuration rejected')
        time.sleep(.15)
    end=time.monotonic()+3
    while time.monotonic()<end:
        s=get_status(a.url)
        if s.get('algorithm_profile_crc')==crc and s.get('algorithm_qualification')==q:
            print('Native profile CRC acknowledged; no motor start sent');return
        time.sleep(.15)
    raise RuntimeError('Native profile CRC acknowledgement missing; no start permitted')
if __name__=='__main__':main()
