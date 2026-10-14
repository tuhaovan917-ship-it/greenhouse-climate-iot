// DC 12V misting pump visualization for Wokwi Custom Chips.
// Educational DIGITAL model only; no actual 12V, pressure, flow, or motor current.
// Same logic as the existing fan12v Custom Chip:
//   VMINUS = LOW  => pump ON  (low-side MOSFET pulls drain low)
//   VMINUS = HIGH => pump OFF (MOSFET releases drain; internal pull-up)
// VPLUS is shown for the schematic but is not an electrical supply in Wokwi.

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
} pump_state_t;

static void pixel(pump_state_t *p, int x, int y,
                  uint8_t r, uint8_t g, uint8_t b) {
  if (x < 0 || y < 0 || x >= (int)p->width || y >= (int)p->height) return;
  uint32_t offset = 4u * ((uint32_t)y * p->width + (uint32_t)x);
  p->pixels[offset] = r;
  p->pixels[offset + 1] = g;
  p->pixels[offset + 2] = b;
  p->pixels[offset + 3] = 255;
}

static void rect(pump_state_t *p, int x, int y, int w, int h,
                 uint8_t r, uint8_t g, uint8_t b) {
  for (int iy = y; iy < y + h; iy++) {
    for (int ix = x; ix < x + w; ix++) {
      pixel(p, ix, iy, r, g, b);
    }
  }
}

static void disc(pump_state_t *p, int cx, int cy, int radius,
                 uint8_t r, uint8_t g, uint8_t b) {
  for (int dy = -radius; dy <= radius; dy++) {
    for (int dx = -radius; dx <= radius; dx++) {
      if (dx * dx + dy * dy <= radius * radius) {
        pixel(p, cx + dx, cy + dy, r, g, b);
      }
    }
  }
}

static void line(pump_state_t *p, int x1, int y1, int x2, int y2,
                 uint8_t r, uint8_t g, uint8_t b) {
  int dx = abs(x2 - x1), sx = x1 < x2 ? 1 : -1;
  int dy = -abs(y2 - y1), sy = y1 < y2 ? 1 : -1;
  int error = dx + dy;
  while (true) {
    pixel(p, x1, y1, r, g, b);
    if (x1 == x2 && y1 == y2) break;
    int twice = 2 * error;
    if (twice >= dy) { error += dy; x1 += sx; }
    if (twice <= dx) { error += dx; y1 += sy; }
  }
}

static void draw_pump(pump_state_t *p) {
  if (!p->pixels) return;

  rect(p, 0, 0, (int)p->width, (int)p->height, 18, 25, 33);
  int cy = (int)p->height / 2;
  int cx = (int)p->width / 2 - 26;

  // Pump body: blue motor and gray pump head.
  rect(p, cx - 44, cy - 20, 62, 40, 36, 84, 126);
  rect(p, cx - 42, cy - 18, 58, 5, 51, 138, 183);
  rect(p, cx + 15, cy - 15, 27, 30, 125, 143, 160);
  rect(p, cx + 21, cy - 10, 14, 20, 77, 96, 111);
  disc(p, cx + 27, cy, 5, 171, 191, 202);

  // Base feet and outlet pipe/nozzle.
  rect(p, cx - 37, cy + 20, 13, 6, 90, 100, 111);
  rect(p, cx + 18, cy + 20, 13, 6, 90, 100, 111);
  rect(p, cx + 42, cy - 4, 34, 8, 117, 135, 147);
  rect(p, cx + 72, cy - 7, 5, 14, 166, 185, 198);

  // Running indicator, plus visible droplets coming out of the nozzle.
  if (p->running) {
    disc(p, cx - 26, cy, 5, 54, 211, 128);
    const int motion = (int)(p->phase % 6);
    for (int i = 0; i < 3; i++) {
      int x = cx + 85 + i * 11 + motion * 2;
      int offset = (i % 2) ? 10 : -10;
      line(p, x - 6, cy, x, cy + offset, 83, 202, 255);
      disc(p, x, cy + offset, 3, 83, 202, 255);
    }
  } else {
    disc(p, cx - 26, cy, 5, 125, 135, 147);
    // Stationary nozzle: no water droplets drawn.
  }

  buffer_write(p->display, 0, p->pixels,
               4u * p->width * p->height);
}

static void on_negative_pin_change(void *user_data, pin_t pin, uint32_t value) {
  (void)pin;
  pump_state_t *p = (pump_state_t *)user_data;
  p->running = (value == LOW);
  draw_pump(p);
}

static void animate(void *user_data) {
  pump_state_t *p = (pump_state_t *)user_data;
  if (p->running) {
    p->phase = (uint8_t)((p->phase + 1) % 6);
    draw_pump(p);
  }
}

void chip_init(void) {
  pump_state_t *p = (pump_state_t *)calloc(1, sizeof(pump_state_t));
  if (!p) return;

  (void)pin_init("VPLUS", INPUT);
  p->negative_pin = pin_init("VMINUS", INPUT_PULLUP);
  p->display = framebuffer_init(&p->width, &p->height);
  p->pixels = (uint8_t *)malloc(4u * p->width * p->height);
  if (!p->pixels) return;

  p->running = (pin_read(p->negative_pin) == LOW);
  draw_pump(p);

  pin_watch_config_t watch = {
    .edge = BOTH,
    .pin_change = on_negative_pin_change,
    .user_data = p
  };
  pin_watch(p->negative_pin, &watch);

  timer_config_t timer_config = {
    .callback = animate,
    .user_data = p
  };
  timer_t timer = timer_init(&timer_config);
  timer_start(timer, 150000, true);
}
