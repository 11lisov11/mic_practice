"""Stage the corrected torque PI and a qualified MCSDK START-to-RUN handoff."""
from hashlib import sha256
import json
import shutil

from prepare_air56_lso_field_guard import OUT as BASE, NEW as OLD, ROOT, replace

OUT = BASE.with_name('air56_lso_run_handoff_r1')
NEW = (2026112313, 2026112314)


def native_tasks(source):
    source = replace(source, 'static float air56_start_flux_A;', '''static float air56_start_flux_A;

typedef struct {
  qd_t current, voltage;
  uint32_t adc_pair;
  uint16_t sector;
} air56_start_sample;

typedef struct {
  uint32_t magic, start_ms, peak_ms, adc_pair;
  uint16_t q_blocks, iq_limit, sector, samples;
  int16_t iq_peak, id_at_peak, vq_at_peak, vd_at_peak;
} air56_start_q_record;

#define AIR56_START_Q_MAGIC 0x3151534cU /* LSQ1 */
_Static_assert(sizeof(air56_start_q_record) == 32, "START current diagnostic must fit one page");
static air56_start_sample air56_start_latest __attribute__((section(".ccmram.air56_start_record")));
static air56_start_q_record air56_start_q __attribute__((section(".ccmram.air56_start_record")));''')
    source = replace(source, 'bool ACIM_IsMagnetized(void);',
                     'static bool ACIM_IsMagnetized(const air56_start_sample *sample);')
    source = replace(source, '              air56_start_flux_A = 0.0f;', '''              air56_start_flux_A = 0.0f;
              air56_start_latest = (air56_start_sample){0};
              air56_start_q = (air56_start_q_record){ .magic = AIR56_START_Q_MAGIC,
                                                      .start_ms = air56_lso_trace.start_ms };''')
    source = replace(source, '''            if(ACIM_IsMagnetized())
            {
              /* The fast loop holds angle zero until RUN, including during this handoff. */
              pACIM_LSO[M1]->fIqds_obs_A = Convert_s16_to_A(FOCVars[M1].Iqd);''', '''            const uint32_t mask = __get_PRIMASK();
            __disable_irq();
            const air56_start_sample sample = air56_start_latest;
            __set_PRIMASK(mask);
            if (ACIM_IsMagnetized(&sample))
            {
              /* Use exactly the sample qualified above while the fast loop holds angle zero. */
              pACIM_LSO[M1]->fIqds_obs_A = Convert_s16_to_A(sample.current);''')
    source = replace(source, '  foc->Vqd = voltage;', '  foc->Vqd = limited;')
    source = replace(source, '''  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);
  return PWMC_SetPhaseVoltage''', '''  const alphabeta_t applied = AIR56_CurrentVoltage(measured, angle, &FOCVars[M1], pPIDIq[M1], pPIDId[M1]);
  if (Mci[M1].State == START)
  {
    air56_start_latest = (air56_start_sample){ .current = FOCVars[M1].Iqd, .voltage = FOCVars[M1].Vqd,
                 .adc_pair = air56_trip_raw_pair, .sector = pwmcHandle[M1]->Sector };
  }
  return PWMC_SetPhaseVoltage''')
    source = replace(source, '''bool ACIM_IsMagnetized(void)
{
  bool bRetVal = false;

  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);
  const float id_A = Convert_s16_to_A(FOCVars[M1].Iqd).fS_Component2;''', '''static bool ACIM_IsMagnetized(const air56_start_sample *sample)
{
  FOCVars[M1].Iqdref = STC_GetDefaultIqdref(pSTC[M1]);
  const qd_t current = sample->current;
  const float id_A = Convert_s16_to_A(current).fS_Component2;''')
    source = replace(source, '  const int16_t id = FOCVars[M1].Iqd.d;', '  const int16_t id = current.d;')
    source = replace(source, '''  const bool in_band = id >= id_low && id <= id_high;
  if (in_band)''', '''  const bool in_band = id >= id_low && id <= id_high;
  /* At the minimum qualified flux, the seeded Iq must explain at most the
   * already allowed 0.75 Hz of slip in the first observer step. */
  const int16_t iq_limit = (int16_t)(id_low * TAU_R * AIR56_FIELD_RAD_PER_TURN * AIR56_FIELD_MARGIN_HZ);
  const bool iq_ready = current.q >= -iq_limit && current.q <= iq_limit;
  if (in_band && iq_ready)''')
    source = replace(source, '    air56_start_record.iq_last = FOCVars[M1].Iqd.q;', '''    air56_start_record.iq_last = current.q;
    ++air56_start_q.samples;
    air56_start_q.iq_limit = iq_limit;
    if (in_band && !iq_ready) { ++air56_start_q.q_blocks; }
    if (air56_start_q.samples == 1 || air56_abs_i16(current.q) > air56_abs_i16(air56_start_q.iq_peak))
    {
      air56_start_q.peak_ms = HAL_GetTick();
      air56_start_q.adc_pair = sample->adc_pair;
      air56_start_q.sector = sample->sector;
      air56_start_q.iq_peak = current.q;
      air56_start_q.id_at_peak = current.d;
      air56_start_q.vq_at_peak = sample->voltage.q;
      air56_start_q.vd_at_peak = sample->voltage.d;
    }''')
    return replace(source, '''  bRetVal = bACIM_MagnValidCount == MAGN_VALIDATION_TICKS &&
            air56_start_flux_A >= Convert_s16_to_A((qd_t){ .d = id_low }).fS_Component2 &&
            air56_start_flux_A <= Convert_s16_to_A((qd_t){ .d = id_high }).fS_Component2;
  return bRetVal;''', '''  return bACIM_MagnValidCount == MAGN_VALIDATION_TICKS &&
         air56_start_flux_A >= Convert_s16_to_A((qd_t){ .d = id_low }).fS_Component2 &&
         air56_start_flux_A <= Convert_s16_to_A((qd_t){ .d = id_high }).fS_Component2;''')


