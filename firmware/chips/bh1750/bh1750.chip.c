// BH1750 Custom Chip for Wokwi - basic educational I2C simulation.
// I2C address: 0x23 (ADDR must be low). Reading: 2 bytes, MSB first.
// Supported measurement commands: 0x10/0x11/0x13 and 0x20/0x21/0x23.
// Also accepts power on/off (0x01/0x00) and reset (0x07).
// Simplifications: no measurement delay, noise, MTreg scaling, or 0x5C address.

#include "wokwi-api.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct {
  uint32_t lux_attr;
  uint8_t mode;
  uint8_t response[2];
  uint8_t response_index;
  bool powered;
} chip_state_t;

static float clamp_lux(float lux) {
  if (!(lux >= 0.0f)) return 0.0f; // Also catches NaN.
  if (lux > 10000.0f) return 10000.0f;
  return lux;
}

static bool is_measurement_mode(uint8_t command) {
  switch (command) {
    case 0x10: // Continuous high resolution
    case 0x11: // Continuous high resolution 2
    case 0x13: // Continuous low resolution
    case 0x20: // One-time high resolution
    case 0x21: // One-time high resolution 2
    case 0x23: // One-time low resolution
      return true;
    default:
      return false;
  }
}

static bool is_one_time_mode(uint8_t mode) {
  return mode == 0x20 || mode == 0x21 || mode == 0x23;
}

static void update_reading(chip_state_t *chip) {
  const float lux = clamp_lux(attr_read_float(chip->lux_attr));
  const float factor = (chip->mode == 0x11 || chip->mode == 0x21)
                           ? 2.4f : 1.2f;
  float scaled = lux * factor;
  if (scaled > 65535.0f) scaled = 65535.0f;
  const uint16_t raw = (uint16_t)(scaled + 0.5f);
  chip->response[0] = (uint8_t)(raw >> 8);
  chip->response[1] = (uint8_t)(raw & 0xFF);
}

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = (chip_state_t *)user_data;
  (void)address; // The I2C API already filters address 0x23.

  if (read) {
    chip->response_index = 0;
    if (chip->powered && is_measurement_mode(chip->mode)) {
      update_reading(chip);
    }
  }
  return true;
}

static bool on_i2c_write(void *user_data, uint8_t command) {
  chip_state_t *chip = (chip_state_t *)user_data;

  switch (command) {
    case 0x00: // Power down
      chip->powered = false;
      chip->mode = 0;
      break;
    case 0x01: // Power on
      chip->powered = true;
      break;
    case 0x07: // Reset measurement data
      chip->response[0] = 0;
      chip->response[1] = 0;
      break;
    default:
      if (is_measurement_mode(command)) {
        chip->powered = true;
        chip->mode = command;
      }
      // Acknowledge other commands, but do not model MTreg changes.
      break;
  }
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (chip->response_index >= 2) return 0xFF;

  const uint8_t value = chip->response[chip->response_index++];
  if (chip->response_index == 2 && is_one_time_mode(chip->mode)) {
    chip->powered = false;
    chip->mode = 0;
  }
  return value;
}

void chip_init(void) {
  chip_state_t *chip = (chip_state_t *)calloc(1, sizeof(chip_state_t));
  if (chip == NULL) return;

  chip->lux_attr = attr_init_float("lux", 500.0f);

  i2c_config_t config = {
    .user_data = chip,
    .address = 0x23,
    .scl = pin_init("SCL", INPUT_PULLUP),
    .sda = pin_init("SDA", INPUT_PULLUP),
    .connect = on_i2c_connect,
    .read = on_i2c_read,
    .write = on_i2c_write,
  };
  i2c_init(&config);
}
