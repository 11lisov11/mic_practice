class RouterClient:
    def __init__(self, endpoint: str) -> None:
        if msgpack is None:
            raise RuntimeError("msgpack not available")
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._unpacker: Optional[msgpack.Unpacker] = None
        self._packer = msgpack.Packer(use_bin_type=False)
        self._msgid = 1
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._unpacker = None

    def _connect(self) -> None:
        if self._sock is not None:
            return
        endpoint = self._endpoint
        if endpoint.startswith("unix:"):
            path = endpoint[5:]
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(path)
        elif "/" in endpoint or endpoint.startswith("."):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(endpoint)
        else:
            host, port = self._parse_tcp(endpoint)
            sock = socket.create_connection((host, port), timeout=1.0)
        sock.settimeout(0.2)
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
        for attempt in range(retries + 1):
            with self._lock:
                try:
                    self._connect()
                    if self._sock is None or self._unpacker is None:
                        raise RuntimeError("no socket")
                    msgid = self._msgid
                    self._msgid += 1
                    self._sock.sendall(self._packer.pack([0, msgid, method, params]))
                    deadline = _now_ts() + timeout
                    while _now_ts() < deadline:
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
                    raise RuntimeError("router timeout")
                except Exception:
                    self.close()
            if attempt < retries:
                time.sleep(0.05)
        return None


