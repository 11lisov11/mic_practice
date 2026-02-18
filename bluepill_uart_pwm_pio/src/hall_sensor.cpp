#include "hall_sensor.h"

#include <math.h>

#include "config.h"
#include "stm32f1xx_hal.h"

static uint8_t s_last_state = 0;
static int8_t s_last_sector = -1;
static float s_last_theta = 0.0f;
static float s_omega = 0.0f;
static uint32_t s_last_transition_ms = 0;
static bool s_valid = false;

static const uint8_t s_hall_seq[6] = {1, 5, 4, 6, 2, 3};

static int8_t hall_state_to_sector(uint8_t state) {
  for (int8_t i = 0; i < 6; ++i) {
    if (s_hall_seq[i] == state) return i;
  }
  return -1;
}

static uint8_t hall_read_state(void) {
  uint8_t h1 = (HAL_GPIO_ReadPin(HALL_GPIO_PORT, HALL_PIN1) != GPIO_PIN_RESET) ? 1U : 0U;
  uint8_t h2 = (HAL_GPIO_ReadPin(HALL_GPIO_PORT, HALL_PIN2) != GPIO_PIN_RESET) ? 1U : 0U;
  uint8_t h3 = (HAL_GPIO_ReadPin(HALL_GPIO_PORT, HALL_PIN3) != GPIO_PIN_RESET) ? 1U : 0U;
  return (uint8_t)((h1 << 2) | (h2 << 1) | h3);
}

void hall_sensor_init(void) {
  __HAL_RCC_GPIOB_CLK_ENABLE();

  GPIO_InitTypeDef gpio = {0};
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = HALL_GPIO_PULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Pin = HALL_PIN1 | HALL_PIN2 | HALL_PIN3;
  HAL_GPIO_Init(HALL_GPIO_PORT, &gpio);

  s_last_state = hall_read_state();
  s_last_sector = hall_state_to_sector(s_last_state);
  s_last_theta = 0.0f;
  s_omega = 0.0f;
  s_last_transition_ms = HAL_GetTick();
  s_valid = (s_last_sector >= 0);
}

bool hall_get_theta(float *theta_elec, float *omega_elec) {
  uint32_t now = HAL_GetTick();
  uint8_t state = hall_read_state();
  int8_t sector = hall_state_to_sector(state);

  if (sector < 0) {
    s_valid = false;
  }

  if (state != s_last_state && sector >= 0 && s_last_sector >= 0) {
    int8_t diff = sector - s_last_sector;
    if (diff == 1 || diff == -5) {
      // forward
      float dt = (now - s_last_transition_ms) * 0.001f;
      if (dt > 0.0f) {
        s_omega = (float)(M_PI / 3.0f) / dt;
      }
      s_last_theta = (float)sector * (float)(M_PI / 3.0f);
      s_last_transition_ms = now;
      s_valid = true;
    } else if (diff == -1 || diff == 5) {
      // reverse
      float dt = (now - s_last_transition_ms) * 0.001f;
      if (dt > 0.0f) {
        s_omega = -(float)(M_PI / 3.0f) / dt;
      }
      s_last_theta = (float)sector * (float)(M_PI / 3.0f);
      s_last_transition_ms = now;
      s_valid = true;
    } else {
      s_valid = false;
    }
  } else if (sector >= 0 && s_last_sector < 0) {
    s_last_sector = sector;
    s_last_theta = (float)sector * (float)(M_PI / 3.0f);
    s_last_transition_ms = now;
    s_valid = true;
  }

  s_last_state = state;
  s_last_sector = sector;

  if ((now - s_last_transition_ms) > HALL_TIMEOUT_MS) {
    s_valid = false;
  }

  float dt = (now - s_last_transition_ms) * 0.001f;
  float theta = s_last_theta + s_omega * dt;
  while (theta > 2.0f * (float)M_PI) theta -= 2.0f * (float)M_PI;
  while (theta < 0.0f) theta += 2.0f * (float)M_PI;

  if (theta_elec) *theta_elec = theta;
  if (omega_elec) *omega_elec = s_omega;
  return s_valid;
}
