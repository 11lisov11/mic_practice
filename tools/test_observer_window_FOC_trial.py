"""Actual1611/1612 trial flow over mocked HTTP, with no socket connections."""
import contextlib,copy,io,json,socket,sys
from pathlib import Path
from unittest.mock import patch
import run_observer_window_FOC_trial as run
from configure_multi_algorithm import crc32c

class Response:
    def __init__(self,obj):self.raw=json.dumps(obj).encode()
    def __enter__(self):return io.BytesIO(self.raw)
    def __exit__(self,*args):return False
class Thread:
    def __init__(self,target,**kw):self.target=target
    def start(self):self.target()
    def join(self,**kw):pass
class Timer:
    def __init__(self,*a,**kw):pass
    def start(self):pass
    def cancel(self):pass
class Heart:
    def __init__(self,request):self.request=request;self.sent=0
    def start(self):self.request('/api/operator-heartbeat',{},timeout=2);self.sent+=1
    def healthy(self):return True
    def stop(self):pass
    def snapshot(self):return dict(sent=self.sent,error=None,mocked=True)

class Network:
    def __init__(self,base,scenario,observer):
        self.s=copy.deepcopy(base);self.scenario=scenario;self.calls=[];self.started=False;self.stopped=False;self.reads=0
        self.s.update(vdc=320.,bp_vdc=320.,algorithm_selected=1,algorithm_requested=1)
        self.observer=observer
        # Synthetic CRC-valid ADC container, never passed off as physical data.
        adc=bytearray(1024);adc[:4]=b'APC1';adc[8:12]=(2026111612).to_bytes(4,'little')
        adc[60:64]=crc32c(adc).to_bytes(4,'little');self.adc=adc.hex()
        if scenario=='BIE_blocked':self.s['mc_sd_live']['break_irq_enabled']=False
        if scenario=='CPU4001':self.s['algorithm_fast_cycles']=4001
    def open(self,request,timeout=None):
        path=request.full_url.split(':8080',1)[1];body=json.loads(request.data) if request.data else None
        self.calls.append((path,body))
        if path=='/api/algorithm':
            assert not self.started and body=={'algorithm':2};self.s.update(algorithm_selected=2,algorithm_requested=2)
            return Response(dict(ok=True))
        if path=='/api/cmd':
            assert body['cmd']!='CLEAR','This test has no CLEAR authorization'
            assert body['cmd'] in ('MODE VF','SET RUNMODE BOUNDED','SET ACCEL 5','SET DECEL 1','SET RUNLIMIT 5','SET FREQ 5')
            if body['cmd']=='SET FREQ 5':self.s['freq_cmd']=5
            return Response(dict(ok=True))
        if path=='/api/operator-heartbeat':return Response(dict(ok=True))
        if path=='/api/hv-arm':return Response(dict(ok=True))
        if path=='/api/start-sequence':
            assert not self.started and body=={'manual':False,'runlimit_s':5.0};self.started=True
            return Response(dict(ok=True))
        if path=='/api/stop-sequence':self.stopped=True;return Response(dict(ok=True))
        assert path=='/api/status',path
        s=copy.deepcopy(self.s);self.s['uno_rx_count']+=4;self.s['mc_good_cnt']+=4
        # Native tick is in the CRC-protected boot packet (not its early-boot CRC).
        packet=bytearray.fromhex(s['mc_boot_packet_hex']);tick=int.from_bytes(packet[34:38],'little')+50
        packet[34:38]=tick.to_bytes(4,'little');packet[39:]=crc32c(packet[:39]).to_bytes(4,'little')
        s['mc_boot_packet_hex']=packet.hex();s['native_boot']['native_tick_ms']=tick
        self.s['mc_boot_packet_hex']=s['mc_boot_packet_hex'];self.s['native_boot']['native_tick_ms']=tick
        if self.scenario=='RPC_new_timeout' and len(self.calls)>3:s['rpc_response_timeouts']+=1
        if self.started:
            self.reads+=1;s.update(run_id=1,run_start_ms=1000)
            s['foc_runtime']['source']='runtime_observer';s['foc_runtime']['observer_steps']=5000
            s.update(mc_adc_peak_complete=1,mc_adc_peak_hex=self.adc,
                mc_observer_trace_complete=1,mc_observer_trace_hex=self.observer,mc_observer_trace_bad=0)
            if self.scenario=='runtime_fault':
                s.update(algorithm_fault=3,mc_fault_current_mask=128,mc_fault_occurred_mask=128,run_reason=2,run_elapsed_ms=99)
            elif self.reads==1 and not self.stopped:
                s.update(state='FOC_RUN',pwm=1,bp_status=0x22,run_elapsed_ms=1000)
            else:s.update(foc_experiment_flags=5,run_elapsed_ms=5000,run_reason=1)
        return Response(dict(ok=True,data=s))

def main():
    p=run.package;out=p.OUT/'verification/trial_runner_20261117_r1';out.mkdir(exist_ok=False)
    run.package_check()
    baseline=json.loads(p.read(p.OUT/'one_CLEAR_deenergized_after_Uno_boot_20261117_r2/final_status.json'))
    model=(p.OUT/'verification/candidate_nominal.bin').read_bytes();assert len(model)==1888
    scenarios={};core=run.runner.driver.trial
    for scenario in ('success','BIE_blocked','CPU4001','RPC_new_timeout','runtime_fault'):
        network=Network(baseline,scenario,model.hex());clock=[0.]
        def now():clock[0]+=.2;return clock[0]
        dest=out/scenario
        argv=['run_observer_window_FOC_trial.py','--confirm-autonomous-powered','--outdir',str(dest)]
        with patch.object(socket.socket,'connect',side_effect=AssertionError('No real network')),\
             patch.object(sys,'argv',argv),patch.object(core.urllib.request,'build_opener',return_value=network),\
             patch.object(core.threading,'Thread',Thread),patch.object(core.threading,'Timer',Timer),\
             patch.object(core,'TrialHeartbeat',Heart),patch.object(core.time,'monotonic',side_effect=now),\
             patch.object(core.time,'sleep',return_value=None),contextlib.redirect_stdout(io.StringIO()):
            try:rc=run.main()
            except (AssertionError,RuntimeError):rc=1
        starts=sum(path=='/api/start-sequence' for path,body in network.calls)
        clears=sum(path=='/api/cmd' and body=={'cmd':'CLEAR'} for path,body in network.calls)
        stops=sum(path=='/api/stop-sequence' for path,body in network.calls)
        assert starts<=1 and clears==0
        if scenario=='success':
            assert rc==0 and starts==1 and stops>=1
            r=json.loads(p.read(dest/'report.json'));assert r['passed'] and r['Uno_limit_done']
            assert r['observer_record_audit']['bytes']==1888 and r['ADC_record_received']
        elif scenario=='runtime_fault':assert rc==1 and starts==1 and stops>=1
        else:assert rc==1 and starts==0
        scenarios[scenario]=dict(passed=True,simulated_START=starts,simulated_CLEAR=clears,simulated_STOP=stops)
    report=dict(passed=True,network_fully_mocked=True,hardware_commands=0,START=0,CLEAR=0,
        scenarios=scenarios,observer_schema3_collected=True,all_protection_limits_unchanged=True,
        synthetic_ADC_fixture_not_physical_data=True,model_observer_fixture_not_physical_data=True)
    p.write(out/'report.json',json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
