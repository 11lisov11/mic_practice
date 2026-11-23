"""Preserve boot evidence; GET/SSH reads only, no motor/reset/service commands."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/live_bench_20261029/foc_observer_schedule_fix_r1/unexpected_boot_audit_20261030_r1'


def main():
    OUT.mkdir(exist_ok=False)
    ssh = ['ssh', '-i', str(ROOT / '.unoq_ssh/id_ed25519'), '-o',
           'UserKnownHostsFile=' + str(ROOT / '.unoq_ssh/known_hosts'),
           '-o', 'StrictHostKeyChecking=yes', '-o', 'BatchMode=yes',
           '-o', 'ConnectTimeout=5', '-p', '2222', 'arduino@192.168.1.138']
    commands = {
        'boot_identity': 'date -Is; cat /proc/uptime; cat /proc/sys/kernel/random/boot_id; journalctl --list-boots --no-pager',
        'previous_boot_tail': 'journalctl -b -1 -n 100 --no-pager -o short-iso',
        'current_boot_head': 'journalctl -b 0 --no-pager -o short-iso | head -n 100',
        'shutdown_evidence': 'last -x -n 18; journalctl -b -1 --no-pager -o short-iso --grep="reboot|shutdown|watchdog|panic|power|reset|oom|segfault" -n 65',
    }
    def collect(item):
        name, command = item
        result = subprocess.run(ssh + [command], capture_output=True, timeout=20)
        (OUT / (name + '.txt')).write_bytes(result.stdout + b'\nSTDERR:\n' + result.stderr)
        return name, result.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        codes = dict(pool.map(collect, commands.items()))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = (ROOT / '.unoq_ssh/control_token').read_text().strip()
    for name, path in [('status', '/api/status'), ('hmi_logs', '/api/logs')]:
        req = urllib.request.Request('http://192.168.1.138:8080' + path,
            headers={'X-UNOQ-Control-Token': token})
        with opener.open(req, timeout=10) as response:
            data = response.read()
        (OUT / (name + ('.json' if name == 'status' else '.txt'))).write_bytes(data)
    report = dict(host_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        user_reports_power_continuous=True, ssh_exit_codes=codes,
        commands_sent=['SSH read-only logs', 'GET /api/status', 'GET /api/logs'],
        START=0, CLEAR=0, ARM=0, RESET=0, flash=0, thresholds_changed=False)
    (OUT / 'collection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    (OUT / 'saved_files_sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(OUT)


if __name__ == '__main__':
    main()
