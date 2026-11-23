"""Replay actual saved capture bytes through C++ paging and the Python decoder."""
import hashlib
import json
import runpy
import subprocess
from types import SimpleNamespace

from prepare_rpc_capture_pages import BASE, OUT, ROOT

TRIAL = ROOT / 'artifacts/live_bench_20261118/boot_stack_integrity_r1/FOC_5Hz_20261120_r1'

STUBS = r'''
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <fstream>
#include <string>
struct String : std::string {
    using std::string::string;
    using std::string::operator=;
    explicit String(unsigned long n) : std::string(std::to_string(n)) {}
};
enum { PC_WIRE_BYTES = 1024, OD_WIRE_BYTES = 1888, BP_STATUS_PWM_ACTIVE = 32,
       NH_META_BYTES = 524, NH_ROW = 22 };
static bool g_pwm_enabled, g_pwm_outputs_active;
static unsigned g_bp_status;
static struct { bool complete; uint8_t data[PC_WIRE_BYTES]; } g_peak;
static struct { bool complete; uint8_t data[OD_WIRE_BYTES]; } g_observer_trace;
struct History {
    bool complete;
    uint8_t meta[524], rows[22], checkpoints[4];
    uint32_t count, epoch;
};
static History g_start_history;
bool nhr_exact(const History *) { return true; }
uint32_t odw_u32(const uint8_t *p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
'''
RUN = r'''
int main(int argc, char **argv) {
    g_peak.complete = std::ifstream(argv[1], std::ios::binary)
        .read(reinterpret_cast<char *>(g_peak.data), PC_WIRE_BYTES).good();
    g_observer_trace.complete = std::ifstream(argv[2], std::ios::binary)
        .read(reinterpret_cast<char *>(g_observer_trace.data), OD_WIRE_BYTES).good();
    for (unsigned part = 3; part <= 4; ++part) {
        unsigned size = part == 3 ? PC_WIRE_BYTES : OD_WIRE_BYTES;
        for (unsigned page = 0; page < (size + 191) / 192; ++page)
            std::cout << rpc_history(part, page) << "\n";
    }
    std::cout << rpc_history(3, UINT32_MAX) << "\n" << rpc_history(0, 0) << "\n";
    g_start_history.complete = true;
    g_start_history.epoch = 77;
    std::cout << rpc_history(0, 0) << "\n";
    g_pwm_enabled = true;
    std::cout << rpc_history(3, 0) << "\n";
    g_pwm_enabled = false;
    g_pwm_outputs_active = true;
    std::cout << rpc_history(4, 0) << "\n";
    g_pwm_outputs_active = false;
    g_bp_status = BP_STATUS_PWM_ACTIVE;
    std::cout << rpc_history(3, 0) << "\n";
}
'''


