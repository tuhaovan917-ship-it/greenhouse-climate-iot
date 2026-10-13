// SHT31 Custom Chip (Wokwi) - educational I2C simulation
// Simulates SHT31 at I2C address 0x44, single-shot measurements,
// status read, and CRC-8. It does not simulate conversion delays,
// electrical characteristics, or every SHT31 command.

#include "wokwi-api.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

typedef struct {
  uint32_t temperature_attr;
  uint32_t humidity_attr;
  uint8_t command_bytes[2];
  uint8_t command_count;
  uint8_t response[6];
  uint8_t response_length;
  uint8_t response_index;
} chip_state_t;

static uint8_t crc8(const uint8_t *data) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < 2; i++) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; bit++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

static float clamp(float value, float low, float high) {
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

static void make_measurement(chip_state_t *chip) {
  const float temperature = clamp(attr_read_float(chip->temperature_attr), -40.0f, 125.0f);
  const float humidity = clamp(attr_read_float(chip->humidity_attr), 0.0f, 100.0f);

  const uint16_t t = (uint16_t)(((temperature + 45.0f) * 65535.0f / 175.0f) + 0.5f);
  const uint16_t h = (uint16_t)((humidity * 65535.0f / 100.0f) + 0.5f);

  chip->response[0] = (uint8_t)(t >> 8);
  chip->response[1] = (uint8_t)t;
  chip->response[2] = crc8(&chip->response[0]);
  chip->response[3] = (uint8_t)(h >> 8);
  chip->response[4] = (uint8_t)h;
  chip->response[5] = crc8(&chip->response[3]);
  chip->response_length = 6;
  chip->response_index = 0;
}

static void make_status(chip_state_t *chip) {
  chip->response[0] = 0;
  chip->response[1] = 0;
  chip->response[2] = crc8(chip->response);
  chip->response_length = 3;
  chip->response_index = 0;
}

static bool on_i2c_connect(void *user_data, uint32_t address, bool read) {
  chip_state_t *chip = (chip_state_t *)user_data;
  (void)address;
  if (read) {
    chip->response_index = 0;
  } else {
    chip->command_count = 0;
  }
  return true;
}

static bool on_i2c_write(void *user_data, uint8_t byte) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (chip->command_count < 2) {
    chip->command_bytes[chip->command_count++] = byte;
  }
  if (chip->command_count == 2) {
    const uint16_t command = ((uint16_t)chip->command_bytes[0] << 8) | chip->command_bytes[1];
    chip->response_length = 0;
    chip->response_index = 0;
    switch (command) {
      case 0x2400: case 0x240B: case 0x2416:
      case 0x2C06: case 0x2C0D: case 0x2C10:
        make_measurement(chip);
        break;
      case 0xF32D:
        make_status(chip);
        break;
      case 0x30A2: // Soft reset
      case 0x3041: // Clear status
        break;
      default:
        break;
    }
    chip->command_count = 0;
  }
  return true;
}

static uint8_t on_i2c_read(void *user_data) {
  chip_state_t *chip = (chip_state_t *)user_data;
  if (chip->response_index < chip->response_length) {
    return chip->response[chip->response_index++];
  }
  return 0xFF;
}

void chip_init(void) {
  chip_state_t *chip = (chip_state_t *)calloc(1, sizeof(chip_state_t));
  if (!chip) return;

  chip->temperature_attr = attr_init_float("temperature", 28.0f);
  chip->humidity_attr = attr_init_float("humidity", 60.0f);

  i2c_config_t config = {
    .user_data = chip,
    .address = 0x44,
    .scl = pin_init("SCL", INPUT_PULLUP),
    .sda = pin_init("SDA", INPUT_PULLUP),
    .connect = on_i2c_connect,
    .read = on_i2c_read,
    .write = on_i2c_write,
  };
  i2c_init(&config);
}
