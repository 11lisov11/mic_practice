"""Prepare Linux-only bounded/coalesced GET. No firmware or motor guard edits."""
from pathlib import Path
import shutil,json,hashlib

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261116/rpc_short_lock_r1'
OUT=ROOT/'artifacts/live_bench_20261116/rpc_hmi_admission_r1'

CLASS='''class RouterClient:
    def __init__(self, endpoint: str) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()
        self._flight_lock = threading.Lock()
        self._get_flight = None

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._unpacker = None

    def _connect(self, deadline: Optional[float] = None) -> None:
        if self._sock is not None:
            return
        remaining = 1.0 if deadline is None else min(1.0, deadline - time.monotonic())
        if remaining <= 0:
            raise TimeoutError("RPC connection deadline")
        endpoint = self._endpoint
        if endpoint.startswith("unix:") or "/" in endpoint or endpoint.startswith("."):
            path = endpoint[5:] if endpoint.startswith("unix:") else endpoint
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(remaining)
            try:
                sock.connect(path)
            except Exception:
                sock.close()
                raise
        else:
            host, port = self._parse_tcp(endpoint)
            sock = socket.create_connection((host, port), timeout=remaining)
        sock.settimeout(min(0.2, remaining))
        self._sock = sock
        self._unpacker = msgpack.Unpacker(raw=False)

    @staticmethod
    def _parse_tcp(endpoint: str) -> tuple[str, int]:
        if ":" in endpoint:
            host, port_str = endpoint.rsplit(":", 1)
        else:
            host, port_str = endpoint, "7501"
        host = host or "127.0.0.1"
        try:
            port = int(port_str)
        except ValueError:
            port = 7501
        return host, port

    def call(self, method: str, params: list, timeout: float = 1.5, retries: int = 1) -> Optional[list]:
        if method != "get" or params:
            # Commands and capture-page changes fence all preceding reads.
            # Never merge, cache or replay a command.
            with self._flight_lock:
                self._get_flight = None
            return self._call_serial(method, params, timeout, retries)
        with self._flight_lock:
            flight = self._get_flight
            leader = flight is None
            if leader:
                flight = {"done": threading.Event(), "reply": None}
                self._get_flight = flight
        if not leader:
            budget = max(0.0, timeout) * (max(0, retries) + 1) + 0.05 * max(0, retries)
            if not flight["done"].wait(budget):
                return None
            return _rpc_copy.deepcopy(flight["reply"])
        reply = None
        try:
            reply = self._call_serial(method, params, timeout, retries)
            return reply
        finally:
            with self._flight_lock:
                flight["reply"] = _rpc_copy.deepcopy(reply)
                flight["done"].set()
                if self._get_flight is flight:
                    self._get_flight = None

    def _call_serial(self, method: str, params: list, timeout: float, retries: int) -> Optional[list]:
        for attempt in range(retries + 1):
            # Queueing, connection, sending and reading share one attempt budget.
            # Wall-clock/NTP changes cannot extend a transport deadline.
            deadline = time.monotonic() + max(0.0, timeout)
            acquired = self._lock.acquire(timeout=max(0.0, timeout))
            if acquired:
                try:
                    self._connect(deadline)
                    if self._sock is None or self._unpacker is None:
                        raise RuntimeError("no socket")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("RPC admission deadline")
                    self._sock.settimeout(min(0.2, remaining))
                    msgid = self._msgid
                    self._msgid += 1
                    self._sock.sendall(self._packer.pack([0, msgid, method, params]))
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("router timeout")
                        self._sock.settimeout(min(0.2, remaining))
                        try:
                            data = self._sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not data:
                            raise RuntimeError("router closed")
                        self._unpacker.feed(data)
                        for obj in self._unpacker:
                            if isinstance(obj, list) and len(obj) >= 4 and obj[0] == 1 and obj[1] == msgid:
                                return obj
                except Exception:
                    self.close()
                finally:
                    self._lock.release()
            # A caller which never owned the socket must not close another call.
            if attempt < retries:
                time.sleep(0.05)
        return None


'''

def main():
    OUT.mkdir(exist_ok=False)
    shutil.copytree(BASE/'web_hmi',OUT/'web_hmi',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    f=OUT/'web_hmi/server.py';original=f.read_text(encoding='utf8')
    a=original.index('class RouterClient:');b=original.index('class SerialClient:',a)
    before=original[:a].replace('import argparse\n','import argparse\nimport copy as _rpc_copy\n',1)
    f.write_text(before+CLASS+original[b:],encoding='utf8')
    # Everything after RouterClient includes all motor guards and decoding.
    assert f.read_text(encoding='utf8').split('class SerialClient:',1)[1]==original[b:].split('class SerialClient:',1)[1]
    (OUT/'manifest.json').write_text(json.dumps(dict(scope='Linux HMI RouterClient only',pair=[2026111609,2026111606],
        motor_guards_unchanged=True,firmware_changes=0,START=0,CLEAR=0,installed=False,
        source_sha256=hashlib.sha256(f.read_bytes()).hexdigest()),indent=2)+'\n')
    print(OUT)

if __name__=='__main__':main()
