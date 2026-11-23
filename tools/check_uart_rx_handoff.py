"""Reproduce the installed RX queue handoff race without accessing hardware.

The mock injects a byte after our FIFO drain, before the vendor IRQ handler.
Vendor receive behaviour is checked against the installed Arduino core source.
The installed, sealed package is never modified.
"""
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'artifacts/live_bench_20261026/nucleo_as5600_r1'
OUT = PACKAGE / 'rx_handoff_audit_r1'
CORE = Path('C:/Users/USER/AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/cores/arduino')


def main():
    OUT.mkdir(exist_ok=True)
    vendor = (CORE / 'zephyrSerial.cpp').read_text()
    assert 'ring_buf_put(&rx.ringbuf, &buf[0], length)' in vendor
    assert 'ring_buf_get(&rx.ringbuf, &data, 1)' in vendor
    src = (PACKAGE / 'UNOQ_MOTOR/nucleo_buffered_serial.h').read_text()
    anchor = '    ZephyrSerial::IrqHandler();'
    assert src.count(anchor) == 1
    fixed = src.replace(anchor, anchor + '''
    // The vendor handler also drains RX. Bytes arriving after our drain can
    // land in its private ring. Move that suffix before leaving this ISR,
    // preserving arrival order and using the same bounded queue/drop counter.
    // No other path consumes the qualified base RX ring in this adapter.
    while (arduino::ZephyrSerial::available() > 0) {
      const int value = arduino::ZephyrSerial::read();
      if (value >= 0) queue.put(static_cast<uint8_t>(value));
    }''')
    (OUT / 'nucleo_buffered_serial_candidate.h').write_text(fixed)
    mock = OUT / 'mock'
    (mock / 'zephyr/drivers').mkdir(parents=True, exist_ok=True)
    (mock / 'Arduino.h').write_text('#pragma once\n#include <cstdint>\ninline unsigned irq_lock(){return 0;}\ninline void irq_unlock(unsigned){}\n')
    (mock / 'zephyr/drivers/uart.h').write_text('''#pragma once
#include <deque>
struct device{};
inline device dev;
inline std::deque<unsigned char> fifo;
inline void(*callback)(const device*,void*)=nullptr;
inline void* callback_arg=nullptr;
inline int late_byte=-1;
inline int uart_irq_callback_user_data_set(const device*,void(*cb)(const device*,void*),void*arg){callback=cb;callback_arg=arg;return 0;}
inline void uart_irq_err_enable(const device*){}
inline bool uart_irq_update(const device*){return true;}
inline int uart_err_check(const device*){return 0;}
inline bool uart_irq_rx_ready(const device*){return !fifo.empty();}
inline int uart_fifo_read(const device*,unsigned char*b,int n){int k=0;while(k<n&&!fifo.empty()){b[k++]=fifo.front();fifo.pop_front();}return k;}
''')
    (mock / 'zephyrSerial.h').write_text('''#pragma once
#include <zephyr/drivers/uart.h>
namespace arduino {
class ZephyrSerial {
public:
 explicit ZephyrSerial(const device*d):uart(d){}
 void begin(unsigned long){}
 virtual int available(){return static_cast<int>(rx.size());}
 virtual int read(){if(rx.empty())return -1;int v=rx.front();rx.pop_front();return v;}
 virtual int peek(){return rx.empty()?-1:rx.front();}
protected:
 const device*uart;
 std::deque<unsigned char>rx;
 void IrqHandler(){
  if(late_byte>=0){fifo.push_back(static_cast<unsigned char>(late_byte));late_byte=-1;}
  unsigned char b[8];int n;
  while(uart_irq_rx_ready(uart)&&(n=uart_fifo_read(uart,b,8))>0)
   for(int i=0;i<n;++i)rx.push_back(b[i]);
 }
};
}
''')
    test = OUT / 'probe.cpp'
    test.write_text('''#include "adapter.h"
#include "uart_v3_transport.h"
#include <cassert>
#include <cstdio>
int main(){
 unsigned exact=0,erased=0,overflow=0;
 for(unsigned gap=0;gap<UV3_FRAME;++gap){
  NucleoBufferedSerial serial(&dev);serial.begin(115200);
  unsigned char frame[UV3_FRAME]={0x55,0xaa,0xda};
  for(unsigned i=3;i<UV3_PAYLOAD;++i)frame[i]=static_cast<unsigned char>(i*7+gap);
  uv3_seal(frame);
  for(unsigned i=0;i<UV3_FRAME;++i){
   if(i==gap)late_byte=frame[i];else fifo.push_back(frame[i]);
   callback(&dev,callback_arg);
  }
  unsigned char got[UV3_FRAME]={};unsigned count=0;
  while(serial.available()&&count<UV3_FRAME)got[count++]=static_cast<unsigned char>(serial.read());
  bool same=count==UV3_FRAME;
  for(unsigned i=0;i<count&&same;++i)same=got[i]==frame[i];
  if(same&&uv3_crc_ok(got))++exact;
  if(count==UV3_FRAME-1)++erased;
 }
 {
  NucleoBufferedSerial serial(&dev);serial.begin(115200);
  for(unsigned i=0;i<1025;++i){fifo.push_back(static_cast<unsigned char>(i));callback(&dev,callback_arg);}
  assert(serial.stats().dropped==1&&serial.available()==1024);++overflow;
 }
 std::printf("{\\"frame_cases\\":43,\\"exact_crc_valid\\":%u,\\"one_byte_erased\\":%u,\\"overflow_checks\\":%u}\\n",exact,erased,overflow);
}
''')
    results = {}
    for name, text in [('installed', src), ('candidate', fixed)]:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        (folder / 'adapter.h').write_text(text)
        exe = folder / 'probe.exe'
        subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-I', str(mock), '-I', str(folder), '-I', str(PACKAGE / 'UNOQ_MOTOR'),
                        str(test), '-o', str(exe)], check=True)
        results[name] = json.loads(subprocess.check_output([str(exe)], text=True))
    assert results['installed']['one_byte_erased'] == 43
    assert results['candidate']['exact_crc_valid'] == 43
    report = dict(passed=True, model_only=True, hardware_commands=0,
                  installed_package_changed=False, firmware_writes=0,
                  results=results,
                  limitation='Reproduces an actual code race; physical attribution of every captured CRC failure remains unproven. Candidate requires target build and hardware verification.')
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
