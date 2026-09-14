#include "stm32g4xx_hal.h"

#if !MIC_ISOLATED_LOGIC_DIAGNOSTIC
#error "This image is exclusively for an isolated Nucleo without any power stage."
#endif

// Logic analyzer only. No UART command can start this image. Never connect an IPM.
static constexpr uint32_t START_KEY = 0x504D5744U;
static constexpr uint32_t BURST_MS = 300U;
static constexpr uint32_t PWM_HZ = 16000U;
static constexpr uint32_t DEADTIME_NS = 1350U;
static constexpr uint32_t PWM_PINS_A = GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10;
static constexpr uint32_t PWM_PINS_B = GPIO_PIN_0 | GPIO_PIN_1;
static constexpr uint32_t OUTPUTS = TIM_CCER_CC1E | TIM_CCER_CC1NE |
    TIM_CCER_CC2E | TIM_CCER_CC2NE | TIM_CCER_CC3E | TIM_CCER_CC3NE;

extern "C" {
volatile uint32_t diag_identity = 0x47343144U;
volatile uint32_t diag_request = 0U;
volatile uint32_t diag_state = 0U;  // 0 boot, 1 ready, 2 running, 3 done, 4 fault
volatile uint32_t diag_timer_hz = 0U;
volatile uint32_t diag_arr = 0U;
volatile uint32_t diag_dtg = 0U;
}

static TIM_HandleTypeDef pwm = {};
static TIM_HandleTypeDef limit_timer = {};
static IWDG_HandleTypeDef watchdog = {};

static void pins_low() {
    HAL_GPIO_WritePin(GPIOA, PWM_PINS_A, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOB, PWM_PINS_B, GPIO_PIN_RESET);
    GPIO_InitTypeDef gpio = {};
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_PULLDOWN;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pin = PWM_PINS_A;
    HAL_GPIO_Init(GPIOA, &gpio);
    gpio.Pin = PWM_PINS_B;
    HAL_GPIO_Init(GPIOB, &gpio);
}

static void outputs_off() {
    TIM1->BDTR &= ~TIM_BDTR_MOE;
    TIM1->CCER &= ~OUTPUTS;
    TIM1->CR1 &= ~TIM_CR1_CEN;
    TIM2->CR1 &= ~TIM_CR1_CEN;
    TIM2->DIER = 0U;
    pins_low();
}

[[noreturn]] static void fail() {
    outputs_off();
    diag_state = 4U;
    while (true) {}  // Independent watchdog resets to an unarmed boot.
}

static void checked(HAL_StatusTypeDef status) {
    if (status != HAL_OK) fail();
}

static void clock_init() {
    checked(HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST));
    RCC_OscInitTypeDef osc = {};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM = RCC_PLLM_DIV4;
    osc.PLL.PLLN = 85U;
    osc.PLL.PLLP = RCC_PLLP_DIV2;
    osc.PLL.PLLQ = RCC_PLLQ_DIV2;
    osc.PLL.PLLR = RCC_PLLR_DIV2;
    checked(HAL_RCC_OscConfig(&osc));
    RCC_ClkInitTypeDef clocks = {};
    clocks.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                      RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clocks.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clocks.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clocks.APB1CLKDivider = RCC_HCLK_DIV1;
    clocks.APB2CLKDivider = RCC_HCLK_DIV1;
    checked(HAL_RCC_ClockConfig(&clocks, FLASH_LATENCY_4));
}

