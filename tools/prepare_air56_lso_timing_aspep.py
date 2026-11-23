"""Prepare the offline STM32 LSO timing / Motor Pilot candidate."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'artifacts/live_bench_20261122'
BASE = BENCH / 'air56_st_lso_off_dwt_r1'
OUT = BENCH / 'air56_st_lso_timing_aspep_r1'
MOTOR = Path('MCSDK_v6.4.2-Full/MotorControl/MCSDK')
LSO = MOTOR / 'MCLibACIM/Any'


def edit(path, update):
    path = OUT / path
    original = path.read_text(encoding='utf8')
    updated = update(original)
    assert original != updated, path
    path.write_text(updated, encoding='utf8')


def replace(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new)


def optimize_observer(s):
    s = replace(s, ' pHandle->pBVS = pBVS;\n \n PI_Float_HandleInit(pHandle->fPI);', '''  pHandle->pBVS = pBVS;
  PI_Float_HandleInit(pHandle->fPI);
  const ACIM_MotorParams_Handle_t *motor = pHandle->pACIM_MotorParams;
  const float sigma = motor->fsigma;
  const float k = pHandle->k;
  const float inv_tr = 1.0f / motor->ftaur;
  const float inv_ts = 1.0f / motor->ftaus;
  const float sigma_rest = 1.0f - sigma;
  pHandle->invRotorTime = inv_tr;
  pHandle->observerK1 = -((k - 1.0f) / sigma) * (inv_tr + inv_ts);
  pHandle->observerK3 = ((k - 1.0f) / sigma_rest) * (inv_tr - k * inv_ts);
  pHandle->observerK4Scale = ((k - 1.0f) * sigma) / sigma_rest;
  pHandle->currentDecay = -(1.0f / sigma) * (inv_ts + sigma_rest * inv_tr);
  pHandle->speedFluxCoupling = sigma_rest * (1.0f / sigma);
  pHandle->directFluxCoupling = sigma_rest / (sigma * motor->ftaur);
  pHandle->voltageGain = 1.0f / (sigma * motor->fLs);
  pHandle->speedUnitDenominator = 2.0f * (float)PI * motor->bPP;''')
    prefix = '''static inline float ACIM_LSO_WrapAngle(float angle)
{
  const float turn = 2.0f * (float)PI;
  // The running angle usually stays within one turn or crosses by a single turn.
  if (angle > -turn && angle < turn) { return angle; }
  if (angle >= turn && angle < 2.0f * turn) { return angle - turn; }
  if (angle < -turn && angle > -2.0f * turn) { return angle + turn; }
  if (angle == -turn) { return -0.0f; }
  return fmodf(angle, turn);
}

'''
    init_end = '\n#if (defined (CCMRAM) || defined(CCMRAM_ENABLED))'
    s = s.replace(init_end, '\n' + prefix + init_end, 1)
    start = s.index('  /*Local variables */')
    end = s.index('  /* Previous values', start)
    s = s[:start] + '''  const ACIM_MotorParams_Handle_t *motor = pHandle->pACIM_MotorParams;
  const float k1 = pHandle->observerK1;
  const float k3 = pHandle->observerK3;
  const float divftaur = pHandle->invRotorTime;

''' + s[end:]
    start = s.index('  float divftaur = 1/ftaur;')
    end = s.index('  /* STEP 1', start)
    s = s[:start] + '''  const float k2 = (pHandle->k - 1.0f) * fRotorElSpeed_obs_rads;
  const float k4 = pHandle->observerK4Scale * fRotorElSpeed_obs_rads;

''' + s[end:]
    for old, new in (
        ('/(2.0f*(float)PI* fPP)', '/pHandle->speedUnitDenominator'),
        ('(fFlux_dr_tmp * ftaur)', '(fFlux_dr_tmp * motor->ftaur)'),
        ('(float) fmod((double)pHandle->fRotorFlux_Angle_rad , (double) (2.0f*(float)PI))',
         'ACIM_LSO_WrapAngle(pHandle->fRotorFlux_Angle_rad)'),
        ('(((-divfsigma)*(divftaus +(fsigmadiff)*divftaur))*pHandle->fIqds_obs_A.fS_Component1)',
         '(pHandle->currentDecay*pHandle->fIqds_obs_A.fS_Component1)'),
        ('(-divfsigma*(divftaus +(fsigmadiff*divftaur))*(pHandle->fIqds_obs_A.fS_Component2))',
         '(pHandle->currentDecay*pHandle->fIqds_obs_A.fS_Component2)'),
        ('((fsigmadiff)*divfsigma*fRotorElSpeed_obs_rads)', '(pHandle->speedFluxCoupling*fRotorElSpeed_obs_rads)'),
        ('((fsigmadiff)/(fsigma*ftaur))', 'pHandle->directFluxCoupling'),
    ):
        s = replace(s, old, new)
    assert s.count('/(fsigma* fLs)') == 2
    return s.replace('/(fsigma* fLs)', '*pHandle->voltageGain')


RX_STATE = '''// USART A uses one continuously running RX channel. Only MC_Scheduler
// consumes the ring and changes ASPEP receive spans.
enum { RX_RING_SIZE = 1024U, RX_RING_MASK = RX_RING_SIZE - 1U };
static uint8_t rx_ring[RX_RING_SIZE];
static uint8_t *rx_target;
static uint16_t rx_size, rx_tail, rx_head_previous;
static uint32_t rx_last_poll, rx_last_progress;
static bool rx_resync;
static bool rx_initialized;

// At 1,843,200 baud an 8N1 sender takes 5.55 ms to lap the ring.
// The largest pending span is 130 bytes (< 0.71 ms on the wire).
// Drop ambiguous data if the 0.5 ms scheduler was absent for 4 ms.
#define RX_MAX_PAUSE (SystemCoreClock / 250U)
#define RX_PARTIAL_TIMEOUT (SystemCoreClock / 40U)
#define RX_WIRE_ERRORS (USART_ISR_ORE | USART_ISR_FE | USART_ISR_NE)
#define RX_CLEAR_ERRORS (USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NECF)

static uint16_t UASPEP_Head(const UASPEP_Handle_t *hw)
{
  return (uint16_t)((RX_RING_SIZE - LL_DMA_GetDataLength(hw->rxDMA, hw->rxChannel)) & RX_RING_MASK);
}

static void UASPEP_StartRing(UASPEP_Handle_t *hw)
{
  LL_DMA_DisableChannel(hw->rxDMA, hw->rxChannel);
  LL_DMA_ClearFlag_GI2(hw->rxDMA);
  LL_DMA_SetMode(hw->rxDMA, hw->rxChannel, LL_DMA_MODE_CIRCULAR);
  LL_DMA_SetMemoryAddress(hw->rxDMA, hw->rxChannel, (uint32_t)rx_ring);
  LL_DMA_SetDataLength(hw->rxDMA, hw->rxChannel, RX_RING_SIZE);
  LL_DMA_EnableChannel(hw->rxDMA, hw->rxChannel);
}

'''

RX_POLL = '''void UASPEP_Poll(ASPEP_Handle_t *protocol)
{
  if (!rx_initialized) { return; }
  UASPEP_Handle_t *hw = (UASPEP_Handle_t *)protocol->ASPEPIp;
  const uint32_t now = DWT->CYCCNT;
  const uint32_t elapsed = now - rx_last_poll;
  rx_last_poll = now;
  const uint16_t head = UASPEP_Head(hw);

  if (LL_DMA_IsActiveFlag_TE2(hw->rxDMA))
  {
    UASPEP_StartRing(hw);
    rx_head_previous = rx_tail = 0U;
    protocol->NewPacketAvailable = false;
    rx_resync = true;
    return;
  }
  const uint16_t arrived = (head - rx_head_previous) & RX_RING_MASK;
  const uint16_t previous_pending = (rx_head_previous - rx_tail) & RX_RING_MASK;
  rx_head_previous = head;
  if (arrived) { rx_last_progress = now; }

  if ((hw->USARTx->ISR & RX_WIRE_ERRORS) || elapsed >= RX_MAX_PAUSE ||
      arrived + previous_pending >= RX_RING_SIZE)
  {
    hw->USARTx->ICR = RX_CLEAR_ERRORS;
    protocol->NewPacketAvailable = false;
    rx_resync = true;
    rx_tail = head;
    rx_last_progress = now;
    return;
  }
  if (rx_resync)
  {
    rx_tail = head;
    // A full scheduler interval with no new bytes provides a quiet boundary.
    if (!arrived)
    {
      rx_resync = false;
      protocol->NewPacketAvailable = false;
      ASPEP_HWReset(protocol);
    }
    return;
  }

  // ASPEP arms the payload from the header callback and the next header
  // after the scheduler consumes the packet. Preserve both boundaries.
  for (unsigned span = 0; span < 2U && rx_size; ++span)
  {
    const uint16_t pending = (head - rx_tail) & RX_RING_MASK;
    if (pending < rx_size)
    {
      if ((pending || protocol->ASPEP_TL_State == WAITING_PAYLOAD) &&
          now - rx_last_progress >= RX_PARTIAL_TIMEOUT)
      {
        rx_resync = true;
        rx_tail = head;
      }
      return;
    }
    const uint16_t count = rx_size;
    __DMB();
    for (uint16_t i = 0; i < count; ++i)
    {
      rx_target[i] = rx_ring[(rx_tail + i) & RX_RING_MASK];
    }
    if ((hw->USARTx->ISR & RX_WIRE_ERRORS) ||
        LL_DMA_IsActiveFlag_TE2(hw->rxDMA) ||
        DWT->CYCCNT - now >= SystemCoreClock / 2000U)
    {
      rx_resync = true;
      return;
    }
    rx_tail = (rx_tail + count) & RX_RING_MASK;
    rx_size = 0;
    ASPEP_HWDataReceivedIT(protocol);
  }
}

'''


def configure_rx(s):
    s = replace(s, 'void UASPEP_TX_INIT(UASPEP_Handle_t *pHandle);', RX_STATE +
                'void UASPEP_TX_INIT(UASPEP_Handle_t *pHandle);')
    start = s.index('    /* DMA interrupt not used for all families */')
    end = s.index('#ifdef NULL_PTR_CHECK_USA_ASP_DRV', start)
    s = s[:start] + '''    LL_DMA_SetPeriphAddress(pHandle->rxDMA, pHandle->rxChannel,
                            (uint32_t)&pHandle->USARTx->RDR);
    pHandle->USARTx->ICR = RX_CLEAR_ERRORS;
    UASPEP_StartRing(pHandle);
    LL_USART_EnableDMAReq_RX(pHandle->USARTx);
    rx_last_poll = rx_last_progress = DWT->CYCCNT;
    rx_initialized = true;
''' + s[end:]
    start = s.index('  UASPEP_Handle_t *pHandle', s.index('void UASPEP_CFG_RECEPTION('))
    end = s.index('\n}', start)
    s = s[:start] + '''  (void)pHWHandle;
  rx_target = buffer;
  rx_size = length;''' + s[end:]
    start = s.index('  UASPEP_Handle_t *pHandle', s.index('void UASPEP_IDLE_ENABLE('))
    end = s.index('\n}', start)
    return s[:start] + '''  (void)pHWHandle;
  rx_resync = true;''' + s[end:end + 3] + '\n' + RX_POLL + s[end + 3:]


def update_irq(s):
    s = s[:s.index('  uint32_t flags;', s.index('void USART2_IRQHandler'))] + s[
        s.index('  if (0U == LL_USART_IsActiveFlag_TC'):]
    start = s.index('  uint32_t oreFlag;')
    s = s[:start] + s[s.index('  /* USER CODE BEGIN USART2_IRQHandler 1 */', start):]
    start = s.index('  /* Buffer is ready by the HW layer to be processed */')
    return s[:start] + s[s.index('  /* USER CODE BEGIN SysTick_IRQn 1 */', start):]


def place_fast_code(s):
    s = replace(s, 'LENGTH = 32K', '''LENGTH = 22K
  /* The remaining SRAM is also mapped on the core instruction/data buses. */
  CCMRAM (xrw)    : ORIGIN = 0x10000000,  LENGTH = 10K''')
    return replace(s, '  /* The program code and other data', '''  /* The linker selects the actual function sections from the -Ofast build. */
  .ccmram :
  {
    . = ALIGN(4);
    _sccmram = .;
    *(.text.ACIM_LSO_CalcAngle .text.ACIM_LSO_GetElAngle .text.PI_Float_Calc)
    *(.text.Convert_s16_to_V .text.Convert_s16_to_A .text.Convert_Rad_to16bit)
    *(.text.VBS_GetAvBusVoltage_V .text.STC_GetMecSpeedRefUnit)
    *(.text.TSK_HighFrequencyTask .text.AIR56_OffDwtService)
    *(.text.PWMC_SetPhaseVoltage .text.R3_2_GetPhaseCurrents .text.R3_2_SetADCSampPointSectX)
    *(.text.MCM_Clarke .text.MCM_Park_Generic .text.MCM_Rev_Park_Generic)
    *(.text.MCM_Trig_Functions .text.MCM_Sqrt .text.PI_Controller .text.Circle_Limitation)
    *(.text.ADC1_2_IRQHandler .text.TIM1_UP_TIM16_IRQHandler)
    *(.text.R3_2_TIMx_UP_IRQHandler .text.AIR56_LsoWatchAdc)
    . = ALIGN(4);
    _eccmram = .;
  } >CCMRAM AT> FLASH
  _siccmram = LOADADDR(.ccmram);

  /* The program code and other data''')


def copy_fast_code(s):
    return replace(s, '/* Zero fill the bss segment. */', '''/* Copy motor code to core-coupled SRAM before interrupts can run. */
  ldr r0, =_siccmram
  ldr r1, =_sccmram
  ldr r2, =_eccmram
LoopCopyCcm:
  cmp r1, r2
  bcs DoneCopyCcm
  ldr r3, [r0], #4
  str r3, [r1], #4
  b LoopCopyCcm
DoneCopyCcm:
  dsb
  isb

/* Zero fill the bss segment. */''')


def main():
    OUT.mkdir()
    for name in ('Drivers', 'Inc', 'MCSDK_v6.4.2-Full', 'Src', 'STM32CubeIDE'):
        shutil.copytree(BASE / name, OUT / name, ignore=shutil.ignore_patterns('Debug', 'Release'))
    for name in ('arm', 'ftl'):
        if (BASE / name).exists():
            shutil.copytree(BASE / name, OUT / name)
    for name in ('.extSettings', '.mxproject', 'ACIM-AIR56B2-LSO_FOC.ioc',
                 'ACIM-AIR56B2-LSO_FOC.settings', 'generation.log',
                 'AIR56B2_profile.json', 'preserved_inputs_sha256.json'):
        shutil.copyfile(BASE / name, OUT / name)
    edit('ACIM-AIR56B2-LSO_FOC.ioc', lambda s: replace(replace(
        s, 'Dma.USART2_RX.0.Mode=DMA_NORMAL', 'Dma.USART2_RX.0.Mode=DMA_CIRCULAR'),
        'NVIC.DMA2_Channel2_IRQn=true', 'NVIC.DMA2_Channel2_IRQn=false'))
    edit(LSO / 'Inc/acim_lso_foc.h', lambda s: replace(
        s, '} ACIM_LSO_Handle_t;', '''  /* Fixed motor/observer coefficients, set once by ACIM_LSO_Init. */
  float invRotorTime, observerK1, observerK3, observerK4Scale;
  float currentDecay, speedFluxCoupling, directFluxCoupling, voltageGain;
  float speedUnitDenominator;
} ACIM_LSO_Handle_t;'''))
    edit(LSO / 'Src/acim_lso_foc.c', optimize_observer)
    edit('Src/usart_aspep_driver.c', configure_rx)
    edit('Src/stm32g4xx_mc_it.c', update_irq)
    edit('STM32CubeIDE/STM32G431RBTX_FLASH.ld', place_fast_code)
    edit('STM32CubeIDE/Application/Startup/startup_stm32g431rbtx.s', copy_fast_code)
    edit('Src/main.c', lambda s: replace(replace(
        s, 'HAL_UARTEx_DisableFifoMode(&huart2)', 'HAL_UARTEx_EnableFifoMode(&huart2)'),
        '  HAL_NVIC_SetPriority(DMA2_Channel2_IRQn, 3, 0);\n  HAL_NVIC_EnableIRQ(DMA2_Channel2_IRQn);',
        '  /* USART RX circular DMA is serviced in MC_Scheduler. */'))
    edit('Src/stm32g4xx_hal_msp.c', lambda s: replace(
        s, 'hdma_usart2_rx.Init.Mode = DMA_NORMAL;', 'hdma_usart2_rx.Init.Mode = DMA_CIRCULAR;'))
    edit('Src/mc_tasks.c', lambda s: replace(replace(
        s, '/* USER CODE BEGIN MC_Scheduler 0 */', '''/* USER CODE BEGIN MC_Scheduler 0 */
  extern void UASPEP_Poll(ASPEP_Handle_t *protocol);'''),
        '    if(hMFTaskCounterM1 > 0u)', '    UASPEP_Poll(&aspepOverUartA);\n    if(hMFTaskCounterM1 > 0u)'))
    edit('Src/aspep.c', lambda s: replace(
        s, '''if (0U == pHandle->rxLengthASPEP) /* data packet with length 0 is a valid packet */
              {
                pHandle->NewPacketAvailable = true;
                /* The receiver is not reconfigure right now on purpose to avoid race condition when the packet will be
                  *  processed in ASPEP_RXframeProcess */
              }''', '''if (pHandle->rxLengthASPEP < 2U)
              {
                /* A Motor Pilot command must contain the complete MCP header. */
                pHandle->badPacketFlag = ASPEP_BAD_PACKET_SIZE;
              }'''))
    edit('Src/mcp.c', lambda s: replace(
        s, '        *pHandle->txBuffer = MCP_VERSION;', '''        pHandle->txBuffer[0] = MCP_VERSION;
        pHandle->txBuffer[1] = 0U;
        pHandle->txBuffer[2] = 0U;
        pHandle->txBuffer[3] = 0U;'''))
    print(OUT)


if __name__ == '__main__':
    main()
