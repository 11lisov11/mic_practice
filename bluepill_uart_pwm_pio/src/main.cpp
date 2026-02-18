#include "stm32f1xx_hal.h"

#include "adc_currents.h"
#include "config.h"
#include "control.h"
#include "foc_controller.h"
#include "hall_sensor.h"
#include "encoder_as5600.h"
#include "pwm_tim1.h"
#include "ipm15_io.h"
#include "proto.h"
#include "safety.h"
#if LINK_USE_SPI
#include "spi_link.h"
#else
#include "uart_link.h"
#endif

UART_HandleTypeDef huart2;
SPI_HandleTypeDef hspi1;

// Blue Pill onboard LED is on PC13 (active low)
#define STATUS_LED_PORT GPIOC
#define STATUS_LED_PIN GPIO_PIN_13
#define STATUS_LED_ACTIVE_LOW 1

static void status_led_set(bool on) {
  if (STATUS_LED_ACTIVE_LOW) {
    HAL_GPIO_WritePin(STATUS_LED_PORT, STATUS_LED_PIN, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
  } else {
    HAL_GPIO_WritePin(STATUS_LED_PORT, STATUS_LED_PIN, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
  }
}

static void status_led_tick(void) {
  static uint32_t led_last_ms = 0;
  static bool led_on = false;
  static uint32_t enc_last_ms = 0;
  static bool enc_present = false;
#if LINK_USE_SPI
  static uint32_t spi_last_cnt = 0;
#endif
  static uint32_t spi_seen_ms = 0;
  uint32_t now = HAL_GetTick();
  if (led_last_ms == 0) {
    led_last_ms = now;
  }

  const safety_state_t *st = safety_state();
  bool fault = st->fault_latched || st->estop || st->timeout_active;
  bool run_blink = st->pwm_active &&
                   (st->last_mode == MODE_SCALAR || st->last_mode == MODE_VECTOR || st->last_mode == MODE_FOC ||
                     st->last_mode == MODE_DUTY || st->last_mode == MODE_DIAG);

  // SPI activity hint: if we see completed SPI frames, blink fast for a short window.
#if LINK_USE_SPI
  uint32_t cnt = spi_link_rx_count();
  if (cnt != spi_last_cnt) {
    spi_last_cnt = cnt;
    spi_seen_ms = now;
  }
#endif

  // Encoder presence hint (does not require UNO Q link). Slow blink in SAFE if encoder reads OK.
  if ((now - enc_last_ms) >= 200U) {
    enc_last_ms = now;
#if USE_AS5600
    uint16_t raw = 0;
    enc_present = encoder_as5600_get_raw(&raw);
#else
    enc_present = false;
#endif
  }

  if (fault) {
    if (!led_on) {
      led_on = true;
      status_led_set(true);
    }
    return;
  }

  if (run_blink) {
    if ((now - led_last_ms) >= 200U) {
      led_last_ms = now;
      led_on = !led_on;
      status_led_set(led_on);
    }
    return;
  }

  if ((now - spi_seen_ms) < 500U) {
    if ((now - led_last_ms) >= 100U) {
      led_last_ms = now;
      led_on = !led_on;
      status_led_set(led_on);
    }
    return;
  }

  if (enc_present) {
    if ((now - led_last_ms) >= 1000U) {
      led_last_ms = now;
      led_on = !led_on;
      status_led_set(led_on);
    }
    return;
  }

  if (led_on) {
    led_on = false;
    status_led_set(false);
  }
}

static void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_USART2_UART_Init(void);
#if LINK_USE_SPI
static void MX_SPI1_Init(void);
#endif

int main(void) {
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
#if !LINK_USE_SPI
  MX_USART2_UART_Init();
#endif
#if LINK_USE_SPI
  MX_SPI1_Init();
#endif
  ipm15_io_init();

  pwm_tim1_init();
  adc_currents_init();
  foc_init();
  hall_sensor_init();
  encoder_as5600_init();
  safety_init();
#if LINK_USE_SPI
  spi_link_init(&hspi1);
#else
  uart_link_init(&huart2);
#endif
  control_init();

  const uint8_t boot_ping[8] = {0x5A, 0xA5, 0x5A, 0xA5, 0x5A, 0xA5, 0x5A, 0xA5};
#if LINK_USE_SPI
  uint8_t boot_rsp[FRAME_LEN] = {0};
  boot_rsp[0] = RSP_HDR0;
  boot_rsp[1] = RSP_HDR1;
  boot_rsp[RSP_OFF_CRC] = proto_crc_xor(boot_rsp);
  spi_link_send(boot_rsp, FRAME_LEN);
#else
  uart_link_send(boot_ping, sizeof(boot_ping));
#endif

  uint8_t cmd[FRAME_LEN];
  uint8_t rsp[FRAME_LEN];

  uint32_t last_ping_ms = HAL_GetTick();
  while (1) {
    uint8_t fault_code = FAULT_OK;
    int res = 0;
#if LINK_USE_SPI
    res = spi_link_poll_frame(cmd, &fault_code);
#else
    res = uart_link_poll_frame(cmd, &fault_code);
#endif
    if (res == 1) {
      safety_on_valid_cmd(cmd);
      control_update_from_cmd(cmd);
      safety_build_reply(rsp, cmd);
#if LINK_USE_SPI
      spi_link_send(rsp, FRAME_LEN);
#else
      uart_link_send(rsp, FRAME_LEN);
#endif
    } else if (res == -2) {
      // Bad CRC but full frame received: report error and reply with seq echo.
      safety_on_bad_frame(fault_code);
      safety_build_reply(rsp, cmd);
#if LINK_USE_SPI
      spi_link_send(rsp, FRAME_LEN);
#else
      uart_link_send(rsp, FRAME_LEN);
#endif
    } else if (res < 0) {
      // Ignore stray header mismatches to avoid spurious shutdowns on line noise.
    }

    uint32_t now = HAL_GetTick();
    if (safety_state()->good_cnt == 0) {
      if ((now - last_ping_ms) > 250U) {
#if LINK_USE_SPI
        spi_link_send(boot_rsp, FRAME_LEN);
#else
        uart_link_send(boot_ping, sizeof(boot_ping));
#endif
        last_ping_ms = now;
      }
    }
    control_tick();
    safety_tick();
    status_led_tick();
  }
}

extern "C" void HAL_UART_MspInit(UART_HandleTypeDef *huart) {
  if (huart->Instance == USART2) {
    __HAL_RCC_USART2_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_AFIO_REMAP_USART2_DISABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;

    gpio.Pin = GPIO_PIN_2;
    gpio.Mode = GPIO_MODE_AF_PP;
    HAL_GPIO_Init(GPIOA, &gpio);

    gpio.Pin = GPIO_PIN_3;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);
  }
}

extern "C" void HAL_SPI_MspInit(SPI_HandleTypeDef *hspi) {
  if (hspi->Instance == SPI1) {
    __HAL_RCC_SPI1_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_AFIO_REMAP_SPI1_DISABLE();

    GPIO_InitTypeDef gpio = {0};
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;

    // NSS (PA4) input
    gpio.Pin = GPIO_PIN_4;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);

    // SCK (PA5) input
    gpio.Pin = GPIO_PIN_5;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);

    // MISO (PA6) AF push-pull
    gpio.Pin = GPIO_PIN_6;
    gpio.Mode = GPIO_MODE_AF_PP;
    HAL_GPIO_Init(GPIOA, &gpio);

    // MOSI (PA7) input
    gpio.Pin = GPIO_PIN_7;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);
  }
}

