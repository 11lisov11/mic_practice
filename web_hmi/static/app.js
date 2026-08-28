const connDot = document.getElementById("connDot");
const connText = document.getElementById("connText");
const sysChip = document.getElementById("sysChip");
const sysText = document.getElementById("sysText");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const estopBtn = document.getElementById("estopBtn");
const hvArmBlock = document.getElementById("hvArmBlock");
const hvArmStatus = document.getElementById("hvArmStatus");
const hvArmTimer = document.getElementById("hvArmTimer");
const hvArmConfirm = document.getElementById("hvArmConfirm");
const hvArmBtn = document.getElementById("hvArmBtn");
const armProfileToggle = document.getElementById("armProfileToggle");
const armProfileButtons = armProfileToggle
  ? Array.from(armProfileToggle.querySelectorAll("[data-arm-profile]"))
  : [];
const armProfileLabel = document.getElementById("armProfileLabel");
const armProfileNote = document.getElementById("armProfileNote");
const vbusMeterInput = document.getElementById("vbusMeterInput");
const vbusCaptureBtn = document.getElementById("vbusCaptureBtn");
const vbusCaptureResult = document.getElementById("vbusCaptureResult");
const modeToggle = document.getElementById("modeToggle");
const modeButtons = Array.from(modeToggle.querySelectorAll(".seg"));
const freqSlider = document.getElementById("freqSlider");
const freqReadout = document.getElementById("freqReadout");
const pfcBtn = document.getElementById("pfcBtn");
const brakeSlider = document.getElementById("brakeSlider");
const brakeReadout = document.getElementById("brakeReadout");
const fanSlider = document.getElementById("fanSlider");
const fanReadout = document.getElementById("fanReadout");
const logHours = document.getElementById("logHours");
const logDownload = document.getElementById("logDownload");
const controlAccessBlock = document.getElementById("controlAccessBlock");
const controlTokenInput = document.getElementById("controlToken");
const controlTokenSave = document.getElementById("controlTokenSave");
const controlAccessStatus = document.getElementById("controlAccessStatus");
const stateVal = document.getElementById("stateVal");
const modeVal = document.getElementById("modeVal");
const backendVal = document.getElementById("backendVal");
const linkVal = document.getElementById("linkVal");
const pwmVal = document.getElementById("pwmVal");
const speedVal = document.getElementById("speedVal");
const vdcVal = document.getElementById("vdcVal");
const tempVal = document.getElementById("tempVal");
const currVal = document.getElementById("currVal");
const phaseVal = document.getElementById("phaseVal");
const idRefVal = document.getElementById("idRefVal");
const micSaveVal = document.getElementById("micSaveVal");
const ioVal = document.getElementById("ioVal");
const fanVal = document.getElementById("fanVal");
const encVal = document.getElementById("encVal");
const lastUpdate = document.getElementById("lastUpdate");

let dragging = false;
let freqTimer = null;
let lastSentFreq = null;
let lastEstop = false;
let brakeDragging = false;
let brakeTimer = null;
let lastBrakeDuty = null;
let fanDragging = false;
let fanTimer = null;
let lastFanDuty = null;
let pfcOn = false;
let supportedModes = ["VF"];
let hvArmed = false;
let hvArmLastError = "";
let armProfileSwitchReady = false;
let vbusCaptureBusy = false;
let controlAuthRequired = false;
let controlToken = localStorage.getItem("unoqControlToken") || "";

if (controlTokenInput) controlTokenInput.value = controlToken;

function controlHeaders(json = false) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (controlToken) headers["X-UNOQ-Control-Token"] = controlToken;
  return headers;
}

function setAccessStatus(ok, message = "") {
  if (!controlAccessStatus) return;
  controlAccessStatus.classList.toggle("ok", Boolean(ok));
  controlAccessStatus.textContent = message || (ok ? "Ключ сохранён" : "Требуется правильный ключ управления");
}

