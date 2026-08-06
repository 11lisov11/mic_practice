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
const modeToggle = document.getElementById("modeToggle");
const modeButtons = Array.from(modeToggle.querySelectorAll(".seg"));
const freqSlider = document.getElementById("freqSlider");
const freqReadout = document.getElementById("freqReadout");
const pfcBtn = document.getElementById("pfcBtn");
const bpFocBtn = document.getElementById("bpFocBtn");
const brakeSlider = document.getElementById("brakeSlider");
const brakeReadout = document.getElementById("brakeReadout");
const fanSlider = document.getElementById("fanSlider");
const fanReadout = document.getElementById("fanReadout");
const logHours = document.getElementById("logHours");
const logDownload = document.getElementById("logDownload");
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
let bpFocOn = false;
let bpFocCanSwitch = false;
let hvArmed = false;
let hvArmLastError = "";

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value)));
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

function bpModeName(mode) {
  const code = Number(mode);
  if (code === 5) return "BP FOC";
  if (code === 4) return "VECTOR";
  if (code === 3) return "SCALAR";
  if (code === 2) return "DUTY";
  if (code === 1) return "DIAG";
  return "OFF";
}

function bpFaultName(code) {
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
  if (bpFocBtn) {
    bpFocBtn.classList.toggle("active", bpFocOn);
    bpFocBtn.disabled = !bpFocCanSwitch;
    bpFocBtn.textContent = `BP FOC: ${bpFocOn ? "ON" : "OFF"}`;
    bpFocBtn.title = bpFocCanSwitch
      ? "Переключать только перед запуском"
      : "Доступно только в SAFE при pwm=0";
  }
}

async function apiCmd(cmd) {
  const res = await fetch("/api/cmd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd }),
  });
  const data = await res.json().catch(() => ({ ok: false }));
  if (data.ok !== true && hvArmStatus) {
    hvArmLastError = data.error || "Команда отклонена";
    hvArmStatus.textContent = hvArmLastError;
  }
  return data.ok === true;
}

async function apiHvArm(action, confirm = "") {
  const res = await fetch("/api/hv-arm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, confirm }),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  if (data.ok !== true && hvArmStatus) {
    hvArmLastError = data.error || "HV-разрешение отклонено";
    hvArmStatus.textContent = hvArmLastError;
  } else if (data.ok === true) {
    hvArmLastError = "";
  }
  return data;
}

