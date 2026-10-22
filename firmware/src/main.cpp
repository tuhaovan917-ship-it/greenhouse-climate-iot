#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <math.h>
#include <Preferences.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define SHT31_ADDR 0x44
#define BH1750_ADDR 0x23
#define WATER_SWITCH_PIN 32
#define FAN_PIN 18
#define PUMP_PIN 19
#define GROWLIGHT_PIN 23

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

String mqttLastCommandId = "";
String mqttLastCommandResult = "";
String mqttLastCommandReason = "";

unsigned long previousMillis = 0;
const unsigned long interval = 2000;

// Thu lai ket noi theo chu ky, khong block bang while/retry lien tuc.
const unsigned long WIFI_RETRY_INTERVAL_MS = 10000;
const unsigned long MQTT_RETRY_INTERVAL_MS = 5000;
unsigned long lastWifiRetryMs = 0;
unsigned long lastMqttRetryMs = 0;


bool fanOn = false;
float FAN_TEMP_ON = 30.0f;
float FAN_TEMP_OFF = 28.0f;

bool pumpOn = false;
float PUMP_HUM_ON = 55.0f;
float PUMP_HUM_OFF = 65.0f;

bool growLightOn = false;
float GROWLIGHT_LUX_ON = 300.0f;
float GROWLIGHT_LUX_OFF = 700.0f;

struct StoredAutoThresholds {
    uint32_t version;
    float tempOnC;
    float tempOffC;
    float humidityOnPct;
    float humidityOffPct;
    float lightOnLux;
    float lightOffLux;
};

bool validStoredThresholds(const StoredAutoThresholds& c) {
    return c.version == 1 &&
           isfinite(c.tempOnC) &&
           isfinite(c.tempOffC) &&
           isfinite(c.humidityOnPct) &&
           isfinite(c.humidityOffPct) &&
           isfinite(c.lightOnLux) &&
           isfinite(c.lightOffLux) &&
           c.tempOnC > c.tempOffC &&
           c.humidityOnPct >= 0.0f &&
           c.humidityOnPct < c.humidityOffPct &&
           c.humidityOffPct <= 100.0f &&
           c.lightOnLux >= 0.0f &&
           c.lightOnLux < c.lightOffLux;
}

bool saveAutoThresholds() {
    StoredAutoThresholds c = {
        1,
        FAN_TEMP_ON,
        FAN_TEMP_OFF,
        PUMP_HUM_ON,
        PUMP_HUM_OFF,
        GROWLIGHT_LUX_ON,
        GROWLIGHT_LUX_OFF
    };

    Preferences prefs;

    if (!prefs.begin("greenhouse", false)) {
        Serial.println("[NVS] Cannot open storage!");
        return false;
    }

    size_t written = prefs.putBytes(
        "auto_cfg_v1", &c, sizeof(c)
    );

    prefs.end();

    bool ok = written == sizeof(c);

    Serial.println(
        ok ? "[NVS] AUTO thresholds saved!"
           : "[NVS] Failed to save thresholds!"
    );

    return ok;
}

void loadAutoThresholds() {
    Preferences prefs;

    if (!prefs.begin("greenhouse", false)) {
        Serial.println("[NVS] Using default thresholds");
        return;
    }

    StoredAutoThresholds c = {};

    size_t bytesRead = 0;

    if (prefs.getBytesLength("auto_cfg_v1") == sizeof(c)) {
        bytesRead = prefs.getBytes(
            "auto_cfg_v1", &c, sizeof(c)
        );
    }

    prefs.end();

    if (bytesRead != sizeof(c) ||
        !validStoredThresholds(c)) {
        Serial.println("[NVS] Using default thresholds");
        return;
    }

    FAN_TEMP_ON = c.tempOnC;
    FAN_TEMP_OFF = c.tempOffC;
    PUMP_HUM_ON = c.humidityOnPct;
    PUMP_HUM_OFF = c.humidityOffPct;
    GROWLIGHT_LUX_ON = c.lightOnLux;
    GROWLIGHT_LUX_OFF = c.lightOffLux;

    Serial.printf(
        "[NVS] Loaded: Temp %.1f/%.1f, "
        "Humidity %.1f/%.1f, Light %.1f/%.1f\n",
        FAN_TEMP_ON, FAN_TEMP_OFF,
        PUMP_HUM_ON, PUMP_HUM_OFF,
        GROWLIGHT_LUX_ON, GROWLIGHT_LUX_OFF
    );
}