function noteApiAccess(data) {
  if (data && data.error === "control access key is missing or invalid") {
    setAccessStatus(false);
  }
}

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value)));
}

function mcField(data, suffix, fallback = 0) {
  const canonical = `mc_${suffix}`;
  const legacy = `bp_${suffix}`;
  if (Object.prototype.hasOwnProperty.call(data, canonical)) return data[canonical];
  if (Object.prototype.hasOwnProperty.call(data, legacy)) return data[legacy];
  return fallback;
}

function setConnection(ok) {
  connDot.classList.toggle("online", ok);
  connText.textContent = ok ? "онлайн" : "офлайн";
}

function setEstopButton(isLatched) {
  lastEstop = Boolean(isLatched);
  estopBtn.classList.toggle("active", lastEstop);
  estopBtn.textContent = lastEstop ? "Сброс ESTOP" : "Аварийный стоп";
}

function setModeUI(mode) {
  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  modeVal.textContent = mode;
}

function setFreqUI(value, fromStatus = false) {
  const v = Number(value);
  if (!fromStatus || !dragging) {
    freqSlider.value = v.toFixed(1);
  }
}

function updateTooltip(value) {
  const v = Number(value);
  freqReadout.textContent = `${v.toFixed(1)} Гц`;
  const min = Number(freqSlider.min);
  const max = Number(freqSlider.max);
  const percent = max > min ? (v - min) / (max - min) : 0;
  const rect = freqSlider.getBoundingClientRect();
  const left = rect.left + rect.width * percent;
  const parentRect = freqSlider.parentElement.getBoundingClientRect();
  const offset = left - parentRect.left;
  freqReadout.style.left = `${offset}px`;
}

function updateBrakeReadout(value) {
  brakeReadout.textContent = `BRK ${(clamp01(value) * 100).toFixed(0)}%`;
}

function updateFanReadout(value) {
  fanReadout.textContent = `FAN ${(clamp01(value) * 100).toFixed(0)}%`;
}

function mcModeName(mode) {
  const code = Number(mode);
  if (code === 5) return "FOC";
  if (code === 4) return "VECTOR";
  if (code === 3) return "SCALAR";
  if (code === 2) return "DUTY";
  if (code === 1) return "DIAG";
  return "OFF";
}

function mcFaultName(code) {
  const names = {
    1: "ESTOP",
    2: "ТАЙМ-АУТ",
    3: "CRC UART",
    4: "КАДР UART",
    5: "ВНУТРЕННЯЯ",
    6: "ТЕМПЕРАТУРА",
  };
  return names[Number(code)] || `КОД ${Number(code)}`;
}

function setIoButtons() {
  if (pfcBtn) {
    pfcBtn.classList.toggle("active", pfcOn);
    pfcBtn.textContent = `PFC: ${pfcOn ? "ON" : "OFF"}`;
  }
}

async function apiCmd(cmd) {
  const res = await fetch("/api/cmd", {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify({ cmd }),
  });
  const data = await res.json().catch(() => ({ ok: false }));
  noteApiAccess(data);
  if (data.ok !== true && hvArmStatus) {
    hvArmLastError = data.error || "Команда отклонена";
    hvArmStatus.textContent = hvArmLastError;
  }
  return data.ok === true;
}

async function apiSequence(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  noteApiAccess(data);
  if (data.ok) {
    hvArmLastError = "";
    if (hvArmStatus) hvArmStatus.textContent = data.message || "Команда выполнена";
  } else {
    hvArmLastError = data.error || "Последовательность отклонена";
    if (hvArmStatus) hvArmStatus.textContent = hvArmLastError;
  }
  return data;
}

