"""Manual scalar UI/backend transforms; ordinary authentication and guards retained."""
from manual_scalar_sources import replace

def server(s):
    s=replace(s,'(2026101415, 2026101414),','(2026101415, 2026101414),\n        (2026101501, 2026101502),')
    s=replace(s,'2026101493, 2026101412, 2026101414)','2026101493, 2026101412, 2026101414, 2026101502)')
    anchor='    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101414'
    s=replace(s,anchor,'''    if cfg.profile == ARM_PROFILE_HV and _as_int(data or {}, "mc_fw_build", -1) == 2026101502 and _as_int(data or {}, "fw_build", -1) != 2026101501:
        return False, "manual scalar image requires its matching supervisory firmware"
'''+anchor)
    s=replace(s,'class HvArmState:', '''def manual_scalar_supported(data):
    return bool(data and _as_int(data,"fw_build",0)==2026101501 and
        _as_int(data,"mc_fw_build",0)==2026101502 and _as_int(data,"manual_scalar_capable",0)==1)

class HvArmState:''')
    # Only the runtime session becomes continuous. An unused ARM still expires.
    s=replace(s,'        self._started = False\n        self._calibration_provider',
        '        self._started = False\n        self._manual_session = False\n        self._calibration_provider')
    s=replace(s,'    def mark_started(self) -> None:', '''    def set_manual_session(self, enabled: bool) -> None:
        with self._lock:
            self._manual_session = bool(enabled)

    def mark_started(self) -> None:''')
    s=replace(s,'            if remaining <= 0.0:\n                if not self._started:',
        '            if remaining <= 0.0 and not (self._started and self._manual_session):\n                if not self._started:')
    s=replace(s,'            if self._expires_at <= 0.0:\n                return False',
        '            if self._started and self._manual_session:\n                return False\n            if self._expires_at <= 0.0:\n                return False')
    s=replace(s,'return self._started and self._expires_at > _now_ts()',
        'return self._started and (self._manual_session or self._expires_at > _now_ts())')
    s=replace(s,'"hmi_hv_armed": int(remaining > 0.0),','"hmi_hv_armed": int(remaining > 0.0 or (self._started and self._manual_session)),')
    s=replace(s,'"hmi_hv_started": int(self._started and remaining > 0.0),',
        '"hmi_hv_started": int(self._started and (self._manual_session or remaining > 0.0)),\n                "hmi_run_continuous": int(self._started and self._manual_session),')
    a=s.index('class HvArmState:');b=s.index('class ControlAccessConfig:',a)
    block=s[a:b].replace('            self._started = False','            self._started = False\n            self._manual_session = False')
    # Conditional expiry branches must reset both fields together.
    block=block.replace('                self._started = False\n            self._manual_session = False',
        '                self._started = False\n                self._manual_session = False')
    s=s[:a]+block+s[b:]
    anchor='            return True, with_motor_controller_aliases(data), None'
    s=replace(s,anchor,'''            if len(result) >= 99:
                data.update(manual_scalar_capable=int(result[91]),manual_run_mode=int(result[92]),
                    accel_hz_per_s=float(result[93]),decel_hz_per_s=float(result[94]),
                    downmode_coast=int(result[95]),mc_frequency_reference_hz=float(result[96]),
                    mc_frequency_reference_valid=int(result[97]),mc_decel_bus_hold=int(result[98]))
                if manual_scalar_supported(data) and data["mc_frequency_reference_valid"]==1 and _as_int(data,"bp_age_ms",999999)<300:
                    data["local_ramp_reference_hz"]=data["freq"]
                    data["freq"]=data["mc_frequency_reference_hz"]
                    data["speed"]=data["freq"]*60.0  # audited AIR56B2: one pole pair; reference, not rotor speed
'''+anchor)
    s=replace(s,'        self._operator_heartbeat_ts = 0.0',
        '        self._operator_heartbeat_ts = 0.0\n        self._manual_start_requested = False\n        self._manual_mcu_watchdog = False')
    s=replace(s,'''    def mark_operator_heartbeat(self) -> None:
        with self._lock:
            self._operator_heartbeat_ts = time.monotonic()''', '''    def mark_operator_heartbeat(self) -> bool:
        if self._manual_mcu_watchdog:
            ok, error = self.rpc.cmd("CONTROL HEARTBEAT")
            if not ok:
                self.logs.add("MANUAL_OPERATOR_HEARTBEAT_FAIL " + str(error))
                return False
        with self._lock:
            self._operator_heartbeat_ts = time.monotonic()
        return True''')
    s=replace(s,'        primary_cmd = "ESTOP" if emergency else "STOP"',
        '        self._manual_mcu_watchdog = False\n        primary_cmd = "ESTOP" if emergency else "STOP"')
    start=s.index('    def start_sequence(');end=s.index('    def _start_without_precharge(',start)
    block=s[start:end]
    block=replace(block,'        runlimit_sec: Optional[float] = None,','        runlimit_sec: Optional[float] = None,\n        manual_run: bool = False,')
    block=replace(block,'        effective_limit = self.start_runlimit_sec', '''        if type(manual_run) is not bool or (manual_run and runlimit_sec is not None):
            return False, "manual mode cannot be combined with a timed run limit", None
        effective_limit = self.start_runlimit_sec''')
    block=replace(block,'        st_ok, status, st_err = self.rpc.get()', '''        st_ok, status, st_err = self.rpc.get()
        if manual_run and not (manual_scalar_supported(status) and self.control_access.enabled and
                self.hv_arm.cfg.enabled and self.hv_arm.cfg.profile==ARM_PROFILE_HV and
                self.hv_arm.cfg.trial_gate is None and self.operator_heartbeat_fresh()):
            return False, "manual scalar requires matching firmware, authenticated live control and normal HV profile", status''')
    block=replace(block,'        return self._start_without_precharge(status, run_timeout_sec, poll_sec, effective_limit)',
        '        self._manual_start_requested = manual_run\n        return self._start_without_precharge(status, run_timeout_sec, poll_sec, effective_limit)')
    s=s[:start]+block+s[end:]
    s=replace(s,'        runlimit_cmd = f"SET RUNLIMIT {self.start_runlimit_sec if effective_limit is None else effective_limit:.3f}"', '''        if manual_scalar_supported(initial_status):
            mode = "MANUAL" if self._manual_start_requested else "BOUNDED"
            setup = ["SET RUNMODE " + mode]
            if self._manual_start_requested:
                setup.append("CONTROL HEARTBEAT")
                effective_limit = 0.0
            for command in setup:
                setup_ok, setup_error = self.rpc.cmd(command)
                if not setup_ok:
                    self.stop_sequence()
                    return False, "manual setup failed: " + str(setup_error), initial_status
            self._manual_mcu_watchdog = self._manual_start_requested
            self.hv_arm.set_manual_session(self._manual_start_requested)
        runlimit_cmd = f"SET RUNLIMIT {self.start_runlimit_sec if effective_limit is None else effective_limit:.3f}"''')
    s=replace(s,'        snapshot["hmi_start_runlimit_s"] = round(self.start_runlimit_sec, 1)',
        '        snapshot["hmi_start_runlimit_s"] = round(self.start_runlimit_sec, 1)\n        snapshot["hmi_manual_scalar_supported"] = int(manual_scalar_supported(status))')
    s=replace(s,'                self.server.app.mark_operator_heartbeat()  # type: ignore[attr-defined]', '''                if self.server.app.mark_operator_heartbeat() is False:  # type: ignore[attr-defined]
                    self._send_json({"ok":False,"error":"MCU operator heartbeat was not acknowledged"},503)
                    return False''')
    s=replace(s,'            if "runlimit_s" in request:\n                ok, detail, status = app.start_sequence(runlimit_sec=request["runlimit_s"])',
        '            if "manual" in request:\n                ok, detail, status = app.start_sequence(manual_run=request["manual"],runlimit_sec=request.get("runlimit_s"))\n            elif "runlimit_s" in request:\n                ok, detail, status = app.start_sequence(runlimit_sec=request["runlimit_s"])')
    return s