// Che do dieu khien he thong
enum ControlMode {
    MODE_AUTO,
    MODE_MANUAL
};

// Mac dinh khoi dong o che do AUTO
ControlMode currentMode = MODE_AUTO;

// Trang thai thiet bi trong che do MANUAL
bool manualFanOn = false;
bool manualPumpOn = false;
bool manualGrowLightOn = false;

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

// Xu ly lenh chuyen che do AUTO / MANUAL

void handleSerialMode() {
    static String command = "";

    while (Serial.available() > 0) {
        char c = Serial.read();

        if (c == '\n' || c == '\r') {
            command.trim();
            command.toUpperCase();

            if (command.length() == 0) {
                command = "";
                continue;
            }

            if (command == "AUTO") {
                currentMode = MODE_AUTO;

                manualFanOn = false;
                manualPumpOn = false;
                manualGrowLightOn = false;

                fanOn = false;
                pumpOn = false;
                growLightOn = false;

                digitalWrite(FAN_PIN, LOW);
                digitalWrite(PUMP_PIN, LOW);
                digitalWrite(GROWLIGHT_PIN, LOW);

                Serial.println("Control Mode: AUTO");
            }
            else if (command == "MANUAL") {
                currentMode = MODE_MANUAL;

                manualFanOn = false;
                manualPumpOn = false;
                manualGrowLightOn = false;

                fanOn = false;
                pumpOn = false;
                growLightOn = false;

                digitalWrite(FAN_PIN, LOW);
                digitalWrite(PUMP_PIN, LOW);
                digitalWrite(GROWLIGHT_PIN, LOW);

                Serial.println("Control Mode: MANUAL");
                Serial.println("All devices: OFF");
            }
            else if (currentMode != MODE_MANUAL) {
                Serial.println(
                    "Please switch to MANUAL mode first!"
                );
            }
            else if (command == "FAN ON" ||
                     command == "FAN OFF") {
                manualFanOn = (command == "FAN ON");
                fanOn = manualFanOn;

                digitalWrite(
                    FAN_PIN,
                    fanOn ? HIGH : LOW
                );

                Serial.printf(
                    "Manual Fan: %s\n",
                    fanOn ? "ON" : "OFF"
                );
            }
            else if (command == "PUMP ON" ||
                     command == "PUMP OFF") {
                bool requestedOn = (command == "PUMP ON");
                bool waterOk =
                    digitalRead(WATER_SWITCH_PIN) == HIGH;

                if (requestedOn && !waterOk) {
                    manualPumpOn = false;
                    pumpOn = false;

                    Serial.println(
                        "WARNING: WATER_LOW - Pump blocked!"
                    );
                }
                else {
                    manualPumpOn = requestedOn;
                    pumpOn = manualPumpOn;
                }

                digitalWrite(
                    PUMP_PIN,
                    pumpOn ? HIGH : LOW
                );

                Serial.printf(
                    "Manual Pump: %s\n",
                    pumpOn ? "ON" : "OFF"
                );
            }
            else if (command == "LIGHT ON" ||
                     command == "LIGHT OFF") {
                manualGrowLightOn =
                    (command == "LIGHT ON");

                growLightOn = manualGrowLightOn;

                digitalWrite(
                    GROWLIGHT_PIN,
                    growLightOn ? HIGH : LOW
                );

                Serial.printf(
                    "Manual Grow Light: %s\n",
                    growLightOn ? "ON" : "OFF"
                );
            }
            else {
                Serial.println("Unknown command!");
            }

            command = "";
        }
        else if (command.length() < 32) {
            command += c;
        }
    }
}

void testWokwiNetwork() {
    Serial.println("[NET] Connecting to Wokwi-GUEST...");

    WiFi.mode(WIFI_STA);
    WiFi.begin("Wokwi-GUEST", "", 6);

    unsigned long startTime = millis();

    while (WiFi.status() != WL_CONNECTED &&
           millis() - startTime < 10000) {
        delay(250);
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[NET] WiFi connection FAILED");
        return;
    }

    Serial.print("[NET] WiFi connected! IP: ");
    Serial.println(WiFi.localIP());

    WiFiClient testClient;

    if (testClient.connect("host.wokwi.internal", 1883)) {
        Serial.println("[NET] MQTT broker TCP connection OK!");
        testClient.stop();
    } else {
        Serial.println("[NET] MQTT broker TCP connection FAILED");
    }
}


