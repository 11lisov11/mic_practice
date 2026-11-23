"""Complete commissioning HMI transport; no network or MCU operations."""
from prepare_standstill_commissioning import ROOT,BASE,OUT,NEW,read,write,once
import ast
def main():
 f=OUT/'web_hmi/server.py';s=read(f).replace('2026102921',str(NEW[0])).replace('2026102922',str(NEW[1]))
 s=once(s,"data.get('research_native_caps')==7","data.get('research_native_caps')==15")
 s=s.replace('status.get("research_native_caps")!=7','status.get("research_native_caps")!=15')
 s=once(s,'algorithm not in (1,2,3)','algorithm not in (1,2,3,4)')
 s=once(s,'{1:"VF",2:"FOC",3:"ADAPTIVE_PWM"}[algorithm]','{1:"VF",2:"FOC",3:"ADAPTIVE_PWM",4:"IDENT"}[algorithm]')
 # Preserve the audited predecessor's unchanged DC-bus measurement identity too.
 anchor='(2026102901,2026102902), (2026102931,2026102932),'
 s=once(s,anchor,'(2026102901,2026102902), (2026102921,2026102922), (2026102931,2026102932),')
 keys=('id_valid','id_flags','id_config_crc','id_result_crc','id_run_id','id_kind','id_duration_ms','id_fault',
       'id_wire_good','id_wire_bad','id_complete','id_view_page')
 anchor='                "rpm_est_valid": int(kv.get("rpm_est_valid","0")),'
 s=once(s,anchor,anchor+'\n'+''.join('                "'+k+'": int(kv.get("'+k+'","0")),\n' for k in keys)+
     '                "id_frequency": float(kv.get("id_frequency","0")),\n                "id_page_hex": kv.get("id_page_hex","-"),')
 anchor='        if parsed.path == "/api/status":'
 s=once(s,anchor,'''        if parsed.path == "/api/identification":
            if not self._require_control_access(mark_heartbeat=False):return
            try:page=int(parse_qs(parsed.query).get("page",["0"])[0])
            except (ValueError,TypeError):self._send_json({"ok":False,"error":"invalid page"},400);return
            if not 0<=page<13:self._send_json({"ok":False,"error":"invalid page"},400);return
            app=self.server.app
            with app.control_lock:
                ok,data,err=app.rpc.get()
                if not ok or not data or data.get("pwm")!=0 or data.get("state")!="SAFE" or data.get("id_complete")!=1:
                    self._send_json({"ok":False,"error":"No complete stopped capture"},409);return
                crc=data.get("id_result_crc")
                ok,err=app.rpc.cmd(f"IDENT PAGE {page}")
                if not ok:self._send_json({"ok":False,"error":err},409);return
                ok,data,err=app.rpc.get()
                if not ok or data.get("id_view_page")!=page or data.get("id_result_crc")!=crc or data.get("id_complete")!=1:
                    self._send_json({"ok":False,"error":"Capture page changed"},409);return
                self._send_json({"ok":True,"page":page,"crc32c":crc,"hex":data.get("id_page_hex"),"run_id":data.get("id_run_id")});return
        if parsed.path == "/api/status":''')
 s=once(s,'def command_requests_start(cmd: str) -> bool:',
    read(ROOT/'tools/motor_commissioning/hmi_completion.py')+'\n\ndef command_requests_start(cmd: str) -> bool:')
 anchor='''                if run_ok and running:
                    self.hv_arm.mark_started()'''
 completion='''                if run_ok and identification_point_complete(candidate,initial_status):
                    self.hv_arm.disarm()
                    return True,"Native identification completed before HTTP response",candidate
'''
 s=once(s,anchor,completion+anchor)
 # No implicit START is added. Completed-point reporting never replaces the
 # original pre-START guards; Uno requires a one-shot IDENT EXECUTE nonce.
 ast.parse(s);write(f,s)
 f=OUT/'web_hmi/static/index.html';s=read(f).replace('2921-model','2931-commissioning')
 s=once(s,'    <option value="3">FOC + адаптивный ШИМ</option>','    <option value="3">FOC + адаптивный ШИМ</option><option value="4">Измерение параметров</option>');write(f,s)
 f=OUT/'web_hmi/static/app.js';s=read(f)
 s=once(s,"3:'FOC · адаптивное положение ШИМ'","3:'FOC · адаптивное положение ШИМ',4:'Измерение параметров на неподвижной оси'")
 s=once(s,'  if(selected!==1){','''  if(selected===4){
    startBtn.disabled=true;
    note.textContent='Измерительный режим: отдельный тест с ограничением тока и автостопом.';
    document.getElementById('simpleField').textContent=`Измерительный сигнал: ${Number(data.id_frequency||0).toFixed(1)} Гц; ось поля фиксирована`;
  }
  if(selected!==1&&selected!==4){''')
 write(f,s)
 print('Commissioning HMI source prepared; no START or network operation')
if __name__=='__main__':main()
