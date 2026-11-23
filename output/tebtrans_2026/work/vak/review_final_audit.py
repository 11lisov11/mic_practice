import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from PIL import Image, ImageChops
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / 'Марикин_Параметрическая_адаптация_ТЭБТРАНС_2026.docx'
RAW_PATH = Path(r'C:\mic_theory\experiments\parameter_adaptive_speed\confirmation_20261006\results.json')
raw = json.loads(RAW_PATH.read_text(encoding='utf-8'))
analysis = json.loads((HERE / 'review_analysis.json').read_text(encoding='utf-8'))
verified = json.loads((HERE.parent / 'verified_metrics.json').read_text(encoding='utf-8'))
assert hashlib.sha256(RAW_PATH.read_bytes()).hexdigest() == analysis['raw_sha256']
assert len(raw['rows']) == 320 and len(raw['seeds']) == 20
assert all(r['failure'] is None and r['completed_steps'] == 25000 for r in raw['rows'])
assert all(r['peak_current_a'] < 2.8 for r in raw['rows'])
metric_names = ['tracking_mae_rad_s', 'peak_current_a', 'steady_torque_std_nm', 'copper_energy_j']
means = {}
for label, reference in verified.items():
    case, method = label.split('/')
    rows = [r for r in raw['rows'] if r['scenario'] == case and r['method'] == method]
    assert len(rows) == 20 and sorted(r['seed'] for r in rows) == sorted(raw['seeds'])
    means[label] = {key: statistics.mean(r[key] for r in rows) for key in metric_names}
    for key in metric_names:
        assert math.isclose(means[label][key], reference[key], rel_tol=1e-12, abs_tol=1e-12)

doc = Document(OUT)
assert len(doc.tables) == 3 and len(doc.inline_shapes) == 3
methods = ['fixed_reference', 'joint_only', 'direct_feedback', 'confidence_feedback']
cases = ['parameter_drift', 'composite']
comparison = doc.tables[1]
checked_cells = 0
for case_index, case in enumerate(cases):
    for metric_index, key in enumerate(metric_names):
        row_index = 2 + case_index * 5 + metric_index
        for col, method in enumerate(methods, 1):
            number = means[f'{case}/{method}'][key]
            scale, places = (1000, 3) if key == 'steady_torque_std_nm' else (1, 2 if key == 'copper_energy_j' else 3)
            expected = f'{number * scale:.{places}f}'.replace('.', ',')
            assert comparison.cell(row_index, col).text == expected, (row_index, col, expected)
            checked_cells += 1

terminal_errors = {}
for case in cases:
    rows = [r for r in raw['rows'] if r['scenario'] == case and r['method'] == 'confidence_feedback']
    terminal_errors[case] = {}
    for index, key in enumerate(['rs', 'rr', 'lm']):
        errors = []
        for row in rows:
            truth = row['actual_initial_parameters'][key] * (1.3 if key == 'rs' else 1)
            estimate = analysis['nominal_motor'][key] * math.exp(row['parameter_logs'][index])
            errors.append(100 * abs(estimate / truth - 1))
        terminal_errors[case][key] = statistics.mean(errors)
        assert math.isclose(terminal_errors[case][key], analysis['terminal_parameter_mape'][case][key], abs_tol=1e-12)

old = Document(HERE / 'before_review_corrections.docx')
def bibliography(document, heading, after):
    paragraphs = [p.text.strip() for p in document.paragraphs]
    start = paragraphs.index(heading) + 1
    end = next(i for i in range(start, len(paragraphs)) if paragraphs[i].startswith(after))
    result = [p for p in paragraphs[start:end] if re.match(r'^\d+\.', p)]
    assert len(result) == 7
    return result

