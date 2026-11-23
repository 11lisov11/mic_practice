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
const hvArmBtn = document.getElementById("hvArmBtn");
const armProfileToggle = document.getElementById("armProfileToggle");
const armProfileButtons = armProfileToggle
  ? Array.from(armProfileToggle.querySelectorAll("[data-arm-profile]"))
  : [];
const armProfileLabel = document.getElementById("armProfileLabel");
const armProfileNote = document.getElementById("armProfileNote");
const vbusMeterInput = document.getElementById("vbusMeterInput");
const vbusCaptureBtn = document.getElementById("vbusCaptureBtn");
const vbusResetBtn = document.getElementById("vbusResetBtn");
const vbusCalibrationState = document.getElementById("vbusCalibrationState");
const vbusCaptureResult = document.getElementById("vbusCaptureResult");
const modeToggle = document.getElementById("modeToggle");
const modeButtons = Array.from(modeToggle.querySelectorAll(".seg"));
const freqSlider = document.getElementById("freqSlider");
const freqReadout = document.getElementById("freqReadout");
const freqLabel = freqSlider.closest(".freq-block")?.querySelector(".label");
if (freqLabel) freqLabel.textContent = "Задание частоты (Гц)";
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
const bkinTraceLoad = document.getElementById("bkinTraceLoad");
const bkinTraceStatus = document.getElementById("bkinTraceStatus");

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
let hvArmConfirmPhrase = "";
let hvArmLastError = "";
let armProfileSwitchReady = false;
let vbusCaptureBusy = false;
let controlAuthRequired = false;
let controlCookieActive = false;
let controlToken = localStorage.getItem("unoqControlToken") || "";
let lastAutoBreakSnapshotKey = "";
let breakSnapshotRequest = null;
const driveDiagnostics = installDriveDiagnosticsPanel();

if (controlTokenInput) controlTokenInput.value = controlToken;

function controlHeaders(json = false) {
  const headers = {};
  if (json) headers["Content-Type"] = "application/json";
  if (controlToken && !controlCookieActive) headers["X-UNOQ-Control-Token"] = controlToken;
  return headers;
}

function setAccessStatus(ok, message = "") {
  if (!controlAccessStatus) return;
  controlAccessStatus.classList.toggle("ok", Boolean(ok));
  controlAccessStatus.textContent = message || (ok ? "Ключ сохранён" : "Требуется правильный ключ управления");
}

function noteApiAccess(data) {
  if (data && data.error === "control access key is missing or invalid") {
    if (controlAccessBlock) controlAccessBlock.hidden = false;
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

function vbusReasonRu(value) {
  const reason = String(value || "").trim();
  const exact = {
    "compile-time calibration override": "используется заводское подтверждение сборки",
    "zero-point capture is required": "требуется записать нулевую точку при разряженной шине",
    "known-HV capture is required": "требуется записать контрольную точку известного высокого напряжения",
    "stored calibration schema is invalid": "неверная версия файла калибровки",
    "stored calibration points are missing": "в файле отсутствуют измерительные точки",
    "calibration identity is missing": "в файле отсутствует идентификатор прошивок",
    "calibration identity is incomplete": "идентификатор прошивок неполный",
    "firmware or telemetry identity changed; recalibration is required": "состав прошивок изменился, требуется повторная проверка",
    "calibration point values are invalid": "значения измерительных точек повреждены",
    "calibration span is invalid": "недостаточный диапазон между нулевой и рабочей точками",
    "two-point Vbus verification passed": "двухточечная проверка Vbus пройдена",
    "capture a new zero point before the known-HV point": "сначала заново запишите нулевую точку",
    "calibration capture is incomplete": "набор измерений неполный",
    "calibration capture contains non-finite values": "в измерениях есть недопустимые значения",
    "MCSDK Vbus telemetry is not valid": "телеметрия Vbus от MCSDK недостоверна",
    "Nucleo firmware identity is not available": "Nucleo не передал идентификатор прошивки",
    "MCSDK Vbus telemetry fields disagree": "поля телеметрии Vbus от MCSDK не согласованы",
    "motor-controller UART error counter changed during capture": "во время измерения изменился счётчик ошибок UART",
    "firmware or telemetry identity changed during capture": "во время измерения изменился состав прошивок или формат телеметрии",
    "clear motor-controller UART error counters before known-HV capture": "перед рабочей точкой сбросьте ошибки связи с Nucleo",
    "meter voltage must be 0..2 V for zero or 250..360 V for known HV": "введите 0...2 В для нулевой точки или 250...360 В для рабочей точки",
  };
  if (exact[reason]) return exact[reason];
  if (reason.startsWith("stored calibration rejected:")) return `сохранённая калибровка отклонена: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("calibration gain mismatch:")) return `несовпадение масштаба Vbus: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("reported zero-bus voltage is too high:")) return `при разряженной шине измерено слишком высокое напряжение: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("zero-point capture is unstable:")) return `нулевая точка нестабильна: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("zero-point mismatch is too large:")) return `слишком большое расхождение нулевой точки: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("known-HV mismatch is too large:")) return `слишком большое расхождение рабочей точки: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("known-HV capture is unstable:")) return `рабочая точка нестабильна: ${reason.split(":", 2)[1].trim()}`;
  if (reason.startsWith("calibration capture requires 20 samples; got")) return `получено недостаточно отсчётов: ${reason.split("got", 2)[1].trim()} из 20`;
  return reason || "причина не указана";
}

function setConnection(ok) {
  connDot.classList.toggle("online", ok);
  connText.textContent = ok ? "онлайн" : "офлайн";
  if (!ok) {
    const banner = document.getElementById("simpleState");
    if (banner) { banner.textContent = "Нет связи"; banner.dataset.state = "error"; }
    document.getElementById("simpleClear")?.setAttribute("hidden", "");
    for (const id of ["simpleVdc","simpleI0","simpleI1","simpleI2"]) {
      const element=document.getElementById(id);if(element)element.textContent="—";
    }
  }
}

function setEstopButton(isLatched) {
  lastEstop = Boolean(isLatched);
  estopBtn.classList.toggle("active", lastEstop);
  estopBtn.textContent = "Аварийный стоп";
}

function setModeUI(mode) {
  modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  modeVal.textContent = mode;
}

function setFreqUI(value, fromStatus = false) {
  const v = Number(value);
  if (!Number.isFinite(v)) return;
  if (!fromStatus || !dragging) {
    freqSlider.value = v.toFixed(1);
    updateTooltip(freqSlider.value);
    if (freqLabel) freqLabel.textContent = "Задание частоты";
  }
}

