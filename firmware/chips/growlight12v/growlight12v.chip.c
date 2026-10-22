
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
    bool lightOn;
} growlight_state_t;

// Ve mot diem anh
static void pixel(growlight_state_t *s, int x, int y,
                  uint8_t r, uint8_t g, uint8_t b) {
    if (x < 0 || y < 0 ||
        x >= (int)s->width || y >= (int)s->height) {
        return;
    }

    uint32_t pos = 4u * ((uint32_t)y * s->width + x);

    s->pixels[pos] = r;
    s->pixels[pos + 1] = g;
    s->pixels[pos + 2] = b;
    s->pixels[pos + 3] = 255;
}

// Ve hinh chu nhat
static void rect(growlight_state_t *s, int x, int y,
                 int w, int h,
                 uint8_t r, uint8_t g, uint8_t b) {
    for (int iy = y; iy < y + h; iy++) {
        for (int ix = x; ix < x + w; ix++) {
            pixel(s, ix, iy, r, g, b);
        }
    }
}

// Ve hinh tron
static void disc(growlight_state_t *s, int cx, int cy,
                 int radius,
                 uint8_t r, uint8_t g, uint8_t b) {
    for (int dy = -radius; dy <= radius; dy++) {
        for (int dx = -radius; dx <= radius; dx++) {
            if (dx * dx + dy * dy <= radius * radius) {
                pixel(s, cx + dx, cy + dy, r, g, b);
            }
        }
    }
}

// Ve den LED Grow Light
static void draw_light(growlight_state_t *s) {
    if (!s->pixels) return;

    // Nen toi
    rect(s, 0, 0, s->width, s->height, 18, 25, 33);

    // Khung den
    rect(s, 10, 10, s->width - 20,
         s->height - 20, 65, 75, 90);

    rect(s, 15, 15, s->width - 30,
         s->height - 30, 25, 30, 45);

    // Ba hang LED
    for (int row = 0; row < 3; row++) {
        for (int col = 0; col < 8; col++) {
            int x = 25 + col * 20;
            int y = 25 + row * 19;

            if (s->lightOn) {
                // Vung phat sang
                disc(s, x, y, 8, 105, 40, 115);

                if ((row + col) % 2 == 0) {
                    disc(s, x, y, 5, 255, 65, 175);
                } else {
                    disc(s, x, y, 5, 95, 115, 255);
                }

                disc(s, x, y, 2, 245, 235, 255);
            } else {
                // LED dang tat
                disc(s, x, y, 5, 75, 75, 90);
                disc(s, x, y, 2, 45, 45, 55);
            }
        }
    }

    buffer_write(s->display, 0, s->pixels,
                 4u * s->width * s->height);
}

// Cap nhat khi MOSFET thay doi
static void on_pin_change(void *user_data,
                          pin_t pin, uint32_t value) {
    (void)pin;

    growlight_state_t *s =
        (growlight_state_t *)user_data;

    s->lightOn = (value == LOW);
    draw_light(s);
}

void chip_init(void) {
    growlight_state_t *s =
        (growlight_state_t *)calloc(
            1, sizeof(growlight_state_t)
        );

    if (!s) return;

    // Mo hinh so, khong mo phong nguon 12V that
    (void)pin_init("VPLUS", INPUT);

    s->negative_pin =
        pin_init("VMINUS", INPUT_PULLUP);

    s->display =
        framebuffer_init(&s->width, &s->height);

    s->pixels = (uint8_t *)malloc(
        4u * s->width * s->height
    );

    if (!s->pixels) return;

    s->lightOn =
        (pin_read(s->negative_pin) == LOW);

    draw_light(s);

    const pin_watch_config_t watch = {
        .edge = BOTH,
        .pin_change = on_pin_change,
        .user_data = s
    };

    pin_watch(s->negative_pin, &watch);
}
