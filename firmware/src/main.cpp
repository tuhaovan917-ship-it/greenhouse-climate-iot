#include <Arduino.h>

unsigned long previousMillis = 0;
const unsigned long interval = 2000;

void setup() {
    Serial.begin(115200);
    Serial.println("Greenhouse IoT System");
    Serial.println("ESP32 initialized successfully!");
}

void loop() {
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;
        Serial.println("ESP32 is running...");
    }
}