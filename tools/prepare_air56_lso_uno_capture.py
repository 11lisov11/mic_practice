"""Assemble the bounded LSO capture pair in a new directory (no board access)."""
from pathlib import Path
import json
import shutil

from prepare_air56_lso_timing_aspep import BENCH, OUT as LSO, ROOT, replace
from install_air56_lso_off_dwt import release

OUT = BENCH / 'air56_st_lso_uno_capture_r1'
SUPERVISOR = BENCH / 'foc_handover_feedback_release_r1'
NEW = (2026112301, 2026112302)
TOOLS = ROOT / 'tools'


def edit(name, change):
    path = OUT / name
    path.write_text(change(path.read_text(encoding='utf8')), encoding='utf8')


def task_changes(s):
    s = replace(s, '#include "air56_st_lso_limits.h"', '''#include "air56_st_lso_limits.h"
#include "air56_lso_capture.h"''')
    s = replace(s, 'static bool air56_run_started;', '''static bool air56_run_started;
volatile air56_trace air56_lso_trace;
static void AIR56_UnoService(void);

static void air56_capture_begin(uint32_t now)
{
  air56_lso_trace = (air56_trace){
    .magic = AIR56_TRACE_MAGIC, .start_ms = now, .start_cycles = DWT->CYCCNT
  };
  air56_lso_trace.active = 1;
}

static void air56_capture_finish(uint32_t reason, uint32_t now)
{
  air56_lso_trace.active = 0;
  air56_trace_window(&air56_lso_trace, DWT->CYCCNT);
  air56_lso_trace.end_ms = now;
  air56_lso_trace.reason = reason;
}''')
    s = replace(s, '/* The local button is STOP only. Motor Pilot is the command owner. */',
                '/* The local button is STOP only. The Uno link owns trial starts. */')
    # Avoid clearing the 8 KiB data region in one scheduler invocation.
    s = replace(s, '''  air56_lso_trace = (air56_trace){
    .magic = AIR56_TRACE_MAGIC, .start_ms = now, .start_cycles = DWT->CYCCNT
  };
  air56_lso_trace.active = 1;''', '''  air56_lso_trace.rows = air56_lso_trace.count = air56_lso_trace.injected_samples = 0;
  air56_lso_trace.first_fault = air56_lso_trace.fast_max = 0;
  air56_lso_trace.peak_a = air56_lso_trace.peak_b = air56_lso_trace.peak_c = 0;
  air56_lso_trace.window_max = 0;
  air56_lso_trace.start_ms = now;
  air56_lso_trace.start_cycles = DWT->CYCCNT;
  air56_lso_trace.magic = AIR56_TRACE_MAGIC;
  __DMB();
  air56_lso_trace.active = 1;''')
    s = replace(s, '    UASPEP_Poll(&aspepOverUartA);', '''    AIR56_UnoService();
    UASPEP_Poll(&aspepOverUartA);''')
    s = replace(s, '''          if (MCP_Over_UartA.txLength > 0U &&
              MCP_Over_UartA.txBuffer[MCP_Over_UartA.txLength - 1U] == MCP_CMD_OK)
          {
            air56_last_packet_ms = HAL_GetTick();
          }
''', '')
    s = replace(s, '''        TSK_MF_StopProcessing(M1);
        air56_run_started = false;
        return;''', '''        TSK_MF_StopProcessing(M1);
        air56_capture_finish(AIR56_END_TIMER, HAL_GetTick());
        air56_run_started = false;
        return;''')
    s = replace(s, '''        air56_run_started = false;
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);''', '''        air56_run_started = false;
        air56_capture_finish(AIR56_END_LINK, HAL_GetTick());
        Mci[M1].DirectCommand = MCI_NO_COMMAND;
        MCI_FaultProcessing(&Mci[M1], MC_SW_ERROR, 0);''')
    s = replace(s, '''  if ((Mci[M1].State == START || Mci[M1].State == RUN) &&
      DWT->CYCCNT - air56_begin > AIR56_LSO_FAST_CYCLES)
  {
    returnValue |= MC_DURATION;
  }''', '''  if (Mci[M1].State == START || Mci[M1].State == RUN)
  {
    if (air56_lso_trace.active)
    {
      const unsigned row = air56_lso_trace.rows;
      const uint32_t before_log = DWT->CYCCNT;
      air56_trace_cycles(&air56_lso_trace, before_log, before_log - air56_begin, returnValue);
      air56_trace_total(&air56_lso_trace, row, DWT->CYCCNT - air56_begin);
    }
    if (DWT->CYCCNT - air56_begin > AIR56_LSO_FAST_CYCLES)
    {
      returnValue |= MC_DURATION;
      if (air56_lso_trace.active && !air56_lso_trace.first_fault)
      {
        air56_lso_trace.first_fault = returnValue;
      }
    }
  }''')
    s = replace(s, '''  PWMC_GetPhaseCurrents(pwmcHandle[M1], &measured);
  if (''', '''  PWMC_GetPhaseCurrents(pwmcHandle[M1], &measured);
  if (air56_lso_trace.active && (Mci[M1].State == START || Mci[M1].State == RUN))
  {
    air56_trace_current(&air56_lso_trace, measured.a, measured.b);
  }
  if (''')
    s = replace(s, '''    ab_t measured;
    const uint32_t begin = DWT->CYCCNT;''', '''    ab_t measured;
    // Include the row publication path in every OFF qualification case.
    air56_lso_trace.rows = 0;
    air56_lso_trace.count = AIR56_TRACE_WINDOW - 1U;
    air56_lso_trace.peak_a = air56_lso_trace.peak_b = air56_lso_trace.peak_c = 0;
    air56_lso_trace.window_max = 0;
    const uint32_t begin = DWT->CYCCNT;''')
    s = replace(s, '''    PWMC_GetPhaseCurrents(&pwm._Super, &measured);
    if''', '''    PWMC_GetPhaseCurrents(&pwm._Super, &measured);
    air56_trace_current(&air56_lso_trace, measured.a, measured.b);
    if''')
    s = replace(s, '''    code |= PWMC_SetPhaseVoltage(&pwm._Super, applied);
    const uint32_t cycles''', '''    code |= PWMC_SetPhaseVoltage(&pwm._Super, applied);
    const uint32_t before_log = DWT->CYCCNT;
    air56_trace_cycles(&air56_lso_trace, before_log, before_log - begin, code);
    air56_trace_total(&air56_lso_trace, 0U, DWT->CYCCNT - begin);
    const uint32_t cycles''')
    return s + '\n#include "air56_lso_uno.inc"\n'