void publishDeviceState() {
    if (!mqttClient.connected()) {
        return;
    }

    JsonDocument doc;

    doc["deviceId"] = "greenhouse-01";
    doc["mode"] = currentMode == MODE_AUTO ? "AUTO" : "MANUAL";

    doc["fan"] = fanOn;
    doc["mist"] = pumpOn;
    doc["lamp"] = growLightOn;

    bool waterOk = digitalRead(WATER_SWITCH_PIN) == HIGH;
    doc["failsafeActive"] = !waterOk;

    if (mqttLastCommandId.length() > 0) {
        doc["lastCommandId"] = mqttLastCommandId;
        doc["lastCommandResult"] = mqttLastCommandResult;

        if (mqttLastCommandReason.length() > 0) {
            doc["reason"] = mqttLastCommandReason;
        }
    } else {
        doc["lastCommandId"] = nullptr;
        doc["lastCommandResult"] = nullptr;
    }

    char payload[256];

    if (measureJson(doc) >= sizeof(payload)) {
        Serial.println("[MQTT] State payload too large");
        return;
    }

    serializeJson(doc, payload, sizeof(payload));

    bool sent = mqttClient.publish(
        "greenhouse/01/state",
        payload,
        true
    );

    if (sent) {
        Serial.print("[MQTT] State published: ");
        Serial.println(payload);
    } else {
        Serial.println("[MQTT] State publish failed");
    }
}


void handleMqttCommand(byte* payload, unsigned int length) {
    JsonDocument doc;

    if (deserializeJson(doc, payload, length)) {
        Serial.println("[MQTT] Invalid command JSON");
        return;
    }

    String commandId = doc["commandId"].as<String>();
    String device = doc["device"].as<String>();

    if (commandId.length() == 0 || !doc["on"].is<bool>()) {
        Serial.println("[MQTT] Invalid command payload");
        return;
    }

    bool requestedOn = doc["on"].as<bool>();

    // Khong thuc thi lai lenh gan nhat neu MQTT gui trung.
    if (commandId == mqttLastCommandId) {
        Serial.println("[MQTT] Duplicate command ignored");
        publishDeviceState();
        return;
    }

    mqttLastCommandId = commandId;
    mqttLastCommandResult = "REJECTED";
    mqttLastCommandReason = "";

    // Kiem tra thiet bi hop le.
    if (device != "fan" &&
        device != "mist" &&
        device != "lamp") {
        mqttLastCommandReason = "INVALID_DEVICE";
    }

    // FAILSAFE luon uu tien cao nhat.
    else if (device == "mist" &&
             requestedOn &&
             digitalRead(WATER_SWITCH_PIN) != HIGH) {
        manualPumpOn = false;
        pumpOn = false;
        digitalWrite(PUMP_PIN, LOW);

        mqttLastCommandReason = "NO_WATER";
    }

    // Chi cho phep dieu khien truc tiep trong MANUAL.
    else if (currentMode != MODE_MANUAL) {
        mqttLastCommandReason = "NOT_MANUAL_MODE";
    }

    // Thuc hien lenh.
    else {
        if (device == "fan") {
            manualFanOn = requestedOn;
            fanOn = requestedOn;
            digitalWrite(FAN_PIN, fanOn ? HIGH : LOW);
        }
        else if (device == "mist") {
            manualPumpOn = requestedOn;
            pumpOn = requestedOn;
            digitalWrite(PUMP_PIN, pumpOn ? HIGH : LOW);
        }
        else if (device == "lamp") {
            manualGrowLightOn = requestedOn;
            growLightOn = requestedOn;
            digitalWrite(
                GROWLIGHT_PIN,
                growLightOn ? HIGH : LOW
            );
        }

        mqttLastCommandResult = "APPLIED";
    }

    Serial.printf(
        "[MQTT] Command %s: %s %s -> %s\n",
        commandId.c_str(),
        device.c_str(),
        requestedOn ? "ON" : "OFF",
        mqttLastCommandResult.c_str()
    );

    if (mqttLastCommandReason.length() > 0) {
        Serial.printf(
            "[MQTT] Reason: %s\n",
            mqttLastCommandReason.c_str()
        );
    }

    // Gui phan hoi thuc te ve Backend.
    publishDeviceState();
}

