// Fan DC 12V (logical visualization) for Wokwi Custom Chips
// MIT License. Demo only: digital switching state, NOT an electrical 12V motor model.
// VPLUS is a schematic supply terminal; no analog voltage/current is simulated.
// VMINUS represents a switched low-side terminal: LOW -> fan ON; HIGH -> fan OFF.
// A MOSFET *digital* simulation must drive this terminal. Never wire a real 12V
// supply to an ESP32 GPIO.

#include "wokwi-api.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef struct {
  pin_t negative_pin;
  buffer_t display;
  uint32_t width;
  uint32_t height;
  uint8_t *pixels;
  uint8_t phase;
  bool running;
} fan_state_t;

static void paint_pixel(fan_state_t *fan, int x, int y,
                        uint8_t r, uint8_t g, uint8_t b) {
  if (x < 0 || y < 0 || x >= (int)fan->width || y >= (int)fan->height) return;
  uint32_t pos = 4u * ((uint32_t)y * fan->width + (uint32_t)x);
  fan->pixels[pos + 0] = r;
  fan->pixels[pos + 1] = g;
  fan->pixels[pos + 2] = b;
  fan->pixels[pos + 3] = 255;
}

static void disc(fan_state_t *fan, int x, int y, int radius,
                 uint8_t r, uint8_t g, uint8_t b) {
  for (int dy = -radius; dy <= radius; dy++) {
    for (int dx = -radius; dx <= radius; dx++) {
      if (dx * dx + dy * dy <= radius * radius) {
        paint_pixel(fan, x + dx, y + dy, r, g, b);
      }
    }
  }
}

static void draw_fan(fan_state_t *fan) {
  if (!fan->pixels) return;
  for (uint32_t y = 0; y < fan->height; y++) {
    for (uint32_t x = 0; x < fan->width; x++) {
      paint_pixel(fan, (int)x, (int)y, 18, 25, 33);
    }
  }

  const int cx = (int)fan->width / 2;
  const int cy = (int)fan->height / 2;
  const int8_t c[12] = {100, 87, 50, 0, -50, -87, -100, -87, -50, 0, 50, 87};
  const int8_t s[12] = {0, 50, 87, 100, 87, 50, 0, -50, -87, -100, -87, -50};
  const uint8_t blade_r = fan->running ? 44 : 106;
  const uint8_t blade_g = fan->running ? 194 : 116;
  const uint8_t blade_b = fan->running ? 110 : 126;

  // Circular housing/ring, drawn as pixels around two squared radii.
  for (int y = -35; y <= 35; y++) {
    for (int x = -35; x <= 35; x++) {
      int rr = x * x + y * y;
      if (rr >= 32 * 32 && rr <= 34 * 34) {
        paint_pixel(fan, cx + x, cy + y, 112, 136, 153);
      }
    }
  }

  for (int blade = 0; blade < 3; blade++) {
    const int p = (fan->phase + 4 * blade) % 12;
    for (int radius = 10; radius <= 24; radius += 2) {
      disc(fan, cx + radius * c[p] / 100, cy + radius * s[p] / 100,
           6, blade_r, blade_g, blade_b);
    }
  }
  disc(fan, cx, cy, 7, 210, 217, 228);
  disc(fan, cx, cy, 3, 46, 55, 68);

  buffer_write(fan->display, 0, fan->pixels, 4u * fan->width * fan->height);
}

static void on_negative_pin_change(void *user_data, pin_t pin, uint32_t value) {
  (void)pin;
  fan_state_t *fan = (fan_state_t *)user_data;
  fan->running = (value == LOW);
  draw_fan(fan);
}

static void animate(void *user_data) {
  fan_state_t *fan = (fan_state_t *)user_data;
  if (fan->running) {
    fan->phase = (fan->phase + 1) % 12;
    draw_fan(fan);
  }
}

void chip_init(void) {
  fan_state_t *fan = (fan_state_t *)calloc(1, sizeof(fan_state_t));
  if (!fan) return;

  (void)pin_init("VPLUS", INPUT);
  fan->negative_pin = pin_init("VMINUS", INPUT_PULLUP);
  fan->display = framebuffer_init(&fan->width, &fan->height);
  fan->pixels = (uint8_t *)malloc(4u * fan->width * fan->height);
  if (!fan->pixels) return;

  fan->running = (pin_read(fan->negative_pin) == LOW);
  draw_fan(fan);

  pin_watch_config_t watch = {
    .edge = BOTH,
    .pin_change = on_negative_pin_change,
    .user_data = fan
  };
  pin_watch(fan->negative_pin, &watch);

  timer_config_t timer_config = {
    .callback = animate,
    .user_data = fan
  };
  timer_t timer = timer_init(&timer_config);
  timer_start(timer, 125000, true);
}
