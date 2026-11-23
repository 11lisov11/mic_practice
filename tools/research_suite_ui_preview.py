"""Local UI fixtures. No connection to a board; all POST requests are recorded stubs."""
import importlib.util,json,time
from http.server import SimpleHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import prepare_research_suite as package

OUT=package.ROOT/'output/playwright/research_suite'
OUT.mkdir(parents=True,exist_ok=True)
base=json.loads((package.BASE/'idle_verification_r1/samples.json').read_text(encoding='utf-8'))[-1]
spec=importlib.util.spec_from_file_location('preview_catalog',package.OUT/'web_hmi/server.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
state={'scenario':'ready','quit':False}

def fixture():
    s=dict(base,fw_build=package.NEW[0],mc_fw_build=package.NEW[1],research_native_valid=1,research_native_caps=1,
        research_native_good=10,research_native_bad=0,state='SAFE',pwm=0,estop=0,mc_fault=0,bp_fault=0,
        mc_transport_fault=0,bp_transport_fault=0,mc_fault_current_mask=0,mc_fault_occurred_mask=0,
        mc_fault_reason=0,mc_fault_detail='',freq_cmd=5.,freq=5.,vdc=320.,bp_vdc=320.,
        mc_frequency_reference_valid=1,mc_frequency_reference_hz=0.,mc_current_telemetry_valid=1,
        mc_current_frozen=1,mc_current_rms_a=[.41,.42,.43],mc_age_ms=20,bp_vbus_valid=1,
        bp_temp_valid=1,hmi_hv_armed=0,hmi_vbus_hv_calibrated=1,hmi_control_auth_required=0,
        mc_bad_cnt=0,bp_bad_cnt=0,mc_last_bad_reason=0,mc_last_uart_error_flags=0,
        ui_fixture_only=True,not_hardware_measurements=True)
    case=state['scenario']
    if case=='fault':s.update(mc_fault_current_mask=0x400,mc_fault_occurred_mask=0x400,mc_fault=8)
    if case=='latched':s.update(estop=1,mc_fault_occurred_mask=0x400,mc_fault=8)
    if case=='stale':s.update(mc_age_ms=900,mc_current_telemetry_valid=0)
    if case=='lowbus':s.update(vdc=3.,bp_vdc=3.,mc_fault_current_mask=4,mc_fault_occurred_mask=4,mc_current_telemetry_valid=0)
    return module.with_research_suite(s)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(package.OUT/'web_hmi/static'),**kwargs)
    def log_message(self,*args):pass
    def reply(self,value):
        body=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if urlsplit(self.path).path=='/api/status':self.reply(dict(ok=True,data=fixture()));return
        if urlsplit(self.path).path=='/api/break-snapshot':
            self.reply(dict(ok=True,data={k:v for k,v in fixture().items() if k.startswith('mc_break_')}));return
        super().do_GET()
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}')
        if self.path=='/preview/scenario':state['scenario']=body['scenario'];self.reply(dict(ok=True));return
        if self.path=='/preview/quit':state['quit']=True;self.reply(dict(ok=True));return
        with (OUT/'stub_requests.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(dict(path=self.path,body=body,hardware_commands=0))+'\n')
        self.reply(dict(ok=True,status=fixture()))

if __name__=='__main__':
    server=HTTPServer(('127.0.0.1',8766),Handler);server.timeout=.5
    until=time.monotonic()+900
    print('Local-only stub preview: http://127.0.0.1:8766/',flush=True)
    try:
        while not state['quit'] and time.monotonic()<until:server.handle_request()
    finally:server.server_close()
