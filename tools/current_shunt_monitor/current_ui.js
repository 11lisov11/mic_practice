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
  currVal.textContent = valid ? `${format(data.mc_current_rms_a)} А RMS${data.mc_current_frozen ? " (последнее окно)" : ""}` : "Нет достоверного измерения";
  currVal.title = data.mc_current_status || "Нет свежих данных";
}
