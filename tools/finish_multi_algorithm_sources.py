"""Finish candidate sources only. Does not build, flash, reset, clear, or start."""
import ast
from pathlib import Path
from prepare_multi_algorithm import ROOT,OUT,read,write,once
def main():
    for src,dst in [('motor_control.h','nucleo/Inc/motor_control.h'),('native.h','nucleo/Inc/multi_native.h'),('native.c','nucleo/Src/multi_native.c'),('research_wire.h','UNOQ_MOTOR/research_wire.h'),('research_wire.h','nucleo/Inc/research_wire.h')]:
        write(OUT/dst,read(ROOT/'tools/multi_algorithm'/src))
    f=OUT/'nucleo/STM32CubeIDE/.project';s=read(f)
    if 'Application/User/multi_native.c' not in s:
        s=once(s,'\t<linkedResources>','''\t<linkedResources>
        <link><name>Application/User/multi_native.c</name><type>1</type>
        <locationURI>PARENT-1-PROJECT_LOC/Src/multi_native.c</locationURI></link>''');write(f,s)
    f=OUT/'web_hmi/server.py';s=read(f)
    s=s.replace('2026102911','2026102921').replace('2026102912','2026102922')
    s=once(s,"data.get('research_native_caps')==1","data.get('research_native_caps')==7")
    s=once(s,"        ready=name=='VF_FIXED' and native", "        ready=native and (name=='VF_FIXED' or name in ('FOC_FIXED','ADAPTIVE_PWM') and data.get('algorithm_qualification')==7)")
    s=once(s,"        else:code,text=RESEARCH_BLOCKS[name]", "        elif name in ('FOC_FIXED','ADAPTIVE_PWM'):code,text='PHYSICAL_FOC_QUALIFICATION_REQUIRED','Код собран и проверен на модели; нужны идентификация двигателя, проверка ампер и времени расчёта на MCU.'\n        else:code,text=RESEARCH_BLOCKS[name]")
    s=once(s,"    data['research_actuator_algorithm']='VF_FIXED' if data.get('mc_capabilities')==1 else None", "    data['research_actuator_algorithm']={1:'VF_FIXED',2:'FOC_FIXED',3:'ADAPTIVE_PWM'}.get(data.get('algorithm_selected'))\n    data['research_speed_source']='current_model_estimate'\n    data['research_speed_is_measured']=False")
    anchor='                "research_native_bad": int(kv.get("research_native_bad","0")),'
    keys=('algorithm_selected','algorithm_requested','algorithm_qualification','algorithm_profile_crc','algorithm_fast_cycles','algorithm_observer_cycles','algorithm_fault','rpm_est_valid')
    s=once(s,anchor,anchor+'\n'+''.join('                "'+k+'": int(kv.get("'+k+'","0")),\n' for k in keys)+'                "rpm_est": float(kv.get("rpm_est","nan")),')
    s=once(s,'            "/api/cmd",','            "/api/cmd",\n            "/api/algorithm",')
    s=once(s,'        if parsed.path == "/api/cmd":','''        if parsed.path == "/api/algorithm":
            request=self._read_json();algorithm=request.get("algorithm")
            if type(algorithm) is not int or algorithm not in (1,2,3):
                self._send_json({"ok":False,"error":"Неизвестный алгоритм"},400);return
            app=self.server.app
            with app.control_lock:
                ok,status,err=app.rpc.get()
                if not ok or not status or (status.get("fw_build"),status.get("mc_fw_build"))!=(2026102921,2026102922) or status.get("research_native_caps")!=7 or status.get("research_native_valid")!=1 or status.get("pwm")!=0 or status.get("state")!="SAFE" or not 0<=status.get("mc_age_ms",9999)<300:
                    self._send_json({"ok":False,"error":"Сначала остановите привод; нужна свежая связь"},409);return
                ok,err=app.rpc.cmd("SET ALGORITHM "+{1:"VF",2:"FOC",3:"ADAPTIVE_PWM"}[algorithm])
                app.logs.add(f"ALGORITHM_CONFIG {algorithm} accepted={int(ok)}")
            self._send_json({"ok":ok,"error":err or ""},200 if ok else 409);return
        if parsed.path == "/api/cmd":''')
    # Bound NaN representation; unknown estimator data is never a valid speed.
    s=s.replace('"rpm_est": float(kv.get("rpm_est","nan")),','"rpm_est": float(kv.get("rpm_est","0")),')
    ast.parse(s);write(f,s)
    f=OUT/'web_hmi/static/index.html';s=read(f).replace('2911-final','2921-model')
    s=once(s,'  <p class="simple-mode" id="simpleMode">Скалярный V/f</p>','''  <label for="algorithmSelect">Алгоритм</label>
  <select id="algorithmSelect" style="color:#f2f5fa;background:#10151c;border:1px solid #354151;border-radius:10px;padding:12px;font-size:16px;width:100%;min-height:46px" disabled aria-describedby="algorithmNote">
    <option value="1">Скалярный V/f</option><option value="2">Векторный FOC</option>
    <option value="3">FOC + адаптивный ШИМ</option>
  </select>
  <p class="simple-mode" id="simpleMode">Ожидание режима</p>
  <p class="simple-note" id="algorithmNote" role="status">Загрузка…</p>''')
    write(f,s)
    f=OUT/'web_hmi/static/app.js';write(f,read(f)+'\n'+read(ROOT/'tools/multi_algorithm/panel.js'))
    print('Candidate sources finished; no hardware commands')
if __name__=='__main__':main()
