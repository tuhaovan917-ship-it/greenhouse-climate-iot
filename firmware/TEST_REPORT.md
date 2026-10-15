
# Firmware Test Report

## Project
Greenhouse Climate IoT

## Environment
- MCU: ESP32
- Framework: Arduino
- Build: PlatformIO
- Simulator: Wokwi

## Tested Components
- SHT31: Temperature and Humidity
- BH1750: Light Intensity
- Water Level Switch
- DC Ventilation Fan
- DC Misting Pump
- LED Grow Light

## Functional Test Results

| Test Case | Expected Result | Status |
|---|---|---|
| Light = 200 lux | Grow Light ON | PASS |
| Light = 900 lux | Grow Light OFF | PASS |
| Temperature = 33 C | Fan ON | PASS |
| Temperature = 27 C | Fan OFF | PASS |
| Humidity = 50%, Water OK | Pump ON | PASS |
| Water Level LOW | Pump OFF | PASS |
| SHT31 Fault Simulation | Fan and Pump OFF | PASS |
| BH1750 Fault Simulation | Grow Light OFF | PASS |

## Safety Features
- Water-level failsafe for misting pump
- Sensor error handling
- Hysteresis control for fan, pump and grow light
- Outputs initialized to OFF during startup

## Conclusion
The local ESP32 control functions have passed
the simulated functional tests on Wokwi.

Physical hardware validation and system integration
are outside the scope of these test results.

## Manual Control Functional Tests

### Test 1: Manual Fan Control
- FAN ON: PASS
- FAN OFF: PASS
- Fan state matches Wokwi simulation: PASS

### Test 2: Manual Misting Pump Control
- PUMP ON with WATER_OK: PASS
- PUMP OFF with WATER_OK: PASS
- Pump state matches Wokwi simulation: PASS

### Test 3: Manual Grow Light Control
- LIGHT ON: PASS
- LIGHT OFF: PASS
- Light state matches Wokwi simulation: PASS

### Test 4: Pump Water-Level Failsafe
- Pump stops when WATER_LOW is detected: PASS
- PUMP ON is rejected during WATER_LOW: PASS
- Pump remains OFF after water recovery: PASS
- Manual PUMP ON works after WATER_OK: PASS
- Manual PUMP OFF works normally: PASS

### Test 5: AUTO / MANUAL Mode Switching
- Switch from AUTO to MANUAL: PASS
- Switch from MANUAL to AUTO: PASS
- Manual device commands operate in MANUAL mode: PASS

### Result
All listed manual control tests passed in Wokwi simulation.

Note: These results are based on simulation testing,
not physical hardware validation.