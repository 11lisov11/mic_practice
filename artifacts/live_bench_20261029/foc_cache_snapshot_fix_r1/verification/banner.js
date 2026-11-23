const assert=require('assert');
function mcFaultSummary(data, code) {
  const regularFault = data.foc_runtime?.first_fault;
  if ((Number(data.mc_fault_current_mask || data.mc_fault_occurred_mask || 0) & 128) &&
      regularFault?.reason_code === 9 && regularFault.regular_adc) {
    return regularFault.reason_ru;
  }

  if (mcLocalStopLatched(data)) return "ЛОКАЛЬНЫЙ STOP B1 (PC13)";
  const frozen = data.foc_runtime?.available ? data.foc_runtime.first_fault : null;
  if (Number(data.algorithm_fault) === 3 && frozen?.reason_ru) return `MA_STALE: ${frozen.reason_ru}`;
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
const data={"mc_fault_current_mask": 128, "foc_runtime": {"available": true, "observer_measured": false, "source": "runtime_observer", "observer_wall_us": 0.0, "irq_body_lower_us": 0.0, "cpu_upper_us": 0.0, "irq_root_count": 0, "max_wall_us": 0.0, "max_irq_body_lower_us": 0.0, "max_cpu_upper_us": 0.0, "window_queue_us": 0.0, "input_age_us": 0.0, "result_age_us": 0.0, "max_window_queue_us": 0.0, "max_result_age_us": 0.0, "observer_steps": 0, "meter_errors": 0, "first_fault": {"reason_code": 9, "reason_ru": "\u0410\u0426\u041f: \u0432\u043e\u0437\u0440\u0430\u0441\u0442 \u043e\u0442\u0441\u0447\u0451\u0442\u0430 \u0434\u043e\u0441\u0442\u0438\u0433 1 \u043c\u0441", "algorithm_fault": 0, "at_cycles": 1000000, "regular_adc": {"reason_code": 3, "reason_ru": "\u0432\u043e\u0437\u0440\u0430\u0441\u0442 \u043e\u0442\u0441\u0447\u0451\u0442\u0430 \u0434\u043e\u0441\u0442\u0438\u0433 1 \u043c\u0441", "id": 0, "channel": 2, "at_cycles": 1000000, "stamp_cycles": 829999, "age_us": 1000.0058823529412, "timer_cnt": 4000, "timer_cr1": 16, "adc_isr": 0, "adc_cr": 0, "adc_sqr1": 0, "pending_id": 4294967295, "flags": 3, "ipsr": 15, "age_valid_for_expiry": true}}, "limitation": "CPU upper includes exception entry/return and profiler edge overhead; IRQ body time is a lower bound."}};
assert.strictEqual(mcFaultSummary(data,5),data.foc_runtime.first_fault.reason_ru);