static void timer_init() {
    diag_timer_hz = HAL_RCC_GetPCLK2Freq();
    if (diag_timer_hz != 170000000U) fail();
    // Same carrier, CKD and DTG quantization as the current MCSDK timer setup.
    diag_arr = diag_timer_hz / (2U * PWM_HZ);
    diag_dtg = ((diag_timer_hz / 1000000U) * DEADTIME_NS / 1000U) / 2U;
    if (diag_dtg > 127U) fail();
    pwm.Instance = TIM1;
    pwm.Init.CounterMode = TIM_COUNTERMODE_CENTERALIGNED1;
    pwm.Init.Period = diag_arr;
    pwm.Init.ClockDivision = TIM_CLOCKDIVISION_DIV2;
    pwm.Init.RepetitionCounter = 1U;
    pwm.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
    checked(HAL_TIM_PWM_Init(&pwm));
    TIM_OC_InitTypeDef oc = {};
    oc.OCMode = TIM_OCMODE_PWM1;
    oc.OCPolarity = TIM_OCPOLARITY_HIGH;
    oc.OCNPolarity = TIM_OCNPOLARITY_HIGH;
    oc.OCIdleState = TIM_OCIDLESTATE_RESET;
    oc.OCNIdleState = TIM_OCNIDLESTATE_RESET;
    oc.Pulse = diag_arr / 5U;
    checked(HAL_TIM_PWM_ConfigChannel(&pwm, &oc, TIM_CHANNEL_1));
    oc.Pulse = diag_arr / 2U;
    checked(HAL_TIM_PWM_ConfigChannel(&pwm, &oc, TIM_CHANNEL_2));
    oc.Pulse = diag_arr * 4U / 5U;
    checked(HAL_TIM_PWM_ConfigChannel(&pwm, &oc, TIM_CHANNEL_3));
    TIM_BreakDeadTimeConfigTypeDef bd = {};
    bd.OffStateRunMode = TIM_OSSR_ENABLE;
    bd.OffStateIDLEMode = TIM_OSSI_ENABLE;
    bd.DeadTime = diag_dtg;
    bd.BreakState = TIM_BREAK_DISABLE;  // No power stage or BKIN source in this isolated test.
    bd.Break2State = TIM_BREAK2_DISABLE;
    bd.AutomaticOutput = TIM_AUTOMATICOUTPUT_DISABLE;
    checked(HAL_TIMEx_ConfigBreakDeadTime(&pwm, &bd));

    limit_timer.Instance = TIM2;
    limit_timer.Init.Prescaler = HAL_RCC_GetPCLK1Freq() / 1000000U - 1U;
    limit_timer.Init.CounterMode = TIM_COUNTERMODE_UP;
    limit_timer.Init.Period = BURST_MS * 1000U - 1U;
    limit_timer.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    checked(HAL_TIM_Base_Init(&limit_timer));
    TIM2->CR1 |= TIM_CR1_OPM;
    HAL_NVIC_SetPriority(TIM2_IRQn, 0U, 0U);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);
    outputs_off();
}

static void start_once() {
    GPIO_InitTypeDef gpio = {};
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_PULLDOWN;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Alternate = GPIO_AF6_TIM1;
    gpio.Pin = PWM_PINS_A;
    HAL_GPIO_Init(GPIOA, &gpio);
    gpio.Pin = PWM_PINS_B;
    HAL_GPIO_Init(GPIOB, &gpio);
    TIM1->EGR = TIM_EGR_UG;
    TIM1->CNT = 0U;
    TIM1->SR = 0U;
    TIM2->CNT = 0U;
    TIM2->SR = 0U;
    diag_state = 2U;
    checked(HAL_TIM_Base_Start_IT(&limit_timer));
    TIM1->CCER |= OUTPUTS;
    TIM1->CR1 |= TIM_CR1_CEN;
    TIM1->BDTR |= TIM_BDTR_MOE;
}

extern "C" void SysTick_Handler() { HAL_IncTick(); }
extern "C" void TIM2_IRQHandler() {
    if ((TIM2->SR & TIM_SR_UIF) != 0U) {
        TIM2->SR = 0U;
        outputs_off();
        diag_state = 3U;
    }
}
extern "C" void HardFault_Handler() { fail(); }
extern "C" void NMI_Handler() { fail(); }

int main() {
    HAL_Init();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_TIM1_CLK_ENABLE();
    __HAL_RCC_TIM2_CLK_ENABLE();
    outputs_off();
    if (diag_identity != 0x47343144U) fail();
    clock_init();
    watchdog.Instance = IWDG;
    watchdog.Init.Prescaler = IWDG_PRESCALER_32;
    watchdog.Init.Reload = 249U;
    watchdog.Init.Window = IWDG_WINDOW_DISABLE;
    checked(HAL_IWDG_Init(&watchdog));
    timer_init();
    diag_request = 0U;
    diag_state = 1U;
    uint32_t started_ms = 0U;
    while (true) {
        checked(HAL_IWDG_Refresh(&watchdog));
        if (diag_state == 1U && diag_request == START_KEY) {
            diag_request = 0U;
            started_ms = HAL_GetTick();
            start_once();
        }
        if (diag_state == 2U && (uint32_t)(HAL_GetTick() - started_ms) >= BURST_MS + 5U) {
            outputs_off();
            diag_state = 4U;  // Backup deadline fired: hardware stop did not complete.
        }
    }
}
