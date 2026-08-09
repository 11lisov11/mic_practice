#include "stm32g4xx_hal.h"

#include <string.h>

#include "bridge_controller.h"
#include "config.h"
#include "proto.h"
#include "uart_link.h"

UART_HandleTypeDef huart1;

static void system_clock_config(void);
static void gpio_init(void);
static void usart1_init(void);
static void error_handler(void);

static void status_led_set(bool on) {
#if NUCLEO_BRIDGE_STATUS_LED
  HAL_GPIO_WritePin(STATUS_LED_PORT, STATUS_LED_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
#else
  (void)on;
#endif
}

static void status_led_tick(uint32_t now_ms) {
#if NUCLEO_BRIDGE_STATUS_LED
  static uint32_t last_toggle_ms = 0;
  static bool led_on = false;
  const bridge_state_t *state = bridge_controller_state();
  if (state->fault_latched) {
    status_led_set(true);
    return;
  }
  if (!state->link_ok) {
    status_led_set(false);
    led_on = false;
    return;
  }
  const uint32_t interval_ms = state->enabled ? 100U : 500U;
  if ((uint32_t)(now_ms - last_toggle_ms) >= interval_ms) {
    last_toggle_ms = now_ms;
    led_on = !led_on;
    status_led_set(led_on);
  }
#else
  (void)now_ms;
#endif
}

static void make_safe_command(uint8_t *cmd, uint8_t seq) {
  memset(cmd, 0, FRAME_LEN);
  cmd[CMD_OFF_HDR0] = CMD_HDR0;
  cmd[CMD_OFF_HDR1] = CMD_HDR1;
  cmd[CMD_OFF_VER] = MIC_PROTOCOL_VERSION;
  cmd[CMD_OFF_MODE] = MODE_OFF;
  cmd[CMD_OFF_SEQ] = seq;
  cmd[CMD_OFF_CRC] = proto_crc_xor(cmd);
}

int main(void) {
  HAL_Init();
  system_clock_config();
  gpio_init();
  usart1_init();
  bridge_controller_init();
  uart_link_init(&huart1);

  const uint8_t boot_ping[8] = {0x5A, 0xA5, 0x5A, 0xA5, 0x5A, 0xA5, 0x5A, 0xA5};
  uint8_t command[FRAME_LEN] = {};
  uint8_t reply[FRAME_LEN] = {};
  make_safe_command(command, 0U);
  uint32_t last_boot_ping_ms = 0;

  while (true) {
    uint8_t parse_fault = FAULT_OK;
    const int result = uart_link_poll_frame(command, &parse_fault);
    const uint16_t uart_errors = uart_link_take_rx_error_count();
    if (uart_errors != 0U) {
      bridge_controller_note_bad_frames(uart_errors);
    }

    if (result == 1) {
      bridge_controller_on_valid_command(command, HAL_GetTick());
      bridge_controller_build_reply(reply, command);
      if (!uart_link_send(reply, FRAME_LEN)) {
        bridge_controller_note_bad_frame();
      }
    } else if (result == -2) {
      const uint8_t seq = command[CMD_OFF_SEQ];
      (void)parse_fault;
      bridge_controller_note_bad_frame();
      make_safe_command(command, seq);
      bridge_controller_build_reply(reply, command);
      (void)uart_link_send(reply, FRAME_LEN);
    }

    const uint32_t now_ms = HAL_GetTick();
    bridge_controller_tick(now_ms);
    status_led_tick(now_ms);
    if (bridge_controller_state()->good_count == 0U &&
        (uint32_t)(now_ms - last_boot_ping_ms) >= BOOT_PING_INTERVAL_MS) {
      last_boot_ping_ms = now_ms;
      (void)uart_link_send(boot_ping, sizeof(boot_ping));
    }
  }
}

extern "C" void HAL_UART_MspInit(UART_HandleTypeDef *huart) {
  if (huart->Instance != USART1) {
    return;
  }

  __HAL_RCC_USART1_CLK_ENABLE();
#if NUCLEO_UART_USE_STLINK_VCP
  __HAL_RCC_GPIOC_CLK_ENABLE();
#else
  __HAL_RCC_GPIOB_CLK_ENABLE();
#endif

  GPIO_InitTypeDef gpio = {};
#if NUCLEO_UART_USE_STLINK_VCP
  // MB1367 default solder-bridge routing: PC4=USART1_TX, PC5=USART1_RX.
  gpio.Pin = GPIO_PIN_4 | GPIO_PIN_5;
#else
  gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;
#endif
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLUP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF7_USART1;
#if NUCLEO_UART_USE_STLINK_VCP
  HAL_GPIO_Init(GPIOC, &gpio);
#else
  HAL_GPIO_Init(GPIOB, &gpio);
#endif

  // The diagnostic control benchmark owns priority 0. UART remains prompt but
  // cannot stretch the measured controller execution pulse.
  HAL_NVIC_SetPriority(USART1_IRQn, 2U, 0U);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

static void usart1_init(void) {
  huart1.Instance = USART1;
  huart1.Init.BaudRate = UART_BAUD;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  huart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  huart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart1) != HAL_OK) {
    error_handler();
  }
}

static void gpio_init(void) {
#if NUCLEO_BRIDGE_STATUS_LED
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef led = {};
  led.Pin = STATUS_LED_PIN;
  led.Mode = GPIO_MODE_OUTPUT_PP;
  led.Pull = GPIO_NOPULL;
  led.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(STATUS_LED_PORT, &led);
  status_led_set(false);
#endif
}

static void system_clock_config(void) {
#if NUCLEO_MOTOR_CLOCK_170MHZ
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST) != HAL_OK) {
    error_handler();
  }

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
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    error_handler();
  }

  RCC_ClkInitTypeDef clock = {};
  clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                    RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_4) != HAL_OK) {
    error_handler();
  }
#else
  RCC_OscInitTypeDef osc = {};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  osc.HSIState = RCC_HSI_ON;
  osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  osc.PLL.PLLState = RCC_PLL_OFF;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    error_handler();
  }

  RCC_ClkInitTypeDef clock = {};
  clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                    RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV1;
  clock.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_0) != HAL_OK) {
    error_handler();
  }
#endif
}

static void error_handler(void) {
  __disable_irq();
  while (true) {
    status_led_set(true);
  }
}