function setFrequencyFromStatus(data) {
  // freq is the local ramp reference, not the operator's setpoint or a measurement.
  setFreqUI(data.freq_cmd ?? data.freq, true);
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

function mcLocalStopLatched(data) {
  return (Number(mcField(data, "status", 0)) & 0x80) !== 0;
}

function mcFaultSummary(data, code) {
  if (mcLocalStopLatched(data)) return "ЛОКАЛЬНЫЙ STOP B1 (PC13)";
  if (Number(data.mc_diag_valid || 0) !== 1) return mcFaultName(code);
  const names = ["NONE", "CRC", "VERSION", "REPLAY", "ESTOP", "SERVICE",
    "COMMAND", "FREQUENCY", "MCSDK", "VBUS", "START", "UART TX", "UART RX", "TIMEOUT", "RX BUFFER"];
  const lastBad = Number(data.mc_last_bad_valid || 0) === 1
    && Number(data.mc_bad_cnt || data.bp_bad_cnt || 0) > 0
    && Number(data.mc_last_bad_reason || 0) > 0;
  const reason = Number(lastBad ? data.mc_last_bad_reason : data.mc_fault_reason || 0);
  if (reason === 0 && Number(code) !== 5) return mcFaultName(code);
  let label = names[reason] || `REASON ${reason}`;
  if (reason === 12) {
    const flags = Number((lastBad ? data.mc_last_uart_error_flags : data.mc_uart_error_flags) || 0);
    const bits = [[1, "PE"], [2, "FE"], [4, "NE"], [8, "ORE"]];
    label += `: ${bits.filter(([bit]) => flags & bit).map(([, name]) => name).join("/") || "--"}`;
  } else if (reason === 8) {
    const mask = Number(data.mc_fault_current_mask || data.mc_fault_occurred_mask || 0);
    const labels = {1: "Дедлайн цикла", 2: "Высокое Vbus", 4: "Низкое Vbus",
      8: "Перегрев", 16: "Сбой пуска", 32: "Обратная связь", 64: "Вход аварии",
      128: "Ошибка MCSDK", 1024: "Защита IPM"};
    label = labels[mask] || `MCSDK 0x${mask.toString(16).padStart(4, "0")}`;
  }
  return label;
}

function installDriveDiagnosticsPanel() {
  const statusPanel = document.querySelector(".panel.status");
  const heading = statusPanel?.querySelector("h2");
  if (!statusPanel || !heading) return null;
  const panel = document.createElement("section");
  panel.className = "drive-diagnostics healthy";
  panel.id = "driveDiagnostics";
  panel.setAttribute("role", "status");
  panel.setAttribute("aria-live", "polite");
  panel.innerHTML = `
    <div class="drive-diag-head">
      <div><div class="drive-diag-eyebrow">ОБЪЯСНЕНИЕ СОСТОЯНИЯ</div><h3 id="driveDiagTitle">Ожидаю данные контроллера</h3></div>
      <span class="drive-diag-badge" id="driveDiagBadge">—</span>
    </div>
    <p id="driveDiagText">Здесь появится причина блокировки или подтверждение штатной остановки.</p>
    <div class="drive-diag-clear" id="driveDiagClear" hidden>
      <button class="btn ghost" id="driveDiagClearBtn" type="button">Сбросить защёлкнутую защиту</button>
      <span id="driveDiagClearStatus">Доступно только при остановленном ШИМ и нормальной DC-шине.</span>
    </div>
    <div class="drive-diag-grid">
      <div><span>Выходы</span><strong id="driveDiagOutputs">—</strong></div>
      <div><span>UART Nucleo</span><strong id="driveDiagUart">—</strong></div>
      <div><span>Частота и вал</span><strong id="driveDiagSpeed">—</strong></div>
      <div><span>Шина и радиатор</span><strong id="driveDiagPower">—</strong></div>
    </div>
    <div class="drive-diag-snapshot">
      <div class="drive-diag-snapshot-head"><strong>Снимок первого останова</strong><button class="btn ghost" id="driveDiagSnapshotBtn" type="button">Обновить снимок</button></div>
      <p id="driveDiagSnapshot">Снимок будет прочитан при появлении ошибки.</p>
    </div>
    <details class="drive-diag-raw"><summary>Код контроллера</summary><code id="driveDiagRaw">—</code></details>`;
  heading.insertAdjacentElement("afterend", panel);

  const style = document.createElement("style");
  style.textContent = `
    .drive-diagnostics{margin:12px 0 16px;padding:14px;border:1px solid #3b4755;border-radius:14px;background:#101820;color:#e7eaee}
    .drive-diagnostics.healthy{border-color:#2c786f;background:rgba(18,74,68,.20)}
    .drive-diagnostics.warning{border-color:#b67a2e;background:rgba(105,65,20,.20)}
    .drive-diagnostics.fault,.drive-diagnostics.offline{border-color:#b9354b;background:rgba(106,23,42,.22)}
    .drive-diag-clear{display:flex;align-items:center;gap:10px;margin:8px 0 12px;padding:10px;border-radius:10px;background:rgba(4,8,12,.35)}
    .drive-diag-clear[hidden]{display:none!important}.drive-diag-clear span{font-size:12px;line-height:1.4;color:#c5ccd5}
    .drive-diag-head,.drive-diag-snapshot-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .drive-diag-eyebrow{font-size:11px;letter-spacing:.12em;color:#aeb8c4;font-weight:700}
    .drive-diag-head h3{font-size:17px;line-height:1.35;margin:4px 0 0}
    .drive-diag-badge{padding:5px 9px;border-radius:999px;background:#25313e;font-size:11px;font-weight:800;white-space:nowrap}
    .drive-diagnostics.healthy .drive-diag-badge{background:#155b52}.drive-diagnostics.warning .drive-diag-badge{background:#704716}.drive-diagnostics.fault .drive-diag-badge,.drive-diagnostics.offline .drive-diag-badge{background:#8e2438}
    #driveDiagText{margin:8px 0 12px;line-height:1.45;color:#d6dbe1}
    .drive-diag-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}
    .drive-diag-grid>div{min-width:0;padding:9px 10px;border-radius:10px;background:rgba(4,8,12,.35)}
    .drive-diag-grid span{display:block;font-size:11px;color:#aeb8c4;margin-bottom:4px}
    .drive-diag-grid strong{font-size:13px;line-height:1.4;overflow-wrap:anywhere}
    .drive-diag-snapshot{margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.1)}
    .drive-diag-snapshot-head strong{font-size:13px}.drive-diag-snapshot p{margin:7px 0 0;font-size:12px;line-height:1.45;color:#c5ccd5}
    .drive-diag-snapshot .btn{min-height:36px;padding:6px 10px;font-size:12px}
    .drive-diag-raw{margin-top:8px;color:#aeb8c4;font-size:12px}.drive-diag-raw summary{cursor:pointer;min-height:32px;padding:6px 0}
    .drive-diag-raw code{display:block;margin-top:5px;white-space:pre-wrap;overflow-wrap:anywhere;color:#d9dee5;font-size:11px}
    @media(max-width:520px){.drive-diag-snapshot-head{align-items:flex-start;flex-direction:column}.drive-diag-snapshot .btn{width:100%}}
  `;
  document.head.appendChild(style);
  const ids = ["driveDiagTitle", "driveDiagBadge", "driveDiagText", "driveDiagOutputs",
    "driveDiagUart", "driveDiagSpeed", "driveDiagPower", "driveDiagSnapshot",
    "driveDiagRaw", "driveDiagSnapshotBtn", "driveDiagClear", "driveDiagClearBtn", "driveDiagClearStatus"];
  const nodes = Object.fromEntries(ids.map((id) => [id, panel.querySelector(`#${id}`)]));
  nodes.driveDiagSnapshotBtn?.addEventListener("click", () => loadDriveBreakSnapshot(false));
  nodes.driveDiagClearBtn?.addEventListener("click", async () => {
    if (nodes.driveDiagClearBtn.disabled) return;
    nodes.driveDiagClearBtn.disabled = true;
    nodes.driveDiagClearBtn.dataset.busy = "1";
    nodes.driveDiagClearStatus.textContent = "Повторно проверяю шину, останов и связь…";
    try {
      const before = await apiStatus();
      const gate = driveFaultClearDecision(before);
      if (!gate.ok) {
        nodes.driveDiagClearStatus.textContent = gate.reason;
        updateDriveDiagnostics(before);
        return;
      }
      if (!await apiCmd("CLEAR")) {
        nodes.driveDiagClearStatus.textContent = hvArmLastError || "Контроллер отклонил сброс.";
        await refreshStatus();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
      const after = await apiStatus();
      updateDriveDiagnostics(after);
      const cleared = Number(mcField(after, "fault", 0)) === 0
        && Number(after.bp_fault || 0) === 0 && Number(after.pwm || 0) === 0;
      nodes.driveDiagClearStatus.textContent = cleared
        ? "Защита сброшена. ШИМ остаётся выключенным."
        : "Защита осталась активной; пуск заблокирован. См. код контроллера.";
      await refreshStatus();
    } catch (error) {
      nodes.driveDiagClearStatus.textContent = error.message || "Не удалось проверить сброс.";
    } finally {
      delete nodes.driveDiagClearBtn.dataset.busy;
      nodes.driveDiagClearBtn.disabled = nodes.driveDiagClear.hidden;
    }
  });
  return { panel, ...nodes };
}

function faultMaskDescription(mask) {
  const bits = [
    [0x0001, "превышено время цикла"], [0x0002, "перенапряжение DC-шины"],
    [0x0004, "пониженное напряжение DC-шины"], [0x0008, "перегрев драйвера"],
    [0x0010, "сбой запуска двигателя"], [0x0020, "ошибка обратной связи двигателя"],
    [0x0040, "защита от сверхтока"], [0x0080, "внутренняя ошибка MCSDK"],
    [0x0400, "защита силового драйвера/IPM (MC_DP_FAULT)"],
  ];
  const labels = bits.filter(([bit]) => mask & bit).map(([, label]) => label);
  const known = bits.reduce((value, [bit]) => value | bit, 0);
  const unknown = mask & ~known;
  if (unknown) labels.push(`неизвестные биты 0x${unknown.toString(16).padStart(4, "0")}`);
  return labels.length ? labels.join("; ") : "MCSDK сообщил о защите без активной маски";
}

function driveFaultClearDecision(data) {
  const fault = Number(mcField(data, "fault", 0));
  const currentMask = Number(data.mc_fault_current_mask || 0);
  const occurredMask = Number(data.mc_fault_occurred_mask || 0);
  const highPoint = Number(data.hmi_vbus_high_meter_vdc || 0);
  const vdc = Number(data.vdc);
  const temp = Number(mcField(data, "temp_c", data.temp_c));
  const age = Number(mcField(data, "age_ms", mcField(data, "rsp_age_ms", -1)));
  const expectedMin = Math.max(250, highPoint * 0.9);
  const expectedMax = Math.min(360, highPoint * 1.1);
  const outputsOff = String(data.state || "") === "SAFE"
    && Number(data.pwm || 0) === 0
    && Number(data.estop || 0) === 0
    && Number(data.precharge || 0) === 0
    && (Number(data.bp_status || 0) & 0x20) === 0
    && (Number(data.bp_ext || 0) & 0x08) === 0
    && Number(data.hmi_local_stop_latched || 0) === 0;
  const knownUndervoltage = fault === 5 && Number(data.bp_fault || 0) === 5
    && Number(mcField(data, "fault_reason", 0)) === 8
    && currentMask === 0x0004
    && (occurredMask === 0x0004 || occurredMask === 0x0404);
  const measurementsGood = Number(data.hmi_vbus_hv_calibrated || 0) === 1
    && Number(data.bp_vbus_valid ?? data.mc_vbus_valid ?? 0) === 1
    && Number.isFinite(vdc) && highPoint > 0 && vdc >= expectedMin && vdc <= expectedMax
    && Number(data.bp_temp_valid ?? data.mc_temp_valid ?? 0) === 1
    && Number(mcField(data, "temp_fault", 0)) === 0 && Number.isFinite(temp) && temp < 70;
  const linkGood = Number.isFinite(age) && age >= 0 && age < 300
    && Number(mcField(data, "bad_cnt", 0)) === 0
    && Number(mcField(data, "bad_integrity", 0)) === 0
    && Number(mcField(data, "bad_sequence", 0)) === 0
    && Number(mcField(data, "uart_error_flags", 0)) === 0
    && Number(data.uno_rx_hw_errors || 0) === 0
    && Number(data.mc_transport_fault || 0) === 0;
  if (!knownUndervoltage) return { ok: false, reason: "Сброс доступен только для защёлкнутой защиты по пониженному напряжению." };
  if (!outputsOff) return { ok: false, reason: "Сначала требуется подтверждённая остановка всех выходов." };
  if (!measurementsGood) return { ok: false, reason: "Нужны свежие измерения нормальной DC-шины и температуры без ошибки." };
  if (!linkGood) return { ok: false, reason: "Сначала восстановите свежую связь без ошибок UART." };
  return { ok: true, reason: "Сброс доступен; команда не запускает ШИМ." };
}

function controllerFaultDiagnosis(data) {
  const fault = Number(mcField(data, "fault", 0));
  const reason = Number(mcField(data, "fault_reason", 0));
  const bad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
  const integrity = Number(mcField(data, "bad_integrity", 0));
  const sequence = Number(mcField(data, "bad_sequence", 0));
  const uartFlags = Number(mcField(data, "uart_error_flags", 0));
  const currentMask = Number(data.mc_fault_current_mask || 0);
  const occurredMask = Number(data.mc_fault_occurred_mask || 0);
  const mask = currentMask || occurredMask;
  if (reason === 8) {
    const driver = faultMaskDescription(mask);
    return {
      severity: "fault",
      badge: "ЗАЩИТА ДРАЙВЕРА",
      title: mask & 0x0400 ? "Останов по защите IPM / драйвера" : "Останов по защите MCSDK",
      text: `${driver}. Nucleo сняла ШИМ по зарегистрированной защите. Это не ошибка UART. По одному флагу нельзя определить точную физическую причину срабатывания.`,
    };
  }
  if (reason === 12 || reason === 11 || reason === 13 || uartFlags !== 0) {
    const labels = [[1,"PE"],[2,"FE"],[4,"NE"],[8,"ORE"]].filter(([bit]) => uartFlags & bit).map(([,name]) => name);
    const detail = reason === 13 ? "Nucleo не ответила в отведённое время"
      : reason === 11 ? "ошибка передачи от Uno Q к Nucleo"
      : reason === 12 ? "Nucleo сообщила об ошибке приёма UART"
      : "счётчик UART содержит ошибки";
    return {
      severity: "fault", badge: "СВЯЗЬ UART",
      title: "Ошибка UART между Uno Q и Nucleo",
      text: `${detail}${labels.length ? ` (флаги ${labels.join("/")})` : ""}. Счётчик bad=${bad}; смотрите возраст последнего ответа ниже.`,
    };
  }
  if (fault !== 0 || Number(data.estop || 0) === 1 || Number(data.bp_fault || 0) !== 0) {
    if (mcLocalStopLatched(data)) {
      return { severity: "fault", badge: "ОСТАНОВ", title: "Защёлкнут локальный STOP B1",
        text: "Контроллер остановил ШИМ после локальной команды STOP. Для нового пуска блокировку нужно снять штатной процедурой." };
    }
    const reasonLabels = {1:"ошибка CRC",2:"версия протокола",3:"повтор команды разрешения",
      4:"аварийный STOP",5:"запрещённое сервисное поле",6:"команда отклонена",
      7:"частота отклонена",9:"напряжение шины вне диапазона",10:"пуск отклонён",
      14:"переполнение приёма UART"};
    const label = reasonLabels[reason] || mcFaultName(fault);
    return { severity: "fault", badge: "ПУСК ЗАБЛОКИРОВАН",
      title: `Контроллер остановлен: ${label}`,
      text: "ШИМ выключен. В карточках ниже показаны состояние выходов и свежесть обмена с Nucleo." };
  }
  if (bad > 0 || integrity > 0 || sequence > 0) {
    return { severity: "warning", badge: "СЧЁТЧИК UART",
      title: "Nucleo отвечает; в счётчиках есть отброшенные кадры",
      text: `bad=${bad}, ошибки целостности=${integrity}, ошибки последовательности=${sequence}. Это накопленные счётчики, не подтверждение текущего обрыва; точная причина последнего кадра не записана.` };
  }
  const age = Number(mcField(data, "age_ms", mcField(data, "rsp_age_ms", -1)));
  if (age < 0 || age >= 300) {
    return { severity: "warning", badge: "НЕТ СВЕЖЕГО ОТВЕТА", title: "Нет свежего статуса Nucleo",
      text: `Последний ответ получен ${age < 0 ? "неизвестно когда" : `${age.toFixed(0)} мс назад`}. До обновления статуса запуск блокируется.` };
  }
  if (Number(data.pwm || 0) === 1) {
    return { severity: "healthy", badge: "РАБОТАЕТ", title: "ШИМ включён, контроллер отвечает",
      text: "UART работает; ниже отдельно показано задание частоты и квалифицированная скорость вала." };
  }
  return { severity: "healthy", badge: "ГОТОВ / СТОП", title: "Останов штатный, ошибок UART нет",
    text: "Nucleo отвечает. Частота поля — это задание регулятора; обороты вала отображаются только при достоверном сигнале энкодера." };
}

function writeDriveSnapshotUnavailable(message) {
  if (driveDiagnostics?.driveDiagSnapshot) driveDiagnostics.driveDiagSnapshot.textContent = message;
}

async function loadDriveBreakSnapshot(automatic = false) {
  if (!driveDiagnostics?.driveDiagSnapshot) return;
  if (breakSnapshotRequest) return breakSnapshotRequest;
  driveDiagnostics.driveDiagSnapshot.textContent = "Читаю сохранённый снимок BKIN…";
  breakSnapshotRequest = (async () => {
    try {
      const res = await fetch("/api/break-snapshot", { headers: controlHeaders(false), cache: "no-store" });
      const envelope = await res.json().catch(() => ({ ok: false }));
      noteApiAccess(envelope);
      if (res.status === 401) throw new Error("Снимок закрыт ключом управления; основная причина уже показана выше.");
      if (!res.ok || envelope.ok !== true) throw new Error(envelope.error || "Снимок пока недоступен");
      const records = envelope.data?.mc_break_snapshots || [];
      const start = records.find((item) => item.kind === "first_start_window");
      const boot = records.find((item) => item.kind === "first_since_boot");
      const record = start?.captured ? start : boot?.captured ? boot : start || boot;
      if (!record) throw new Error("Контроллер не передал запись первого останова.");
      if (!record.available || !record.captured) {
        const reasons = { not_received: "Nucleo ещё не передала снимок.",
          wrong_peer_build: "Снимок создан другой версией Nucleo.",
          stale_or_wrong_peer: "Снимок устарел или версия Nucleo не совпала.",
          invalid_hex: "Ответ со снимком повреждён.", invalid_record: "Запись снимка имеет неверный формат.",
          invalid_metadata: "Метаданные снимка некорректны." };
        writeDriveSnapshotUnavailable(reasons[record.reason] || "Снимок недоступен.");
        return;
      }
      const event = record.event || {};
      const context = record.cached_context || {};
      const at = Number.isFinite(Number(record.age_ms)) ? `${Number(record.age_ms).toFixed(0)} мс назад` : "возраст неизвестен";
      const flags = `BIF=${event.bif ? 1 : 0}, B2IF=${event.b2if ? 1 : 0}, PA6 при входе в обработчик=${event.pa6_high_at_irq ? "HIGH" : "LOW"}, BKE=${event.bke_at_irq ? 1 : 0}, MOE=${event.moe_at_irq ? 1 : 0}`;
      const hz = Number.isFinite(Number(context.reference_electrical_hz))
        ? `; кэшированная частота поля ${Number(context.reference_electrical_hz).toFixed(1)} Гц` : "";
      const bus = Number.isFinite(Number(context.vbus_v)) ? `; Vbus ${Number(context.vbus_v).toFixed(1)} В` : "";
      const temp = Number.isFinite(Number(context.temperature_c)) ? `; радиатор ${Number(context.temperature_c).toFixed(1)} °C` : "";
      const contextAge = Number.isFinite(Number(context.age_at_irq_ms)) ? `; контекст за ${Number(context.age_at_irq_ms).toFixed(0)} мс до события` : "";
      const origin = event.start_window_flag_stale_after_run ? "Уже после перехода в RUN (флаг окна пуска не сброшен)" :
        event.during_start_request_window ? "Во время запроса пуска" : "При останове";
      let pulseText = "Полная запись PA6 пока не получена.";
      try {
        const waveRes = await fetch("/api/bkin-trace", { headers: controlHeaders(false), cache: "no-store" });
        const waveEnvelope = await waveRes.json();
        const wave = waveEnvelope.data;
        if (waveRes.ok && waveEnvelope.ok && wave?.available) pulseText = wave.summary_ru;
      } catch (_) { /* Snapshot remains useful if the waveform request fails. */ }
      writeDriveSnapshotUnavailable(`${origin} (${at}): ${flags}${hz}${bus}${temp}${contextAge}. ${pulseText} По одному SD точная физическая причина не определяется.`);
    } catch (error) {
      writeDriveSnapshotUnavailable(error.message || "Не удалось прочитать снимок.");
    } finally {
      breakSnapshotRequest = null;
    }
  })();
  return breakSnapshotRequest;
}

function updateDriveDiagnostics(data) {
  if (!driveDiagnostics) return;
  const d = driveDiagnostics;
  if (!data) {
    d.panel.className = "drive-diagnostics offline";
    d.driveDiagBadge.textContent = "НЕТ СВЯЗИ";
    d.driveDiagTitle.textContent = "Страница не получает статус контроллера";
    d.driveDiagText.textContent = "Проверьте соединение с HMI. Команды пуска в таком состоянии заблокированы.";
    d.driveDiagOutputs.textContent = "Статус неизвестен";
    d.driveDiagUart.textContent = "Статус неизвестен";
    d.driveDiagSpeed.textContent = "Измерение недоступно";
    d.driveDiagPower.textContent = "Измерение недоступно";
    d.driveDiagRaw.textContent = "—";
    return;
  }
  const diagnosis = controllerFaultDiagnosis(data);
  d.panel.className = `drive-diagnostics ${diagnosis.severity}`;
  d.driveDiagBadge.textContent = diagnosis.badge;
  d.driveDiagTitle.textContent = diagnosis.title;
  d.driveDiagText.textContent = diagnosis.text;

  const mcFault = Number(mcField(data, "fault", 0));
  const estop = Number(data.estop || 0) === 1;
  d.driveDiagOutputs.textContent = `${data.state || "?"} · ШИМ ${Number(data.pwm || 0) ? "ВКЛ" : "выкл"} · ${estop ? "STOP/защита защёлкнута" : "STOP не защёлкнут"}${mcFault ? ` · код ${mcFault}` : ""}`;

  const age = Number(mcField(data, "age_ms", mcField(data, "rsp_age_ms", -1)));
  const bad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
  const good = Number(mcField(data, "good_cnt", 0));
  const integrity = Number(mcField(data, "bad_integrity", 0));
  const sequence = Number(mcField(data, "bad_sequence", 0));
  const uartFlags = Number(mcField(data, "uart_error_flags", 0));
  const uartAge = age < 0 ? "возраст неизвестен" : `${age.toFixed(0)} мс${age < 300 ? " (свежий)" : " (устарел)"}`;
  d.driveDiagUart.textContent = `Ответ ${uartAge} · принятых ${good} · bad ${bad} · целостность ${integrity} · seq ${sequence} · UART-флаги 0x${uartFlags.toString(16).padStart(2, "0")}`;

  const fieldValid = Number(data.mc_frequency_reference_valid || 0) === 1;
  const fieldHz = fieldValid ? Number(data.mc_frequency_reference_hz) : Number(data.freq_cmd ?? data.freq ?? 0);
  const actualValid = Number(data.enc_ok || 0) === 1 && Number(data.enc_speed_ok || 0) === 1;
  const rotor = actualValid ? `${Number(data.enc_rpm || 0).toFixed(0)} об/мин (энкодер)` : "скорость вала не измерена";
  d.driveDiagSpeed.textContent = `Поле ${Number.isFinite(fieldHz) ? fieldHz.toFixed(1) : "—"} Гц${fieldValid ? "" : " (задание)"} · ${rotor}`;

  const vdc = Number(data.vdc);
  const vdcAge = Number(data.bp_vbus_age_ms ?? data.mc_vbus_age_ms ?? -1);
  const temp = Number(data.bp_temp_c ?? data.mc_temp_c ?? data.temp_c);
  const tempAge = Number(data.bp_temp_age_ms ?? data.mc_temp_age_ms ?? -1);
  const vdcText = Number.isFinite(vdc) ? `${vdc.toFixed(1)} В${vdcAge >= 0 ? ` / ${vdcAge.toFixed(0)} мс` : ""}` : "нет данных";
  const tempText = Number.isFinite(temp) ? `${temp.toFixed(1)} °C${tempAge >= 0 ? ` / ${tempAge.toFixed(0)} мс` : ""}` : "нет данных";
  const sdText = data.mc_sd_live?.summary_ru || "Текущий SD: нет измерения";
  d.driveDiagPower.textContent = `DC-шина ${vdcText} · радиатор IPM ${tempText} · ${sdText}`;
  d.driveDiagRaw.textContent = String(data.mc_fault_detail || "Нет кода ошибки от контроллера.");

  const hasFault = Number(data.estop || 0) === 1 || mcFault !== 0
    || Number(data.bp_fault || 0) !== 0 || Number(mcField(data, "fault_reason", 0)) !== 0;
  const clearDecision = driveFaultClearDecision(data);
  d.driveDiagClear.hidden = !clearDecision.ok;
  d.driveDiagClearBtn.disabled = !clearDecision.ok || d.driveDiagClearBtn.dataset.busy === "1";
  if (d.driveDiagClearBtn.dataset.busy !== "1") d.driveDiagClearStatus.textContent = clearDecision.reason;
  if (hasFault) {
    const key = [data.mc_fw_build, mcField(data, "fault_reason", 0), data.mc_fault_current_mask,
      data.mc_fault_occurred_mask, data.mc_fault_sequence, mcFault].join(":");
    if (key !== lastAutoBreakSnapshotKey) {
      lastAutoBreakSnapshotKey = key;
      loadDriveBreakSnapshot(true);
    }
  } else if (lastAutoBreakSnapshotKey) {
    lastAutoBreakSnapshotKey = "";
  }
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

async function apiVbusReset() {
  const res = await fetch("/api/calibration/vbus", {
    method: "POST",
    headers: controlHeaders(true),
    body: JSON.stringify({ action: "reset" }),
  });
  const data = await res.json().catch(() => ({ ok: false, error: "Некорректный ответ" }));
  noteApiAccess(data);
  if (!data.ok) throw new Error(data.error || "Сброс калибровки отклонён");
  return data.calibration;
}

function describeBkinTrace(trace) {
  if (![4, 5].includes(Number(trace.schema)) || typeof trace.summary_ru !== "string") {
    return "Неизвестный формат сохранённой записи SD; длительность не подтверждена.";
  }
  const age = Number(trace.age_since_delivery_ms);
  const ageText = Number.isFinite(age) && age >= 0 ? ` Получена ${(age / 1000).toFixed(1)} с назад.` : "";
  const live = trace.live_sd?.summary_ru || "Текущий SD: нет измерения";
  return `Сохранённая запись: ${trace.summary_ru}${ageText} ${live}. ` +
    "Возраст доставки не означает время от события. Шаг записи 0,2 мкс.";
}


async function loadBkinTrace() {
  if (!bkinTraceLoad || !bkinTraceStatus) return;
  bkinTraceLoad.disabled = true;
  bkinTraceStatus.textContent = "Читаю сохранённый снимок…";
  try {
    const res = await fetch("/api/bkin-trace", {
      headers: controlHeaders(false), cache: "no-store",
    });
    const envelope = await res.json().catch(() => ({ ok: false }));
    noteApiAccess(envelope);
    if (!res.ok || envelope.ok !== true) throw new Error(envelope.error || "Снимок недоступен");
    const trace = envelope.data || {};
    if (!trace.available) {
      const reasons = { not_received: "снимок ещё не получен", wrong_peer_build: "не совпадает версия Nucleo",
        invalid_hex: "повреждён ответ", invalid_record: "неверный формат снимка", stale: "снимок устарел" };
      bkinTraceStatus.textContent = reasons[trace.reason] || "снимок пока недоступен";
      return;
    }
    bkinTraceStatus.textContent = describeBkinTrace(trace);
  } catch (error) {
    bkinTraceStatus.textContent = error.message || "ошибка чтения снимка";
  } finally {
    bkinTraceLoad.disabled = false;
  }
}

if (bkinTraceLoad) bkinTraceLoad.addEventListener("click", loadBkinTrace);

async function apiStatus() {
  const res = await fetch("/api/status", { cache: "no-store" });
  const data = await res.json().catch(() => ({ ok: false }));
  if (!data.ok) {
    throw new Error(data.error || "status error");
  }
  return data.data;
}

async function sendOperatorHeartbeat() {
  if (!controlAuthRequired || (!controlToken && !controlCookieActive)) return;
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
  const mcFault = Number(mcField(data, "fault", 0));
  const mcBad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
  if (estop || mcFault !== 0 || Number(data.bp_fault || 0) !== 0) {
    const diagnosis = controllerFaultDiagnosis(data);
    sysText.textContent = `СТОП: ${diagnosis.title}`;
    sysChip.classList.remove("run", "stop");
    sysChip.classList.add("estop");
    return;
  }
  if (mcBad !== 0) {
    sysText.textContent = `СЧЁТЧИК UART: ${mcBad}`;
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

function manualStartAllowed(data, isHvArmed) {
  const basicStartReady =
    String(data.state || "") === "SAFE" &&
    Number(data.pwm || 0) === 0 &&
    Number(data.estop || 0) === 0 &&
    Number(mcField(data, "fault", 0)) === 0 &&
    Number(mcField(data, "bad", 0)) === 0 &&
    Number(mcField(data, "bad_cnt", 0)) === 0;
  const standaloneHv = Number(data.hmi_hv_enabled || 0) === 1;
  const manualScalarSupported = Number(data.hmi_manual_scalar_supported || 0) === 1;
  return basicStartReady && (!standaloneHv || isHvArmed || manualScalarSupported);
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
  hvArmConfirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));
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
  hvArmTimer.textContent = Number(data.hmi_run_continuous)===1 ? "до STOP" : `${remaining.toFixed(1)} с`;
  hvArmBtn.textContent = hvArmed ? `Снять ${profileName}-разрешение` : `Разрешить ${profileName} на 30 секунд`;
  hvArmBtn.classList.toggle("disarm", hvArmed);
  if (armProfileLabel) armProfileLabel.textContent = isLv ? "Низковольтный тест, HV отключена" : "Силовая шина";
  if (armProfileNote) {
    armProfileNote.textContent = isLv
      ? `Только при физически отключённой HV-шине. Каждый пуск ограничен ${Number(data.hmi_start_runlimit_s || 3).toFixed(0)} с; STOP или потеря контроля немедленно отключают выходы.`
      : "Разрешение ограничено по времени. STOP, ESTOP, перезапуск, потеря контроля или тайм-аут снимают его.";
  }
  if (vbusCaptureBtn) vbusCaptureBtn.disabled = hvArmed || vbusCaptureBusy;
  if (vbusResetBtn) vbusResetBtn.disabled = hvArmed || vbusCaptureBusy;
  if (vbusMeterInput) vbusMeterInput.disabled = hvArmed || vbusCaptureBusy;
  if (vbusCalibrationState) {
    const calibrated = Number(data.hmi_vbus_hv_calibrated || 0) === 1;
    const zeroCaptured = Number(data.hmi_vbus_zero_captured || 0) === 1;
    const highCaptured = Number(data.hmi_vbus_high_captured || 0) === 1;
    const reason = vbusReasonRu(data.hmi_vbus_calibration_reason);
    if (calibrated) {
      const meter = Number(data.hmi_vbus_high_meter_vdc || 0).toFixed(1);
      const measured = Number(data.hmi_vbus_high_mc_vdc || 0).toFixed(1);
      vbusCalibrationState.textContent = `Vbus подтверждён: мультиметр ${meter} В, MCSDK ${measured} В.`;
    } else if (zeroCaptured && !highCaptured) {
      vbusCalibrationState.textContent = `Нулевая точка записана; рабочая HV-точка ещё не подтверждена. ${reason}`;
    } else {
      vbusCalibrationState.textContent = `Калибровка Vbus не подтверждена: ${reason}.`;
    }
  }
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
  const capable=document.getElementById("manualConfig")?.hidden===false;
  if (capable && Number(freqSlider.value)<=0) {
    document.getElementById("manualState").textContent="Задайте частоту выше 0 Гц перед пуском.";
    startBtn.disabled=false;
    return;
  }
  if (capable && hvArmBlock && !hvArmBlock.hidden && !hvArmed) {
    const armed=await apiHvArm("arm", hvArmConfirmPhrase);
    if (!armed.ok) { await refreshStatus(); startBtn.disabled=false; return; }
  }
  await apiSequence("/api/start-sequence", capable ? {manual:true} : {});
  await refreshStatus();
});

if (hvArmBtn) {
  hvArmBtn.addEventListener("click", async () => {
    const action = hvArmed ? "disarm" : "arm";
    const result = await apiHvArm(action, action === "arm" ? hvArmConfirmPhrase : "");
    await refreshStatus();
  });
}

armProfileButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    if (!armProfileSwitchReady || hvArmed) return;
    const profile = String(btn.dataset.armProfile || "").toLowerCase();
    const result = await apiArmProfile(profile);
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
      await refreshStatus();
    } catch (err) {
      vbusCaptureResult.textContent = vbusReasonRu(err.message || "Измерение Vbus не выполнено.");
    } finally {
      vbusCaptureBusy = false;
      vbusCaptureBtn.disabled = hvArmed;
      if (vbusMeterInput) vbusMeterInput.disabled = hvArmed;
    }
  });
}