async function apiStatus() {
  const res = await fetch("/api/status", { cache: "no-store" });
  const data = await res.json().catch(() => ({ ok: false }));
  if (!data.ok) {
    throw new Error(data.error || "status error");
  }
  return data.data;
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
  const bpFault = Number(data.bp_fault || 0);
  const bpBad = Number(data.bp_bad_cnt || data.bp_bad || 0);
  if (bpFault !== 0 || bpBad !== 0) {
    sysText.textContent = bpFault !== 0
      ? `БЛОКИРОВКА: ${bpFaultName(bpFault)}`
      : `ОШИБКА UART: ${bpBad}`;
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
  hvArmBlock.classList.toggle("armed", hvArmed);
  hvArmStatus.textContent = hvArmed
    ? (started ? "HV-сеанс активен" : "HV разрешена, ожидается пуск")
    : (hvArmLastError || "HV заблокирована");
  hvArmTimer.textContent = `${remaining.toFixed(1)} с`;
  hvArmBtn.textContent = hvArmed ? "Снять HV-разрешение" : "Разрешить HV на 30 секунд";
  hvArmBtn.classList.toggle("disarm", hvArmed);
  if (hvArmConfirm) hvArmConfirm.disabled = hvArmed;
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
  await apiCmd("START");
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

stopBtn.addEventListener("click", async () => {
  await apiCmd("STOP");
});

estopBtn.addEventListener("click", async () => {
  await apiCmd(lastEstop ? "ESTOP CLEAR" : "ESTOP");
});

if (pfcBtn) {
  pfcBtn.addEventListener("click", async () => {
    pfcOn = !pfcOn;
    await apiCmd(`PFC ${pfcOn ? "ON" : "OFF"}`);
    setIoButtons();
  });
}

if (bpFocBtn) {
  bpFocBtn.addEventListener("click", async () => {
    if (!bpFocCanSwitch) return;
    const next = !bpFocOn;
    const ok = await apiCmd(`BPFOC ${next ? "ON" : "OFF"}`);
    if (ok) {
      bpFocOn = next;
      setIoButtons();
    }
  });
}

modeButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const mode = btn.dataset.mode;
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

logHours.addEventListener("change", () => {
  const hours = logHours.value;
  logDownload.href = `/api/logs?hours=${hours}&download=1`;
});

async function refreshStatus() {
  try {
    const data = await apiStatus();
    setConnection(true);
    setModeUI(data.mode);
    setFreqUI(data.freq, true);
    setSystemStatus(data);
    setHvArmUI(data);
    stateVal.textContent = data.state;
    if (backendVal) {
      const bpFoc = Number(data.bp_foc_backend || 0) === 1;
      backendVal.textContent = `${bpModeName(data.bp_cmd_mode)}${bpFoc ? " / opt-in" : ""}`;
    }
    if (linkVal) {
      const bpFault = Number(data.bp_fault || 0);
      const bpBad = Number(data.bp_bad_cnt || data.bp_bad || 0);
      const bpAge = Number(data.bp_rsp_age_ms ?? data.bp_age_ms ?? -1);
      const linkState = bpFault !== 0 ? bpFaultName(bpFault) : (bpBad !== 0 ? "ОШИБКА UART" : "OK");
      linkVal.textContent = `${linkState} / bad=${bpBad} / ${bpAge.toFixed(0)} мс`;
    }
    pwmVal.textContent = data.pwm;
    speedVal.textContent = `${data.speed.toFixed(0)} об/мин`;
    vdcVal.textContent = `${data.vdc.toFixed(2)} В`;

    if (tempVal) {
      const tempRaw = typeof data.bp_temp_raw === "number" ? data.bp_temp_raw : 0;
      const tempV = typeof data.bp_temp_v === "number" ? data.bp_temp_v : 0;
      const tempC = typeof data.bp_temp_c === "number" ? data.bp_temp_c : 0;
      const tempValid = Number(data.bp_temp_valid || 0) === 1;
      const tempFault = Number(data.bp_temp_fault || 0) === 1 || Number(data.bp_fault || 0) === 6;
      tempVal.textContent = tempValid
        ? `${tempC.toFixed(1)} C / ${tempV.toFixed(3)} V (${tempRaw})${tempFault ? " ОШИБКА" : ""}`
        : `-- / ${tempV.toFixed(3)} V (${tempRaw})`;
    }

    currVal.textContent = `${data.ia.toFixed(2)} / ${data.ib.toFixed(2)} / ${data.ic.toFixed(2)} А`;

    if (phaseVal) {
      const phaseValid = Number(data.bp_phase_valid || 0) === 1;
      const cVirtual = Number(data.bp_phase_c_virtual || 0) === 1;
      const pa = typeof data.bp_phase_a_v === "number" ? data.bp_phase_a_v : 0;
      const pb = typeof data.bp_phase_b_v === "number" ? data.bp_phase_b_v : 0;
      const pc = typeof data.bp_phase_c_v === "number" ? data.bp_phase_c_v : 0;
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
    if (typeof data.bp_foc_backend === "number") bpFocOn = Number(data.bp_foc_backend) === 1;
    bpFocCanSwitch =
      String(data.state || "") === "SAFE" &&
      Number(data.pwm || 0) === 0 &&
      Number(data.estop || 0) === 0;
    const basicStartReady =
      String(data.state || "") === "SAFE" &&
      Number(data.pwm || 0) === 0 &&
      Number(data.estop || 0) === 0 &&
      Number(data.bp_fault || 0) === 0 &&
      Number(data.bp_bad || 0) === 0 &&
      Number(data.bp_bad_cnt || 0) === 0;
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
      const bpFanDuty = typeof data.bp_fan_duty === "number" ? data.bp_fan_duty : fanDuty;
      const fanRpm = typeof data.bp_fan_rpm === "number" ? data.bp_fan_rpm : 0;
      fanVal.textContent = `${(bpFanDuty * 100).toFixed(0)}% / ${fanRpm.toFixed(0)} rpm`;
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
    bpFocCanSwitch = false;
    setIoButtons();
    lastUpdate.textContent = "Нет связи";
  }
}

setModeUI("FOC");
setFreqUI(10.0);
setConnection(false);
setEstopButton(false);
startBtn.disabled = true;
setIoButtons();
if (brakeSlider) updateBrakeReadout(brakeSlider.value);
if (fanSlider) updateFanReadout(fanSlider.value);

refreshStatus();
setInterval(refreshStatus, 1000);