def setup_web(s):
    s = replace(s, "data.get('research_native_caps')==15", "data.get('research_native_caps')==2")
    s = replace(s, "ready=native and (name=='VF_FIXED' or name in ('FOC_FIXED','ADAPTIVE_PWM') and data.get('algorithm_qualification')==7)",
                "ready=False  # LSO-only capability")
    s = replace(s, 'status.get("research_native_caps")!=15', 'status.get("research_native_caps")!=2')
    s = replace(s, '''    def trial_command_check(self, cmd: str) -> tuple[bool, str]:
        if self.hv_arm.cfg.trial_gate is None:''', '''    def trial_command_check(self, cmd: str) -> tuple[bool, str]:
        page = _cmd_tokens(cmd)
        if len(page) == 3 and [p.upper() for p in page[:2]] == ["LSO", "PAGE"]:
            return (True, "ok") if page[2].isascii() and page[2].isdigit() and len(page[2]) <= 3 and int(page[2]) <= 256 else (False, "invalid LSO page")
        if self.hv_arm.cfg.trial_gate is None:''')
    s = replace(s, 'Расчётный FOC: только0–5Гц,5сек,без нагрузки; скорость оценочная.',
                'LSO-FOC: 5 Гц, 5 с, без нагрузки; скорость оценочная.')
    return replace(s, '"mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),',
                   '"mc_lso_page_hex": kv.get("mc_lso_page_hex", "-"),\n                "mc_uart_reject_hex": kv.get("mc_uart_reject_hex", "-"),')


def setup_uno(s):
    s = replace(s, 'static uint8_t g_ma_algorithm=1;', '''static uint8_t g_ma_algorithm=2;
static uint16_t g_lso_page_index;
static uint8_t g_lso_page[UV3_FRAME];
static bool g_lso_page_valid;''')
    s = replace(s, '  if(g_ma_pending)return "algorithm configuration pending";', '''  if(g_ma_pending)return "algorithm configuration pending";
  if(g_freq_cmd != 5.0f)return "LSO trial requires 5 Hz";''')
    assert s.count('if (starts_ci(cmd,"NOISE PAGE ") ||') == 2
    s = s.replace('if (starts_ci(cmd,"NOISE PAGE ") ||',
                  'if (starts_ci(cmd,"LSO PAGE ") || starts_ci(cmd,"NOISE PAGE ") ||')
    s = replace(s, '  s += " repeat_meta_hex=";', '''  s += " mc_lso_page_hex=";
  if (g_lso_page_valid) {
    for (unsigned i=0;i<UV3_FRAME;++i) {
      s += break_hex[g_lso_page[i]>>4];
      s += break_hex[g_lso_page[i]&15];
    }
  } else s += "-";
  s += " repeat_meta_hex=";''')
    s = replace(s, '      if(buf[2]==XP_WIRE){', '''      if (buf[2] == 0xB6) {
        const unsigned page = buf[3] | (unsigned)buf[4] << 8;
        if (!g_pwm_enabled && !(g_bp_status & 0x22U) && g_bp_fw_build == 2026112302U &&
            (uint32_t)(millis()-g_bp_last_rsp_ms)<300U &&
            page == g_lso_page_index && uv3_crc_ok(buf)) {
          memcpy(g_lso_page, buf, UV3_FRAME);
          g_lso_page_valid = true;
        }
        continue;
      }
      if(buf[2]==XP_WIRE){''')
    s = replace(s, '''static bool manual_command(const char *cmd) {
  if(starts_ci(cmd,"NOISE PAGE ")){''','''static bool manual_command(const char *cmd) {
  if (starts_ci(cmd,"LSO PAGE ")) {
    unsigned page; char extra;
    if (g_pwm_enabled || g_start_req || g_state!=STATE_SAFE || g_ma_pending ||
        sscanf(cmd+9,"%u %c",&page,&extra)!=1 || page>256U) return false;
    g_lso_page_index = (uint16_t)page;
    g_lso_page_valid = false;
    g_ma_op = 7; g_ma_index = 0; g_ma_value = page; g_ma_pending = true;
    return true;
  }
  if(starts_ci(cmd,"NOISE PAGE ")){''')
    return replace(s, '    if(!algo)return false;', '    if(algo!=2)return false;')