if (vbusResetBtn) {
  vbusResetBtn.addEventListener("click", async () => {
    vbusCaptureBusy = true;
    vbusResetBtn.disabled = true;
    if (vbusCaptureResult) vbusCaptureResult.textContent = "Сбрасываю калибровку и подтверждаю STOP...";
    try {
      await apiVbusReset();
      if (vbusCaptureResult) vbusCaptureResult.textContent = "Калибровка Vbus сброшена.";
      await refreshStatus();
    } catch (err) {
      if (vbusCaptureResult) vbusCaptureResult.textContent = vbusReasonRu(err.message || "Сброс не выполнен.");
    } finally {
      vbusCaptureBusy = false;
      vbusResetBtn.disabled = hvArmed;
    }
  });
}

stopBtn.addEventListener("click", async () => {
  await apiSequence("/api/stop-sequence");
  await refreshStatus();
});

estopBtn.addEventListener("click", async () => {
  await apiSequence("/api/stop-sequence", { emergency: true });
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
      if (controlAccessBlock) controlAccessBlock.hidden = Boolean(controlAuthRequired);
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
    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired || Boolean(controlToken);
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
    setFrequencyFromStatus(data);
    setSystemStatus(data);
    updateDriveDiagnostics(data);
    setHvArmUI(data);
    updateManualUI(data);
    stateVal.textContent = data.state;
    if (backendVal) {
      backendVal.textContent = mcModeName(mcField(data, "cmd_mode", mcField(data, "mode", 0)));
    }
    if (linkVal) {
      const mcBad = Number(mcField(data, "bad_cnt", mcField(data, "bad", 0)));
      const mcAge = Number(mcField(data, "rsp_age_ms", mcField(data, "age_ms", -1)));
      const linkState = mcAge >= 0 && mcAge < 300 ? "ОТВЕТ ЕСТЬ" : "НЕТ СВЕЖЕГО ОТВЕТА";
      linkVal.title = data.mc_fault_detail || "";
      linkVal.textContent = `${linkState} / bad=${mcBad} / ${mcAge >= 0 ? `${mcAge.toFixed(0)} мс` : "—"}`;
    }
    pwmVal.textContent = data.pwm;
    speedVal.textContent = Number(data.enc_ok || 0) === 1 && Number(data.enc_speed_ok || 0) === 1
      ? `${Number(data.enc_rpm || 0).toFixed(0)} об/мин`
      : "Не измеряется";
    speedVal.title = Number(data.enc_ok || 0) === 1 && Number(data.enc_speed_ok || 0) === 1
      ? "Измеренная скорость по квалифицированному энкодеру"
      : `Обороты вала не квалифицированы. Задание поля: ${Number(data.freq_cmd ?? data.freq ?? 0).toFixed(1)} Гц.`;
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

    updateShuntCurrentPanel(data);

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
    startBtn.disabled = !manualStartAllowed(data, hvArmed);

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

    if (encVal && data.enc_source === "disabled") {
      encVal.textContent = "Без датчика; скорость вала не измеряется";
      encVal.title = "Исследовательский режим: фазные токи и частота поля. Оценка скорости ещё не квалифицирована.";
    } else if (encVal) {
      const encOk = Number(data.enc_ok || 0) === 1;
      const encRaw = typeof data.enc_raw === "number" ? data.enc_raw : 0;
      const encDeg = typeof data.enc_deg === "number" ? data.enc_deg : 0;
      const encRpm = typeof data.enc_rpm === "number" ? data.enc_rpm : null;
      let text = encOk ? `${encDeg.toFixed(1)} deg (${encRaw})` : `-- (${encRaw})`;
      if (encOk && encRpm !== null && Number(data.enc_speed_ok) === 1) {
        text += ` / ${encRpm.toFixed(1)} rpm`;
      }
      if (["uno_q_i2c2", "nucleo_g431_i2c1"].includes(data.enc_source) && !encOk) {
        const sensorStatus = Number(data.enc_status || 0);
        text = Number(data.enc_bus_ok) !== 1 ? "AS5600: нет связи"
          : !(sensorStatus & 0x20) ? "AS5600: нет магнита"
          : sensorStatus & 0x10 ? "AS5600: слабое поле"
          : sensorStatus & 0x08 ? "AS5600: сильное поле"
          : "AS5600: угол недостоверен";
      }
      const faultRecords = Array.isArray(data.enc_fault_records) ? data.enc_fault_records : [];
      const faultRecord = faultRecords.find(x => x.kind === "first_with_pwm") || faultRecords[0];
      if (faultRecord) text += `; I²C ${faultRecord.cause}: снимок сохранён`;
      const releaseRecords = Array.isArray(data.enc_release_records) ? data.enc_release_records : [];
      const releaseRecord = releaseRecords.find(x => x.kind === "first_with_pwm") || releaseRecords[0];
      if (releaseRecord) text += `; ${releaseRecord.summary_ru}`;
      if (data.enc_bus_clear_record) text += `; ${data.enc_bus_clear_record.summary_ru}`;
      encVal.textContent = text;
      encVal.title = `Источник: ${data.enc_source || "—"}; ошибок чтения: ${Number(data.enc_errors || 0)}; стадия: ${Number(data.enc_diag_stage || 0)}; причина: ${Number(data.enc_diag_cause || 0)}; возраст: ${Number(data.enc_age_ms || 0)} мс`;
    }

    updateSimpleUI(data);
    refreshResearchCatalog(data);
    const ts = new Date(data.ts);
    lastUpdate.textContent = `Обновлено ${ts.toLocaleTimeString("ru-RU")}`;
  } catch (err) {
    setConnection(false);
    setSystemStatus(null);
    updateDriveDiagnostics(null);
    startBtn.disabled = true;
    setIoButtons();
    lastUpdate.textContent = "Нет связи";
  }
}