def main():
    outdir = OUT / 'verification'
    outdir.mkdir(exist_ok=True)
    sketch = (OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(encoding='utf-8')
    start = sketch.index('static String rpc_capture_page')
    end = sketch.index('static String rpc_get()', start)
    fixture = outdir / 'page_fixture.cpp'
    fixture.write_text(STUBS + sketch[start:end] + RUN, encoding='utf-8')
    exe = outdir / 'page_fixture.exe'
    subprocess.run(['g++', '-std=c++17', str(fixture), '-o', str(exe)], check=True, timeout=40)
    stdout = subprocess.check_output(
        [str(exe), str(TRIAL / 'ADC_peak.bin'), str(TRIAL / 'observer_trace.bin')],
        timeout=10, text=True,
    )
    records = stdout.splitlines()
    assert len(records) == 22
    assert records[16:18] == ['ERR PAGE', 'ERR NOT_COMPLETE']
    assert records[18].startswith('NH 77 1 524 ')
    assert records[19:] == ['ERR RUN'] * 3
    server = runpy.run_path(str(OUT / 'web_hmi/server.py'))
    parse = server['parse_capture_page']
    receive = server['receive_capture_pages']
    mapping = server['CAPTURE_PAGES']

    def fetch(kind, page):
        part, size = mapping[kind]
        return parse(records[(0 if part == 3 else 6) + page], part, page, size)

    hashes = {}
    for kind, name in [('adc', 'ADC_peak.bin'), ('observer', 'observer_trace.bin')]:
        actual = receive(fetch, kind)
        assert actual == (TRIAL / name).read_bytes()
        hashes[name] = hashlib.sha256(actual).hexdigest()

    def rejected(fetcher):
        try:
            receive(fetcher, 'adc')
        except ValueError:
            return True
        return False

    def altered(kind, page, field, value):
        response = fetch(kind, page)
        if page == 1:
            response[field] = value(response[field])
        return response

    assert rejected(lambda kind, page: altered(kind, page, 'crc32c', lambda crc: crc ^ 1))
    assert rejected(lambda kind, page: altered(kind, page, 'page', lambda number: number + 1))
    assert rejected(lambda kind, page: altered(kind, page, 'hex', lambda data: data[2:]))
    assert rejected(lambda kind, page: altered(kind, page, 'hex', lambda data: ('01' if data[:2] == '00' else '00') + data[2:]))

    handler_class = server['Handler']
    rpc_calls = []
    sent = []

    def history_rpc(method, params, **options):
        rpc_calls.append((method, params, options))
        return [1, 1, None, records[0]]

    handler = object.__new__(handler_class)
    handler.path = '/api/capture-page?kind=adc&page=0'
    handler.headers = {}
    handler.client_address = ('127.0.0.1', 1)
    handler.server = SimpleNamespace(app=SimpleNamespace(
        control_access=SimpleNamespace(enabled=True, read_token=lambda: 'test-fixture'),
        ui_sessions=SimpleNamespace(valid=lambda cookie: False),
        logs=SimpleNamespace(add=lambda message: None),
        rpc=SimpleNamespace(_call=history_rpc),
    ))
    handler._send_json = lambda payload, code=200: sent.append((code, payload))
    handler.do_GET()
    assert sent[-1][0] == 401 and not rpc_calls
    handler.headers['X-UNOQ-Control-Token'] = 'test-fixture'
    handler.do_GET()
    assert sent[-1] == (200, {'ok': True, 'data': fetch('adc', 0)})
    assert rpc_calls == [('history', [3, 0], {'timeout': 1.5, 'retries': 0})]
    handler.path = '/api/capture-page?kind=adc&page=6'
    handler.do_GET()
    assert sent[-1][0] == 400 and len(rpc_calls) == 1

    original = json.loads((TRIAL / 'post_STOP_RPC_diagnosis_r1/raw_internal_peer_r1/get_response.json').read_text())[3]
    removed = {'mc_adc_peak_hex', 'mc_observer_trace_hex'}
    words = original.split(' ')
    stripped = ' '.join(word.split('=')[0] + '=-' if word.split('=')[0] in removed else word for word in words)
    assert len(original) - len(stripped) == 2 * (1024 + 1888) - 2
    assert server['RpcBridge']._parse_status_string(stripped.replace('fw_build=2026111809', 'fw_build=2026112013'))['pwm'] == 0
    old_hashes = json.loads((TRIAL / 'saved_files_sha256.json').read_text())
    assert all(hashlib.sha256((TRIAL / name).read_bytes()).hexdigest() == digest
               for name, digest in old_hashes.items())
    updated = [path.relative_to(OUT).as_posix() for path in (OUT / 'UNOQ_MOTOR').rglob('*')
               if path.is_file() and path.read_bytes() != (BASE / path.relative_to(OUT)).read_bytes()]
    assert updated == ['UNOQ_MOTOR/UNOQ_MOTOR.ino']
    result = {'passed': True, 'status_bytes_before': len(original), 'status_bytes_after': len(stripped),
              'capture_pages': 16, 'max_page_text_bytes': max(map(len, records[:16])),
              'roundtrip_sha256': hashes, 'preserved_originals': len(old_hashes),
              'negative_cases': ['out_of_range', 'RUN', 'outputs_active', 'peer_PWM_active',
                                 'record_changed', 'page_reordered', 'short_page', 'bad_CRC', 'unauthorized_HTTP'],
              'authenticated_HTTP_route_verified': True,
              'stand_commands': 0}
    (outdir / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
