// Run the actual shipped renderer against a minimal DOM, without motor commands.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const renderer = source.slice(source.indexOf('function updateShuntCurrentPanel(data)'));
assert(renderer.startsWith('function updateShuntCurrentPanel(data)'));
const elements = new Map();
let insertions = 0;
const document = {
  getElementById: id => elements.get(id) || null,
  createElement: () => ({
    set innerHTML(html) {
      for (const match of html.matchAll(/id="([^"]+)"/g)) elements.set(match[1], {textContent: ''});
    },
  }),
};
elements.set('driveDiagnostics', {insertAdjacentElement(position, panel) {
  assert.equal(position, 'afterend'); elements.set(panel.id, panel); insertions++;
}});
const currVal = {};
const context = vm.createContext({document, currVal});
vm.runInContext(renderer, context);
const text = id => elements.get(id).textContent;
const update = context.updateShuntCurrentPanel;
let checks = 0;
const check = value => { assert(value); checks++; };
const valid = {mc_current_telemetry_valid: 1, mc_current_rms_a: [.707, .708, .706],
  mc_current_peak_a: [1, 1.001, .999], mc_current_instant_a: [.5, -.6, .1],
  mc_current_status: 'Измерение при работе; номинальный масштаб', mc_current_window_ms: 200,
  mc_current_coverage_pct: 100, mc_current_reconstructed_mask: 7,
  mc_current_rejected_samples: 0, mc_current_raw_adc: [2048, 2051, 2043, 2045],
  mc_current_offsets_adc: [2048, 2051, 2043, 2045], mc_current_zero_ready: 1};
update(valid);
check(text('shuntCurrentRms') === '0.707 / 0.708 / 0.706');
check(text('shuntCurrentPeak') === '1.000 / 1.001 / 0.999');
check(text('shuntCurrentInstant') === '0.500 / -0.600 / 0.100');
check(text('shuntCurrentQuality').includes('U, V, W'));
check(text('shuntCurrentAdc').includes('2048 / 2051 / 2043 / 2045'));
check(currVal.textContent.includes('А RMS'));
update({...valid, mc_current_frozen: 1, mc_current_status: 'Последнее окно перед остановом'});
check(text('shuntCurrentState').includes('перед остановом'));
check(currVal.textContent.includes('(последнее окно)'));
update({mc_current_telemetry_valid: 0, mc_current_status: 'Данные токов устарели'});
for (const id of ['shuntCurrentRms', 'shuntCurrentPeak', 'shuntCurrentInstant']) check(text(id) === '—');
check(!text('shuntCurrentAdc').includes('2048'));
check(currVal.textContent === 'Нет достоверного измерения');
update({...valid, mc_current_rms_a: [NaN, .2, .3]});
check(text('shuntCurrentRms') === '—');
update({...valid, mc_current_rms_a: [1, 2]});
check(text('shuntCurrentRms') === '—');
if (renderer.includes('mc_current_zero_spans')) {
  const quality = {mc_current_zero_spans: [20, 24, 30, 28], mc_current_zero_stable: 3,
    mc_current_zero_attempts: 4, mc_current_zero_last_reject: 0};
  update({...valid, ...quality});
  check(text('shuntCurrentAdc').includes('20 / 24 / 30 / 28'));
  check(text('shuntCurrentAdc').includes('3/3') && text('shuntCurrentAdc').includes('4/8'));
  update({...valid, ...quality, mc_current_telemetry_valid: 0, mc_current_zero_last_reject: 4});
  check(text('shuntCurrentAdc').includes('средние блоков расходятся'));
  update({mc_current_telemetry_valid: 0, mc_current_status: 'Данные токов устарели'});
  check(!text('shuntCurrentAdc').includes('20 / 24'));
}
check(insertions === 1);
if (renderer.includes('mc_zero_history_status')) {
  update({...valid, mc_zero_history_status: 'Блоки нуля: 1: стабилен 1/3 | 2: дрейф'});
  check(text('shuntCurrentAdc').includes('1: стабилен 1/3 | 2: дрейф'));
  update(valid);
  check(!text('shuntCurrentAdc').includes('2: дрейф'));
}
console.log(JSON.stringify({passed: true, checks, hardware_commands: 0}));
