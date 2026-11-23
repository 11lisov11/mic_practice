"""Qualify versioned pairs and adapt the retained detached-fixture adversarial vectors."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import hashlib
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status
from prepare_ipm_break_wifi import source_hashes

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main(package,out=None):
    out=out or package/'qualification';out.mkdir(exist_ok=False)
    pairs=json.loads((package/'manifest.json').read_text())
    prod_pair=pairs['production_pair'];fixture_pair=pairs['fixture_pair']
    template=(ROOT/'tools/local_stop_fixture_selftest.py').read_text()
    template=template.replace('from prepare_local_stop_pwm_fixture import NUCLEO, ROOT',
        'ROOT=Path('+repr(str(ROOT))+')\nNUCLEO=Path('+repr(str(package/'production/nucleo'))+')')
    for old,new in ((2026101298,fixture_pair[0]),(2026101299,fixture_pair[1]),(2026101205,prod_pair[0]),(2026101204,prod_pair[1])):
        template=template.replace(str(old),str(new))
    adapted=out/'fixture_vectors.py';adapted.write_text(template)
    call=subprocess.run([sys.executable,str(adapted),'--fixture',str(package/'fixture'),'--outdir',str(out/'fixture_vectors')],
        env=__import__('os').environ|{'PYTHONPATH':str(ROOT/'tools')},capture_output=True,text=True)
    (out/'fixture_vectors.log').write_text(call.stdout+call.stderr);call.check_returncode()
    m=load_module(package/'production/web_hmi/server.py')
    old=safe_status(fw_build=2026101205,mc_fw_build=2026101204,bp_mcsdk_telemetry=1)
    new=dict(old,fw_build=prod_pair[0],mc_fw_build=prod_pair[1])
    assert not m._vbus_calibration_identity_matches(m._vbus_calibration_identity(old),m._vbus_calibration_identity(new))
    for peer in (prod_pair[1],fixture_pair[1]):
        ok,why=m.hv_arm_precheck(dict(new,mc_fw_build=peer),m.HvArmConfig(enabled=True,profile='hv'),True)
        assert not ok and 'awaits new calibration' in why
    report={'pass':True,'hardware_commands':0,'old_calibration_rejected':True,'new_pair_hv_blocked':True,
            'fixture_vectors_sha256':sha(adapted),'packages':{},'target_disassembly':{}}
    objdump=Path('C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740/tools/bin/arm-none-eabi-objdump.exe')
    for name,pair in (('production',prod_pair),('fixture',fixture_pair)):
        p=package/name;mf=json.loads((p/'manifest.json').read_text())
        assert source_hashes(p/'nucleo')==mf['nucleo_source_sha256']
        assert source_hashes(p/'UNOQ_MOTOR')==mf['uno_source_sha256']
        assert sha(p/'web_hmi/server.py')==mf['hmi_sha256']
        artifacts={}
        for directory,file,build in ((p/'uno_build','unoq_mcsdk_scalar.build-manifest.json',pair[0]),
              (p/'nucleo/STM32CubeIDE/Debug','ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json',pair[1])):
            manifest=json.loads((directory/file).read_text(encoding='utf-8-sig'));assert manifest['firmware_build_id']==build
            for item in manifest['artifacts']:
                f=directory/item['file'];assert f.stat().st_size==item['bytes'] and sha(f)==item['sha256'].lower()
                artifacts[str(f.relative_to(package))]=sha(f)
        assert json.loads((p/'uno_build/llext-check.json').read_text())['pass']
        elf=p/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf'
        for function,count in (('PWM_SetPhasePWMOutputs',3),('ACIM_VF_Controller',7)):
            result=subprocess.run([str(objdump),'-d','--disassemble='+function,str(elf)],capture_output=True,text=True,check=True)
            # Actual exponent masks and early branches, rather than source-only isfinite calls.
            assert result.stdout.count('and.w')>=count and result.stdout.count('0x7f800000')>=count*2
            target=out/(name+'_'+function+'.asm');target.write_text(result.stdout)
            report['target_disassembly'][target.name]=sha(target)
        report['packages'][name]={'pair':list(pair),'artifacts_sha256':artifacts,'manifest_sha256':sha(p/'manifest.json')}
    assert json.loads((package/'fastmath/report.json').read_text())['pass']
    guard=subprocess.run([sys.executable,str(ROOT/'tools/ipm_break_hmi_guard_selftest.py'),'--candidate',str(package/'production'),
                           '--outdir',str(out/'hmi_guards')],capture_output=True,text=True)
    (out/'hmi_guards.log').write_text(guard.stdout+guard.stderr);guard.check_returncode()
    assert json.loads((out/'hmi_guards/report.json').read_text())['pass']
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'pair_checks':list(report['packages']),'hv_release_approved':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--outdir',type=Path);a=p.parse_args();main(a.package.resolve(),a.outdir.resolve() if a.outdir else None)