bool readMqttNumber(JsonVariantConst value, float &result) {
    if (!value.is<int>() &&
        !value.is<long>() &&
        !value.is<float>() &&
        !value.is<double>()) {
        return false;
    }

    result = value.as<float>();
    return isfinite(result);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, "greenhouse/01/command") == 0) {
        handleMqttCommand(payload, length);
        return;
    }

    if (strcmp(topic, "greenhouse/01/config") != 0) {
        return;
    }

    JsonDocument doc;

    DeserializationError error =
        deserializeJson(doc, payload, length);

    if (error) {
        Serial.println("[MQTT] Invalid config JSON");
        return;
    }

    String requestedMode = doc["mode"].as<String>();
    requestedMode.toUpperCase();

    if (requestedMode != "AUTO" &&
        requestedMode != "MANUAL") {
        Serial.println("[MQTT] Invalid control mode");
        return;
    }

    float tempOnC, tempOffC;
    float humidityOnPct, humidityOffPct;
    float lightOnLux, lightOffLux;

    // Doc day du 6 nguong tu MQTT config.
    bool validNumbers =
        readMqttNumber(doc["tempOnC"], tempOnC) &&
        readMqttNumber(doc["tempOffC"], tempOffC) &&
        readMqttNumber(doc["humidityOnPct"], humidityOnPct) &&
        readMqttNumber(doc["humidityOffPct"], humidityOffPct) &&
        readMqttNumber(doc["lightOnLux"], lightOnLux) &&
        readMqttNumber(doc["lightOffLux"], lightOffLux);

    if (!validNumbers) {
        Serial.println("[CONFIG] Invalid or missing thresholds!");
        return;
    }

    // Kiem tra hysteresis va gioi han cam bien.
    bool validThresholds =
        tempOnC > tempOffC &&
        humidityOnPct < humidityOffPct &&
        lightOnLux < lightOffLux &&
        humidityOnPct >= 0.0f &&
        humidityOffPct <= 100.0f &&
        lightOnLux >= 0.0f &&
        lightOffLux >= 0.0f;

    if (!validThresholds) {
        Serial.println("[CONFIG] Threshold validation failed!");
        return;
    }

    // So sanh voi gia tri cu TRUOC khi cap nhat.
    bool thresholdsChanged =
        FAN_TEMP_ON != tempOnC ||
        FAN_TEMP_OFF != tempOffC ||
        PUMP_HUM_ON != humidityOnPct ||
        PUMP_HUM_OFF != humidityOffPct ||
        GROWLIGHT_LUX_ON != lightOnLux ||
        GROWLIGHT_LUX_OFF != lightOffLux;

    // Chi cap nhat sau khi tat ca gia tri deu hop le.
    FAN_TEMP_ON = tempOnC;
    FAN_TEMP_OFF = tempOffC;

    PUMP_HUM_ON = humidityOnPct;
    PUMP_HUM_OFF = humidityOffPct;

    GROWLIGHT_LUX_ON = lightOnLux;
    GROWLIGHT_LUX_OFF = lightOffLux;

    if (thresholdsChanged) {
        saveAutoThresholds();
    }
    Serial.printf(
        "[CONFIG] AUTO thresholds applied: "
        "Temp %.1f/%.1f C, "
        "Humidity %.1f/%.1f %%, "
        "Light %.1f/%.1f lux\n",
        FAN_TEMP_ON,
        FAN_TEMP_OFF,
        PUMP_HUM_ON,
        PUMP_HUM_OFF,
        GROWLIGHT_LUX_ON,
        GROWLIGHT_LUX_OFF
    );

    ControlMode nextMode =
        requestedMode == "AUTO" ? MODE_AUTO : MODE_MANUAL;

    if (nextMode != currentMode) {
        currentMode = nextMode;

        // Chuyen che do an toan: tat thiet bi truoc.
        manualFanOn = false;
        manualPumpOn = false;
        manualGrowLightOn = false;

        fanOn = false;
        pumpOn = false;
        growLightOn = false;

        digitalWrite(FAN_PIN, LOW);
        digitalWrite(PUMP_PIN, LOW);
        digitalWrite(GROWLIGHT_PIN, LOW);
    }

    Serial.printf(
        "[MQTT] Control mode applied: %s\n",
        requestedMode.c_str()
    );

    publishDeviceState();
}