def main():
    OUT.mkdir()
    previous = json.loads((LSO / 'verification.json').read_text(encoding='utf8'))
    release.base.verify_inventory(previous['images_sha256'], LSO / 'image')
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE'):
        shutil.copytree(LSO / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release'))
    for name in ('UNOQ_MOTOR','libraries','web_hmi'):
        shutil.copytree(SUPERVISOR / name, OUT / name, ignore=shutil.ignore_patterns(
            '__pycache__', '*.log', '*.pyc', 'backups'))
    for name in ('ACIM-AIR56B2-LSO_FOC.ioc', 'generation.log', 'AIR56B2_profile.json'):
        shutil.copyfile(LSO / name, OUT / name)
    for name in ('air56_lso_capture.h','air56_lso_uno.inc'):
        shutil.copyfile(TOOLS / name, OUT / 'Inc' / name)
    for name in ('uart_v3_transport.h','sd_live_status.h'):
        shutil.copyfile(SUPERVISOR / 'nucleo/Inc' / name, OUT / 'Inc' / name)
    edit('Src/mc_tasks.c', task_changes)
    edit('Src/main.c', lambda s: replace(s, '  MX_MotorControl_Init();', '''  extern void AIR56_UnoInit(void);
  AIR56_UnoInit();
  MX_MotorControl_Init();'''))
    edit('Src/mc_interface.c', lambda s: replace(s, '''  if (!AIR56_OffDwtReady()) { return false; }''',
        '''  extern bool AIR56_UnoOwnsStart(void);
  if (!AIR56_UnoOwnsStart() || !AIR56_OffDwtReady()) { return false; }'''))
    edit('Src/mcp.c', setup_mcp)
    for file in [OUT / 'UNOQ_MOTOR/UNOQ_MOTOR.ino', OUT / 'web_hmi/server.py']:
        s = file.read_text(encoding='utf8').replace('2026112201', str(NEW[0])).replace('2026112202', str(NEW[1]))
        file.write_text(s, encoding='utf8')
    edit('UNOQ_MOTOR/research_wire.h', lambda s: replace(s, 'p[4]==15', 'p[4]==2'))
    edit('UNOQ_MOTOR/UNOQ_MOTOR.ino', setup_uno)
    edit('web_hmi/server.py', setup_web)
    protected = {}
    for name in ('preserved_inputs_sha256.json','preserved_lso_captures_sha256.json'):
        protected.update(json.loads((LSO / name).read_text(encoding='utf8')))
    for file in (LSO / 'hardware_install_r1').iterdir():
        if file.is_file(): protected[file.relative_to(ROOT).as_posix()] = release.base.sha(file)
    release.base.verify_inventory(protected, ROOT)
    (OUT / 'preserved_inputs_sha256.json').write_text(json.dumps(protected, indent=2)+'\n', encoding='utf8')
    print(OUT)


def setup_mcp(s):
    return replace(s, '    command = (uint16_t)(*packetHeader & CMD_MASK);', '''    command = (uint16_t)(*packetHeader & CMD_MASK);
    /* Uno alone sets the trial reference and owns the start lease.
       Motor Pilot still permits reads and an independent stop. */
    if (command != GET_MCP_VERSION && command != GET_DATA_ELEMENT && command != STOP_MOTOR)
    {
      pHandle->txBuffer[0] = MCP_CMD_NOK;
      pHandle->txLength = 1U;
      return;
    }''')


if __name__ == '__main__':
    main()
