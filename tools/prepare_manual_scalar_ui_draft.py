"""Create a local, UI-only simplification draft from the latest installed HMI assets.

This script never contacts hardware or changes the HMI server. Authentication and
the server-side timed HV preflight remain in place.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/live_bench_20261015/manual_scalar_working_pair_r3/web_hmi/static"
OUT = ROOT / "artifacts/live_bench_20261017/manual_scalar_ui_draft_20261017"
STATIC = OUT / "web_hmi/static"


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    assert count == 1, (old[:100], count)
    return source.replace(old, new, 1)


def simplify_html(source: str) -> str:
    start = source.index('        <div class="manual-config" id="manualConfig" hidden>')
    end = source.index('        <div class="hv-arm-block"', start)
    panel = '''        <div class="manual-config" id="manualConfig" hidden>
          <p>Задание 0–50 Гц. Пуск работает до «Стоп»; останов — свободный выбег.</p>
          <div class="hv-arm-note" id="manualState">Настройки доступны после подключения.</div>
          <details class="manual-settings">
            <summary>Настройки разгона и снижения</summary>
            <label>Разгон, Гц/с <input id="manualAccel" type="number" min="0.1" max="50" step="0.1" value="5" /></label>
            <label>Замедление, Гц/с <input id="manualDecel" type="number" min="0.1" max="5" step="0.1" value="1" /></label>
            <button class="btn ghost full" id="manualApply">Применить настройки</button>
            <label>Снижение задания <select id="manualDownmode"><option value="RAMP">Плавно, с контролем DC-шины</option><option value="COAST">Выбег, затем отдельный пуск</option></select></label>
          </details>
        </div>
'''
    source = source[:start] + panel + source[end:]
    arm_input = '''          <input
            id="hvArmConfirm"
            class="hv-arm-input"
            type="text"
            inputmode="text"
            autocomplete="off"
            autocapitalize="characters"
            placeholder="Введите ARM 310V"
          />
'''
    source = replace_once(source, arm_input, "")
    return source


def simplify_js(source: str) -> str:
    start = source.index('startBtn.addEventListener("click", async () => {')
    end = source.index('\nif (hvArmBtn) {', start)
    source = source[:start] + '''startBtn.addEventListener("click", async () => {
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
''' + source[end:]

    old_start_gate = '''    const basicStartReady =
      String(data.state || "") === "SAFE" &&
      Number(data.pwm || 0) === 0 &&
      Number(data.estop || 0) === 0 &&
      Number(mcField(data, "fault", 0)) === 0 &&
      Number(mcField(data, "bad", 0)) === 0 &&
      Number(mcField(data, "bad_cnt", 0)) === 0;
    const standaloneHv = Number(data.hmi_hv_enabled || 0) === 1;
    startBtn.disabled = !basicStartReady || (standaloneHv && !hvArmed);
'''
    source = replace_once(source, old_start_gate,
        '    startBtn.disabled = !manualStartAllowed(data, hvArmed);\n')
    source = replace_once(source, 'function updateManualUI(data) {', '''function manualStartAllowed(data, isHvArmed) {
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

function updateManualUI(data) {''')

    start = source.index('function updateManualUI(data) {')
    end = source.index('document.getElementById("manualApply")', start)
    source = source[:start] + '''function updateManualUI(data) {
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
''' + source[end:]
    source = replace_once(source, '''document.getElementById("manualFrequencyApply").addEventListener("click",async()=>{
  const f=Number(document.getElementById("manualFrequency").value);
  if (!Number.isFinite(f) || f<0 || f>50) return;
  if (await apiCmd(`SET FREQ ${f.toFixed(1)}`)) delete document.getElementById("manualFrequency").dataset.dirty;
  await refreshStatus();
});
''', "")
    source = replace_once(source, 'for (const id of ["manualAccel","manualDecel","manualFrequency"]) {',
        'for (const id of ["manualAccel","manualDecel"]) {')

    source = replace_once(source, 'const hvArmConfirm = document.getElementById("hvArmConfirm");\n', "")
    source = replace_once(source, 'let hvArmed = false;\n', 'let hvArmed = false;\nlet hvArmConfirmPhrase = "";\n')
    source = replace_once(source,
        '  const confirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));',
        '  hvArmConfirmPhrase = String(data.hmi_arm_confirm || (isLv ? "ARM LV HV OFF" : "ARM 310V"));')
    source = replace_once(source, '''  if (hvArmConfirm) {
    hvArmConfirm.disabled = hvArmed;
    hvArmConfirm.placeholder = `Введите ${confirmPhrase}`;
  }
''', "")
    old = '''    const confirm = hvArmConfirm ? hvArmConfirm.value.trim().toUpperCase() : "";
    const result = await apiHvArm(action, confirm);
    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";
'''
    source = replace_once(source, old, '    const result = await apiHvArm(action, action === "arm" ? hvArmConfirmPhrase : "");\n')
    source = replace_once(source, '''if (hvArmConfirm) {
  hvArmConfirm.addEventListener("input", () => {
    hvArmLastError = "";
  });
}

''', "")
    source = replace_once(source, '    if (result.ok && hvArmConfirm) hvArmConfirm.value = "";\n', "")

    source = replace_once(source, '    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired;',
        '    if (controlAccessBlock) controlAccessBlock.hidden = !controlAuthRequired || Boolean(controlToken);')
    source = replace_once(source, '''function noteApiAccess(data) {
  if (data && data.error === "control access key is missing or invalid") {
    setAccessStatus(false);
  }
}''', '''function noteApiAccess(data) {
  if (data && data.error === "control access key is missing or invalid") {
    if (controlAccessBlock) controlAccessBlock.hidden = false;
    setAccessStatus(false);
  }
}''')
    source = replace_once(source, '      setAccessStatus(true);\n    } else {',
        '      setAccessStatus(true);\n      if (controlAccessBlock) controlAccessBlock.hidden = Boolean(controlAuthRequired);\n    } else {')
    source = replace_once(source, 'setFreqUI(0.0);', 'setFreqUI(5.0);')
    return source


def main() -> None:
    assert SOURCE.is_dir(), SOURCE
    if (OUT / "manifest.json").exists():
        existing = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
        assert existing.get("installed") is False, "Refusing to overwrite an installed artifact"
    STATIC.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(SOURCE / name, STATIC / name)
    (STATIC / "index.html").write_text(simplify_html((STATIC / "index.html").read_text(encoding="utf-8")), encoding="utf-8")
    (STATIC / "app.js").write_text(simplify_js((STATIC / "app.js").read_text(encoding="utf-8")), encoding="utf-8")
    css = STATIC / "style.css"
    css.write_text(css.read_text(encoding="utf-8") + '''
[hidden]{display:none!important;}
.manual-settings{display:grid;gap:10px;border-top:1px solid #303844;padding-top:10px;}
.manual-settings summary{cursor:pointer;color:#b9c2ce;}
''', encoding="utf-8")
    digests = {name: hashlib.sha256((STATIC / name).read_bytes()).hexdigest() for name in ("index.html", "app.js", "style.css")}
    manifest = {
        "schema": "mic_ai.manual_scalar_ui_draft.v1",
        "source_candidate": "artifacts/live_bench_20261015/manual_scalar_working_pair_r3",
        "source_firmware_pair": [2026101505, 2026101504],
        "installed": False,
        "hardware_commands": 0,
        "firmware_changed": False,
        "server_auth_changed": False,
        "timed_hv_preflight_changed": False,
        "calibration_changed": False,
        "static_sha256": digests,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Simplified manual scalar HMI draft\n\n"
        "UI-only draft based on the current installed firmware pair. The main controls are Start, Stop, emergency stop, and a 0–50 Hz slider. Ramp/downshift settings are collapsed. The ARM phrase and separate ARM button are removed from the normal manual flow; Start invokes the existing authenticated, time-limited server preflight. The access-key field is hidden while a token is stored and reappears when the server rejects it. Server authentication, the timed HV permission, calibration, MCU protections, and firmware are unchanged. This draft has not been deployed.\n",
        encoding="utf-8",
    )
    print(json.dumps({"draft": str(OUT), "installed": False, "hardware_commands": 0, "files": digests}, indent=2))


if __name__ == "__main__":
    main()
