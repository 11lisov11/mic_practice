"""Local-only operator console. Simulation is the default; no auto-start/arming."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser

from .control import PROFILES, readiness
from .runner import dump, probe, probe_red_controller, run_live
from .simulation import export_csv, simulate


def serve(config_path, port=8094, open_browser=True):
    config_path=Path(config_path).resolve()
    root=Path(__file__).resolve().parents[1]
    state={"busy":False,"message":"Готово к проверке. Привод ещё не квалифицирован.","result":None}
    lock=threading.Lock()
    cancel=threading.Event()
    worker_holder=[]

    def job(mode,profile):
        try:
            config=json.loads(config_path.read_text(encoding="utf-8-sig"))
            if mode=="red_probe":
                result=probe_red_controller(config)
            elif mode=="probe":result=probe(config)
            else:
                folder=root/"artifacts"/"t3d_runs"/(time.strftime("%Y%m%d_%H%M%S")+"_"+str(time.time_ns()%1000000)+"_"+mode)
                if mode=="simulate":result=simulate(config,profile,folder)
                else:result=run_live(config,profile,folder,cancel=cancel.is_set)
                export_csv(folder)
                result={"completed":result["completed"],"simulation":result["simulation"],"folder":str(folder)}
            with lock:state.update(message="Завершено",result=result)
        except BaseException as exc:
            with lock:state.update(message=f"{type(exc).__name__}: {exc}",result=None)
        finally:
            with lock:state["busy"]=False

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send_json(self,value,code=200):
            data=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code);self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.path=="/favicon.ico":
                self.send_response(204);self.end_headers()
            elif self.path=="/":
                data=(Path(__file__).parent/"console.html").read_bytes()
                self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            elif self.path=="/api/status":
                config=json.loads(config_path.read_text(encoding="utf-8-sig"))
                with lock:value=dict(state)
                value.update(missing=readiness(config),kit=config["kit"],config=str(config_path),red_board=config.get("red_board",{}))
                self.send_json(value)
            else:self.send_json({"error":"not_found"},404)
        def do_POST(self):
            if self.headers.get("Origin") not in (None,f"http://127.0.0.1:{port}",f"http://localhost:{port}"):
                return self.send_json({"error":"origin"},403)
            if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                return self.send_json({"error":"content_type"},415)
            try:
                length=int(self.headers.get("Content-Length",0))
                if not 0<length<=2048:raise ValueError("body_size")
                data=json.loads(self.rfile.read(length))
                if self.path=="/api/stop":
                    cancel.set();return self.send_json({"message":"Остановка запрошена; ждите подтверждения в журнале"})
                if self.path!="/api/job":return self.send_json({"error":"not_found"},404)
                mode,profile=data.get("mode"),data.get("profile","step")
                if mode not in ("simulate","probe","red_probe","run") or profile not in PROFILES:raise ValueError("job")
                config=json.loads(config_path.read_text(encoding="utf-8-sig"))
                if mode=="run" and readiness(config):
                    return self.send_json({"error":"commissioning_incomplete","missing":readiness(config)},409)
                with lock:
                    if state["busy"]:return self.send_json({"error":"busy"},409)
                    state.update(busy=True,message="Выполняется "+mode,result=None)
                cancel.clear()
                worker=threading.Thread(target=job,args=(mode,profile),daemon=False)
                worker_holder[:]=[worker]
                worker.start()
                self.send_json({"accepted":True},202)
            except Exception as exc:self.send_json({"error":str(exc)},400)
    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    if open_browser:webbrowser.open(f"http://127.0.0.1:{port}/")
    try:server.serve_forever()
    finally:
        cancel.set();server.server_close()
        if worker_holder:worker_holder[0].join(timeout=3)
