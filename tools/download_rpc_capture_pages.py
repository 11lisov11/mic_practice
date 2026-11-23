"""Download the ADC and observer records from a stopped Uno 2026112013."""
import argparse
import hashlib
import json
import runpy
import urllib.parse
import urllib.request
from pathlib import Path

from prepare_rpc_capture_pages import OUT, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    parser.add_argument('--usb', action='store_true')
    args = parser.parse_args()
    if args.outdir.exists():
        parser.error('Choose a new output directory')
    receive = runpy.run_path(str(OUT / 'web_hmi/server.py'))['receive_capture_pages']
    token = (ROOT / '.unoq_ssh/control_token').read_text(encoding='utf-8').strip()
    origin = 'http://127.0.0.1:18080' if args.usb else 'http://192.168.1.138:8080'
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fetch(kind, page):
        query = urllib.parse.urlencode({'kind': kind, 'page': page})
        request = urllib.request.Request(origin + '/api/capture-page?' + query,
                                         headers={'X-UNOQ-Control-Token': token})
        with client.open(request, timeout=4) as response:
            payload = json.load(response)
        if payload.get('ok') is not True:
            raise RuntimeError('Capture page unavailable')
        return payload['data']

    args.outdir.mkdir(parents=True)
    hashes = {}
    errors = {}
    for kind, name in [('adc', 'ADC_peak.bin'), ('observer', 'observer_trace.bin')]:
        try:
            raw = receive(fetch, kind)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            errors[kind] = str(error)
            continue
        (args.outdir / name).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    report = {'sha256': hashes, 'errors': errors}
    (args.outdir / 'download.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
