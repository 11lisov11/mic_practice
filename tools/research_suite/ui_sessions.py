# Local bench UI: opening the control page creates an operator session.
# The persistent script/API control key is never sent to the browser.
class UiSessionStore:
    COOKIE='mic_ui_session'
    def __init__(self,clock=None,ttl=43200):
        self._clock=clock or time.monotonic
        self._ttl=ttl
        self._sessions={}
        self._lock=threading.RLock()

    def _read(self,header):
        from http.cookies import SimpleCookie
        try:
            if not isinstance(header,str) or len(header)>8192:return ''
            jar=SimpleCookie();jar.load(header)
            return jar[self.COOKIE].value if self.COOKIE in jar else ''
        except Exception:return ''

    def valid(self,header):
        value=self._read(header);now=self._clock()
        with self._lock:
            if not value or self._sessions.get(value,0)<=now:
                self._sessions.pop(value,None);return False
            self._sessions[value]=now+self._ttl
            return True

    def issue(self,header=''):
        from http.cookies import SimpleCookie
        value=self._read(header);now=self._clock()
        with self._lock:
            self._sessions={k:v for k,v in self._sessions.items() if v>now}
            if value not in self._sessions:
                if len(self._sessions)>=32:self._sessions.pop(min(self._sessions,key=self._sessions.get))
                value=secrets.token_urlsafe(32)
            self._sessions[value]=now+self._ttl
        jar=SimpleCookie();jar[self.COOKIE]=value
        for key,val in {'path':'/','httponly':True,'samesite':'Strict','max-age':str(self._ttl)}.items():jar[self.COOKIE][key]=val
        return jar[self.COOKIE].OutputString()
