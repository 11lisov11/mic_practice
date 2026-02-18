const connDot = document.getElementById("connDot");
const connText = document.getElementById("connText");
const sysChip = document.getElementById("sysChip");
const sysText = document.getElementById("sysText");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const estopBtn = document.getElementById("estopBtn");
const modeToggle = document.getElementById("modeToggle");
const modeButtons = Array.from(modeToggle.querySelectorAll(".seg"));
const freqSlider = document.getElementById("freqSlider");
const freqReadout = document.getElementById("freqReadout");
const ntcBtn = document.getElementById("ntcBtn");
const pfcBtn = document.getElementById("pfcBtn");
const brakeSlider = document.getElementById("brakeSlider");
const brakeReadout = document.getElementById("brakeReadout");
const logHours = document.getElementById("logHours");
const logDownload = document.getElementById("logDownload");
const stateVal = document.getElementById("stateVal");
const modeVal = document.getElementById("modeVal");
const pwmVal = document.getElementById("pwmVal");
const speedVal = document.getElementById("speedVal");
const vdcVal = document.getElementById("vdcVal");
const currVal = document.getElementById("currVal");
const idRefVal = document.getElementById("idRefVal");
const micSaveVal = document.getElementById("micSaveVal");
const ioVal = document.getElementById("ioVal");
const encVal = document.getElementById("encVal");
const lastUpdate = document.getElementById("lastUpdate");

let dragging = false;
let freqTimer = null;
let lastSentFreq = null;
let lastEstop = false;
let brakeDragging = false;
let brakeTimer = null;
let lastBrakeDuty = null;
let ntcOn = false;
let pfcOn = false;

function setConnection(ok) {
  connDot.classList.toggle("online", ok);
  connText.textContent = ok ? "онлайн" : "офлайн";
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
  const v = Math.max(0, Math.min(1, Number(value)));
  brakeReadout.textContent = `BRK ${(v * 100).toFixed(0)}%`;
}

function setIoButtons() {
  if (ntcBtn) {
    ntcBtn.classList.toggle("active", ntcOn);
    ntcBtn.textContent = `NTC: ${ntcOn ? "ON" : "OFF"}`;
  }
  if (pfcBtn) {
    pfcBtn.classList.toggle("active", pfcOn);
    pfcBtn.textContent = `PFC: ${pfcOn ? "ON" : "OFF"}`;
  }
}

async function apiCmd(cmd) {
  const res = await fetch("/api/cmd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd })
  });
  const data = await res.json().catch(() => ({ ok: false }));
  return data.ok === true;
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
    sysText.textContent = "СТОП";
    sysChip.classList.remove("run", "estop");
    sysChip.classList.add("stop");
    return;
  }
  const estop = Number(data.estop || 0) === 1;
  lastEstop = estop;
  if (estop) {
    sysText.textContent = "АВАРИЙНЫЙ СТОП";
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

function scheduleFreqSend(value) {
  if (freqTimer) {
    clearTimeout(freqTimer);
  }
  freqTimer = setTimeout(async () => {
    const val = Number(value);
    if (Number.isNaN(val)) {
      return;
    }
    if (lastSentFreq === val) {
      return;
    }
    lastSentFreq = val;
    await apiCmd(`SET FREQ ${val.toFixed(1)}`);
  }, 160);
}

function scheduleBrakeSend(value) {
  if (brakeTimer) {
    clearTimeout(brakeTimer);
  }
  brakeTimer = setTimeout(async () => {
    const val = Math.max(0, Math.min(1, Number(value)));
    if (Number.isNaN(val)) {
      return;
    }
    if (lastBrakeDuty === val) {
      return;
    }
    lastBrakeDuty = val;
    if (val <= 0.0001) {
      await apiCmd("BRAKE OFF");
    } else {
      await apiCmd(`BRAKE PWM ${val.toFixed(2)}`);
    }
  }, 160);
}

startBtn.addEventListener("click", async () => {
  await apiCmd("START");
});

stopBtn.addEventListener("click", async () => {
  await apiCmd("STOP");
});

estopBtn.addEventListener("click", async () => {
  await apiCmd("STOP");
});

if (ntcBtn) {
  ntcBtn.addEventListener("click", async () => {
    ntcOn = !ntcOn;
    await apiCmd(`NTC ${ntcOn ? "ON" : "OFF"}`);
    setIoButtons();
  });
}
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
  if (!dragging) {
    freqReadout.classList.remove("show");
  }
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
    if (!brakeDragging) {
      brakeReadout.classList.remove("show");
    }
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
    estopBtn.textContent = "Аварийный стоп";
    stateVal.textContent = data.state;
    pwmVal.textContent = data.pwm;
    speedVal.textContent = `${data.speed.toFixed(0)} об/мин`;
    vdcVal.textContent = `${data.vdc.toFixed(2)} В`;
    currVal.textContent = `${data.ia.toFixed(2)} / ${data.ib.toFixed(2)} / ${data.ic.toFixed(2)} А`;
    if (typeof data.id_ref === "number") {
      idRefVal.textContent = `${data.id_ref.toFixed(2)} А`;
    } else {
      idRefVal.textContent = "--";
    }
    if (micSaveVal) {
      if (typeof data.mic_saving_pct === "number") {
        const micActive = Number(data.mic_active || 0) === 1;
        const prefix = micActive ? "ON" : "OFF";
        micSaveVal.textContent = `${prefix} ${data.mic_saving_pct.toFixed(1)} %`;
      } else {
        micSaveVal.textContent = "--";
      }
    }
    if (typeof data.ntc === "number") {
      ntcOn = Number(data.ntc) === 1;
    }
    if (typeof data.pfc === "number") {
      pfcOn = Number(data.pfc) === 1;
    }
    let brakeDuty = 0;
    if (typeof data.brake_duty === "number") {
      brakeDuty = data.brake_duty;
    }
    if (!brakeDragging && brakeSlider) {
      brakeSlider.value = Math.max(0, Math.min(1, brakeDuty)).toFixed(2);
      updateBrakeReadout(brakeDuty);
    }
    setIoButtons();
    if (ioVal) {
      const brkPct = (brakeDuty * 100).toFixed(0);
      ioVal.textContent = `NTC ${ntcOn ? "ON" : "OFF"} / PFC ${pfcOn ? "ON" : "OFF"} / BRK ${brkPct}%`;
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
    lastUpdate.textContent = "Нет связи";
  }
}

setModeUI("FOC");
setFreqUI(10.0);
setConnection(false);
setIoButtons();
if (brakeSlider) {
  updateBrakeReadout(brakeSlider.value);
}

refreshStatus();
setInterval(refreshStatus, 1000);