async function apiHvArm(action, confirm = "") {
  const res = await fetch("/api/hv-arm", {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify({ action, confirm }),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  noteApiAccess(data);
  if (data.ok !== true && hvArmStatus) {
    hvArmLastError = data.error || "HV-разрешение отклонено";
    hvArmStatus.textContent = hvArmLastError;
  } else if (data.ok === true) {
    hvArmLastError = "";
  }
  return data;
}

async function apiArmProfile(profile) {
  const res = await fetch("/api/arm-profile", {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify({ profile }),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  noteApiAccess(data);
  if (!data.ok) {
    hvArmLastError = data.error || "Переключение профиля отклонено";
    if (hvArmStatus) hvArmStatus.textContent = hvArmLastError;
  } else {
    hvArmLastError = "";
  }
  return data;
}

async function apiVbusCapture(meterVdc) {
  const body = {};
  if (Number.isFinite(meterVdc)) body.meter_vdc = meterVdc;
  const res = await fetch("/api/calibration/vbus", {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  noteApiAccess(data);
  if (!data.ok) throw new Error(data.error || "Измерение Vbus отклонено");
  return data.capture;
}

async function apiStatus() {
  const res = await fetch("/api/status", { cache: "no-store" });
  const data = await res.json().catch(() => ({ ok: false }));
  if (!data.ok) {
    throw new Error(data.error || "status error");
  }
  return data.data;
}

async function sendOperatorHeartbeat() {
  if (!controlAuthRequired || !controlToken) return;
  try {
    const res = await fetch("/api/operator-heartbeat", {
      method: "POST",
      headers: controlHeaders(true),
      body: "{}",
      cache: "no-store",
    });
    const data = await res.json().catch(() => ({ ok: false }));
    if (!res.ok || data.ok !== true) noteApiAccess(data);
  } catch (_) {
    setAccessStatus(false, "Нет связи: привод будет остановлен watchdog");
  }
}

async function downloadLogs() {
  const hours = logHours.value;
  const res = await fetch(`/api/logs?hours=${encodeURIComponent(hours)}&download=1`, {
    cache: "no-store",
    headers: controlHeaders(false),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ error: "Логи недоступны" }));
    noteApiAccess(data);
    throw new Error(data.error || "Логи недоступны");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `unoq_logs_${hours}h.txt`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function setSystemStatus(data) {
  if (!data) {
    setEstopButton(false);
    sysText.textContent = "СТОП";
    sysChip.classList.remove("run", "estop");
    sysChip.classList.add("stop");
    return;
  }
  const estop = Number(data.estop || 0) === 1;
  setEstopButton(estop);
  if (estop) {
    sysText.textContent = "АВАРИЙНЫЙ СТОП";
    sysChip.classList.remove("run", "stop");
    sysChip.classList.add("estop");
    return;
  }
  const mcFault = Number(mcField(data, "fault", 0));
  const mcBad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
  if (mcFault !== 0 || mcBad !== 0) {
    sysText.textContent = mcFault !== 0
      ? `БЛОКИРОВКА: ${mcFaultName(mcFault)}`
      : `ОШИБКА UART: ${mcBad}`;
    sysChip.classList.remove("run", "stop");
    sysChip.classList.add("estop");
    return;
  }
  if (Number(data.pwm || 0) === 0) {
    sysText.textContent = "СТОП";
    sysChip.classList.remove("run", "estop");
    sysChip.classList.add("stop");
    return;
  }
  const target = typeof data.freq_cmd === "number" ? data.freq_cmd : data.freq;
  sysText.textContent = `РАЗГОН ДО ${target.toFixed(1)} Гц`;
  sysChip.classList.remove("stop", "estop");
  sysChip.classList.add("run");
}

function setHvArmUI(data) {
  if (!hvArmBlock || !hvArmStatus || !hvArmTimer || !hvArmBtn) return;
  const enabled = Number(data?.hmi_hv_enabled || 0) === 1;
  hvArmBlock.hidden = !enabled;
  if (!enabled) {
    hvArmed = false;
    return;
  }
  hvArmed = Number(data.hmi_hv_armed || 0) === 1;
  const started = Number(data.hmi_hv_started || 0) === 1;
  const remaining = Number(data.hmi_hv_remaining_s || 0);
  const profile = String(data.hmi_arm_profile || "hv").toLowerCase();
  const isLv = profile === "lv";
  const profileName = isLv ? "LV-тест" : "HV";
  const confirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));
  const availableProfiles = Array.isArray(data.hmi_arm_profiles) ? data.hmi_arm_profiles : [profile];
  armProfileSwitchReady = Number(data.hmi_arm_profile_switch_ready || 0) === 1;
  armProfileButtons.forEach((btn) => {
    const target = String(btn.dataset.armProfile || "").toLowerCase();
    btn.classList.toggle("active", target === profile);
    btn.hidden = !availableProfiles.includes(target);
    btn.disabled = hvArmed || !armProfileSwitchReady || target === profile;
  });
  hvArmBlock.classList.toggle("armed", hvArmed);
  hvArmStatus.textContent = hvArmed
    ? (started ? `${profileName}-сеанс активен` : `${profileName} разрешён, ожидается пуск`)
    : (hvArmLastError || `${profileName} заблокирован`);
  hvArmTimer.textContent = `${remaining.toFixed(1)} с`;
  hvArmBtn.textContent = hvArmed ? `Снять ${profileName}-разрешение` : `Разрешить ${profileName} на 30 секунд`;
  hvArmBtn.classList.toggle("disarm", hvArmed);
  if (hvArmConfirm) {
    hvArmConfirm.disabled = hvArmed;
    hvArmConfirm.placeholder = `Введите ${confirmPhrase}`;
  }
  if (armProfileLabel) armProfileLabel.textContent = isLv ? "Низковольтный тест, HV отключена" : "Силовая шина";
  if (armProfileNote) {
    armProfileNote.textContent = isLv
      ? `Только при физически отключённой HV-шине. Каждый пуск ограничен ${Number(data.hmi_start_runlimit_s || 3).toFixed(0)} с; STOP или потеря контроля немедленно отключают выходы.`
      : "Разрешение ограничено по времени. STOP, ESTOP, перезапуск, потеря контроля или тайм-аут снимают его.";
  }
  if (vbusCaptureBtn) vbusCaptureBtn.disabled = hvArmed || vbusCaptureBusy;
  if (vbusMeterInput) vbusMeterInput.disabled = hvArmed || vbusCaptureBusy;
}

function scheduleFreqSend(value) {
  if (freqTimer) clearTimeout(freqTimer);
  freqTimer = setTimeout(async () => {
    const val = Number(value);
    if (Number.isNaN(val) || lastSentFreq === val) return;
    lastSentFreq = val;
    await apiCmd(`SET FREQ ${val.toFixed(1)}`);
  }, 160);
}

function scheduleBrakeSend(value) {
  if (brakeTimer) clearTimeout(brakeTimer);
  brakeTimer = setTimeout(async () => {
    const val = clamp01(value);
    if (Number.isNaN(val) || lastBrakeDuty === val) return;
    lastBrakeDuty = val;
    await apiCmd(val <= 0.0001 ? "BRAKE OFF" : `BRAKE PWM ${val.toFixed(2)}`);
  }, 160);
}

function scheduleFanSend(value) {
  if (fanTimer) clearTimeout(fanTimer);
  fanTimer = setTimeout(async () => {
    const val = clamp01(value);
    if (Number.isNaN(val) || lastFanDuty === val) return;
    lastFanDuty = val;
    await apiCmd(val <= 0.0001 ? "FAN OFF" : `FAN PWM ${val.toFixed(2)}`);
  }, 160);
}

startBtn.addEventListener("click", async () => {
  startBtn.disabled = true;
  await apiSequence("/api/start-sequence");
  await refreshStatus();
});

if (hvArmBtn) {
  hvArmBtn.addEventListener("click", async () => {
    const action = hvArmed ? "disarm" : "arm";
    const confirm = hvArmConfirm ? hvArmConfirm.value.trim().toUpperCase() : "";
    const result = await apiHvArm(action, confirm);
    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";
    await refreshStatus();
  });
}

if (hvArmConfirm) {
  hvArmConfirm.addEventListener("input", () => {
    hvArmLastError = "";
  });
}

armProfileButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!armProfileSwitchReady || hvArmed) return;
    const profile = String(btn.dataset.armProfile || "").toLowerCase();
    const result = await apiArmProfile(profile);
    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";
    await refreshStatus();
  });
});