void testMqttConnection() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[MQTT] WiFi not connected!");
        return;
    }

    mqttClient.setServer("host.wokwi.internal", 1883);
    mqttClient.setCallback(onMqttMessage);
    mqttClient.setBufferSize(512);
    // Gioi han thoi gian cho phan hoi MQTT CONNACK.
    mqttClient.setSocketTimeout(2);

    Serial.println("[MQTT] Connecting to broker...");

    bool connected = mqttClient.connect(
        "esp32-greenhouse-01-test",
        "greenhouse/01/status",
        1,
        true,
        "{\"online\":false}"
    );

    if (connected) {
        Serial.println("[MQTT] Connected successfully!");

        bool subscribed = mqttClient.subscribe(
            "greenhouse/01/config",
            1
        );

        bool commandSubscribed = mqttClient.subscribe(
            "greenhouse/01/command",
            1
        );

        Serial.println(
            commandSubscribed
                ? "[MQTT] Subscribed to command!"
                : "[MQTT] Command subscription failed!"
        );

        Serial.println(
            subscribed
                ? "[MQTT] Subscribed to config!"
                : "[MQTT] Config subscription failed!"
        );

        // Neu thieu topic, dong ket noi de thu lai sau 5 giay.
        if (!subscribed || !commandSubscribed) {
            Serial.println("[MQTT] Retry scheduled because subscribe failed");
            mqttClient.disconnect();
            return;
        }

        bool sent = mqttClient.publish(
            "greenhouse/01/status",
            "{\"online\":true}",
            true
        );

        Serial.println(
            sent
                ? "[MQTT] Online status published!"
                : "[MQTT] Online status publish failed!"
        );

        publishDeviceState();
    } else {
        Serial.printf(
            "[MQTT] Connection failed! Code: %d\n",
            mqttClient.state()
        );
    }
}

// Quan ly ket noi trong loop: tiep tuc thu lai neu mat mang/broker.
// Khong duoc dung while (!mqttClient.connected()) vi se lam dung doc cam bien.
void maintainConnectivity() {
    unsigned long now = millis();

    if (WiFi.status() != WL_CONNECTED) {
        if (mqttClient.connected()) {
            mqttClient.disconnect();
        }

        if (now - lastWifiRetryMs >= WIFI_RETRY_INTERVAL_MS) {
            lastWifiRetryMs = now;
            Serial.println("[NET] WiFi lost - attempting reconnect...");
            // WiFi.begin() bat dau ket noi, khong cho trong while.
            WiFi.begin("Wokwi-GUEST", "", 6);
        }
        return;
    }

    if (mqttClient.connected()) {
        mqttClient.loop();
        return;
    }

    if (now - lastMqttRetryMs >= MQTT_RETRY_INTERVAL_MS) {
        lastMqttRetryMs = now;
        Serial.println("[MQTT] Disconnected - attempting reconnect...");
        // Ham nay da subscribe lai command/config, publish online/state.
        testMqttConnection();
    }
}

void publishTelemetry(
    bool sht31Ok,
    float temperature,
    float humidity,
    bool bh1750Ok,
    float lightLux,
    bool waterOk
) {
    if (!mqttClient.connected()) {
        Serial.println("[MQTT] Cannot publish: disconnected");
        return;
    }

    JsonDocument doc;

    doc["deviceId"] = "greenhouse-01";

    if (sht31Ok) {
        doc["temperatureC"] = temperature;
        doc["humidityPct"] = humidity;
    } else {
        doc["temperatureC"] = nullptr;
        doc["humidityPct"] = nullptr;
    }

    if (bh1750Ok) {
        doc["lightLux"] = lightLux;
    } else {
        doc["lightLux"] = nullptr;
    }

    doc["waterOk"] = waterOk;

    char payload[256];

    size_t required = measureJson(doc);
    if (required >= sizeof(payload)) {
        Serial.println("[MQTT] Telemetry payload too large");
        return;
    }

    serializeJson(doc, payload, sizeof(payload));

    bool sent = mqttClient.publish(
        "greenhouse/01/telemetry",
        payload
    );

    if (sent) {
        Serial.print("[MQTT] Telemetry published: ");
        Serial.println(payload);
    } else {
        Serial.println("[MQTT] Telemetry publish failed");
    }
}

