"""No manual key entry in the local bench UI; preserve API keys and heartbeats."""
from pathlib import Path
import ast

def once(s,a,b):
    assert s.count(a)==1,a[:100]
    return s.replace(a,b)

def enable(root):
    root=Path(root);f=root/'server.py';s=f.read_text(encoding='utf-8')
    s=once(s,'class AppState:',(Path(__file__).parent/'ui_sessions.py').read_text(encoding='utf-8')+'\n\nclass AppState:')
    s=once(s,'        self.control_access = control_access or ControlAccessConfig()',
             '        self.control_access = control_access or ControlAccessConfig()\n        self.ui_sessions = UiSessionStore()')
    a=s.index('    def _send_static(');b=s.index('\n    def ',a+5);chunk=s[a:b]
    chunk=once(chunk,'            self.end_headers()', '''            self.send_header("Cache-Control", "no-store")
            if name == "index.html" and self.server.app.control_access.enabled:
                cookie=self.server.app.ui_sessions.issue(self.headers.get("Cookie", ""))
                self.send_header("Set-Cookie", cookie)
            self.end_headers()''')
    s=s[:a]+chunk+s[b:]
    s=once(s,'        if expected and provided and secrets.compare_digest(provided, expected):',
       '''        header_ok = bool(expected and provided and provided.isascii() and secrets.compare_digest(provided, expected))
        cookie_ok = self.server.app.ui_sessions.valid(self.headers.get("Cookie", ""))
        if header_ok or cookie_ok:''')
    s=once(s,'        data["hmi_control_auth_required"] = int(self.server.app.control_access.enabled)',
       '        data["hmi_ui_session_active"] = int(self.server.app.ui_sessions.valid(self.headers.get("Cookie", "")))\n        data["hmi_control_auth_required"] = int(self.server.app.control_access.enabled)')
    ast.parse(s);f.write_text(s,encoding='utf-8',newline='\n')
    f=root/'static/app.js';s=f.read_text(encoding='utf-8')
    s=once(s,'let controlAuthRequired = false;','let controlAuthRequired = false;\nlet controlCookieActive = false;')
    s=once(s,'  if (controlToken) headers["X-UNOQ-Control-Token"] = controlToken;',
       '  if (controlToken && !controlCookieActive) headers["X-UNOQ-Control-Token"] = controlToken;')
    s=once(s,'  if (!controlAuthRequired || !controlToken) return;',
       '  if (!controlAuthRequired || (!controlToken && !controlCookieActive)) return;')
    s=once(s,'function updateSimpleUI(data) {','function updateSimpleUI(data) {\n  controlCookieActive = Number(data.hmi_ui_session_active) === 1;')
    f.write_text(s,encoding='utf-8',newline='\n')
    f=root/'static/index.html';s=f.read_text(encoding='utf-8').replace('?ui=2911','?ui=2911-final');f.write_text(s,encoding='utf-8',newline='\n')

if __name__=='__main__':
    import sys
    enable(Path(sys.argv[1]))