function updateManualUI(data) {
  const panel=document.getElementById("manualConfig");
  const supported=Number(data.hmi_manual_scalar_supported)===1;
  panel.hidden=!supported;
  if (!supported) return;
  if (!document.getElementById("manualSettings")) {
    const settings = document.createElement("details");
    settings.id = "manualSettings";
    settings.className = "manual-settings";
    const summary = document.createElement("summary");
    summary.textContent = "Настройки разгона и снижения";
    settings.appendChild(summary);
    for (const control of [
      document.getElementById("manualAccel")?.closest("label"),
      document.getElementById("manualDecel")?.closest("label"),
      document.getElementById("manualApply"),
      document.getElementById("manualDownmode")?.closest("label"),
    ]) if (control) settings.appendChild(control);
    const state = document.getElementById("manualState");
    if (state?.parentNode) state.parentNode.insertBefore(settings, state);
    else panel.appendChild(settings);
  }
  if (!document.getElementById("manualSettingsStyle")) {
    const style = document.createElement("style");
    style.id = "manualSettingsStyle";
    style.textContent = ".manual-settings{display:grid;gap:10px;border-top:1px solid #303844;padding-top:10px}.manual-settings summary{cursor:pointer;color:#b9c2ce}[hidden]{display:none!important}";
    document.head.appendChild(style);
  }
  for (const id of ["manualContinuous", "manualFrequency", "manualFrequencyApply", "hvArmConfirm"]) {
    const element = document.getElementById(id);
    const target = id === "manualContinuous" || id === "manualFrequency" ? element?.closest("label") : element;
    if (target) { target.hidden = true; target.setAttribute("hidden", ""); }
  }
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
setFreqUI(5.0);
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

function updateShuntCurrentPanel(data) {
  let panel = document.getElementById("shuntCurrentPanel");
  if (!panel) {
    panel = document.createElement("section");
    panel.id = "shuntCurrentPanel";
    panel.className = "drive-diagnostics";
    panel.innerHTML = `<h3>Токи двигателя U / V / W</h3>
      <p id="shuntCurrentState" aria-live="polite"></p>
      <div class="drive-diag-grid">
        <div><span>Действующие, А</span><strong id="shuntCurrentRms">—</strong></div>
        <div><span>Пиковые за окно, А</span><strong id="shuntCurrentPeak">—</strong></div>
        <div><span>Последний отсчёт, А</span><strong id="shuntCurrentInstant">—</strong></div>
      </div>
      <p id="shuntCurrentQuality"></p>
      <details><summary>Сырые измерения и нули АЦП</summary><p id="shuntCurrentAdc"></p></details>`;
    const anchor = document.getElementById("driveDiagnostics");
    if (anchor) anchor.insertAdjacentElement("afterend", panel);
    else currVal.parentElement.insertAdjacentElement("afterend", panel);
  }
  const valid = Number(data.mc_current_telemetry_valid) === 1;
  const format = values => valid && Array.isArray(values) && values.length === 3 && values.every(Number.isFinite)
    ? values.map(v => v.toFixed(3)).join(" / ") : "—";
  document.getElementById("shuntCurrentState").textContent = data.mc_current_status || "Нет свежих измерений шунтов";
  document.getElementById("shuntCurrentRms").textContent = format(data.mc_current_rms_a);
  document.getElementById("shuntCurrentPeak").textContent = format(data.mc_current_peak_a);
  document.getElementById("shuntCurrentInstant").textContent = format(data.mc_current_instant_a);
  const recovered = ["U", "V", "W"].filter((_, i) => Number(data.mc_current_reconstructed_mask || 0) & (1 << i));
  document.getElementById("shuntCurrentQuality").textContent =
    `Окно ${Number(data.mc_current_window_ms || 0)} мс; принято ${Number(data.mc_current_coverage_pct || 0)}%; ` +
    `отброшено ${Number(data.mc_current_rejected_samples || 0)}. ` +
    `Восстанавливались по сумме токов: ${recovered.join(", ") || "—"}.`;
  const raw = data.mc_current_raw_adc;
  const offsets = data.mc_current_offsets_adc;
  document.getElementById("shuntCurrentAdc").textContent =
    `Пути U/ADC1, V/ADC1, V/ADC2, W/ADC2: отсчёты ${Array.isArray(raw) ? raw.join(" / ") : "—"}; ` +
    `нули ${Array.isArray(offsets) ? offsets.join(" / ") : "—"}. Автоноль ${Number(data.mc_current_zero_ready) === 1 ? "готов" : "не готов"}.`;
  if (Array.isArray(data.mc_current_zero_spans)) {
    document.getElementById("shuntCurrentAdc").textContent +=
      ` Разброс: ${data.mc_current_zero_spans.join(" / ")} отсч.; ` +
      `стабильных блоков ${data.mc_current_zero_stable}/3, проверено ${data.mc_current_zero_attempts}/8. Сырой размах — справочно; оценка 3σ среднего ≤2 отсчётов, дрейф ≤2.`;
    const why = [];
    const reject = Number(data.mc_current_zero_last_reject || 0);
    if (reject & 1) why.push("оценка 3σ среднего больше 2 отсчётов");
    if (reject & 2) why.push("средний уровень вне 1600–2500");
    if (reject & 4) why.push("средние блоков расходятся больше чем на 2");
    if (reject & 8) why.push("сырой АЦП достиг границы диапазона");
    if (why.length) document.getElementById("shuntCurrentAdc").textContent += ` Причина: ${why.join("; ")}.`;
  }
  if (data.mc_zero_history_status) document.getElementById("shuntCurrentAdc").textContent += ` ${data.mc_zero_history_status}.`;
  if (data.mc_adc_peak_status) document.getElementById("shuntCurrentAdc").textContent += ` ${data.mc_adc_peak_status}.`;
  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS${data.mc_current_frozen ? " (последнее окно)" : ""}` : "Нет достоверного измерения";
  currVal.title = data.mc_current_status || "Нет свежих данных";
}

// Capability catalog only: never issues START, CLEAR or an algorithm change.
let lastResearchCatalog = "";
function refreshResearchCatalog(data) {
  const panel = document.getElementById("researchAlgorithms");
  if (!panel) return;
  try {
    const algorithms = data.research_algorithms;
    if (!Array.isArray(algorithms)) throw new Error("Прошивки не подтверждают исследовательский профиль");
    const key=JSON.stringify(algorithms);
    if (key===lastResearchCatalog) return;
    lastResearchCatalog=key;
    panel.replaceChildren();
    for (const row of algorithms) {
      const item = document.createElement("p");
      item.textContent = `${row.hardware_ready ? "ДОСТУПЕН" : "ЗАБЛОКИРОВАН"}: ${row.label}. ${row.reason}`;
      panel.appendChild(item);
    }
  } catch (error) { panel.textContent = error.message; }
}


let simpleLastStatus = null;
function updateSimpleUI(data) {
  controlCookieActive = Number(data.hmi_ui_session_active) === 1;
  simpleLastStatus = data;
  const banner = document.getElementById("simpleState");
  const clear = document.getElementById("simpleClear");
  if (!banner || !clear) return; // A cached older page can safely finish loading.
  const fresh = Number.isFinite(Number(data.mc_age_ms)) && Number(data.mc_age_ms) >= 0 && Number(data.mc_age_ms) < 300;
  setConnection(fresh);
  const running = Number(data.pwm) === 1;
  const active = Number(data.mc_fault_current_mask || 0);
  const occurred = Number(data.mc_fault_occurred_mask || 0);
  const estop = Number(data.estop) === 1;
  let text = "Остановлен", tone = "idle";
  const faultName = bits => bits & 0x400 ? "Защита SD/IPM" : bits & 0x40 ? "Защита по току"
    : bits & 8 ? "Перегрев" : bits & 2 ? "Перенапряжение DC-шины"
    : bits & 4 ? "Низкое напряжение DC-шины" : "Защита привода";
  if (!fresh) { text = "Нет свежей связи с Nucleo"; tone = "error"; }
  else if (active) {
    text = active === 4 && Number(data.vdc) < 50 ? "Силовое питание выключено" : faultName(active);
    tone = active === 4 && Number(data.vdc) < 50 ? "idle" : "error";
  } else if (estop) { text = "Аварийный стоп зафиксирован"; tone = "error"; }
  else if (occurred || Number(data.mc_fault || 0) || Number(data.mc_transport_fault || 0)) {
    const reason = Number(data.mc_fault_reason || 0);
    text = occurred ? `${faultName(occurred)} — событие сохранено` : [1,2,3,11,12,13,14].includes(reason)
      ? "Ошибка связи UART — привод остановлен" : "Пуск заблокирован контроллером";
    tone = "error";
  } else if (hvArmLastError) {
    text = hvArmLastError.includes("PWM did not enter") ? "Пуск не подтверждён: контроллер не включил ШИМ"
      : hvArmLastError.includes("key") ? "Нет доступа к управлению" : "Команда не выполнена — подробности в диагностике";
    tone = "error";
  } else if (running) { text = "Работает"; tone = "running"; }
  banner.textContent = text; banner.dataset.state = tone;
  clear.hidden = !(fresh && !running && active === 0 && (estop || occurred || Number(data.mc_fault || 0) || Number(data.mc_transport_fault || 0)));
  const hz = Number(data.mc_frequency_reference_hz);
  document.getElementById("simpleField").textContent = fresh && Number(data.mc_frequency_reference_valid) === 1 && Number.isFinite(hz)
    ? `Частота поля: ${hz.toFixed(1)} Гц` : "Частота поля: —";
  document.getElementById("simpleMode").textContent = data.mode === "VF" ? "Скалярный V/f" : "Режим не подтверждён";
  document.getElementById("simpleVdc").textContent = fresh && Number(data.bp_vbus_valid) === 1 && typeof data.vdc === "number" && Number.isFinite(data.vdc) ? `${data.vdc.toFixed(0)} В` : "—";
  const rms = data.mc_current_rms_a;
  const valid = fresh && Number(data.mc_current_telemetry_valid) === 1 && Array.isArray(rms) && rms.length === 3 && rms.every(Number.isFinite);
  for (let i = 0; i < 3; i++) document.getElementById(`simpleI${i}`).textContent = valid ? `${rms[i].toFixed(2)} А` : "—";
  document.getElementById("simpleCurrentNote").textContent = !valid ? "Нет достоверного токового окна"
    : Number(data.mc_current_frozen) === 1 ? "Токи: последнее окно перед остановкой" : "Токи RMS по шунтам";
  if (!fresh || active || occurred || estop || Number(data.mc_fault || 0) || Number(data.mc_transport_fault || 0) || Number(freqSlider.value) <= 0) startBtn.disabled = true;
}
document.getElementById("simpleClear")?.addEventListener("click", async event => {
  const s = simpleLastStatus;
  if (!s || Number(s.pwm) !== 0 || Number(s.mc_fault_current_mask) !== 0 || !Number.isFinite(Number(s.mc_age_ms)) || Number(s.mc_age_ms) < 0 || Number(s.mc_age_ms) >= 300) return;
  event.target.disabled = true;
  try { await apiCmd("CLEAR"); await refreshStatus(); }
  finally { event.target.disabled = false; }
});

function updateAlgorithmUI(data) {
  const select=document.getElementById('algorithmSelect');
  if(!select)return;
  const fresh=Number(data.mc_age_ms)>=0&&Number(data.mc_age_ms)<300&&Number(data.research_native_valid)===1;
  const requested=Number(data.algorithm_requested),selected=Number(data.algorithm_selected);
  const running=Number(data.pwm)===1;
  if(document.activeElement!==select)select.value=String(requested||1);
  select.disabled=!fresh||running;
  const names={1:'Скалярный V/f',2:'Векторный FOC',3:'FOC · адаптивное положение ШИМ'};
  document.getElementById('simpleMode').textContent=fresh?names[selected]||'Ожидание режима':'Режим не подтверждён';
  const note=document.getElementById('algorithmNote');
  const qualified=Number(data.algorithm_qualification)===7;
  note.textContent=!fresh?'Ожидание подтверждения Nucleo':requested!==selected?'Ожидание выбора алгоритма':
    selected!==1&&!qualified?'Пуск FOC заблокирован: нужны параметры двигателя, проверка ампер и времени расчёта.':
    running?'Для смены алгоритма нажмите «Стоп».':'Смена режима при остановленном ШИМ. Пуск — отдельной кнопкой.';
  if(!fresh||requested!==selected||(selected!==1&&!qualified))startBtn.disabled=true;
  if(selected!==1){
    const rpm=Number(data.rpm_est);
    document.getElementById('simpleField').textContent=running&&Number(data.rpm_est_valid)===1&&Number.isFinite(rpm)?
      `Оценка скорости: ${rpm.toFixed(0)} об/мин · по токам, без энкодера`:'Оценка скорости: —';
  }
  freqSlider.setAttribute('aria-label',selected===1?'Задание частоты поля, Гц':'Задание скорости, Гц электрического эквивалента');
}
const updateSimpleBase=updateSimpleUI;
updateSimpleUI=function(data){updateSimpleBase(data);updateAlgorithmUI(data);};
document.getElementById('algorithmSelect')?.addEventListener('change',async event=>{
  const algo=Number(event.target.value);event.target.disabled=true;
  try{
    const response=await fetch('/api/algorithm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({algorithm:algo})});
    const result=await response.json();
    if(!result.ok)document.getElementById('algorithmNote').textContent=result.error||'Команда отклонена';
    await refreshStatus();
  }finally{updateAlgorithmUI(simpleLastStatus||{});}
});
