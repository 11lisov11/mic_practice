"""Install sealed 2931/2932 once on the confirmed discharged USB bench.

Uses the established write/verify/halt -> Uno write/verify -> native boot order.
No START, CLEAR, ARM, or measurement command is sent by this installer.
"""
import json,subprocess
from types import SimpleNamespace
import prepare_standstill_commissioning as p
import install_multi_algorithm as install
from seal_standstill_commissioning import sha

OLD=(2026102921,2026102922)
install.p=p;install.OLD=OLD
guard=p.read(p.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((OLD,p.NEW)))
scope={'math':__import__('math')};exec(guard,scope)
install.GUARD=guard;install.precheck=scope['precheck'];install.base.GUARD=guard
install.hmi.p=SimpleNamespace(ROOT=p.ROOT,OUT=p.OUT,OLD=OLD,NEW=p.NEW,read=p.read,once=p.once,write=p.write,sha=sha)

def verify():
 m=json.loads(p.read(p.OUT/'manifest.json'))
 assert m['schema']=='mic_ai.standstill_commissioning.v1' and m['pair']==list(p.NEW)
 assert m['built'] and not m['physical_qualification'] and not m['thresholds_changed'] and not m['adc_guard_changed']
 for rel,digest in json.loads(p.read(p.OUT/'source_hashes.json')).items():assert sha(p.OUT/rel)==digest,rel
 for rel,digest in m['artifacts'].items():assert sha(p.OUT/rel)==digest,rel
 preservation=json.loads(p.read(p.OUT/'archive_preservation.json'))
 assert sha(__import__('pathlib').Path(preservation['reference']))==preservation['reference_sha256']
 uno=p.OUT/'build/uno/UNOQ_MOTOR.ino.elf-zsk.bin'
 assert sha(uno)==sha(p.OUT/'release/unoq_2026102931_commissioning.elf-zsk.bin')
 native=p.OUT/'nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex'
 from build_multi_native import BIN
 converted=p.OUT/'hardware_install_r1/native_hex_content.bin'
 subprocess.run([str(BIN/'arm-none-eabi-objcopy.exe'),'-I','ihex','-O','binary',str(native),str(converted)],check=True)
 assert sha(converted)==sha(p.OUT/'release/nucleo_2026102932_commissioning.bin')
 assert json.loads(p.read(p.OUT/'nucleo_build_report.json'))['passed']
 assert json.loads(p.read(p.OUT/'build/uno/llext-check.json'))['pass']
 return uno,native

install.verify=verify
if __name__=='__main__':raise SystemExit(install.main())
