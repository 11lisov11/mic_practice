const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const appPath = "artifacts/live_bench_20261017/manual_scalar_hmi_simplified_r1/web_hmi/static/app.js";
const source = fs.readFileSync(appPath, "utf8");
const nodes = new Map();

function node() {
  const value = {
    value: "", min: "0", max: "50", textContent: "", innerHTML: "", title: "",
    hidden: false, disabled: false, style: {}, dataset: {}, parentElement: null,
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {}, setAttribute() {}, appendChild() {}, insertAdjacentElement() {},
    querySelector() { return node(); }, querySelectorAll() { return []; }, closest() { return node(); },
    getBoundingClientRect() { return { left: 0, width: 100 }; },
  };
  value.parentElement = { getBoundingClientRect() { return { left: 0, width: 100 }; } };
  return value;
}

const statusPanel = node();
statusPanel.querySelector = (selector) => selector === "h2" ? node() : node();
const document = {
  head: node(),
  getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, node());
    return nodes.get(id);
  },
  querySelector(selector) {
    if (selector === ".panel.status") return statusPanel;
    return node();
  },
  querySelectorAll() { return []; },
  createElement() { return node(); },
};

const context = {
  document,
  localStorage: { getItem() { return ""; }, setItem() {} },
  fetch: async () => ({ ok: false, json: async () => ({ ok: false, error: "offline" }) }),
  setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {},
  URL: { createObjectURL() {}, revokeObjectURL() {} },
  Blob: class {}, console,
};
vm.createContext(context);
vm.runInContext(source, context, { filename: appPath });

const ipmFault = context.controllerFaultDiagnosis({
  estop: 1, pwm: 0, mc_fault: 1, mc_diag_valid: 1, mc_fault_reason: 8,
  mc_fault_current_mask: 0x0400, mc_fault_occurred_mask: 0x0400,
  mc_uart_error_flags: 0, mc_bad_cnt: 0, mc_age_ms: 40,
});
assert.equal(ipmFault.severity, "fault");
assert.match(ipmFault.title, /IPM/);
assert.match(ipmFault.text, /MC_DP_FAULT/);
assert.match(ipmFault.text, /не ошибка UART/);

const uartFault = context.controllerFaultDiagnosis({
  estop: 1, pwm: 0, mc_fault: 1, mc_diag_valid: 1, mc_fault_reason: 12,
  mc_uart_error_flags: 2, mc_bad_cnt: 3, mc_age_ms: 40,
});
assert.equal(uartFault.severity, "fault");
assert.match(uartFault.title, /UART/);
assert.match(uartFault.text, /FE/);

const healthy = context.controllerFaultDiagnosis({
  estop: 0, pwm: 0, state: "SAFE", mc_fault: 0, bp_fault: 0,
  mc_diag_valid: 1, mc_fault_reason: 0, mc_uart_error_flags: 0,
  mc_bad_cnt: 0, mc_age_ms: 40,
});
assert.equal(healthy.severity, "healthy");

const manualReadyButNotArmed = {
  state: "SAFE", pwm: 0, estop: 0, mc_fault: 0, mc_bad: 0, mc_bad_cnt: 0,
  hmi_hv_enabled: 1, hmi_manual_scalar_supported: 1,
};
assert.equal(context.manualStartAllowed(manualReadyButNotArmed, false), true);
assert.equal(context.manualStartAllowed({ ...manualReadyButNotArmed, mc_fault: 5 }, false), false);
assert.equal(context.manualStartAllowed({ ...manualReadyButNotArmed, estop: 1 }, false), false);
assert.equal(context.manualStartAllowed({ ...manualReadyButNotArmed, hmi_manual_scalar_supported: 0 }, false), false);
assert.equal(context.manualStartAllowed({ ...manualReadyButNotArmed, hmi_manual_scalar_supported: 0 }, true), true);

const oneRejectedFrame = context.controllerFaultDiagnosis({
  estop: 0, pwm: 0, mc_fault: 0, bp_fault: 0, mc_diag_valid: 1,
  mc_fault_reason: 0, mc_uart_error_flags: 0, mc_bad_cnt: 0,
  mc_bad_integrity: 1, mc_bad_sequence: 0, mc_age_ms: 24,
});
assert.equal(oneRejectedFrame.severity, "warning");
assert.match(oneRejectedFrame.text, /ошибки целостности=1/);
assert.match(oneRejectedFrame.text, /не подтверждение текущего обрыва/);

const stale = context.controllerFaultDiagnosis({
  estop: 0, pwm: 0, mc_fault: 0, bp_fault: 0, mc_diag_valid: 1,
  mc_fault_reason: 0, mc_uart_error_flags: 0, mc_bad_cnt: 0, mc_age_ms: 500,
});
assert.equal(stale.severity, "warning");
assert.match(stale.title, /свежего статуса/);

const recoverableUndervoltage = {
  state: "SAFE", pwm: 0, estop: 0, precharge: 0, bp_status: 9, bp_ext: 0,
  hmi_local_stop_latched: 0, mc_fault: 5, bp_fault: 5, mc_fault_reason: 8,
  mc_fault_current_mask: 0x0004, mc_fault_occurred_mask: 0x0404,
  vdc: 321, hmi_vbus_high_meter_vdc: 322.7, hmi_vbus_hv_calibrated: 1,
  bp_vbus_valid: 1, mc_temp_valid: 1, mc_temp_c: 49, mc_temp_fault: 0,
  mc_age_ms: 36, mc_bad_cnt: 0, mc_bad_integrity: 0, mc_bad_sequence: 0,
  mc_uart_error_flags: 0, uno_rx_hw_errors: 0, mc_transport_fault: 0,
};
assert.equal(context.driveFaultClearDecision(recoverableUndervoltage).ok, true);
assert.equal(context.driveFaultClearDecision({ ...recoverableUndervoltage, pwm: 1 }).ok, false);
assert.equal(context.driveFaultClearDecision({ ...recoverableUndervoltage, vdc: 100 }).ok, false);
assert.equal(context.driveFaultClearDecision({ ...recoverableUndervoltage, mc_temp_c: 75 }).ok, false);
assert.equal(context.driveFaultClearDecision({ ...recoverableUndervoltage, mc_uart_error_flags: 1 }).ok, false);
assert.equal(context.driveFaultClearDecision({ ...recoverableUndervoltage, mc_fault_current_mask: 0x40 }).ok, false);

console.log("clear_fault_status_hmi_selftest: PASS");
