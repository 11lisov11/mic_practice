"""Offline browser fixture; never connects to either board."""
import importlib.util,json,time
from http.server import HTTPServer
import prepare_multi_algorithm as candidate
import research_suite_ui_preview as base
base.package=candidate;base.OUT=candidate.ROOT/'output/playwright/multi_algorithm'
base.OUT.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('multi_preview',candidate.OUT/'web_hmi/server.py')
base.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(base.module)
original=base.fixture;base.state['algorithm']=1
def fixture():
    s=original();s.update(research_native_caps=7,algorithm_selected=base.state['algorithm'],
        algorithm_requested=base.state['algorithm'],algorithm_qualification=0,rpm_est=0)
    return base.module.with_research_suite(s)
base.fixture=fixture
class Handler(base.Handler):
    def do_POST(self):
        if self.path!='/api/algorithm':return super().do_POST()
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        base.state['algorithm']=body['algorithm']
        with (base.OUT/'stub_requests.jsonl').open('a') as f:f.write(json.dumps(dict(path=self.path,body=body,hardware_commands=0))+'\n')
        self.reply(dict(ok=True))
if __name__=='__main__':
    server=HTTPServer(('127.0.0.1',8767),Handler);server.timeout=.5;end=time.monotonic()+600
    print('OFFLINE MOCK ONLY http://127.0.0.1:8767',flush=True)
    try:
        while not base.state['quit'] and time.monotonic()<end:server.handle_request()
    finally:server.server_close()