ru = bibliography(doc, 'Библиографический список', 'Контактная информация')
en = bibliography(doc, 'References', 'Author’s information')
assert ru == bibliography(old, 'Библиографический список', 'Контактная информация')
assert en == bibliography(old, 'References', 'Author’s information')
texts = [p.text for p in doc.paragraphs]
body = '\n'.join(texts[:next(i for i,p in enumerate(texts) if p == 'Библиографический список')])
cited = {int(x) for group in re.findall(r'\[([1-7](?:,\s*[1-7])*)\]', body) for x in re.findall(r'\d+', group)}
assert cited == set(range(1, 8))
assert len([p for p in texts if re.match(r'^[1-5]\. ', p) and p not in ru + en]) == 5
all_text = '\n'.join(texts + [c.text for t in doc.tables for r in t.rows for c in r.cells])
assert not re.search(r'</?(?:sub|sup)>', all_text)
assert not re.search(r'\b(?:прогон\w*|пики|метрики|фидбек\w*|холд[ао]ут\w*)\b', all_text, re.I)
assert '21,4; 1,26; 4,85%' in all_text
assert '21,4; 1,21; 4,84%' in all_text

reference = next(Path(r'C:\Study\Статьи и конференции\ВАК').glob('Марикин*.docx'))
assert doc.sections[0]._sectPr.xml == Document(reference).sections[0]._sectPr.xml
with ZipFile(OUT) as result, ZipFile(reference) as source:
    for part in ['word/styles.xml', 'word/fontTable.xml', 'word/theme/theme1.xml', 'word/footer1.xml']:
        assert result.read(part) == source.read(part), part

