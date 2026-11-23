from prepare_standstill_commissioning import once,read

def patch_server(s,template):
 s=once(s,'def sd_live_status(data):',read(template/'hmi_decoder.py')+'\n\ndef sd_live_status(data):')
 return once(s,'                "foc_runtime_valid":','                **foc_runtime_status(kv),\n                "foc_runtime_valid":')

def patch_js(s):
 a='  if (mcLocalStopLatched(data)) return "ЛОКАЛЬНЫЙ STOP B1 (PC13)";'
 s=once(s,a,a+'''\n  const frozen = data.foc_runtime?.available ? data.foc_runtime.first_fault : null;
  if (Number(data.algorithm_fault) === 3 && frozen?.reason_ru) return `MA_STALE: ${frozen.reason_ru}`;''')
 s=once(s,'text = active === 4 && Number(data.vdc) < 50 ? "Силовое питание выключено" : faultName(active);',
  '''text = active === 4 && Number(data.vdc) < 50 ? "Силовое питание выключено"
      : active === 128 ? mcFaultSummary(data, Number(data.mc_fault || 0)) : faultName(active);''')
 return once(s,'document.getElementById("simpleMode").textContent = data.mode === "VF" ? "Скалярный V/f" : "Режим не подтверждён";',
  '''document.getElementById("simpleMode").textContent = fresh && Number(data.research_native_valid) === 1
    ? ({1: "Скалярный V/f", 2: "FOC", 3: "FOC + адаптивный ШИМ"}[Number(data.algorithm_selected)] || "Режим не подтверждён") : "Режим не подтверждён";''')
