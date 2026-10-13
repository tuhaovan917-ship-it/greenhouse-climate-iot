
#include <Arduino.h>
#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define SHT31_ADDR 0x44

unsigned long previousMillis = 0;
const unsigned long interval = 2000;

// Tinh CRC-8 cua 2 byte du lieu
uint8_t calculateCRC(const uint8_t *data) {
    uint8_t crc = 0xFF;

    for (int i = 0; i < 2; i++) {
        crc ^= data[i];

        for (int bit = 0; bit < 8; bit++) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0x31;
            } else {
                crc <<= 1;
            }
        }
    }

    return crc;
}

// Doc nhiet do va do am SHT31
bool readSHT31(float &temperature, float &humidity) {
    Wire.beginTransmission(SHT31_ADDR);
    Wire.write(0x24);
    Wire.write(0x00);

    if (Wire.endTransmission() != 0) {
        Serial.println("SHT31: Command failed!");
        return false;
    }

    delay(20);

    if (Wire.requestFrom((uint8_t)SHT31_ADDR, (uint8_t)6) != 6) {
        Serial.println("SHT31: Invalid response length!");
        return false;
    }

    uint8_t data[6];

    for (int i = 0; i < 6; i++) {
        data[i] = Wire.read();
    }

    if (calculateCRC(&data[0]) != data[2] ||
        calculateCRC(&data[3]) != data[5]) {
        Serial.println("SHT31: CRC error!");
        return false;
    }

    uint16_t rawTemp = (data[0] << 8) | data[1];
    uint16_t rawHum = (data[3] << 8) | data[4];

    temperature = -45.0f + 175.0f * rawTemp / 65535.0f;
    humidity = 100.0f * rawHum / 65535.0f;

    return true;
}

void setup() {
    Serial.begin(115200);
    Wire.begin(SDA_PIN, SCL_PIN);

    Serial.println("Greenhouse IoT System");
    Serial.println("SHT31 Sensor Test");
}

void loop() {
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;

        float temperature;
        float humidity;

        if (readSHT31(temperature, humidity)) {
            Serial.printf("Temperature: %.2f C\n", temperature);
            Serial.printf("Humidity: %.2f %%\n", humidity);
            Serial.println("--------------------");
        } else {
            Serial.println("Failed to read SHT31!");
        }
    }
}