if (vbusCaptureBtn) {
  vbusCaptureBtn.addEventListener("click", async () => {
    const meterText = vbusMeterInput ? vbusMeterInput.value.trim() : "";
    const meterVdc = meterText === "" ? Number.NaN : Number(meterText.replace(",", "."));
    if (meterText !== "" && !Number.isFinite(meterVdc)) {
      vbusCaptureResult.textContent = "Введите корректное напряжение мультиметра.";
      return;
    }
    vbusCaptureBusy = true;
    vbusCaptureBtn.disabled = true;
    if (vbusMeterInput) vbusMeterInput.disabled = true;
    vbusCaptureResult.textContent = "Собираю 20 безопасных отсчётов...";
    try {
      const capture = await apiVbusCapture(meterVdc);
      const raw = capture.mc_vbus_raw;
      const scaled = capture.mc_vdc;
      const meter = capture.meter_vdc == null ? "не введено" : `${Number(capture.meter_vdc).toFixed(1)} В`;
      vbusCaptureResult.textContent =
        `Записано: raw ${raw.mean.toFixed(1)} (${raw.min.toFixed(0)}...${raw.max.toFixed(0)}), ` +
        `Vbus ${scaled.mean.toFixed(2)} В, мультиметр ${meter}.`;
    } catch (err) {
      vbusCaptureResult.textContent = err.message || "Измерение Vbus не выполнено.";
    } finally {
      vbusCaptureBusy = false;
      vbusCaptureBtn.disabled = hvArmed;
      if (vbusMeterInput) vbusMeterInput.disabled = hvArmed;
    }
  });
}

