#include "encoder_as5600.h"

#include <math.h>

#include "config.h"
#include "stm32f1xx_hal.h"

#if USE_AS5600

#define AS5600_REG_ANGLE_H 0x0E

static I2C_HandleTypeDef s_hi2c2;
static bool s_ready = false;
static uint16_t s_last_raw = 0;
static uint32_t s_last_ok_ms = 0;
static uint32_t s_last_recover_ms = 0;
static uint8_t s_fail_streak = 0;

extern "C" void HAL_I2C_MspInit(I2C_HandleTypeDef *hi2c) {
  if (hi2c->Instance != I2C2) return;
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_I2C2_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = GPIO_PIN_10 | GPIO_PIN_11;
  gpio.Mode = GPIO_MODE_AF_OD;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOB, &gpio);
}

static void i2c2_bus_recover(void) {
  // Best-effort I2C bus recovery for "stuck low" conditions.
  // This is common after noise on long wires. We keep it simple:
  // toggle SCL ~9 times while SDA released, then generate a STOP.
  __HAL_RCC_GPIOB_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Pin = GPIO_PIN_10 | GPIO_PIN_11;
  gpio.Mode = GPIO_MODE_OUTPUT_OD;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOB, &gpio);

  // Release lines (OD high = float). External pull-ups must bring them high.
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10 | GPIO_PIN_11, GPIO_PIN_SET);
  HAL_Delay(1);

  for (int i = 0; i < 9; ++i) {
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, GPIO_PIN_RESET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, GPIO_PIN_SET);
    HAL_Delay(1);
  }

  // STOP: SDA low while SCL high, then release SDA high.
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11, GPIO_PIN_RESET);
  HAL_Delay(1);
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11, GPIO_PIN_SET);
  HAL_Delay(1);
}

static bool as5600_read_raw(uint16_t *raw) {
  uint8_t buf[2] = {0};
  uint16_t addr = (AS5600_I2C_ADDR << 1);
  if (HAL_I2C_Mem_Read(&s_hi2c2, addr, AS5600_REG_ANGLE_H, I2C_MEMADD_SIZE_8BIT, buf, 2, 2) != HAL_OK) {
    return false;
  }
  uint16_t val = ((uint16_t)(buf[0] & 0x0F) << 8) | buf[1];
  *raw = val;
  s_last_raw = val;
  s_last_ok_ms = HAL_GetTick();
  return true;
}

static bool as5600_try_recover(void) {
  uint32_t now = HAL_GetTick();
  if ((now - s_last_recover_ms) < 200U) {
    return false;
  }
  s_last_recover_ms = now;

  // Reset the peripheral and try a bus clear sequence.
  (void)HAL_I2C_DeInit(&s_hi2c2);
  __HAL_RCC_I2C2_FORCE_RESET();
  HAL_Delay(1);
  __HAL_RCC_I2C2_RELEASE_RESET();
  HAL_Delay(1);
  i2c2_bus_recover();

  if (HAL_I2C_Init(&s_hi2c2) != HAL_OK) {
    return false;
  }
  uint16_t raw = 0;
  if (as5600_read_raw(&raw)) {
    s_ready = true;
    s_fail_streak = 0;
    return true;
  }
  return false;
}

bool encoder_as5600_init(void) {
  s_hi2c2.Instance = I2C2;
  s_hi2c2.Init.ClockSpeed = AS5600_I2C_SPEED;
  s_hi2c2.Init.DutyCycle = I2C_DUTYCYCLE_2;
  s_hi2c2.Init.OwnAddress1 = 0;
  s_hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  s_hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  s_hi2c2.Init.OwnAddress2 = 0;
  s_hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  s_hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&s_hi2c2) != HAL_OK) {
    s_ready = false;
    return false;
  }

  uint16_t raw = 0;
  s_ready = as5600_read_raw(&raw);
  s_fail_streak = 0;
  return s_ready;
}

bool encoder_as5600_get_raw(uint16_t *raw) {
  if (!s_ready) {
    (void)as5600_try_recover();
    if (raw) *raw = s_last_raw;
    return s_ready;
  }
  uint16_t val = 0;
  if (!as5600_read_raw(&val)) {
    if (s_fail_streak < 255) {
      s_fail_streak++;
    }
    if (s_fail_streak >= 3) {
      (void)as5600_try_recover();
    }
    if (raw) *raw = s_last_raw;
    return false;
  }
  s_fail_streak = 0;
  if (raw) *raw = val;
  return true;
}

bool encoder_as5600_get_theta(float *theta_rad) {
  uint16_t raw = 0;
  if (!encoder_as5600_get_raw(&raw)) {
    return false;
  }
  float mech = ((float)raw / 4096.0f) * (2.0f * 3.1415926f);
  float theta = mech * (float)AS5600_POLE_PAIRS;
  while (theta >= 2.0f * 3.1415926f) theta -= 2.0f * 3.1415926f;
  while (theta < 0.0f) theta += 2.0f * 3.1415926f;
  if (theta_rad) *theta_rad = theta;
  return true;
}

#else

bool encoder_as5600_init(void) { return false; }
bool encoder_as5600_get_raw(uint16_t *raw) {
  if (raw) *raw = 0;
  return false;
}
bool encoder_as5600_get_theta(float *theta_rad) {
  if (theta_rad) *theta_rad = 0.0f;
  return false;
}

#endif
