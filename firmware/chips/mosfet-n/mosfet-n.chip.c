// Digital low-side N-MOSFET model for Wokwi Custom Chip (educational simulation).
// HIGH on GATE -> DRAIN pulled LOW (switch ON).
// LOW on GATE  -> DRAIN high-impedance (switch OFF).
// SOURCE is a schematic pin: wire it to GND in diagram.json.
// This is NOT a model of voltage, current, heat or motor power. Do not wire 12V to an ESP32 GPIO.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdlib.h>

typedef struct {
  pin_t gate;
  pin_t drain;
} chip_state_t;

static void set_switch_state(chip_state_t *chip, uint32_t gate_level) {
  // In the ON state, imitate a conducting low-side MOSFET by pulling DRAIN low.
  // In the OFF state, release DRAIN: the fan model's INPUT_PULLUP pulls it high.
  pin_mode(chip->drain, gate_level == HIGH ? OUTPUT_LOW : INPUT);
}

static void on_gate_change(void *user_data, pin_t pin, uint32_t value) {
  (void)pin;
  set_switch_state((chip_state_t *)user_data, value);
}

void chip_init(void) {
  chip_state_t *chip = (chip_state_t *)calloc(1, sizeof(chip_state_t));
  if (chip == NULL) return;

  chip->gate = pin_init("GATE", INPUT_PULLDOWN);
  chip->drain = pin_init("DRAIN", INPUT);
  (void)pin_init("SOURCE", INPUT);

  set_switch_state(chip, pin_read(chip->gate));

  const pin_watch_config_t watcher = {
    .edge = BOTH,
    .pin_change = on_gate_change,
    .user_data = chip,
  };
  pin_watch(chip->gate, &watcher);
}
