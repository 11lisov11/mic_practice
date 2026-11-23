let simpleLastStatus = null;
function updateSimpleUI(data) {
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
