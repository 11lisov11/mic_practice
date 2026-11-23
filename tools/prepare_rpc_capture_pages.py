"""Build an offline candidate that keeps ADC and observer records out of GET."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'artifacts/live_bench_20261120'
BASE = PARENT / 'rpc_stage_trace_r1'
OUT = PARENT / 'rpc_capture_pages_r1'
OLD_UNO = '2026112011'
NEW_UNO = '2026112013'

ENCODE_PAGE = '''static String rpc_capture_page(uint32_t part, uint32_t page) {
  // Called by rpc_history while holding g_control_owner, after its RUN guard.
  const bool adc = part == 3U;
  if (!(adc ? g_peak.complete : g_observer_trace.complete)) return "ERR NOT_COMPLETE";
  const uint8_t *data = adc ? g_peak.data : g_observer_trace.data;
  const unsigned size = adc ? (unsigned)PC_WIRE_BYTES : (unsigned)OD_WIRE_BYTES;
  const unsigned chunk = 192U;
  if (page >= (size + chunk - 1U) / chunk) return "ERR PAGE";
  const unsigned offset = page * chunk;
  const unsigned count = size - offset < chunk ? size - offset : chunk;
  String reply;
  reply.reserve(440);
  reply = "CP ";
  reply += String((unsigned long)part);
  reply += " "; reply += String((unsigned long)page);
  reply += " "; reply += String((unsigned long)size);
  reply += " "; reply += String((unsigned long)odw_u32(data + 8));
  reply += " "; reply += String((unsigned long)odw_u32(data + 60));
  reply += " ";
  const char hex[] = "0123456789abcdef";
  for (unsigned i = offset; i < offset + count; ++i) {
    reply += hex[data[i] >> 4];
    reply += hex[data[i] & 15];
  }
  return reply;
}

'''

DECODE_PAGE = '''CAPTURE_PAGES = {"adc": (3, 1024), "observer": (4, 1888)}


def parse_capture_page(value, part, page, expected_size):
    if not isinstance(value, str) or len(value) > 440:
        raise ValueError("Invalid capture page")
    fields = value.split()
    if len(fields) != 7 or fields[0] != "CP":
        raise ValueError("Capture page unavailable")
    identity = tuple(map(int, fields[1:6]))
    chunk = bytes.fromhex(fields[6])
    if (identity[:4] != (part, page, expected_size, 2026111810)
            or not 0 <= identity[4] <= 0xffffffff
            or len(chunk) != min(192, expected_size - page * 192)):
        raise ValueError("Capture page identity or length changed")
    return {"part": part, "page": page, "total": expected_size, "firmware": identity[3],
            "crc32c": identity[4], "hex": chunk.hex()}


def receive_capture_pages(fetch, kind):
    part, expected_size = CAPTURE_PAGES[kind]
    chunks = []
    crc = None
    for page in range((expected_size + 191) // 192):
        data = fetch(kind, page)
        if (data["part"], data["page"], data["total"], data["firmware"]) != (
            part, page, expected_size, 2026111810
        ):
            raise ValueError("Capture page identity changed")
        if crc is None:
            crc = data["crc32c"]
        if data["crc32c"] != crc:
            raise ValueError("Capture changed while downloading")
        chunk = bytes.fromhex(data["hex"])
        if len(chunk) != min(192, expected_size - page * 192):
            raise ValueError("Capture page length changed")
        chunks.append(chunk)
    record = b"".join(chunks)
    if (len(record) != expected_size or int.from_bytes(record[8:12], "little") != 2026111810
            or int.from_bytes(record[60:64], "little") != crc
            or crc32c(record[:60] + bytes(4) + record[64:]) != crc):
        raise ValueError("Capture CRC or identity mismatch")
    return record


'''

HTTP_PAGE = '''        if parsed.path == "/api/capture-page":
            if not self._require_control_access(mark_heartbeat=False):
                return
            query = parse_qs(parsed.query)
            kind = query.get("kind", [""])[0]
            try:
                part, total = CAPTURE_PAGES[kind]
                page = int(query.get("page", [""])[0])
                if not 0 <= page < (total + 191) // 192:
                    raise ValueError("Invalid page")
            except (KeyError, ValueError):
                self._send_json({"ok": False, "error": "Invalid capture page"}, 400)
                return
            reply = self.server.app.rpc._call("history", [part, page], timeout=1.5, retries=0)
            if reply is None or len(reply) != 4 or reply[2] is not None:
                self._send_json({"ok": False, "error": "Capture RPC unavailable"}, 503)
                return
            if reply[3] in ("ERR NOT_COMPLETE", "ERR RUN"):
                self._send_json({"ok": False, "error": reply[3]}, 409)
                return
            try:
                data = parse_capture_page(reply[3], part, page, total)
            except ValueError:
                self._send_json({"ok": False, "error": "Invalid capture data"}, 502)
                return
            self._send_json({"ok": True, "data": data})
            return
'''


def replace_once(text, original, replacement):
    if text.count(original) != 1:
        raise ValueError(f'Unexpected source for {original!r}')
    return text.replace(original, replacement, 1)


def strip_blob(text, field):
    start = text.index(f'  s += " {field}_hex=";')
    next_field = 'good' if field == 'mc_adc_peak' else 'complete'
    end = text.index(f'  s+=" {field}_{next_field}=";', start)
    return text[:start] + f'  s += " {field}_hex=-";\n' + text[end:]


def main():
    OUT.mkdir()
    for name in ('UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('__pycache__', 'backups'))
    sketch = OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino'
    firmware = sketch.read_text(encoding='utf-8').replace(OLD_UNO, NEW_UNO)
    marker = 'static String rpc_history(uint32_t part,uint32_t page) {'
    firmware = replace_once(firmware, marker, ENCODE_PAGE + marker)
    marker = '  if(!g_start_history.complete)return "ERR NOT_COMPLETE";'
    firmware = replace_once(firmware, marker, '  if (part == 3U || part == 4U) return rpc_capture_page(part, page);\n' + marker)
    for field in ('mc_adc_peak', 'mc_observer_trace'):
        firmware = strip_blob(firmware, field)
    sketch.write_text(firmware, encoding='utf-8')
    path = OUT / 'web_hmi/server.py'
    server = path.read_text(encoding='utf-8').replace(OLD_UNO, NEW_UNO)
    marker = 'class RpcBridge:'
    server = replace_once(server, marker, DECODE_PAGE + marker)
    marker = '        if parsed.path == "/api/status":'
    server = replace_once(server, marker, HTTP_PAGE + marker)
    path.write_text(server, encoding='utf-8')


if __name__ == '__main__':
    main()
