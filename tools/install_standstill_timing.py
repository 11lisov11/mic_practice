"""Write/verify the sealed timing fix, then leave the outputs stopped."""
import json,subprocess
from types import SimpleNamespace
import prepare_standstill_timing as p
import install_multi_algorithm as install
from seal_standstill_commissioning import sha
OLD=(2026102931,2026102932)
install.p=p;install.OLD=OLD
guard=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((OLD,p.NEW)))
scope={'math':__import__('math')};exec(guard,scope)
install.GUARD=guard;install.precheck=scope['precheck'];install.base.GUARD=guard
install.hmi.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,OLD=OLD,NEW=p.NEW,read=p.read,once=p.once,write=p.write,sha=sha)
def verify():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['schema']=='mic_ai.standstill_timing.v1' and m['pair']==list(p.NEW) and m['built'] and not m['physical_qualification']
 assert not m['thresholds_changed'] and not m['adc_guard_changed']
 for rel,h in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==h,rel
 for rel,h in m['artifacts'].items():assert sha(p.OUT/rel)==h,rel
 for path,h in json.loads(p.read(p.OUT/'preserved_measured_evidence.json')).items():assert sha(__import__('pathlib').Path(path))==h,path
 uno=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
 assert sha(uno)==sha(p.OUT/'release/unoq_2026102933_timing.elf-zsk.bin')
 native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
 from build_multi_native import BIN
 converted=p.OUT/'hardware_install_r1/native_hex_content.bin'
 subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-I','ihex','-O','binary',str(native),str(converted)],check=True)
 assert sha(converted)==sha(p.OUT/'release/nucleo_2026102934_timing.bin')
 return uno,native
install.verify=verify
if __name__=='__main__':raise SystemExit(install.main())
