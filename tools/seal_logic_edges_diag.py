"""Seal2793 with auxiliary-waveform scope and hash-preserved older recordings."""
import json,re,subprocess
from prepare_logic_edges_diag import configure_common,normalize_manifest
import logic_edges_diag_io as io
p=configure_common()
def main():
 import seal_no_switch_diag as seal
 seal.decode=io.decode;seal.eligible=io.eligible;seal.main()
 c=p.OUT;v=c/'verification';m=normalize_manifest(json.loads(p.read(c/'manifest.json')));r=json.loads(p.read(v/'report.json'))
 host=json.loads(p.read(v/'capture_host_cases/report.json'));assert host['passed'] and host['actual_hardware_calls']==0
 raw=subprocess.check_output([str(seal.GNU/'arm-none-eabi-nm.exe'),'-S','-n',str(c/'build/nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf')],text=True)
 line=next(line for line in raw.splitlines() if line.split()[-1]=='mic_logic_edge_report');a=line.split();addr,size=int(a[0],16),int(a[1],16)
 assert size==48 and 0x20000000<=addr<addr+size<=0x20008000
 symbols=json.loads(p.read(v/'symbols.json'));symbols['mic_logic_edge_report']=dict(address=addr,bytes=size);p.write(v/'symbols.json',json.dumps(symbols,indent=2)+'\n')
 su=p.read(c/'nucleo/STM32CubeIDE/Debug/Application/User/logic_edges.su')
 frames={name:int(amount) for name,amount in re.findall(r':(\w+)\s+(\d+)\s',su)}
 assert max(frames.values())<=128
 r.update(auxiliary_outputs='TIM8 PC6/PC7/PC8; PC9 marker',auxiliary_BKIN='PD2 active LOW; external PA6 jumper required',
  TIM1_original_six_pins_GPIO_LOW=True,TIM8_AOE_disabled=True,TIM8_break_locked=True,
  quiet_ms=2000,edge_ms=3000,auxiliary_stack_frames=frames,capture_host_tests=host,
  limitations=m['limitations'],physical_edges_measured=False)
 p.write(v/'report.json',json.dumps(r,indent=2)+'\n')
 m.update(request_command='python tools/run_logic_edges_diag.py --confirm-j1-j4-off-meter-below20-nucleo-usb --confirm-sd-pa6-pd2-jumper-and-probes --request-once --outdir <new-folder>',
  install_command='python tools/install_logic_edges_diag.py --confirm-j1-j4-off-meter-below20-nucleo-usb --confirm-sd-pa6-pd2-jumper-and-probes --outdir <new-folder>',
  capture_required_before_request=True,archived_file_count=len(m['preserved_records']),
  wiring={'0':'PC6 CN10-4','1':'PC7 CN10-19','2':'PC8 CN10-2','3':'PB8 SCL CN10-3','4':'PB9 SDA CN10-5',
   '5':'PA6 SD CN10-13','6':'PD2 auxiliary BKIN CN7-4','7':'PC9 marker CN10-1','GND':'CN7-19',
   'jumper':'PA6 CN10-13 to PD2 CN7-4; original PA6/SD wiring stays connected'},
  switching={'J1':'OFF throughout','J4_15V':'OFF throughout','Nucleo':'USB PC','Uno_Q':'powerbank','Saleae':'USB PC after probe map',
   'motor_and_TP23_PA4':'leave existing connections'})
 m['sealed_sha256']={str(f.relative_to(c)).replace('\\','/'):p.sha(f) for tree in ('nucleo','build','restore','verification','preserved_live','preserved_records','test_resources') for f in sorted((c/tree).rglob('*')) if f.is_file() and not any(x in ('Debug','Release','__pycache__') for x in f.relative_to(c).parts)}
 for name in ('prepare_logic_edges_diag.py','check_logic_edges_diag.py','logic_edges.c','logic_edges.h','logic_edges_diag_io.py',
   'run_logic_edges_diag.py','install_logic_edges_diag.py','logic_edges_host_selftest.py','analyze_logic_edges_diag.py','seal_logic_edges_diag.py'):
  m['tool_sha256']['tools/'+name]=p.sha(p.ROOT/'tools'/name)
 p.write(c/'manifest.json',json.dumps(m,indent=2)+'\n')
 print(json.dumps(dict(ready=True,build=p.BUILD,hardware_tested=False,installed=False,archive_files=len(m['preserved_records']),auxiliary_report_bytes=size)))
if __name__=='__main__':main()