def native_wire(source):
    source = replace(source, '    const bool field_page =', '''    const bool start_q_page = air56_start_q.magic == AIR56_START_Q_MAGIC && air56_page == 262U;
    const bool field_page =''')
    source = replace(source, '(field_page || start_page || trip_page ||',
                     '(start_q_page || field_page || start_page || trip_page ||')
    source = replace(source, '        if (field_page)\n        {', '''        if (start_q_page)
        {
            memcpy(p + 7, &air56_start_q, sizeof(air56_start_q));
        }
        else if (field_page)
        {''')
    return replace(source, 'page_index <= 261U', 'page_index <= 262U')


def native_config(source):
    return replace(source, '.hKpDivisorPOW2      = (uint16_t)TF_KPDIV_LOG,',
                   '.hKpDivisorPOW2      = (uint16_t)T_KPDIV_LOG,')


def main():
    report = json.loads((BASE / 'verification.json').read_text(encoding='utf8'))
    assert report['passed'] and report['pair'] == list(OLD)
    for name, expected in report['images_sha256'].items():
        assert sha256((BASE / 'image' / name).read_bytes()).hexdigest() == expected
    assert sha256((BASE / 'web_hmi/server.py').read_bytes()).hexdigest() == report['web_hmi_sha256']
    preserved = json.loads((BASE / 'preserved_inputs_sha256.json').read_text(encoding='utf8'))
    for dirpath in OUT.parent.glob('lso_23*'):
        if dirpath.is_dir():
            for path in dirpath.rglob('*'):
                if path.is_file():
                    preserved[path.relative_to(ROOT).as_posix()] = sha256(path.read_bytes()).hexdigest()
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE', 'UNOQ_MOTOR', 'libraries', 'web_hmi'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release', '__pycache__', '*.pyc'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(BASE / name, OUT / name)
    edits = {'Src/mc_tasks.c': native_tasks, 'Src/mc_config.c': native_config,
             'Inc/air56_lso_uno.inc': native_wire,
             'UNOQ_MOTOR/UNOQ_MOTOR.ino': lambda s: replace(replace(s, 'g_ma_value <= 261U', 'g_ma_value <= 262U'),
                                                          'page>261U', 'page>262U'),
             'web_hmi/server.py': lambda s: replace(s, 'int(page[2]) <= 261', 'int(page[2]) <= 262')}
    for name, edit in edits.items():
        path = OUT / name
        source = path.read_text(encoding='utf8')
        for old, new in zip(OLD, NEW):
            source = source.replace(str(old), str(new))
        path.write_text(edit(source), encoding='utf8')
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(preserved, indent=2) + '\n', encoding='utf8')
    print(OUT)


if __name__ == '__main__':
    main()
