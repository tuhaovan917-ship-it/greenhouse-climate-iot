
#include <Arduino.h>
#include <Wire.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define SHT31_ADDR 0x44
#define BH1750_ADDR 0x23
#define WATER_SWITCH_PIN 32
#define FAN_PIN 18
#define PUMP_PIN 19

unsigned long previousMillis = 0;
const unsigned long interval = 2000;
bool fanOn = false;
const float FAN_TEMP_ON = 30.0f;
const float FAN_TEMP_OFF = 28.0f;
bool pumpOn = false;
const float PUMP_HUM_ON = 55.0f;
const float PUMP_HUM_OFF = 65.0f;

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


void scanI2C() {
    Serial.println("Scanning I2C devices...");

    int count = 0;

    for (uint8_t address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        uint8_t error = Wire.endTransmission();

        if (error == 0) {
            Serial.printf("I2C device found at 0x%02X\n", address);
            count++;
        }
    }

    Serial.printf("Total I2C devices: %d\n", count);
    Serial.println("--------------------");
}


bool initBH1750() {
    Wire.beginTransmission(BH1750_ADDR);
    Wire.write(0x10); // Continuous H-Resolution Mode

    if (Wire.endTransmission() != 0) {
        Serial.println("BH1750 initialization failed!");
        return false;
    }

    Serial.println("BH1750 initialized successfully!");
    return true;
}

bool readBH1750(float &lux) {
    uint8_t received = Wire.requestFrom(
        (uint8_t)BH1750_ADDR,
        (uint8_t)2
    );

    if (received != 2) {
        Serial.println("BH1750 read failed!");
        return false;
    }

    uint16_t rawLight =
        ((uint16_t)Wire.read() << 8) | Wire.read();

    lux = rawLight / 1.2f;

    return true;
}

void setup() {
    Serial.begin(115200);
    Wire.begin(SDA_PIN, SCL_PIN);
    pinMode(WATER_SWITCH_PIN, INPUT_PULLDOWN);
    pinMode(FAN_PIN, OUTPUT);
    digitalWrite(FAN_PIN, LOW);
    pinMode(PUMP_PIN, OUTPUT);
    digitalWrite(PUMP_PIN, LOW);
    initBH1750();
    delay(500);
    scanI2C();
    Serial.println("Greenhouse IoT System");
    Serial.println("SHT31 Sensor Test");
}


void loop() {
    // FAILSAFE: Kiem tra muc nuoc lien tuc
    if (digitalRead(WATER_SWITCH_PIN) == LOW && pumpOn) {
        pumpOn = false;
        digitalWrite(PUMP_PIN, LOW);

        Serial.println(
            "FAILSAFE: WATER_LOW - Pump stopped immediately!"
        );
    }
    
    unsigned long currentMillis = millis();

    // Doc cac cam bien moi 2 giay
    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;

        // 1. Doc SHT31
        float temperature;
        float humidity;

        Serial.println("===== GREENHOUSE SENSOR DATA =====");
        
        bool sht31Ok = readSHT31(temperature, humidity);

        if (sht31Ok) {
            Serial.printf("Temperature: %.2f C\n", temperature);
            Serial.printf("Humidity: %.2f %%\n", humidity);

            // AUTO: Dieu khien quat theo nhiet do
            if (temperature >= FAN_TEMP_ON) {
                fanOn = true;
            } 
            else if (temperature <= FAN_TEMP_OFF) {
                fanOn = false;
            }

            digitalWrite(FAN_PIN, fanOn ? HIGH : LOW);

        } else {
            Serial.println("Failed to read SHT31!");

            // Tam tat quat khi loi cam bien trong bai kiem thu
            fanOn = false;
            digitalWrite(FAN_PIN, LOW);
        }

        // 2. Doc BH1750
        float lightLux;

        if (readBH1750(lightLux)) {
            Serial.printf("Light: %.2f lux\n", lightLux);
        } else {
            Serial.println("Failed to read BH1750!");
        }
        
        // 3. Doc trang thai muc nuoc
        bool waterOk = digitalRead(WATER_SWITCH_PIN) == HIGH;

        if (waterOk) {
            Serial.println("Water Level: WATER_OK");
        } else {
            Serial.println("Water Level: WATER_LOW");
        }
        
        // 4. Kiem tra dieu khien quat
        Serial.printf(
            "Ventilation Fan: %s\n",
            fanOn ? "ON" : "OFF"
        );

        // 5. AUTO: Dieu khien bom theo do am
        // Uu tien dieu kien an toan

        if (!waterOk || !sht31Ok) {
            pumpOn = false;
        }
        else if (humidity <= PUMP_HUM_ON) {
            pumpOn = true;
        }
        else if (humidity >= PUMP_HUM_OFF) {
            pumpOn = false;
        }

        digitalWrite(PUMP_PIN, pumpOn ? HIGH : LOW);

        Serial.printf(
            "Misting Pump: %s\n",
            pumpOn ? "ON" : "OFF"
        );

        if (!waterOk) {
            Serial.println("WARNING: Water level low - Pump disabled!");
        }

        if (!sht31Ok) {
            Serial.println("WARNING: SHT31 error - Pump disabled!");
        }

        Serial.println("==================================");
        Serial.println();
    }
}