static void MX_USART2_UART_Init(void) {
  huart2.Instance = USART2;
  huart2.Init.BaudRate = UART_BAUD;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  HAL_UART_Init(&huart2);
}

#if LINK_USE_SPI
static void MX_SPI1_Init(void) {
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_SLAVE;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  // Slave link is robust if we don't rely on a dedicated NSS wire.
  // We still recommend wiring NSS, but with SOFT NSS the slave will accept clocks
  // even if PA4 is left floating or not connected.
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 7;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_8;
  HAL_SPI_Init(&hspi1);
}
#endif

static void MX_GPIO_Init(void) {
  auto enable_port_clk = [](GPIO_TypeDef *port) {
    if (port == GPIOA) __HAL_RCC_GPIOA_CLK_ENABLE();
    if (port == GPIOB) __HAL_RCC_GPIOB_CLK_ENABLE();
    if (port == GPIOC) __HAL_RCC_GPIOC_CLK_ENABLE();
  };

  enable_port_clk(EM_STOP_GPIO_PORT);
  enable_port_clk(STATUS_LED_PORT);

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = EM_STOP_GPIO_PIN;
  gpio.Mode = GPIO_MODE_OUTPUT_PP;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(EM_STOP_GPIO_PORT, &gpio);

  if (BRAKE_ACTIVE_STATE) {
    HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_SET);
  } else {
    HAL_GPIO_WritePin(EM_STOP_GPIO_PORT, EM_STOP_GPIO_PIN, GPIO_PIN_RESET);
  }

  GPIO_InitTypeDef led = {0};
  led.Pin = STATUS_LED_PIN;
  led.Mode = GPIO_MODE_OUTPUT_PP;
  led.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(STATUS_LED_PORT, &led);
  status_led_set(false);

#if USE_TIM1_BKIN
  // TIM1_BKIN is fixed on PB12. Configure as input with optional pull.
  enable_port_clk(GPIOB);
  GPIO_InitTypeDef bkin = {0};
  bkin.Pin = GPIO_PIN_12;
  bkin.Mode = GPIO_MODE_INPUT;
  if (BKIN_ENABLE_PULLUP) {
    bkin.Pull = BKIN_ACTIVE_LOW ? GPIO_PULLUP : GPIO_PULLDOWN;
  } else {
    bkin.Pull = GPIO_NOPULL;
  }
  HAL_GPIO_Init(GPIOB, &bkin);
#endif
}

static void SystemClock_Config(void) {
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9; // 72 MHz
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    RCC_OscInitStruct.HSEState = RCC_HSE_OFF;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI_DIV2;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL16; // 64 MHz fallback
    HAL_RCC_OscConfig(&RCC_OscInitStruct);
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
  HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
}
