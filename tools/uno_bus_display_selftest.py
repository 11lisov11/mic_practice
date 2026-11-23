"""Test actual matrix renderer/core packing; no physical display or motor test."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import prepare_unoq_bus_display as package
import uno_matrix_renderer_selftest as original

EXTRA_GLOBALS = '''
using std::isfinite;
static bool g_bp_mcsdk_telemetry=true, g_bp_vbus_valid=true;
static uint32_t g_bp_fw_build=2026102402U, g_bp_vbus_ms, g_bp_last_rsp_ms;
static const uint32_t BP_VBUS_STALE_MS=500, BP_REPLY_TIMEOUT_MS=500;
static float g_bp_vdc;
'''

CASES = r'''
void fresh(float v) {
  clock_ms+=1000; g_bp_vdc=v; g_bp_vbus_ms=clock_ms; g_bp_last_rsp_ms=clock_ms;
  g_bp_vbus_valid=true; g_bp_mcsdk_telemetry=true; g_bp_fw_build=2026102402U;
  g_pwm_enabled=false; g_freq_cmd=25; g_estop_latched=false;
}
void expect_volts(int n) {
  for(int pos=0;pos<3;++pos) {
    int x0=1+4*pos;
    if ((pos==0 && n<100) || (pos==1 && n<10)) {
      for(int y=1;y<=5;++y)for(int x=x0;x<x0+3;++x)check(!raw_pixel(x,y));
    } else check_digit(x0, pos==0?n/100:pos==1?(n/10)%10:n%10);
  }
  check(raw_pixel(0,6) && raw_pixel(2,6) && raw_pixel(1,7));
  check(!raw_pixel(8,6)); // no frequency decimal point
}
void expect_missing() {
  for(int pos=0;pos<3;++pos)for(int y=1;y<=5;++y)for(int x=0;x<3;++x)
    check(raw_pixel(1+4*pos+x,y)==(y==3));
  check(raw_pixel(0,6) && raw_pixel(2,6) && raw_pixel(1,7));
}
int main() {
  matrix_init(); check(initialized && writes==1);
  for(int v=0;v<=999;++v) {
    fresh(float(v)); unsigned old=writes; matrix_update();
    check(writes==old+1); expect_volts(v);
    old=writes; matrix_update(); check(writes==old);
  }
  fresh(.32f); matrix_update(); expect_volts(0);
  fresh(19.6f); matrix_update(); expect_volts(20);
  fresh(322.7f); matrix_update(); expect_volts(323);
  fresh(323); g_estop_latched=true; matrix_update(); expect_volts(323);
  for(float v : {-1.0f,1000.0f,NAN,INFINITY}) {
    fresh(v); matrix_update(); expect_missing();
  }
  fresh(323); g_bp_vbus_valid=false; matrix_update(); expect_missing();
  fresh(323); g_bp_mcsdk_telemetry=false; matrix_update(); expect_missing();
  fresh(323); g_bp_fw_build=0; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms=0; matrix_update(); expect_missing();
  fresh(323); g_bp_last_rsp_ms=0; matrix_update(); expect_missing();
  fresh(323); clock_ms+=500; matrix_update(); expect_volts(323);
  fresh(323); clock_ms+=501; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms-=501; matrix_update(); expect_missing();
  fresh(323); g_bp_last_rsp_ms-=501; matrix_update(); expect_missing();
  fresh(323); g_bp_vbus_ms=0xfffffff0U; g_bp_last_rsp_ms=g_bp_vbus_ms;
  g_matrix_last_ms=0xfffffe00U; clock_ms=0x100U; matrix_update(); expect_volts(323);
  clock_ms=0x400U; matrix_update(); expect_missing();
  fresh(323); matrix_update(); expect_volts(323); // recover after stale
  g_pwm_enabled=true; g_estop_latched=false;
  for(int tenths=0;tenths<=999;++tenths) {
    g_freq_ref=tenths/10.0f; clock_ms=2000000U+tenths*2000U;
    matrix_update(); check_digit(5,(tenths/10)%10); check_digit(9,tenths%10);
    if(tenths>=100)check_digit(1,tenths/100);
    check(raw_pixel(8,5) && raw_pixel(8,6));
  }
  g_freq_ref=5; clock_ms=4001000; matrix_update();
  check_digit(1,3);check_digit(5,0);check_digit(9,0);
  for(int x=10;x<13;++x)check(raw_pixel(x,7));
  g_pwm_enabled=false; matrix_start_test(15000);
  for(int i=0;i<4;++i) {
    clock_ms+=500;matrix_update();
    for(int w=0;w<4;++w)check(submitted[w]==(((clock_ms/500)&1)?0xffffffffU:0U));
  }
  g_matrix_test_until_ms=0;fresh(323);matrix_update();expect_volts(323);
  printf("{\"passed\":true,\"checks\":%u,\"voltage_values\":1000,\"running_frequency_values\":1000}",checks);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args(); out=args.outdir.resolve();out.mkdir(parents=True,exist_ok=False)
    core=Path.home()/'AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/libraries/Arduino_LED_Matrix/src/Arduino_LED_Matrix.h'
    program,_=original.generate(package.OUT,core)
    program=program[:program.index('int main() {')]+CASES
    program=program.replace('static bool matrix_test_active() {',EXTRA_GLOBALS+'\nstatic bool matrix_test_active() {',1)
    report=dict(passed=False,physical_display_verified=False,hardware_commands=0)
    try:
        with tempfile.TemporaryDirectory() as folder:
            tmp=Path(folder)
            for name in ('Arduino.h','cmsis_core.h'):(tmp/name).write_text('#pragma once\n')
            unit=out/'renderer.cpp';exe=tmp/'renderer.exe'
            compiler=[shutil.which('g++'),' -std=c++17'.strip(),'-Wall','-Wextra','-Werror','-I',str(tmp),'-I',str(core.parent),str(unit),'-o',str(exe)]
            def run_source(source,label):
                unit.write_text(source,encoding='utf-8')
                build=subprocess.run(compiler,capture_output=True,text=True,timeout=60)
                (out/(label+'_compile.log')).write_text(build.stdout+build.stderr,encoding='utf-8')
                assert build.returncode==0,label+' failed to compile'
                return subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            result=run_source(program,'production');assert result.returncode==0,result.stderr
            report.update(json.loads(result.stdout))
            report['mutations_detected']={}
            for label,old,new in (
                ('stale_as_fresh','(uint32_t)(now - g_bp_vbus_ms) <= BP_VBUS_STALE_MS','true'),
                ('wrong_source','const int volts = (int)(g_bp_vdc + 0.5f);','const int volts = (int)(g_freq_cmd + 0.5f);'),
                ('corrupted_glyph','uint8_t row = DIGIT_3X5[digit][y];','uint8_t row = DIGIT_3X5[0][y];'),
            ):
                assert program.count(old)==1
                result=run_source(program.replace(old,new),label)
                report['mutations_detected'][label]=result.returncode!=0
                assert result.returncode!=0,label+' was not detected'
            unit.write_text(program,encoding='utf-8')
        # Prove the sketch change is confined to display rendering and identity.
        old=(package.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
        new=(package.OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8-sig')
        before=old[:old.index('static void matrix_update() {')].replace('2026102401U','2026102403U')
        assert before==new[:new.index('static void matrix_update() {')]
        assert old[old.index('static void matrix_set_pixel(int x, int y) {'):]==new[new.index('static void matrix_set_pixel(int x, int y) {'):]
        for path in (package.BASE/'UNOQ_MOTOR').rglob('*'):
            if path.is_file() and path.name!='UNOQ_MOTOR.ino':
                assert path.read_bytes()==(package.OUT/path.relative_to(package.BASE)).read_bytes()
        spec=importlib.util.spec_from_file_location('matrix_hmi',package.OUT/'web_hmi/server.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        stored=dict(fw_build=package.OLD[0],mc_fw_build=package.OLD[1],rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
        current=dict(stored,fw_build=package.NEW[0])
        assert module._vbus_calibration_identity_matches(stored,current)
        assert not module._vbus_calibration_identity_matches(stored,dict(current,fw_build=0))
        assert module.manual_scalar_supported(dict(current,manual_scalar_capable=1))
        report.update(passed=True,control_and_uart_source_unchanged=True,existing_calibration_accepted=True,unknown_firmware_rejected=True)
    except Exception as exc:report.update(passed=False,error=str(exc))
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