supp_dir = HERE / 'matched_covariance_20261027'
supp = json.loads((supp_dir / 'results.json').read_text(encoding='utf-8'))
supp_analysis = json.loads((supp_dir / 'analysis.json').read_text(encoding='utf-8'))
channel_analysis = json.loads((supp_dir / 'channel_analysis.json').read_text(encoding='utf-8'))
assert len(supp['rows']) == 40
assert supp['protocol']['independent_new_holdout'] is False
assert supp['protocol']['load_density'] == .01
assert all(r['failure'] is None and r['completed_steps'] == 25000 and r['peak_current_a'] < 2.8 for r in supp['rows'])
assert supp['protocol']['original_sha256'] == analysis['raw_sha256']
assert hashlib.sha256((HERE / 'matched_covariance_study.py').read_bytes()).hexdigest() == supp['protocol']['runner_sha256']
for path, expected in raw['source_sha256'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected

indices = np.random.default_rng(20261027).integers(0, 20, size=(10000, 20))
additional_cells = 0
for case_index, case in enumerate(cases):
    fixed = sorted([r for r in supp['rows'] if r['scenario'] == case], key=lambda r: r['seed'])
    weighted = sorted([r for r in raw['rows'] if r['scenario'] == case and r['method'] == 'confidence_feedback'], key=lambda r: r['seed'])
    assert len(fixed) == 20
    for a, b in zip(fixed, weighted):
        for key in ['seed', 'actual_initial_parameters', 'load_start_s', 'load_level_nm']:
            assert a[key] == b[key]
    for key in metric_names:
        assert math.isclose(statistics.mean(r[key] for r in fixed), supp_analysis[case]['fixed_same_q'][key], abs_tol=1e-12)
    f = np.array([r['tracking_mae_rad_s'] for r in fixed])
    w = np.array([r['tracking_mae_rad_s'] for r in weighted])
    ratio = w.mean() / f.mean()
    interval = np.quantile(w[indices].mean(axis=1) / f[indices].mean(axis=1), [.025, .975])
    v = supp_analysis[case]['confidence_feedback']['tracking_mae_rad_s']
    assert math.isclose(ratio, v['ratio_to_fixed_same_q'], abs_tol=1e-12)
    assert np.allclose(interval, v['ratio_ci95'], rtol=0, atol=1e-12)
    fmt = lambda x: f'{x:.3f}'.replace('.', ',')
    expected_cells = [fmt(f.mean()), fmt(w.mean()), f'{fmt(ratio)} [{fmt(interval[0])}; {fmt(interval[1])}]']
    assert [c.text for c in doc.tables[2].rows[case_index+1].cells[1:]] == expected_cells
    additional_cells += 3
    joint = sorted([r for r in raw['rows'] if r['scenario'] == case and r['method'] == 'joint_only'], key=lambda r: r['seed'])
    for method in ['direct_feedback', 'confidence_feedback']:
        candidate = sorted([r for r in raw['rows'] if r['scenario'] == case and r['method'] == method], key=lambda r: r['seed'])
        for key in metric_names:
            j = np.array([r[key] for r in joint])
            c = np.array([r[key] for r in candidate])
            ratio = c.mean() / j.mean()
            ci = np.quantile(c[indices].mean(axis=1) / j[indices].mean(axis=1), [.025, .975])
            record = channel_analysis[case][method][key]
            assert math.isclose(100*(ratio-1), record['percent_change'], abs_tol=1e-12)
            assert np.allclose(ci, record['ci95_ratio'], rtol=0, atol=1e-12)

sys.path.insert(0, r'C:\mic_theory')
from tools import study_parameter_adaptive_speed as simulator
from control.current_only_induction_ekf import CurrentOnlyInductionEKF
from control.parameter_adaptive_induction_ekf import ParameterAdaptiveInductionEKF
motor = simulator.nominal_motor(json.loads(simulator.DEFAULT_BUNDLE.read_text(encoding='utf-8')))
r = np.array(analysis['measurement_covariance'])
fixed_observer = CurrentOnlyInductionEKF(motor, r)
fixed_observer.q_spectral[5] = simulator.Q['fixed_q01']
adaptive_observer = ParameterAdaptiveInductionEKF(motor, r)
assert np.array_equal(fixed_observer.p, adaptive_observer.p[:6, :6])
assert np.array_equal(fixed_observer.q_spectral, adaptive_observer.q_spectral[:6])
assert np.array_equal(fixed_observer.r, adaptive_observer.r)
assert simulator.Q['fixed_q1'] == .1
assert '0,1 в номинальном режиме' in doc.tables[0].cell(6, 1).text
assert 'Научная новизна результатов' in body
assert 'Всего выполнено 360 расчётов' in body
assert 'поправка на множественные сравнения не вводилась' in body

pages = sorted((HERE / 'render_completion_v3').glob('page-*.png'))
assert len(pages) == 12
identical_previously_reviewed = []
for page in pages:
    original = HERE / 'render_completion_v1' / page.name
    if ImageChops.difference(Image.open(page).convert('RGB'), Image.open(original).convert('RGB')).getbbox() is None:
        identical_previously_reviewed.append(int(page.stem.split('-')[1]))
assert set(identical_previously_reviewed) == {2, 3, 5, 6, 8, 11, 12}
report = {
    'output': str(OUT),
    'output_sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
    'raw_sha256': analysis['raw_sha256'],
    'completed_source_trials': 320,
    'completed_additional_control_trials': 40,
    'total_trials': 360,
    'independent_realizations_per_case_method': 20,
    'aggregate_values_recomputed': len(means) * len(metric_names),
    'comparison_table_numeric_cells_verified': checked_cells,
    'additional_table_cells_verified': additional_cells,
    'additional_means_and_paired_intervals_recomputed': True,
    'channel_effects_and_paired_intervals_recomputed': True,
    'common_state_initial_and_process_covariances_matched': True,
    'original_fourteen_simulation_source_hashes_unchanged': True,
    'nominal_baseline_load_density_corrected_to_actual_0_1': True,
    'terminal_parameter_mape': terminal_errors,
    'all_currents_below_2_8_a': True,
    'raw_maximum_current_a': max(r['peak_current_a'] for r in raw['rows']),
    'russian_and_english_bibliographies_unchanged': True,
    'all_seven_references_cited': True,
    'numbered_conclusions': 5,
    'figures': 3,
    'tables': 3,
    'source_section_styles_theme_font_table_footer_preserved': True,
    'final_render_pages_visually_reviewed': list(range(1, 13)),
    'final_pages_identical_to_previously_reviewed_render': sorted(identical_previously_reviewed),
    'final_pages_reviewed_after_last_changes': [1, 4, 7, 9, 10],
    'final_render_directory': str(HERE / 'render_completion_v3'),
    'new_simulations_executed': True,
}
(HERE / 'completion_final_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