stopBtn.addEventListener("click", async () => {
  await apiSequence("/api/stop-sequence");
  await refreshStatus();
});

estopBtn.addEventListener("click", async () => {
  if (lastEstop) {
    await apiCmd("ESTOP CLEAR");
  } else {
    await apiSequence("/api/stop-sequence", { emergency: true });
  }
  await refreshStatus();
});

if (pfcBtn) {
  pfcBtn.addEventListener("click", async () => {
    pfcOn = !pfcOn;
    await apiCmd(`PFC ${pfcOn ? "ON" : "OFF"}`);
    setIoButtons();
  });
}

modeButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const mode = btn.dataset.mode;
    if (!supportedModes.includes(mode)) return;
    setModeUI(mode);
    await apiCmd(`MODE ${mode}`);
  });
});

freqSlider.addEventListener("input", (event) => {
  const value = Number(event.target.value);
  setFreqUI(value);
  updateTooltip(value);
  freqReadout.classList.add("show");
  scheduleFreqSend(value);
});

freqSlider.addEventListener("pointerdown", () => {
  dragging = true;
  updateTooltip(freqSlider.value);
  freqReadout.classList.add("show");
});

freqSlider.addEventListener("pointerup", () => {
  dragging = false;
  freqReadout.classList.remove("show");
});

freqSlider.addEventListener("pointerleave", () => {
  if (!dragging) freqReadout.classList.remove("show");
});

if (brakeSlider) {
  brakeSlider.addEventListener("input", (event) => {
    const value = Number(event.target.value);
    updateBrakeReadout(value);
    scheduleBrakeSend(value);
  });
  brakeSlider.addEventListener("pointerdown", () => {
    brakeDragging = true;
  });
  brakeSlider.addEventListener("pointerup", () => {
    brakeDragging = false;
  });
  brakeSlider.addEventListener("pointerleave", () => {
    brakeDragging = false;
  });
}

