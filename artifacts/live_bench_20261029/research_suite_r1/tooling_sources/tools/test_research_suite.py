import importlib.util,json,subprocess,tempfile,unittest,shutil,ast,io
from pathlib import Path
import prepare_research_suite as p
from audit_production_pwm_filters import function
from research_suite.catalog import research_catalog,RESEARCH_ORDER
from research_suite_runner import plan

class Suite(unittest.TestCase):
    def test_honest_modes_and_no_skip_plan(self):
        s=dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],research_native_valid=1,research_native_caps=1)
        rows=research_catalog(s)
        self.assertEqual([r['id'] for r in rows if r['hardware_ready']],['VF_FIXED'])
        self.assertFalse(plan(rows,list(RESEARCH_ORDER))['executable'])
        self.assertTrue(plan(rows,['VF_FIXED'])['executable'])
        for change in ({'research_native_valid':0},{'mc_fw_build':p.OLD[1]},{'research_native_caps':255}):
            self.assertFalse(any(r['hardware_ready'] for r in research_catalog(dict(s,**change))))

    def test_current_adc_and_safety_unchanged(self):
        for rel in ('Src/current_shunt.c','Src/mc_tasks.c','Inc/current_core.h','Src/stm32g4xx_mc_it.c','Src/stm32g4xx_hal_msp.c','Inc/drive_parameters.h'):
            self.assertEqual((p.BASE/'nucleo'/rel).read_bytes(),(p.OUT/'nucleo'/rel).read_bytes(),rel)
        old=(p.BASE/'nucleo/Src/main.c').read_text(encoding='utf-8');new=(p.OUT/'nucleo/Src/main.c').read_text(encoding='utf-8')
        for name in ('MX_TIM1_Init','mic_bkin_capture_start','mic_send_current_page','uno_handle_valid_frame','mic_local_stop_blocked'):
            self.assertEqual(function(old,name).replace(str(p.OLD[1]),str(p.NEW[1])),function(new,name),name)

    def test_actual_packet_parser_crc_peer_ttl_and_capability_fail_closed(self):
        source=r'''
#include <cassert>
#include "research_wire.h"
int main(){
 xp_receiver r={};uint8_t p[UV3_FRAME];xp_packet(p,2026102912U);
 assert(!xp_fresh(&r,true,1));assert(xp_receive(&r,p,2026102912U,true,10));assert(xp_fresh(&r,true,2509));
 assert(!xp_fresh(&r,true,2510));assert(!xp_fresh(&r,false,20));
 assert(!xp_receive(&r,p,2026102902U,true,20));assert(!xp_receive(&r,p,2026102912U,false,20));
 for(unsigned i=0;i<UV3_FRAME;i++){p[i]^=1;assert(!xp_receive(&r,p,2026102912U,true,20));p[i]^=1;}
 p[4]=3;uv3_seal(p);assert(!xp_receive(&r,p,2026102912U,true,20));assert(r.caps==1);
 xp_packet(p,2026102912U);p[14]=1;uv3_seal(p);assert(!xp_receive(&r,p,2026102912U,true,20));
 xp_packet(p,2026102912U);assert(xp_receive(&r,p,2026102912U,true,0xfffffff0U));assert(xp_fresh(&r,true,10));
}
'''
        with tempfile.TemporaryDirectory() as d:
            unit=Path(d)/'test.cpp';unit.write_text(source);exe=Path(d)/'test.exe'
            subprocess.run([shutil.which('g++'),'-std=c++17','-Wall','-Wextra','-Werror','-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True)

    def test_hmi_profile_capability_and_calibration_contract(self):
        spec=importlib.util.spec_from_file_location('suite_hmi',p.OUT/'web_hmi/server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        data=dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],research_native_valid=1,research_native_caps=1,mc_capabilities=1)
        data=m.with_research_suite(m.with_current_only_profile(data))
        self.assertEqual(data['enc_source'],'disabled');self.assertIsNone(data['speed_measured_rpm'])
        self.assertEqual(sum(r['hardware_ready'] for r in data['research_algorithms']),1)
        self.assertEqual(data['research_actuator_algorithm'],'VF_FIXED')

    def test_full_program_fails_before_any_start(self):
        import sys
        from unittest.mock import patch
        import research_suite_runner as runner
        s=dict(fw_build=p.NEW[0],mc_fw_build=p.NEW[1],research_native_valid=1,research_native_caps=1,research_native_bad=0)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'blocked'
            argv=['suite','--execute','--confirm-powered-unloaded-autonomous','--outdir',str(out)]
            with patch.object(sys,'argv',argv),patch.object(runner.lab,'get_status',return_value=s),patch.object(runner.trial,'main',side_effect=AssertionError('Unexpected START')):
                self.assertEqual(runner.main(),2)
            report=json.loads((out/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['start_commands'],0)
            self.assertEqual(report['status'],'blocked')

    def test_browser_session_without_exposing_script_key_and_guards_unchanged(self):
        from types import SimpleNamespace
        spec=importlib.util.spec_from_file_location('session_hmi',p.OUT/'web_hmi/server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        clock=[10.];store=m.UiSessionStore(clock=lambda:clock[0],ttl=2)
        cookie=store.issue().split(';',1)[0]
        self.assertTrue(store.valid(cookie));self.assertFalse(store.valid('mic_ui_session=foreign'))
        self.assertFalse(m.UiSessionStore().valid(cookie))
        clock[0]=13.;self.assertFalse(store.valid(cookie))
        store=m.UiSessionStore();headers=[];rejected=[]
        app=SimpleNamespace(control_access=SimpleNamespace(enabled=True,read_token=lambda:'test-script-key'),ui_sessions=store,
             mark_operator_heartbeat=lambda:True,logs=SimpleNamespace(add=lambda line:None))
        fake=SimpleNamespace(server=SimpleNamespace(app=app),headers={},client_address=('127.0.0.1',1),path='/api/cmd',
             _send_json=lambda data,status:rejected.append(status),wfile=io.BytesIO(),
             send_response=lambda code:None,send_header=lambda key,value:headers.append((key,value)),end_headers=lambda:None)
        self.assertFalse(m.Handler._require_control_access(fake,mark_heartbeat=False));self.assertEqual(rejected,[401])
        m.Handler._send_static(fake,'index.html','text/html')
        value=next(v for k,v in headers if k=='Set-Cookie')
        self.assertNotIn('test-script-key',value);self.assertIn('HttpOnly',value);self.assertIn('SameSite=Strict',value)
        fake.headers={'Cookie':value.split(';',1)[0]}
        self.assertTrue(m.Handler._require_control_access(fake))
        fake.headers={'X-UNOQ-Control-Token':'test-script-key'}
        self.assertTrue(m.Handler._require_control_access(fake))
        def methods(path):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
            return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
        old=methods(p.BASE/'web_hmi/server.py');new=methods(p.OUT/'web_hmi/server.py')
        for name in ('start_sequence','stop_sequence','_start_without_precharge','operator_heartbeat_fresh'):
            self.assertEqual(old[name],new[name],name)

if __name__=='__main__':unittest.main()