void setup() {
    Serial.begin(115200);
    delay(100);
    loadAutoThresholds();
    Wire.begin(SDA_PIN, SCL_PIN);
    pinMode(WATER_SWITCH_PIN, INPUT_PULLDOWN);
    pinMode(FAN_PIN, OUTPUT);
    digitalWrite(FAN_PIN, LOW);
    pinMode(PUMP_PIN, OUTPUT);
    digitalWrite(PUMP_PIN, LOW);
    pinMode(GROWLIGHT_PIN, OUTPUT);
    digitalWrite(GROWLIGHT_PIN, LOW);
    initBH1750();
    delay(500);
    scanI2C();
    testWokwiNetwork();
    testMqttConnection();
    lastWifiRetryMs = millis();
    lastMqttRetryMs = millis();
    Serial.println("Greenhouse IoT System");
    Serial.println("SHT31 Sensor Test");
    Serial.println("Control Mode: AUTO");
}


void loop() {
    // Nhan lenh AUTO / MANUAL
    handleSerialMode();

    // FAILSAFE: Kiem tra muc nuoc lien tuc
    if (digitalRead(WATER_SWITCH_PIN) == LOW &&
        (pumpOn || manualPumpOn)) {

        pumpOn = false;
        manualPumpOn = false;
        digitalWrite(PUMP_PIN, LOW);

        Serial.println(
            "FAILSAFE: WATER_LOW - Pump stopped immediately!"
        );
    }

    // Kiem tra failsafe truoc khi thu ket noi (MQTT connect co the cho ngan).
    maintainConnectivity();

    unsigned long currentMillis = millis();

    // Doc cac cam bien moi 2 giay
    if (currentMillis - previousMillis >= interval) {
        previousMillis = currentMillis;

        // 1. Doc SHT31
        float temperature = NAN;
        float humidity = NAN;

        Serial.println("===== GREENHOUSE SENSOR DATA =====");

        bool sht31Ok = readSHT31(temperature, humidity);

        if (sht31Ok) {
            Serial.printf("Temperature: %.2f C\n", temperature);
            Serial.printf("Humidity: %.2f %%\n", humidity);
        } else {
            Serial.println("Failed to read SHT31!");
        }

        // Dieu khien quat theo che do
        if (currentMode == MODE_AUTO) {
            if (!sht31Ok) {
                fanOn = false;
            }
            else if (temperature >= FAN_TEMP_ON) {
                fanOn = true;
            }
            else if (temperature <= FAN_TEMP_OFF) {
                fanOn = false;
            }
        }
        else {
            fanOn = manualFanOn;
        }

        digitalWrite(FAN_PIN, fanOn ? HIGH : LOW);

        // 2. Doc BH1750
        float lightLux = 0.0f;
        bool bh1750Ok = readBH1750(lightLux);

        if (bh1750Ok) {
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

        // 5. Dieu khien bom va bao ve muc nuoc
        if (!waterOk) {
            pumpOn = false;
            manualPumpOn = false;
        }
        else if (currentMode == MODE_MANUAL) {
            pumpOn = manualPumpOn;
        }
        else if (!sht31Ok) {
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

        if (!sht31Ok && currentMode == MODE_AUTO) {
            Serial.println("WARNING: SHT31 error - Pump disabled!");
        }

        // 6. Dieu khien Grow Light
        if (currentMode == MODE_MANUAL) {
            growLightOn = manualGrowLightOn;
        }
        else if (!bh1750Ok) {
            growLightOn = false;
        }
        else if (lightLux <= GROWLIGHT_LUX_ON) {
            growLightOn = true;
        }
        else if (lightLux >= GROWLIGHT_LUX_OFF) {
            growLightOn = false;
        }

        // Trong vung tre: giu nguyen trang thai
        digitalWrite(
            GROWLIGHT_PIN,
            growLightOn ? HIGH : LOW
        );

        Serial.printf(
            "Grow Light: %s\n",
            growLightOn ? "ON" : "OFF"
        );

        if (!bh1750Ok && currentMode == MODE_AUTO) {
            Serial.println(
                "WARNING: BH1750 error - Grow Light disabled!"
            );
        }

        publishTelemetry(
            sht31Ok,
            temperature,
            humidity,
            bh1750Ok,
            lightLux,
            waterOk
        );

        publishDeviceState();

        Serial.println("==================================");
        Serial.println();
    }
}