def html(s):
    s=replace(s,'        <div class="freq-block">', '''        <div class="manual-config" id="manualConfig" hidden>
          <p>Задание 0–50 Гц. Пуск продолжает работу до «Стоп»; «Стоп» — свободный выбег.</p>
          <div class="hv-arm-note" id="manualState">Настройки доступны после подключения.</div>
          <details class="manual-settings">
            <summary>Настройки разгона и снижения</summary>
            <label>Разгон, Гц/с <input id="manualAccel" type="number" min="0.1" max="50" step="0.1" value="5" /></label>
            <label>Замедление, Гц/с <input id="manualDecel" type="number" min="0.1" max="5" step="0.1" value="1" /></label>
            <button class="btn ghost full" id="manualApply">Применить настройки</button>
            <label>Снижение задания <select id="manualDownmode"><option value="RAMP">Плавно, с контролем DC-шины</option><option value="COAST">Выбег, затем отдельный пуск</option></select></label>
          </details>
        </div>
        <div class="freq-block">''')
    start=s.index('        <div class="manual-config"')
    end=s.index('        <div class="freq-block">',start)
    panel=s[start:end];s=s[:start]+s[end:]
    anchor='        <div class="hv-arm-block"'
    s=replace(s,anchor,panel+anchor)
    s=replace(s,'''          <input
            id="hvArmConfirm"
            class="hv-arm-input"
            type="text"
            inputmode="text"
            autocomplete="off"
            autocapitalize="characters"
            placeholder="Введите ARM 310V"
          />
''','')
    s=replace(s,'          <div class="vbus-capture-block">',
        '          <details class="vbus-capture-block"><summary>Калибровка DC-шины</summary>')
    s=replace(s,'            <button class="btn ghost full" id="vbusResetBtn">Сбросить калибровку Vbus</button>\n          </div>',
        '            <button class="btn ghost full" id="vbusResetBtn">Сбросить калибровку Vbus</button>\n          </details>')
    return s

