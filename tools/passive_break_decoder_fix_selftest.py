"""Regression, malformed input, mutation, route and retained UART incident checks."""
import argparse
import ast
import json
from pathlib import Path
import struct
from types import SimpleNamespace

from prepare_passive_break_decoder_fix import BASE, BASE_SHA, NEW, ROOT, control_ast, sha
from ipm_break_wifi_selftest import hmi_tests, load_module
from install_passive_break_decoder_fix import validate_idle


def decoder_only(text):
    tree = ast.parse(text)
    tree.body = [node for node in tree.body if
        isinstance(node, ast.Import) and any(n.name == 'struct' for n in node.names) or
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_BREAK_FIELDS' for t in node.targets) or
        isinstance(node, ast.FunctionDef) and node.name == 'break_wire_status']
    namespace = {}
    exec(compile(tree, '<passive-decoder-test>', 'exec'), namespace)
    return SimpleNamespace(**namespace)


def cases(module):
    checks = []
    def check(label, ok):
        if not ok:
            raise AssertionError(label)
        checks.append(label)
    values = [0] * 23
    values[:5] = [0x314B5242, 2, 92, 16, 0x80]
    values[6], values[12], values[13] = 0x9000, 0x40, 1
    values[14], values[15], values[20], values[22] = 0xfffffff0, 0xfffffff6, 0xffffffce, 1
    kv = {'bp_fw_build':'2026101204','bp_age_ms':'10',
          'mc_break1_age_ms':'100','mc_break1_hex':struct.pack('<23I', *values).hex()}
    result = lambda data: module.break_wire_status(data)['mc_break_snapshots'][1]
    for peer in (2026101102,2026101204):
        item = result({**kv,'bp_fw_build':str(peer)})
        check('known peer '+str(peer),item['available'] and item['captured'])
        check('signed frequency '+str(peer),item['cached_context']['reference_electrical_hz']==-1)
        check('signed temperature '+str(peer),item['cached_context']['temperature_c']==-5)
        check('cached context tick wrap '+str(peer),item['cached_context']['age_at_irq_ms']==32)
    for field,bad in (
        ('bp_fw_build','2026101006'),('bp_fw_build','2026101203'),('bp_fw_build','2026101299'),
        ('bp_fw_build','0'),('bp_fw_build','nan'),('bp_fw_build','2026101204.5'),
        ('bp_age_ms','-1'),('bp_age_ms','300'),('bp_age_ms','999999'),('bp_age_ms','inf'),
        ('mc_break1_age_ms','-1'),('mc_break1_age_ms','5001'),('mc_break1_age_ms','nan'),
        ('mc_break1_hex','xx'),('mc_break1_hex','0'*182),('mc_break1_hex','g'*184),
        ('bp_fw_build',None),('bp_age_ms',None),('mc_break1_age_ms',None)):
        check('reject '+field+'='+str(bad),not result({**kv,field:bad})['available'])
    for field in ('bp_fw_build','bp_age_ms','mc_break1_age_ms','mc_break1_hex'):
        check('missing '+field,not result({k:v for k,v in kv.items() if k!=field})['available'])
    check('freshness inclusive boundary',result({**kv,'bp_age_ms':'299','mc_break1_age_ms':'5000'})['captured'])
    for word,bad in ((0,0),(1,1),(1,3),(2,88),(2,96),(4,0),(13,2),(22,0),(22,2)):
        altered = values.copy(); altered[word]=bad
        check('reject ABI '+str(word)+'='+str(bad),not result({**kv,'mc_break1_hex':struct.pack('<23I',*altered).hex()})['available'])
    empty = result({**kv,'mc_break1_hex':bytes(92).hex()})
    check('explicit no event',empty['available'] and not empty['captured'] and empty['reason']=='no_recorded_break')
    no_context = values.copy(); no_context[13]=0
    item = result({**kv,'mc_break1_hex':struct.pack('<23I',*no_context).hex()})
    check('no manufactured cached context',item['captured'] and item['cached_context'] is None)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',required=True,type=Path)
    parser.add_argument('--outdir',required=True,type=Path)
    args=parser.parse_args(); out=args.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    path=args.candidate.resolve()/'web_hmi/server.py'
    manifest=json.loads((args.candidate/'manifest.json').read_text())
    assert sha(BASE)==BASE_SHA and sha(path)==manifest['hmi_sha256']
    source=path.read_text(encoding='utf-8'); base=BASE.read_text(encoding='utf-8')
    assert control_ast(source)==control_ast(base)
    mod=load_module(path)
    checks=cases(mod)+hmi_tests(mod)
    old=load_module(BASE)
    try: cases(old)
    except AssertionError: checks.append('regression detects original 1204 rejection')
    else: raise AssertionError('Old decoder should fail the new-peer regression')
    mutations={
      'allow_unknown_peer':source.replace(NEW,'False'),
      'allow_stale_peer':source.replace('not 0 <= peer_age < 300','False'),
      'allow_stale_record':source.replace('not 0 <= age <= 5000','False'),
      'ignore_magic':source.replace('raw["magic"] != 0x314B5242','False'),
      'ignore_schema':source.replace('raw["schema"] != 2','False'),
      'ignore_record_size':source.replace('raw["bytes"] != 92','False'),
      'ignore_context_tag':source.replace('raw["context_valid"] not in (0, 1)','False'),
    }
    detected=[]
    for label,text in mutations.items():
        assert text!=source
        try: cases(decoder_only(text))
        except AssertionError: detected.append(label)
        else: raise AssertionError('Mutation survived: '+label)
    # Exercise the actual text parser for the installed peer and both record kinds.
    values=[0]*23; values[:5]=[0x314B5242,2,92,1200,0x80]; values[22]=1
    record=struct.pack('<23I',*values).hex()
    line=('DATA state=SAFE mode=VF pwm=0 fw_build=2026101205 bp_fw_build=2026101204 rpc_schema=3 '
          'bp_age_ms=10 mc_break0_age_ms=100 mc_break1_age_ms=100 '
          f'mc_break0_hex={record} mc_break1_hex={record}')
    parsed=mod.RpcBridge._parse_status_string(line)
    assert all(item['captured'] for item in parsed['mc_break_snapshots'])
    checks.append('actual RPC text decoder accepts both 1204 record kinds')
    trial=ROOT/'artifacts/live_bench_20261012/local_button/motor_short_r1/report.json'
    saved=json.loads(trial.read_text())
    rows=[entry['status'] for entry in saved['samples']]
    results=[]
    for data in rows:
        before=old.PoweredTrialGate.live_check(data,pair=old.BOOT_TRIAL_PAIR)
        after=mod.PoweredTrialGate.live_check(data,pair=mod.BOOT_TRIAL_PAIR)
        assert before==after
        results.append({'pwm':data.get('pwm'),'uno_hw_errors':data.get('uno_rx_hw_errors'),
            'uno_hw_flags':data.get('uno_rx_hw_flags'),'nucleo_ne_observed':data.get('bp_ne_observed'),
            'nucleo_ne_accepted':data.get('bp_ne_accepted'),'guard_result':after})
    assert any(r['guard_result']==(False,'RX snapshot trial transport unhealthy: uno_rx_hw_errors') for r in results)
    checks.append('retained powered incident still rejected by unchanged guard')
    idle={**rows[0],'state':'SAFE','pwm':0,'hmi_hv_armed':0,'hmi_hv_started':0,
        'hmi_powered_trial_enabled':0,'vdc':0.,'bp_vdc':0.,'bp_status':9,
        'bp_vbus_valid':1,'bp_age_ms':20,'bp_vbus_age_ms':20,'mc_diag_valid':1,
        'bp_transport_fault':0}
    validate_idle(idle); checks.append('installer accepts fresh discharged disarmed telemetry')
    for field,bad in (('fw_build',2026101206),('fw_build',2026101205.),
        ('mc_fw_build',2026101203),('state','VF_RUN'),('pwm',1),('hmi_hv_armed',1),
        ('hmi_hv_started',1),('hmi_powered_trial_enabled',1),('bp_transport_fault',7),
        ('mc_diag_valid',0),('vdc',3.),('vdc',float('nan')),('vdc',float('inf')),
        ('bp_vdc',3.),('bp_age_ms',300),('bp_age_ms',-1),('bp_vbus_age_ms',300),
        ('bp_vbus_valid',0),('bp_status',0x22),('bp_status','9')):
        try: validate_idle({**idle,field:bad})
        except RuntimeError: checks.append('installer rejects '+field+'='+str(bad))
        else: raise AssertionError('Unsafe installation telemetry accepted: '+field)
    for field in ('vdc','bp_vdc','bp_age_ms','bp_vbus_age_ms','hmi_hv_armed'):
        try: validate_idle({k:v for k,v in idle.items() if k!=field})
        except RuntimeError: checks.append('installer rejects missing '+field)
        else: raise AssertionError('Missing installation field accepted: '+field)
    report=dict(schema='mic_ai.passive_break_decoder_selftest.v1',**{'pass':True},
        hmi_sha256=sha(path),base_sha256=BASE_SHA,checks=checks,check_count=len(checks),
        mutations_detected=detected,retained_trial_sha256=sha(trial),retained_guard_results=results,
        hardware_commands=0,control_ast_identical=True,hv_release_approved=False,
        test_source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (
            Path(__file__),ROOT/'tools/install_passive_break_decoder_fix.py',
            ROOT/'tools/prepare_passive_break_decoder_fix.py')})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pass':True,'checks':len(checks),'mutations_detected':len(detected),'retained_rows':len(rows)}))


if __name__=='__main__': main()