if (fanSlider) {
  fanSlider.addEventListener("input", (event) => {
    const value = Number(event.target.value);
    updateFanReadout(value);
    scheduleFanSend(value);
  });
  fanSlider.addEventListener("pointerdown", () => {
    fanDragging = true;
  });
  fanSlider.addEventListener("pointerup", () => {
    fanDragging = false;
  });
  fanSlider.addEventListener("pointerleave", () => {
    fanDragging = false;
  });
}

if (controlTokenSave) {
  controlTokenSave.addEventListener("click", () => {
    controlToken = controlTokenInput ? controlTokenInput.value.trim() : "";
    if (controlToken) {
      localStorage.setItem("unoqControlToken", controlToken);
      setAccessStatus(true);
    } else {
      localStorage.removeItem("unoqControlToken");
      setAccessStatus(false, "Ключ удалён");
    }
  });
}

logDownload.addEventListener("click", async () => {
  logDownload.disabled = true;
  try {
    await downloadLogs();
  } catch (err) {
    setAccessStatus(false, err.message || "Логи недоступны");
  } finally {
    logDownload.disabled = false;
  }
});

async function refreshStatus() {
  try {
    const data = await apiStatus();
    controlAuthRequired = Number(data.hmi_control_auth_required || 0) === 1;
    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired;
    if (controlAuthRequired && controlToken) setAccessStatus(true, "Ключ загружен на этом устройстве");
    setConnection(true);
    supportedModes = Array.isArray(data.mc_supported_modes) && data.mc_supported_modes.length
      ? data.mc_supported_modes
      : ["VF"];
    modeButtons.forEach((btn) => {
      const available = supportedModes.includes(btn.dataset.mode);
      btn.disabled = !available;
      btn.title = available ? "" : "Не поддерживается загруженной прошивкой контроллера";
    });
    setModeUI(data.mode);
    setFreqUI(data.freq, true);
    setSystemStatus(data);
    setHvArmUI(data);
    stateVal.textContent = data.state;
    if (backendVal) {
      backendVal.textContent = mcModeName(mcField(data, "cmd_mode", mcField(data, "mode", 0)));
    }
    if (linkVal) {
      const mcFault = Number(mcField(data, "fault", 0));
      const mcBad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
      const mcAge = Number(mcField(data, "rsp_age_ms", mcField(data, "age_ms", -1)));
      const linkState = mcFault !== 0 ? mcFaultName(mcFault) : (mcBad !== 0 ? "ОШИБКА UART" : "OK");
      linkVal.textContent = `${linkState} / bad=${mcBad} / ${mcAge.toFixed(0)} мс`;
    }
    pwmVal.textContent = data.pwm;
    speedVal.textContent = `${data.speed.toFixed(0)} об/мин`;
    vdcVal.textContent = `${data.vdc.toFixed(2)} В`;

    if (tempVal) {
      const tempRaw = Number(mcField(data, "temp_raw", 0));
      const tempV = Number(mcField(data, "temp_v", 0));
      const tempC = Number(mcField(data, "temp_c", 0));
      const tempValid = Number(mcField(data, "temp_valid", 0)) === 1;
      const tempFault = Number(mcField(data, "temp_fault", 0)) === 1 || Number(mcField(data, "fault", 0)) === 6;
      tempVal.textContent = tempValid
        ? `${tempC.toFixed(1)} C / ${tempV.toFixed(3)} V (${tempRaw})${tempFault ? " ОШИБКА" : ""}`
        : `-- / ${tempV.toFixed(3)} V (${tempRaw})`;
    }

    currVal.textContent = `${data.ia.toFixed(2)} / ${data.ib.toFixed(2)} / ${data.ic.toFixed(2)} А`;

    if (phaseVal) {
      const phaseValid = Number(mcField(data, "phase_valid", 0)) === 1;
      const cVirtual = Number(mcField(data, "phase_c_virtual", 0)) === 1;
      const pa = Number(mcField(data, "phase_a_v", 0));
      const pb = Number(mcField(data, "phase_b_v", 0));
      const pc = Number(mcField(data, "phase_c_v", 0));
      phaseVal.textContent = phaseValid
        ? `${pa.toFixed(3)} / ${pb.toFixed(3)} / ${pc.toFixed(3)} V${cVirtual ? " (C virt)" : ""}`
        : "--";
    }

    idRefVal.textContent = typeof data.id_ref === "number" ? `${data.id_ref.toFixed(2)} А` : "--";

    if (micSaveVal) {
      if (typeof data.mic_saving_pct === "number") {
        const micActive = Number(data.mic_active || 0) === 1;
        micSaveVal.textContent = `${micActive ? "ON" : "OFF"} ${data.mic_saving_pct.toFixed(1)} %`;
      } else {
        micSaveVal.textContent = "--";
      }
    }

    if (typeof data.pfc === "number") pfcOn = Number(data.pfc) === 1;
    const basicStartReady =
      String(data.state || "") === "SAFE" &&
      Number(data.pwm || 0) === 0 &&
      Number(data.estop || 0) === 0 &&
      Number(mcField(data, "fault", 0)) === 0 &&
      Number(mcField(data, "bad", 0)) === 0 &&
      Number(mcField(data, "bad_cnt", 0)) === 0;
    const standaloneHv = Number(data.hmi_hv_enabled || 0) === 1;
    startBtn.disabled = !basicStartReady || (standaloneHv && !hvArmed);

    let brakeDuty = typeof data.brake_duty === "number" ? data.brake_duty : 0;
    if (!brakeDragging && brakeSlider) {
      brakeSlider.value = clamp01(brakeDuty).toFixed(2);
      updateBrakeReadout(brakeDuty);
    }
    setIoButtons();
    if (ioVal) {
      ioVal.textContent =
        `PFC ${pfcOn ? "ON" : "OFF"} / BRK ${(brakeDuty * 100).toFixed(0)}%`;
    }

    const fanDuty = typeof data.fan_duty === "number" ? data.fan_duty : 0;
    if (!fanDragging && fanSlider) {
      fanSlider.value = clamp01(fanDuty).toFixed(2);
      updateFanReadout(fanDuty);
    }
    if (fanVal) {
      const mcFanDuty = Number(mcField(data, "fan_duty", fanDuty));
      const fanRpm = Number(mcField(data, "fan_rpm", 0));
      fanVal.textContent = `${(mcFanDuty * 100).toFixed(0)}% / ${fanRpm.toFixed(0)} rpm`;
    }

    if (encVal) {
      const encOk = Number(data.enc_ok || 0) === 1;
      const encRaw = typeof data.enc_raw === "number" ? data.enc_raw : 0;
      const encDeg = typeof data.enc_deg === "number" ? data.enc_deg : 0;
      const encRpm = typeof data.enc_rpm === "number" ? data.enc_rpm : null;
      let text = encOk ? `${encDeg.toFixed(1)} deg (${encRaw})` : `-- (${encRaw})`;
      if (encOk && encRpm !== null) {
        text += ` / ${encRpm.toFixed(1)} rpm`;
      }
      encVal.textContent = text;
    }

    const ts = new Date(data.ts);
    lastUpdate.textContent = `Обновлено ${ts.toLocaleTimeString("ru-RU")}`;
  } catch (err) {
    setConnection(false);
    setSystemStatus(null);
    startBtn.disabled = true;
    setIoButtons();
    lastUpdate.textContent = "Нет связи";
  }
}

setModeUI("VF");
setFreqUI(10.0);
setConnection(false);
setEstopButton(false);
startBtn.disabled = true;
setIoButtons();
if (brakeSlider) updateBrakeReadout(brakeSlider.value);
if (fanSlider) updateFanReadout(fanSlider.value);

refreshStatus();
setInterval(refreshStatus, 1000);
sendOperatorHeartbeat();
setInterval(sendOperatorHeartbeat, 1000);