def javascript(s):
    s=replace(s,'  await apiSequence("/api/start-sequence");', '''  const capable=document.getElementById("manualConfig")?.hidden===false;
  if (capable && Number(freqSlider.value)<=0) {
    document.getElementById("manualState").textContent="Задайте частоту выше 0 Гц перед пуском.";
    startBtn.disabled=false;
    return;
  }
  if (capable && hvArmBlock && !hvArmBlock.hidden && !hvArmed) {
    const armed=await apiHvArm("arm", hvArmConfirmPhrase);
    if (!armed.ok) { await refreshStatus(); startBtn.disabled=false; return; }
  }
  await apiSequence("/api/start-sequence", capable ? {manual:true} : {});''')
    s=replace(s,'    setHvArmUI(data);','    setHvArmUI(data);\n    updateManualUI(data);')
    s=replace(s,'  hvArmTimer.textContent = `${remaining.toFixed(1)} с`;',
        '  hvArmTimer.textContent = Number(data.hmi_run_continuous)===1 ? "до STOP" : `${remaining.toFixed(1)} с`;')
    s=replace(s,'setModeUI("VF");\nsetFreqUI(10.0);', '''function updateManualUI(data) {
  const panel=document.getElementById("manualConfig");
  const supported=Number(data.hmi_manual_scalar_supported)===1;
  panel.hidden=!supported;
  if (!supported) return;
  document.querySelector(".io-block")?.setAttribute("hidden", "");
  const modeRow=document.querySelector(".mode-row");
  if (modeRow) modeRow.hidden=supportedModes.length<=1;
  if (armProfileToggle) armProfileToggle.hidden=String(data.hmi_arm_profile||"hv").toLowerCase()==="hv";
  if (hvArmBtn) hvArmBtn.hidden=true;
  armProfileNote.textContent="Пуск включает ограниченное разрешение автоматически. Работа до «Стоп»; при потере связи или защите ШИМ отключается.";
  const running=Number(data.pwm)===1;
  document.getElementById("manualDownmode").disabled=running;
  for (const [id,key] of [["manualAccel","accel_hz_per_s"],["manualDecel","decel_hz_per_s"]]) {
    const input=document.getElementById(id);
    if (document.activeElement!==input && !input.dataset.dirty && Number.isFinite(Number(data[key]))) input.value=Number(data[key]).toFixed(1);
  }
  const mode=document.getElementById("manualDownmode");
  if (document.activeElement!==mode) mode.value=Number(data.downmode_coast)===1 ? "COAST" : "RAMP";
  const reference=Number(data.mc_frequency_reference_valid)===1 ? Number(data.mc_frequency_reference_hz).toFixed(1)+" Гц" : "нет свежего отсчёта";
  document.getElementById("manualState").textContent=(Number(data.mc_decel_bus_hold)===1 ? "Замедление приостановлено по DC-шине. " : "")+
    "Частота поля контроллера: "+reference+". Тормозной резистор отключён. Скорость ротора не измерена.";
}
document.getElementById("manualApply").addEventListener("click",async()=>{
  const accel=Number(document.getElementById("manualAccel").value);
  const decel=Number(document.getElementById("manualDecel").value);
  if (!Number.isFinite(accel) || accel<0.1 || accel>50 || !Number.isFinite(decel) || decel<0.1 || decel>5) return;
  if (await apiCmd(`SET ACCEL ${accel.toFixed(2)}`)) delete document.getElementById("manualAccel").dataset.dirty;
  if (await apiCmd(`SET DECEL ${decel.toFixed(2)}`)) delete document.getElementById("manualDecel").dataset.dirty;
  await refreshStatus();
});
document.getElementById("manualDownmode").addEventListener("change",async(e)=>{
  await apiCmd(`SET DOWNMODE ${e.target.value}`);await refreshStatus();
});
for (const id of ["manualAccel","manualDecel"]) {
  document.getElementById(id).addEventListener("input",e=>{e.target.dataset.dirty="1";});
}
setModeUI("VF");
setFreqUI(5.0);''')
    s=replace(s,'const hvArmConfirm = document.getElementById("hvArmConfirm");','')
    s=replace(s,'let hvArmed = false;','let hvArmed = false;\nlet hvArmConfirmPhrase = "";')
    s=replace(s,'  const confirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));',
        '  hvArmConfirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));')
    s=replace(s,'  if (hvArmConfirm) {\n    hvArmConfirm.disabled = hvArmed;\n    hvArmConfirm.placeholder = `Введите ${confirmPhrase}`;\n  }','')
    s=replace(s,'    const confirm = hvArmConfirm ? hvArmConfirm.value.trim().toUpperCase() : "";\n    const result = await apiHvArm(action, confirm);\n    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";\n',
        '    const result = await apiHvArm(action, action === "arm" ? hvArmConfirmPhrase : "");\n')
    s=replace(s,'if (hvArmConfirm) {\n  hvArmConfirm.addEventListener("input", () => {\n    hvArmLastError = "";\n  });\n}\n\n','')
    s=replace(s,'    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";\n','')
    s=replace(s,'    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired;',
        '    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired || Boolean(controlToken);')
    s=replace(s,'function noteApiAccess(data) {\n  if (data && data.error === "control access key is missing or invalid") {\n    setAccessStatus(false);\n  }\n}',
        'function noteApiAccess(data) {\n  if (data && data.error === "control access key is missing or invalid") {\n    if (controlAccessBlock) controlAccessBlock.hidden = false;\n    setAccessStatus(false);\n  }\n}')
    s=replace(s,'      setAccessStatus(true);\n    } else {',
        '      setAccessStatus(true);\n      if (controlAccessBlock) controlAccessBlock.hidden = Boolean(controlAuthRequired);\n    } else {')
    return s
